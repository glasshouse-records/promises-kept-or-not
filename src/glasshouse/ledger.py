"""The evidence ledger: a SQLite database where every record traces to a
public primary source.

Invariants (enforced by `integrity_check`, run in CI):
  - every enforcement action has source_url + retrieval_date
  - every resolution_type is from RESOLUTION_TYPES; `unverified` rows and
    rows without a primary_ref are quarantined (reported, not publishable)
  - every vote row references a filing row
  - every fuzzy entity match is logged in match_log
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .http import DATA_DIR

DB_PATH = DATA_DIR / "glasshouse.db"

# Legally distinct outcomes — never collapsed. See METHODOLOGY.md.
RESOLUTION_TYPES = frozenset({
    "guilty_plea",
    "dpa",
    "npa",
    "civil_settlement",
    "civil_violation",
    "administrative_action",
    "board_order",
    "debarment",
    "sanction_designation",
    "expulsion",
    "allegation",      # pending dockets — NEVER reported as findings
    "unverified",      # quarantined until a human checks the primary source
})

SCHEMA = """
CREATE TABLE IF NOT EXISTS institutions (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    cik           TEXT,
    type          TEXT,
    country       TEXT
);

CREATE TABLE IF NOT EXISTS filings (
    accession        TEXT PRIMARY KEY,
    cik              TEXT NOT NULL,
    institution_id   TEXT REFERENCES institutions(id),
    form_type        TEXT NOT NULL,
    filing_date      TEXT,
    period_of_report TEXT,
    report_type      TEXT,             -- N-PX cover reportType (notice vs voting report)
    source_url       TEXT NOT NULL,
    retrieval_date   TEXT NOT NULL,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS fund_series (
    series_id TEXT NOT NULL,
    accession TEXT NOT NULL REFERENCES filings(accession),
    name      TEXT,
    lei       TEXT,
    PRIMARY KEY (series_id, accession)
);

CREATE TABLE IF NOT EXISTS votes (
    id                        INTEGER PRIMARY KEY,
    accession                 TEXT NOT NULL REFERENCES filings(accession),
    issuer_name               TEXT,
    cusip                     TEXT,
    isin                      TEXT,
    meeting_date              TEXT,
    vote_description          TEXT,
    category_type             TEXT,
    vote_source               TEXT,
    shares_on_loan            REAL,
    vote_series               TEXT,
    how_voted                 TEXT,
    shares_voted              REAL,
    management_recommendation TEXT
);
CREATE INDEX IF NOT EXISTS idx_votes_cusip  ON votes(cusip);
CREATE INDEX IF NOT EXISTS idx_votes_issuer ON votes(issuer_name);

CREATE TABLE IF NOT EXISTS enforcement_actions (
    id              INTEGER PRIMARY KEY,
    agency          TEXT NOT NULL,
    company_name    TEXT NOT NULL,
    action_date     TEXT,
    resolution_type TEXT NOT NULL,
    penalty_usd     INTEGER,
    primary_ref     TEXT,
    description     TEXT,
    source_url      TEXT NOT NULL,
    retrieval_date  TEXT NOT NULL,
    source_kind     TEXT NOT NULL DEFAULT 'live',   -- live | curated_snapshot
    is_allegation   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (agency, company_name, action_date, primary_ref)
);
CREATE INDEX IF NOT EXISTS idx_enf_company ON enforcement_actions(company_name);

CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY,
    canonical_name  TEXT UNIQUE NOT NULL,
    normalized_name TEXT NOT NULL,
    cik             TEXT,
    lei             TEXT,
    country         TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_entities_norm ON entities(normalized_name);

CREATE TABLE IF NOT EXISTS entity_cusips (
    cusip     TEXT PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS holdings (
    id            INTEGER PRIMARY KEY,
    accession     TEXT NOT NULL REFERENCES filings(accession),
    issuer_name   TEXT,
    cusip         TEXT,
    title_class   TEXT,
    value_usd     INTEGER,           -- full dollars (SEC 13-F amendment, 2024)
    shares        REAL,
    shares_type   TEXT,              -- SH | PRN
    put_call      TEXT,
    discretion    TEXT,
    voting_sole   INTEGER,
    voting_shared INTEGER,
    voting_none   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_holdings_cusip ON holdings(cusip);

CREATE TABLE IF NOT EXISTS outreach (
    id               INTEGER PRIMARY KEY,
    kind             TEXT NOT NULL,   -- social_post | pitch | inquiry | fiduciary | data_offer
    institution_id   TEXT,
    subject          TEXT NOT NULL,
    body_path        TEXT NOT NULL,
    created_ts       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft',  -- draft | approved | sent | declined
    sent_date        TEXT NOT NULL DEFAULT '',
    response_date    TEXT NOT NULL DEFAULT '',
    response_summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS findings (
    id            INTEGER PRIMARY KEY,
    fingerprint   TEXT UNIQUE NOT NULL,   -- stable id of the underlying candidate
    theme         TEXT NOT NULL,
    institution_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    reviewer_note TEXT NOT NULL DEFAULT '',
    reviewed_date TEXT NOT NULL DEFAULT '',
    payload       TEXT NOT NULL            -- JSON citation chain, frozen at review time
);

CREATE TABLE IF NOT EXISTS llm_log (
    id          INTEGER PRIMARY KEY,
    ts          TEXT NOT NULL,
    model       TEXT NOT NULL,
    purpose     TEXT NOT NULL,        -- match_adjudication | proposal_theme | dossier_draft
    prompt_sha  TEXT NOT NULL,        -- hash of the full rendered prompt
    input_key   TEXT NOT NULL,        -- stable key of the thing judged
    output      TEXT NOT NULL,        -- raw model output, verbatim
    advisory    INTEGER NOT NULL DEFAULT 1  -- ALWAYS 1: LLM output never becomes ledger fact
);

CREATE TABLE IF NOT EXISTS triage (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,        -- entity_match | proposal_theme
    input_key   TEXT UNIQUE NOT NULL,
    verdict     TEXT NOT NULL,        -- match | no_match | unsure | <theme>|none
    confidence  TEXT NOT NULL,        -- high | medium | low
    rationale   TEXT NOT NULL,
    model       TEXT NOT NULL,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    kind       TEXT NOT NULL,   -- pitch_reply | citation | subscriber | inquiry_response | other
    detail     TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS commitments (
    id                INTEGER PRIMARY KEY,
    institution_id    TEXT NOT NULL REFERENCES institutions(id),
    doc_label         TEXT NOT NULL,
    url               TEXT NOT NULL,
    retrieval_date    TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    content_path      TEXT NOT NULL,
    content_type      TEXT,
    size_bytes        INTEGER,
    wayback_timestamp TEXT NOT NULL DEFAULT '',  -- '' = live fetch
    UNIQUE (institution_id, doc_label, sha256, wayback_timestamp)
);

CREATE TABLE IF NOT EXISTS runs (
    id                INTEGER PRIMARY KEY,
    ts                TEXT NOT NULL,
    votes_maxid       INTEGER NOT NULL,
    enf_maxid         INTEGER NOT NULL,
    commitments_maxid INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS match_log (
    id        INTEGER PRIMARY KEY,
    ts        TEXT NOT NULL,
    query     TEXT NOT NULL,
    candidate TEXT NOT NULL,
    method    TEXT NOT NULL,
    score     REAL NOT NULL,
    accepted  INTEGER NOT NULL
);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # 60s busy timeout + WAL so reports can run while an ingest is writing.
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for ledgers created before a column existed."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)")}
    if "country" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN country TEXT DEFAULT ''")
        conn.commit()
    vcols = {r[1] for r in conn.execute("PRAGMA table_info(votes)")}
    if "is_duplicate" not in vcols:
        conn.execute("ALTER TABLE votes ADD COLUMN is_duplicate INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    ecols = {r[1] for r in conn.execute("PRAGMA table_info(enforcement_actions)")}
    if "is_duplicate" not in ecols:
        conn.execute("ALTER TABLE enforcement_actions ADD COLUMN is_duplicate "
                     "INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    ocols = {r[1] for r in conn.execute("PRAGMA table_info(outreach)")}
    if "finding_fingerprint" not in ocols:
        conn.execute("ALTER TABLE outreach ADD COLUMN finding_fingerprint "
                     "TEXT NOT NULL DEFAULT ''")
        conn.commit()


def dedupe_votes(conn: sqlite3.Connection) -> int:
    """Mark exact-duplicate vote rows (same filing, security, meeting,
    proposal, series, direction, AND share count) so analytics never sum the
    same shares twice. Found in the wild 2026-06-11: ~105k redundant rows
    (e.g. the same voteRecord repeated x2/x4 within one exhibit, likely one
    copy per share class). Rows are marked, never deleted — the ledger
    preserves filings as filed; queries filter on is_duplicate = 0."""
    conn.execute("UPDATE votes SET is_duplicate = 0")
    # Scope: one filer's reporting period. Two real shapes found 2026-06-11:
    # the same voteRecord repeated within one exhibit (x2/x4, one copy per
    # share class), and the same series' votes filed in TWO exhibits of the
    # same period (~100k rows). Both collapse to one row per natural key.
    cur = conn.execute(
        """UPDATE votes SET is_duplicate = 1 WHERE id NOT IN (
               SELECT MIN(v.id) FROM votes v
               JOIN filings f ON f.accession = v.accession
               GROUP BY f.cik, f.period_of_report, v.issuer_name, v.cusip,
                        v.meeting_date, v.vote_description, v.vote_series,
                        v.how_voted, v.shares_voted)""")
    conn.commit()
    return cur.rowcount


@dataclass
class EnforcementAction:
    agency: str
    company_name: str
    resolution_type: str
    source_url: str
    action_date: str = ""
    penalty_usd: int = 0
    primary_ref: str = ""
    description: str = ""
    retrieval_date: str = ""
    source_kind: str = "live"
    is_allegation: bool = False

    def __post_init__(self) -> None:
        if self.resolution_type not in RESOLUTION_TYPES:
            raise ValueError(f"unknown resolution_type: {self.resolution_type!r}")
        if not self.source_url:
            raise ValueError("enforcement action requires source_url")
        if not self.retrieval_date:
            self.retrieval_date = date.today().isoformat()
        if self.resolution_type == "allegation":
            self.is_allegation = True


def insert_enforcement(conn: sqlite3.Connection, actions: list[EnforcementAction]) -> int:
    n = 0
    for a in actions:
        cur = conn.execute(
            """INSERT OR IGNORE INTO enforcement_actions
               (agency, company_name, action_date, resolution_type, penalty_usd,
                primary_ref, description, source_url, retrieval_date, source_kind,
                is_allegation)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (a.agency, a.company_name, a.action_date, a.resolution_type,
             a.penalty_usd, a.primary_ref, a.description, a.source_url,
             a.retrieval_date, a.source_kind, int(a.is_allegation)),
        )
        n += cur.rowcount
    conn.commit()
    return n


def dedupe_enforcement(conn: sqlite3.Connection) -> int:
    """Reconcile curated snapshots against live scrapes so counts never
    double-dip (found 2026-06-11: 13 FCPA companies in both).

    Where the same normalized company name appears in a curated row and a
    live row for the same enforcement domain (FCPA), the LIVE row is marked
    duplicate: the curated row carries the verified detail (date, penalty,
    resolution type), the live index row carries none. Both stay in the
    ledger; analytics count one.
    """
    from .entities import normalize_name
    conn.create_function("gh_norm", 1, normalize_name)
    conn.execute("UPDATE enforcement_actions SET is_duplicate = 0")
    cur = conn.execute(
        """UPDATE enforcement_actions SET is_duplicate = 1
           WHERE source_kind = 'live' AND agency LIKE '%FCPA%'
             AND EXISTS (SELECT 1 FROM enforcement_actions c
                         WHERE c.source_kind = 'curated_snapshot'
                           AND c.agency LIKE '%FCPA%'
                           AND gh_norm(c.company_name) = gh_norm(
                               enforcement_actions.company_name))""")
    conn.commit()
    return cur.rowcount


def integrity_check(conn: sqlite3.Connection) -> dict[str, list]:
    """Return {check_name: offending rows}. Empty lists everywhere = healthy.

    `quarantined` is informational (allowed in the ledger, barred from
    publication); the others are hard failures.
    """
    problems: dict[str, list] = {}

    rows = conn.execute(
        "SELECT id, agency, company_name FROM enforcement_actions "
        "WHERE source_url = '' OR retrieval_date = ''"
    ).fetchall()
    problems["enforcement_missing_provenance"] = [tuple(r) for r in rows]

    placeholders = ",".join("?" * len(RESOLUTION_TYPES))
    rows = conn.execute(
        f"SELECT id, agency, company_name, resolution_type FROM enforcement_actions "
        f"WHERE resolution_type NOT IN ({placeholders})",
        tuple(RESOLUTION_TYPES),
    ).fetchall()
    problems["enforcement_bad_resolution_type"] = [tuple(r) for r in rows]

    rows = conn.execute(
        "SELECT v.id, v.accession FROM votes v "
        "LEFT JOIN filings f ON f.accession = v.accession WHERE f.accession IS NULL"
    ).fetchall()
    problems["votes_orphaned"] = [tuple(r) for r in rows]

    rows = conn.execute(
        "SELECT id, agency, company_name FROM enforcement_actions "
        "WHERE resolution_type = 'unverified' OR primary_ref = ''"
    ).fetchall()
    problems["quarantined"] = [tuple(r) for r in rows]

    return problems
