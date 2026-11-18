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

# N-PX reports meeting dates as US 'MM/DD/YYYY'. Stored verbatim — that is
# what the source said, and provenance outranks convenience — but NEVER sorted
# or compared as stored: '12/31/2024' > '06/30/2025' lexicographically. On the
# live ledger MAX(meeting_date) returned 12/31/2024 while the latest meeting
# was 2025-06-30, so published coverage bounds were wrong and every
# "most recent evidence" LIMIT picked the wrong rows. Sort on this instead.
# The GLOB guard passes any value already in ISO through untouched.
def iso_meeting_date(col: str = "meeting_date") -> str:
    # Filers write 06/30/2025 or, since 2026, 9/30/2025 — both are M/D/YYYY.
    rest = f"substr({col}, instr({col},'/')+1)"
    return (f"CASE WHEN {col} GLOB '[0-9]*/[0-9]*/[0-9][0-9][0-9][0-9]' "
            f"AND length({col}) <= 10 "
            f"THEN substr({rest}, instr({rest},'/')+1)||'-'||"
            f"printf('%02d', substr({col},1,instr({col},'/')-1))||'-'||"
            f"printf('%02d', substr({rest},1,instr({rest},'/')-1)) "
            f"ELSE {col} END")


ISO_MEETING_DATE = iso_meeting_date()

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
    notes            TEXT,
    partial          INTEGER NOT NULL DEFAULT 0  -- 1: a limited run (--max-tables) stopped
                                                 -- before the last table; ingest redoes it
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
    -- Version identity is the POLICY TEXT, not the bytes: CDN beacons
    -- (Akamai mPulse) carry a per-request token, so raw sha256 changes
    -- on every fetch of an unchanged policy. '' = text unreadable.
    text_sha256       TEXT NOT NULL DEFAULT '',
    -- THE version identity: SHA-256 of the identity text (the label's `body` span
    -- if configured, whitespace-normalised, no whitespace before a trademark
    -- sign). Derived from the stored file at ingest / by backfill; '' = the
    -- text is unreadable. Ships in the release so a restored ledger (no files)
    -- reproduces the same version count.
    identity_sha256   TEXT NOT NULL DEFAULT '',
    -- The identity_text normaliser version identity_sha256 was computed under
    -- (contradictions.IDENTITY_VERSION); a stale row is recomputed from its file.
    identity_version  INTEGER NOT NULL DEFAULT 0,
    -- 0, or the id of the earlier capture this one is a DECLARED REPRINT of (config
    -- `reprints`): its identity_sha256 is that capture's, so it is not a new version.
    reprint_of        INTEGER NOT NULL DEFAULT 0,
    -- What the DOCUMENT says about its own authorship, written by the
    -- manager's own software. Independent of both our hash and the Wayback
    -- timestamp. Corroboration only: a creation date is not a publication
    -- date, and nothing may present it as one.
    doc_created_at    TEXT NOT NULL DEFAULT '',
    doc_modified_at   TEXT NOT NULL DEFAULT '',
    doc_producer      TEXT NOT NULL DEFAULT '',
    -- SAI-printed versions only: the EDGAR filing date of the earliest filing
    -- that carried this text. The text was public by this date; it says nothing
    -- about when the manager first wrote it. '' = dated by wayback/retrieval.
    public_by         TEXT NOT NULL DEFAULT '',
    -- '' = fetched from the manager's own URL; 'edgar-sai' = a section extracted
    -- from a fund SAI on EDGAR (url is then that SAI document).
    via               TEXT NOT NULL DEFAULT '',
    -- 1 = replaced by a rebuild with different extraction settings. Rows are
    -- NEVER deleted (an id, once published, must never point at other text);
    -- readers and the release skip superseded rows.
    superseded        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (institution_id, doc_label, sha256, wayback_timestamp)
);

-- Every live capture ATTEMPT, including the ones that found nothing new and
-- the ones that failed. `commitments` only gains a row when the policy text
-- changes, so on its own it cannot tell "confirmed unchanged this morning"
-- from "not looked at since June". Operator-internal: never published.
CREATE TABLE IF NOT EXISTS capture_attempts (
    id             INTEGER PRIMARY KEY,
    institution_id TEXT NOT NULL,
    doc_label      TEXT NOT NULL,
    url            TEXT NOT NULL,
    attempted_at   TEXT NOT NULL,   -- ISO-8601, local time with offset
    outcome        TEXT NOT NULL CHECK (outcome IN ('new_version','unchanged','failed','needs_review')),
    detail         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_capture_attempts_doc
    ON capture_attempts (institution_id, doc_label, id);

-- Every enforcement-source ingest RUN, including the ones that found nothing
-- new. `enforcement_actions` only gains a row when a record is new, so on its
-- own it cannot tell "checked this morning, nothing new" from "not looked at
-- since June". ok = 1 only when the fetch returned records (a blocked endpoint
-- that returns 0 is not a success). Operator-internal: never published.
CREATE TABLE IF NOT EXISTS ingest_runs (
    id       INTEGER PRIMARY KEY,
    source   TEXT NOT NULL,         -- CLI source name, e.g. doj_fcpa
    run_at   TEXT NOT NULL,         -- ISO-8601, local time with offset
    fetched  INTEGER NOT NULL,
    inserted INTEGER NOT NULL,
    ok       INTEGER NOT NULL CHECK (ok IN (0,1)),
    error    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_source ON ingest_runs (source, ok, id);

-- Coverage watermark of the last vote dedupe: every vote with id <= max_vote_id
-- had its is_duplicate flag computed by that run. Votes above it were ingested
-- since and may be unflagged duplicates. Operator-internal: never published.
CREATE TABLE IF NOT EXISTS dedupe_runs (
    id          INTEGER PRIMARY KEY,
    run_at      TEXT NOT NULL,
    max_vote_id INTEGER NOT NULL,
    marked      INTEGER NOT NULL
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


# The date a commitment version was demonstrably public: the Wayback capture, else
# the EDGAR filing date of an SAI-printed version, else our own retrieval date.
VERSION_DATE_SQL = "COALESCE(NULLIF(wayback_timestamp,''), NULLIF(public_by,''), retrieval_date)"


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
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
    if "partial" not in fcols:
        conn.execute("ALTER TABLE filings ADD COLUMN partial INTEGER NOT NULL DEFAULT 0")
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
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(commitments)")}
    if "text_sha256" not in ccols:
        conn.execute("ALTER TABLE commitments ADD COLUMN text_sha256 "
                     "TEXT NOT NULL DEFAULT ''")
        conn.commit()
    for col in ("doc_created_at", "doc_modified_at", "doc_producer", "public_by", "via",
                "identity_sha256"):
        if col not in ccols:
            conn.execute(f"ALTER TABLE commitments ADD COLUMN {col} "
                         "TEXT NOT NULL DEFAULT ''")
            conn.commit()
    for col in ("identity_version", "reprint_of"):
        if col not in ccols:
            conn.execute(f"ALTER TABLE commitments ADD COLUMN {col} "
                         "INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    sql = (conn.execute("SELECT sql FROM sqlite_master WHERE name='capture_attempts'")
           .fetchone() or [""])[0] or ""
    if sql and "needs_review" not in sql:
        # SQLite cannot alter a CHECK: rebuild this operator-internal log table.
        conn.executescript("""
            ALTER TABLE capture_attempts RENAME TO capture_attempts_old;
            CREATE TABLE capture_attempts (
                id INTEGER PRIMARY KEY, institution_id TEXT NOT NULL, doc_label TEXT NOT NULL,
                url TEXT NOT NULL, attempted_at TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN
                    ('new_version','unchanged','failed','needs_review')),
                detail TEXT NOT NULL DEFAULT '');
            INSERT INTO capture_attempts SELECT id, institution_id, doc_label, url,
                attempted_at, outcome, detail FROM capture_attempts_old;
            DROP TABLE capture_attempts_old;
            DROP INDEX IF EXISTS idx_capture_attempts_doc;
            CREATE INDEX idx_capture_attempts_doc
                ON capture_attempts (institution_id, doc_label, id);""")
    if "superseded" not in {r[1] for r in conn.execute("PRAGMA table_info(commitments)")}:
        conn.execute("ALTER TABLE commitments ADD COLUMN superseded INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    ocols = {r[1] for r in conn.execute("PRAGMA table_info(outreach)")}
    if "finding_fingerprint" not in ocols:
        conn.execute("ALTER TABLE outreach ADD COLUMN finding_fingerprint "
                     "TEXT NOT NULL DEFAULT ''")
        conn.commit()
    # Every analytic join goes votes→filings on accession; 2.8M rows pay for
    # this index many times per site build (found in review).
    conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_accession ON votes(accession)")
    conn.commit()
    # Self-measurement memory: one row per assessment run, so the
    # self-improvement loop can see the dataset's trend, not just its state.
    conn.execute("""CREATE TABLE IF NOT EXISTS metrics (
        id        INTEGER PRIMARY KEY,
        ts        TEXT NOT NULL,
        balanced_index REAL NOT NULL,
        components TEXT NOT NULL,   -- JSON {coverage, completeness, provenance, freshness}
        raw        TEXT NOT NULL    -- JSON of the underlying counts
    )""")
    conn.commit()


def dedupe_votes(conn: sqlite3.Connection, ciks: list[str] | None = None) -> int:
    """Mark exact-duplicate vote rows (same filing, security, meeting,
    proposal, series, direction, AND share count) so analytics never sum the
    same shares twice. Found in the wild 2026-06-11: ~105k redundant rows
    (e.g. the same voteRecord repeated x2/x4 within one exhibit, likely one
    copy per share class). Rows are marked, never deleted — the ledger
    preserves filings as filed; queries filter on is_duplicate = 0.

    `ciks` scopes the run to those filers. That is exact, not approximate: the
    duplicate key includes the filer's CIK, so no group spans two filers. A
    scoped run advances the coverage watermark only when every vote newer than
    the previous watermark belongs to the scoped filers; the full run (about
    3 minutes on the 21.8M-row ledger) always does."""
    scope, args = "", []
    if ciks is not None:
        ciks = sorted({str(c) for c in ciks})
        if not ciks:
            return 0
        scope = f"f.cik IN ({','.join('?' * len(ciks))})"
        args = ciks
    prev = conn.execute("SELECT COALESCE(MAX(max_vote_id), 0) FROM dedupe_runs").fetchone()[0]
    if scope:
        conn.execute(
            f"UPDATE votes SET is_duplicate = 0 WHERE accession IN "
            f"(SELECT accession FROM filings f WHERE {scope})", args)
    else:
        conn.execute("UPDATE votes SET is_duplicate = 0")
    # Scope: one filer's reporting period. Two real shapes found 2026-06-11:
    # the same voteRecord repeated within one exhibit (x2/x4, one copy per
    # share class), and the same series' votes filed in TWO exhibits of the
    # same period (~100k rows). Both collapse to one row per natural key.
    where = f"WHERE {scope}" if scope else ""
    outer = (f"accession IN (SELECT accession FROM filings f WHERE {scope}) AND "
             if scope else "")
    cur = conn.execute(
        f"""UPDATE votes SET is_duplicate = 1 WHERE {outer}id NOT IN (
               SELECT MIN(v.id) FROM votes v
               JOIN filings f ON f.accession = v.accession
               {where}
               GROUP BY f.cik, f.period_of_report, v.issuer_name, v.cusip,
                        v.meeting_date, v.vote_description, v.vote_series,
                        v.how_voted, v.shares_voted)""", args + args)
    marked = cur.rowcount
    from datetime import datetime
    top = conn.execute("SELECT COALESCE(MAX(id), 0) FROM votes").fetchone()[0]
    covers_all = True
    if scope:
        covers_all = conn.execute(
            f"SELECT COUNT(*) FROM votes v JOIN filings f ON f.accession = v.accession "
            f"WHERE v.id > ? AND f.cik NOT IN ({','.join('?' * len(ciks))})",
            [prev, *ciks]).fetchone()[0] == 0
    if covers_all:
        conn.execute("INSERT INTO dedupe_runs (run_at, max_vote_id, marked) VALUES (?,?,?)",
                     (datetime.now().astimezone().isoformat(timespec="seconds"), top, marked))
    conn.commit()
    return marked


def duplicate_flags_stale(conn: sqlite3.Connection) -> str:
    """Empty string when every vote is covered by a dedupe run; otherwise the
    reason the is_duplicate flags may be stale (votes ingested since the last
    `glasshouse dedupe`, which would count duplicate shares twice)."""
    top = conn.execute("SELECT COALESCE(MAX(id), 0) FROM votes").fetchone()[0]
    if top == 0:
        return ""
    row = conn.execute("SELECT MAX(max_vote_id) FROM dedupe_runs").fetchone()
    covered = row[0] if row and row[0] is not None else None
    if covered is None or covered < top:
        return (f"duplicate flags may be stale: the last dedupe covered votes up to id "
                f"{covered}, the ledger's max vote id is {top}. Run `glasshouse dedupe`.")
    return ""


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


def record_ingest_run(conn: sqlite3.Connection, source: str, fetched: int,
                      inserted: int, error: str = "") -> None:
    """Record one ingest run in its own short transaction, after the fetch has
    returned (no write lock is held across a network wait). A run is a success
    only if it fetched at least one record and did not error."""
    from datetime import datetime
    ok = 1 if fetched > 0 and not error else 0
    conn.execute(
        "INSERT INTO ingest_runs (source, run_at, fetched, inserted, ok, error) "
        "VALUES (?,?,?,?,?,?)",
        (source, datetime.now().astimezone().isoformat(timespec="seconds"),
         fetched, inserted, ok, error[:300]))
    conn.commit()


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

    # Custody of the archive. A policy snapshot is the ONE artefact here that
    # cannot be re-fetched once its URL rots — three already have — so a missing
    # or altered file is a hard failure, not a warning. This is also what catches
    # a CI pipeline that captures bytes onto a runner and then discards them.
    import hashlib as _hashlib

    bad_custody = []
    for cid, inst, label, path_s, sha in conn.execute(
            "SELECT id, institution_id, doc_label, content_path, sha256 "
            "FROM commitments").fetchall():
        fp = Path(path_s)
        if not fp.exists():
            bad_custody.append((cid, inst, label, "missing"))
            continue
        try:
            actual = _hashlib.sha256(fp.read_bytes()).hexdigest()
        except OSError as exc:
            bad_custody.append((cid, inst, label, f"unreadable: {exc}"))
            continue
        if actual != sha:
            bad_custody.append((cid, inst, label, "sha256 mismatch"))
    problems["commitments_custody"] = bad_custody

    # Dating inversion: a document cannot have been authored AFTER the capture
    # that contains it. The manager's own software wrote that date, so an
    # inversion means our lineage is wrong — not that the manager is. Currently
    # 0 of 63 datable documents; the value of the check is that it stays 0
    # without anyone remembering to look.
    from .ingest.commitments import dating_is_consistent

    problems["commitments_dating"] = [
        (cid, inst, label, created, wb)
        for cid, inst, label, created, wb in conn.execute(
            "SELECT id, institution_id, doc_label, doc_created_at, "
            "COALESCE(NULLIF(wayback_timestamp,''), replace(retrieval_date,'-','')) "
            "FROM commitments WHERE doc_created_at != ''").fetchall()
        if not dating_is_consistent(created, wb)]

    rows = conn.execute(
        "SELECT id, agency, company_name FROM enforcement_actions "
        "WHERE resolution_type = 'unverified' OR primary_ref = ''"
    ).fetchall()
    problems["quarantined"] = [tuple(r) for r in rows]

    return problems
