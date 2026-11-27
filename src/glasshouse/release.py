"""Versioned, verifiable, open-format release bundle — the product the world uses.

`glasshouse export` historically produced one ~700 MB VACUUM'd SQLite blob:
not versioned, not checksummed, not partially consumable, impossible to diff or
to cite. The mission needs the opposite — an artifact an outside researcher or
journalist can download, **verify without trusting us**, query in standard
tools, and **cite** in a publication. This module builds that bundle from the
live ledger:

    release/v<DATE>/
      facts/<table>.csv[.gz]    open, deduped, PUBLIC tables only (one per table)
      facts/<table>.parquet     researcher-grade columnar (when pyarrow installed)
      datapackage.json          Frictionless descriptor (schema + provenance + hashes)
      DATASHEET.md              human self-description (schema, coverage, limits)
      COVERAGE.json             honest per-institution scope (absence = no data)
      derived/glasshouse.db     SQLite convenience view for Datasette / browsing
      MANIFEST.sha256           checksum of every file → reproducibility + tamper check
      README.md                 how to cite, how to verify, license, what's NOT here

The disclosure boundary is inherited wholesale from `publish.PUBLIC_TABLES`:
operator-internal tables (triage/llm_log/outreach/signals/match_log/runs) and
unapproved findings never enter a release. That invariant is tested
(test_release.py) on this surface, not just the SQLite one.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from . import dataset, ledger, publish, registry
from .contradictions import commitment_identity
from .http import DATA_DIR

RELEASES_DIR = DATA_DIR / "releases"
# Above this row count we gzip the CSV (votes/holdings get huge); below it we
# leave it plain so small tables stay clickable and diffable.
GZIP_THRESHOLD_ROWS = 50_000


def _existing_public_tables(conn: sqlite3.Connection) -> dict[str, str]:
    """publish.PUBLIC_TABLES restricted to tables that actually exist."""
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: w for t, w in publish.PUBLIC_TABLES.items() if t in have}


def _emit_csv(conn: sqlite3.Connection, table: str, where: str, facts: Path) -> tuple[str, int]:
    """Stream one public table to CSV (gzipped past the threshold). Header is
    always written so every table's contract is visible even when empty."""
    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    gz = n > GZIP_THRESHOLD_ROWS
    name = f"{table}.csv.gz" if gz else f"{table}.csv"
    path = facts / name
    cols = publish.public_columns(conn, table)     # drops operator-only cols (e.g. content_path)
    cur = conn.execute(f"SELECT {','.join(cols)} FROM {table} {where}")
    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8")) if gz \
        else (lambda p: open(p, "w", newline="", encoding="utf-8"))
    with opener(path) as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for row in cur:                      # streamed, not fetchall — votes is millions
            w.writerow([row[c] for c in cols])
    return name, n


PARQUET_BATCH_ROWS = 250_000   # bounded memory: votes is ~51M rows on an 8 GB machine
_PARQUET_SCHEMA_PENDING_MAX = 2_000_000   # all-NULL columns past this default to string


def _write_parquet(path: Path, cols: list[str], rows) -> bool:
    """Stream `rows` (tuples in `cols` order) to Parquet in PARQUET_BATCH_ROWS
    row groups. The schema is inferred from the data; a column that is NULL in
    the first batches is held back until a later batch reveals its type (or the
    pending cap is reached, when it is typed string). Returns False if pyarrow
    is not installed."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return False
    writer = None
    schema = None
    pending: list = []
    pending_rows = 0

    def to_batch(chunk):
        return pa.table({c: [r[i] for r in chunk] for i, c in enumerate(cols)})

    def resolve(tables, force):
        fields = []
        for i, c in enumerate(cols):
            types = [t.schema.field(i).type for t in tables]
            real = [ty for ty in types if not pa.types.is_null(ty)]
            if not real:
                if not force:
                    return None
                fields.append(pa.field(c, pa.null() if force == "end" else pa.string()))
            else:
                fields.append(pa.field(c, real[0]))
        return pa.schema(fields)

    def flush(tables):
        nonlocal writer
        for t in tables:
            t = t.cast(schema)
            if writer is None:
                writer = pq.ParquetWriter(path, schema)
            writer.write_table(t)

    chunk: list = []
    try:
        for row in rows:
            chunk.append(tuple(row))
            if len(chunk) < PARQUET_BATCH_ROWS:
                continue
            t, chunk = to_batch(chunk), []
            if schema is None:
                pending.append(t)
                pending_rows += t.num_rows
                schema = resolve(pending, "cap" if pending_rows >= _PARQUET_SCHEMA_PENDING_MAX
                                 else None)
                if schema is not None:
                    flush(pending)
                    pending = []
            else:
                flush([t])
        if chunk:
            pending.append(to_batch(chunk)) if schema is None else flush([to_batch(chunk)])
        if schema is None:
            if not pending:
                pending = [to_batch([])]
            schema = resolve(pending, "end")
        flush(pending)
    finally:
        if writer is not None:
            writer.close()
    return True


def _emit_parquet(conn: sqlite3.Connection, table: str, where: str, facts: Path) -> str | None:
    cols = publish.public_columns(conn, table)
    cur = conn.execute(f"SELECT {','.join(cols)} FROM {table} {where}")
    name = f"{table}.parquet"
    return name if _write_parquet(facts / name, cols, cur) else None


class StaleEngineError(RuntimeError):
    """The engine index does not describe the current ledger (or is missing)."""


class PromotionBlockedError(StaleEngineError):
    """Promoted legacy votes are stale or inconsistent: refuse to release them."""


def _emit_rows(name: str, cols: list[str], rows_fn, n: int, facts: Path,
               with_parquet: bool) -> tuple[str, str | None]:
    """Write a table that is not a plain ledger table (config- or engine-derived).
    `rows_fn()` yields tuples in `cols` order. Same CSV/gzip/Parquet rules as
    the ledger tables."""
    gz = n > GZIP_THRESHOLD_ROWS
    csv_name = f"{name}.csv.gz" if gz else f"{name}.csv"
    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8")) if gz \
        else (lambda p: open(p, "w", newline="", encoding="utf-8"))
    with opener(facts / csv_name) as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for row in rows_fn():
            w.writerow(row)
    pq_name = None
    if with_parquet and _write_parquet(facts / f"{name}.parquet", cols, rows_fn()):
        pq_name = f"{name}.parquet"
    return csv_name, pq_name


def _csv_header(path: Path) -> list[str]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


class UndocumentedColumnError(RuntimeError):
    """A column is about to ship that COLUMN_DICTIONARY does not define."""


def _schema_in_file_order(name: str, header: list[str], fields: list[dict]) -> list[dict]:
    """The descriptor's fields in the order the CSV carries them. A shipped column with no
    definition stops the build: a column cannot ship undocumented."""
    by_name = {f["name"]: f for f in fields}
    missing = [c for c in header if not (by_name.get(c) or {}).get("description", "").strip()]
    if missing:
        raise UndocumentedColumnError(
            f"table {name!r} ships column(s) {missing} with no definition: add them to "
            "dataset.DATA_DICTIONARY (or release.NEW_TABLES / VOTES_ADDED)")
    return [by_name[c] for c in header]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()



VOTING_ADVISERS_COLS = ["institution", "registrant_cik", "registrant_name", "series_id",
                        "adviser_key", "from", "until", "adviser", "adviser_source",
                        "adviser_verified"]
POLICY_VERSIONS_COLS = ["commitment_id", "institution", "doc_label", "adviser_key",
                        "adviser_key_date", "authored", "captured", "wayback_timestamp",
                        "source_url", "text_sha256", "identity_sha256", "file_sha256",
                        "readable"]
PROPOSAL_COLS = ["proposal_id", "institution_id", "issuer_name", "cusip", "meeting_date",
                 "year", "description", "category", "mgmt_rec", "position", "n_lines",
                 "n_for", "n_against", "n_other", "themes", "oppositional", "ballot_key",
                 "adviser_key", "accession", "source_url", "vote_id", "weight_basis"]
DIRECTOR_COLS = ["director_id", "institution_id", "issuer_name", "cusip", "meeting_date",
                 "year", "nominee_item", "position", "n_lines", "n_for", "n_against",
                 "n_other", "meeting_key", "adviser_key", "accession", "source_url",
                 "vote_id", "isin_country", "weight_basis"]
PAY_COLS = ["pay_id", "institution_id", "issuer_name", "cusip", "meeting_date", "year",
            "description", "kind", "position", "n_lines", "n_for", "n_against", "n_other",
            "meeting_key", "adviser_key", "accession", "source_url", "vote_id",
            "isin_country", "weight_basis"]

# Verbatim excerpts of METHODOLOGY.md ("The evidence engine"); tests pin that each
# is still a substring of it (whitespace-collapsed), so this text cannot drift.
METHODOLOGY_PROPOSALS = (
    "N-PX reports one line per fund per ballot item.",
    "Rates over lines weight a proposal by how many of a manager's funds hold the "
    "stock; the engine counts each decision once.",
    "The position is SHARE-weighted: funds routinely file a sliver the other way "
    "(0.2–2.5% of shares at State Street), so the minority side must carry at least "
    "5% of shares voted before the position is `SPLIT`.",
    "the engine never aggregates lines voted by different advisers into one item: "
    "each adviser's decision is its own row",
)
METHODOLOGY_DIRECTORS = (
    "Director items are counted per nominee item as filed and per meeting; `opposed` "
    "is AGAINST or WITHHOLD, share-weighted.",
    "N-PX never records the reason for a vote, so a director-opposition rate cannot "
    "be attributed to any one policy provision (diversity, overboarding, pay).",
    "Each director item carries `isin_country`, the first two letters of the ISIN on "
    "its fund lines. That is the country that *issued the ISIN*, not where the "
    "company is run (a Cayman-registered company is `KY`); it is NULL where no line "
    "has an ISIN, the prefix is malformed, or the lines disagree.",
)
METHODOLOGY_PAY = (
    "say-on-pay *frequency* items (1/2/3 years) are not for/against, so they are "
    "excluded from every count and reported only as `frequency_items`.",
)

NEW_TABLES: dict[str, dict] = {
    "voting_advisers": {"_": "Which adviser votes which registrant's shares, one row per "
        "key rule, from config/institutions.yaml. Resolution order per vote line: series "
        "rule matching the meeting date, then registrant history, then default. Rules "
        "without a source URL are omitted (counted in DATASHEET.md).",
        "institution": "→ institutions.id", "registrant_cik": "N-PX filer CIK, no leading zeros",
        "registrant_name": "registrant as named in the registry",
        "series_id": "fund series the rule applies to; NULL = registrant-wide",
        "adviser_key": "short key of the voting adviser group",
        "from": "first meeting date (inclusive, ISO) the rule covers; NULL = unbounded",
        "until": "last meeting date (inclusive, ISO) the rule covers; NULL = unbounded",
        "adviser": "adviser's full name as recorded in the registry; filled only where "
                   "the rule's key is the registrant's default key",
        "adviser_source": "SEC filing URL that names the adviser",
        "adviser_verified": "date the source was checked"},
    "voting_scope_notes": {"_": "Verbatim caveats the registry records about who votes an "
        "institution's shares. Read them before pooling votes.",
        "institution": "→ institutions.id", "note": "verbatim from config/institutions.yaml"},
    "policy_versions": {"_": "One row per archived version of a policy document, by TEXT "
        "identity. Hashes, dates and URLs only: no policy text and no local paths.",
        "commitment_id": "→ commitments.id of the first capture of this text",
        "institution": "→ institutions.id", "doc_label": "label of the policy document",
        "adviser_key": "whose policy this is, as the engine resolved it on adviser_key_date; "
                       "NULL = not on record",
        "adviser_key_date": "date the key was resolved on (= captured)",
        "authored": "date the manager's own software wrote the file (PDF metadata); '' if none",
        "captured": "ISO date the text was demonstrably public: the Wayback capture, our "
                    "fetch, or, for labels ending '-as-printed-in-sai', the EDGAR filing date "
                    "of the earliest fund SAI printing this text (source_url is that SAI)",
        "wayback_timestamp": "Wayback capture timestamp; '' = live fetch or an SAI on EDGAR",
        "source_url": "the document's URL", "text_sha256": "SHA-256 of the raw extracted text as captured (the ledger's own hash; "
                       "for a label with a `body` span, the whole page). In releases before "
                       "2026-11-18.3 this column held the version identity: use identity_sha256",
        "identity_sha256": "SHA-256 of the text the version identity uses: the extracted text "
                           "(for a label with a `body` span, only that span), whitespace-"
                           "normalised, no whitespace before a trademark sign; '' if unreadable. "
                           "Two rows with the same identity_sha256 are one version",
        "file_sha256": "hash of the file bytes",
        "readable": "1 if text was extracted from the file, else 0"},
    "proposal_decisions": {"_": "DERIVED. One row per (manager, adviser, company, meeting, "
        "proposal) decision on shareholder-sponsored proposals, rebuilt from `votes` by "
        "src/glasshouse/engine.py (`glasshouse engine build`). Not a ledger table.",
        "proposal_id": "engine row id; not stable across rebuilds",
        "institution_id": "→ institutions.id", "issuer_name": "company voted on, as filed",
        "cusip": "security CUSIP, as filed",
        "meeting_date": "meeting date, ISO YYYY-MM-DD", "year": "meeting year",
        "description": "proposal text as filed",
        "category": "N-PX category_type of the item, as filed", "mgmt_rec": "vote vs management: WITH | AGAINST | MIXED | ''",
        "position": "FOR | AGAINST | ABSTAIN | SPLIT | NONE (share-weighted)",
        "n_lines": "ballot lines folded into the decision", "n_for": "lines FOR",
        "n_against": "lines AGAINST or WITHHOLD", "n_other": "lines ABSTAIN or with another code",
        "themes": "lexical theme tags ',climate,' — a lead, not a classification",
        "oppositional": "1 if the proposal asks to roll back the theme",
        "ballot_key": "same proposal across managers (strict match)",
        "adviser_key": "voting adviser group. NULL = institution has fewer than two known "
                       "advisers; 'unlabelled' = no adviser on record; UNRESOLVED / EXTERNAL / "
                       "UNDATED are never comparable with any policy",
        "accession": "→ filings.accession", "source_url": "EDGAR source",
        "weight_basis": "how `position` was weighted: 'shares' = by shares_voted; 'lines' = by "
                        "line count, the 2022-23 legacy era (those filings print no share counts); "
                        "'xml-no-shares' = XML lines that filed no share counts, also by line count. Line-weighted and share-weighted positions are not comparable "
                        "in rates across periods; legacy and XML lines are never pooled into "
                        "one decision",
        "vote_id": "→ votes.id of a representative line"},
    "director_decisions": {"_": "DERIVED. One row per management director-nominee item "
        "(`vote_source = ISSUER`, category DIRECTOR ELECTIONS) per manager and adviser, "
        "rebuilt from `votes` by src/glasshouse/engine.py. Not a ledger table.",
        "director_id": "engine row id; not stable across rebuilds",
        "institution_id": "→ institutions.id", "issuer_name": "company voted on, as filed",
        "cusip": "security CUSIP, as filed",
        "meeting_date": "meeting date, ISO YYYY-MM-DD", "year": "meeting year",
        "nominee_item": "the ballot line as filed (names the nominee)",
        "position": "FOR | AGAINST (incl. WITHHOLD) | ABSTAIN | SPLIT | NONE",
        "n_lines": "ballot lines folded in", "n_for": "lines FOR", "n_against": "lines AGAINST or WITHHOLD",
        "n_other": "lines ABSTAIN or with another code", "meeting_key": "same meeting across managers (CUSIP|date)",
        "adviser_key": "voting adviser group; same semantics as proposal_decisions",
        "accession": "→ filings.accession", "source_url": "EDGAR source",
        "weight_basis": "how `position` was weighted: 'shares' = by shares_voted; 'lines' = by "
                        "line count, the 2022-23 legacy era (those filings print no share counts); "
                        "'xml-no-shares' = XML lines that filed no share counts, also by line count. Line-weighted and share-weighted positions are not comparable "
                        "in rates across periods; legacy and XML lines are never pooled into "
                        "one decision",
        "vote_id": "→ votes.id of a representative line",
        "isin_country": "country that ISSUED the ISIN (not where the company is run); "
                        "NULL if none, malformed or lines disagree"},
    "pay_decisions": {"_": "DERIVED. One row per management say-on-pay item (N-PX category "
        "SECTION 14A SAY-ON-PAY VOTES) per manager and adviser, rebuilt from `votes` by "
        "src/glasshouse/engine.py. Not a ledger table. Both kinds are shipped: `approval` "
        "items are FOR/AGAINST; `frequency` items (1, 2 or 3 years) are NOT for/against, so "
        "exclude kind = 'frequency' from any opposition count or rate.",
        "pay_id": "engine row id; not stable across rebuilds",
        "institution_id": "→ institutions.id", "issuer_name": "company voted on, as filed",
        "cusip": "security CUSIP, as filed",
        "meeting_date": "meeting date, ISO YYYY-MM-DD", "year": "meeting year",
        "description": "the ballot line as filed",
        "kind": "approval = a FOR/AGAINST vote on pay; frequency = a say-on-pay frequency "
                "item (1/2/3 years), where `position` and n_for/n_against do not mean "
                "support or opposition: exclude it from opposition counts",
        "position": "FOR | AGAINST (incl. WITHHOLD) | ABSTAIN | SPLIT | NONE (share-weighted); "
                    "not a for/against when kind = frequency",
        "n_lines": "ballot lines folded in", "n_for": "lines FOR", "n_against": "lines AGAINST or WITHHOLD",
        "n_other": "lines ABSTAIN or with another code (frequency choices land here)",
        "meeting_key": "same meeting across managers (CUSIP|date)",
        "adviser_key": "voting adviser group; same semantics as proposal_decisions",
        "accession": "→ filings.accession", "source_url": "EDGAR source",
        "weight_basis": "how `position` was weighted: 'shares' = by shares_voted; 'lines' = by "
                        "line count, the 2022-23 legacy era (those filings print no share counts); "
                        "'xml-no-shares' = XML lines that filed no share counts, also by line count. Line-weighted and share-weighted positions are not comparable "
                        "in rates across periods; legacy and XML lines are never pooled into "
                        "one decision",
        "vote_id": "→ votes.id of a representative line",
        "isin_country": "country that ISSUED the ISIN (not where the company is run); "
                        "NULL if none, malformed or lines disagree"},
}


# The two columns appended to the shipped `votes` table at release time.
VOTES_ADDED_COLS = ["institution_id", "adviser_key"]
VOTES_ADDED: dict[str, str] = {
    "institution_id": "→ institutions.id: the institution of the filing (copied from "
                      "filings.institution_id so a vote needs no join to name it)",
    "adviser_key": "voting adviser group of this line: engine.resolve_key over the registrant "
                   "CIK (filings.cik), vote_series and meeting date, so it equals the "
                   "adviser_key of proposal_decisions / director_decisions. Set only for "
                   "institutions with two or more adviser groups; 'unlabelled' = the line "
                   "resolves to no key; UNRESOLVED, EXTERNAL, UNDATED, unlabelled are never "
                   "comparable with a policy; NULL = no adviser key recorded for the institution",
}

# THE column dictionary: every column of every shipped table, one line each. The
# datapackage, the datasheet and the test that fails on an undocumented column all
# read this; dataset.DATA_DICTIONARY (ledger tables) and NEW_TABLES (config- and
# engine-derived tables) are its two sources.
COLUMN_DICTIONARY: dict[str, dict] = {
    **{t: dict(d) for t, d in dataset.DATA_DICTIONARY.items()}, **NEW_TABLES}
COLUMN_DICTIONARY["votes"].update(VOTES_ADDED)


def _http(u) -> bool:
    return isinstance(u, str) and u.strip().lower().startswith(("http://", "https://"))


def adviser_context(conn: sqlite3.Connection, institutions: dict) -> tuple[dict, set]:
    """(rules, split): the registry's key rules per institution and CIK, and the
    institutions the engine splits by adviser. Built exactly as engine.build does, with
    the engine's own functions, so a shipped vote line resolves as the engine would."""
    from . import engine
    rules = {iid: {engine._norm_cik(e["cik"]): engine.normalize_rules(e)
                   for e in (inst.get("npx_ciks") or []) if e.get("cik")}
             for iid, inst in institutions.items()}
    doc_rules = {(iid, c["label"]): engine.normalize_rules(c) for iid, inst in institutions.items()
                 for c in (inst.get("commitments") or []) if c.get("label")}
    return rules, set(engine._multi_group(conn, rules, doc_rules))


def votes_rows(conn: sqlite3.Connection, cols: list[str], where: str, rules: dict, split: set):
    """A function yielding the shipped votes (`cols`) plus institution_id and adviser_key.
    adviser_key is engine.resolve_key per line for institutions the engine splits by
    adviser ('unlabelled' where a line resolves to none), NULL for all others."""
    from . import engine
    iso = ledger.iso_meeting_date("v.meeting_date")
    sel = ",".join(f"v.{c} AS {c}" for c in cols)

    def fn():
        cache: dict[tuple, str | None] = {}
        for r in conn.execute(
                f"SELECT {sel}, f.institution_id AS _iid, f.cik AS _cik, {iso} AS _md "
                f"FROM votes v LEFT JOIN filings f ON f.accession = v.accession {where}"):
            iid = r["_iid"]
            adv = None
            if iid in split:
                k = (iid, r["_cik"], r["vote_series"], r["_md"])
                if k not in cache:
                    cache[k] = engine.resolve_key(
                        rules.get(iid, {}).get(engine._norm_cik(r["_cik"])),
                        r["vote_series"], r["_md"]) or engine.UNLABELLED
                adv = cache[k]
            yield tuple(r[c] for c in cols) + (iid, adv)
    return fn


def voting_advisers_rows(institutions: dict) -> tuple[list[tuple], int]:
    """([row], n_omitted): one row per key rule of every registrant in the registry.
    A rule whose registrant has no source URL is omitted and counted."""
    from . import engine
    out: list[tuple] = []
    omitted = 0
    for iid in sorted(institutions):
        for e in institutions[iid].get("npx_ciks") or []:
            if not e.get("cik"):
                continue
            r = engine.normalize_rules(e)
            rules = ([(None, r["default"], None, None)] if r["default"] else [])
            rules += [(None, k, lo, hi) for k, lo, hi in r["history"]]
            rules += [(sid, k, lo, hi) for sid, lst in sorted(r["series"].items())
                      for k, lo, hi in lst]
            src = e.get("adviser_source")
            for sid, k, lo, hi in rules:
                if not _http(src):
                    omitted += 1
                    continue
                out.append((iid, engine._norm_cik(e["cik"]), e.get("name"), sid, k, lo, hi,
                            (e.get("adviser") or None) if k == r["default"] else None,
                            str(src).strip(),
                            str(e["adviser_verified"]) if e.get("adviser_verified") else None))
    return out, omitted


def scope_notes_rows(institutions: dict) -> list[tuple]:
    return [(iid, str(n)) for iid in sorted(institutions)
            for n in institutions[iid].get("voting_scope_notes") or []]


def _engine_ro(engine_path: Path) -> sqlite3.Connection:
    if not Path(engine_path).exists():
        raise StaleEngineError(f"engine index {engine_path} not found: run "
                               "`glasshouse engine build` (or pass --no-derived)")
    e = sqlite3.connect(f"file:{engine_path}?mode=ro", uri=True)
    e.row_factory = sqlite3.Row
    return e


def check_engine_current(conn: sqlite3.Connection, eng: sqlite3.Connection) -> int:
    """The engine's ledger_max_vote_id, refusing (StaleEngineError) if it is not the
    ledger's current max vote id."""
    row = eng.execute("SELECT value FROM meta WHERE key='ledger_max_vote_id'").fetchone()
    cur = conn.execute("SELECT MAX(id) FROM votes").fetchone()[0]
    if row is None or str(row[0]) != str(cur):
        raise StaleEngineError(
            f"engine index is stale: it covers votes up to id {row[0] if row else None}, the "
            f"ledger's max vote id is {cur}. Run `glasshouse engine build`, or pass "
            "--no-derived to ship without the derived tables.")
    return int(cur) if cur is not None else 0


def policy_versions_rows(conn: sqlite3.Connection, eng: sqlite3.Connection) -> list[tuple]:
    out = []
    for p in eng.execute("SELECT * FROM policy_versions ORDER BY institution_id, doc_label, "
                         "captured, commitment_id"):
        c = conn.execute("SELECT institution_id, doc_label, content_path, text_sha256, "
                         "identity_sha256, "
                         "wayback_timestamp, sha256 FROM commitments "
                         "WHERE id=?", (p["commitment_id"],)).fetchone()
        ident = (commitment_identity(c["institution_id"], c["doc_label"], c["content_path"],
                                     c["identity_sha256"], c["sha256"]) if c else "")
        # The identity hash the version is grouped by; '' when unreadable.
        ident_hash = ident[len("text:"):] if ident.startswith("text:") else ""
        out.append((p["commitment_id"], p["institution_id"], p["doc_label"], p["adviser"],
                    p["adviser_key_date"], p["authored"] or "", p["captured"],
                    (c["wayback_timestamp"] if c else "") or "", p["url"],
                    (c["text_sha256"] if c else "") or "", ident_hash, p["sha256"],
                    int((p["n_sentences"] or 0) > 0)))
    return out


def _engine_rows(eng, table: str, src_cols: list[str], names: list[str], order: str):
    sel = ",".join(f"{s} AS {n}" if s != n else s for s, n in zip(src_cols, names, strict=True))

    def fn():
        for r in eng.execute(f"SELECT {sel} FROM {table} ORDER BY {order}"):
            yield tuple(r[n] for n in names)
    return fn



CODE_LISTS_MD = """\
## Code lists

### `votes.how_voted` and the position codes

`votes.how_voted` is N-PX field howVoted, kept as filed; spelling and case vary
(`Take No Action`, `TAKE NO ACTION`, `Takenoaction`). Lines with an empty value are not shipped.

- `FOR`: voted for the item.
- `AGAINST`: voted against. `WITHHOLD` (a withheld director vote) is counted as AGAINST by the engine.
- `ABSTAIN`: abstained. Whether a withheld director vote is filed as WITHHOLD or ABSTAIN is the filer's coding choice.
- Anything else, as filed (frequency votes `ONE YEAR`, `1 YEAR`, `TWO YEARS`, `THREE YEARS`; `TAKE NO ACTION`; `DO NOT VOTE`; `NONE`; `Not Applicable`): the engine counts these lines as "other": in no FOR, AGAINST or ABSTAIN tally. A filed `NONE` is a `how_voted` value; the position `NONE` below is something else.

`position` (`proposal_decisions`, `director_decisions`, `pay_decisions`) is one decision per manager and adviser
for one item, folded from its fund lines and weighted by `shares_voted` (by line count where no
shares were filed):

- `FOR`: FOR carries at least 95% of the FOR plus AGAINST shares.
- `AGAINST` (includes WITHHOLD): FOR carries 5% or less of the FOR plus AGAINST shares.
- `SPLIT`: in between: the minority side carries at least 5% of the shares voted, so the manager's own funds voted both ways. The 5% floor exists because funds routinely file a sliver the other way (0.2 to 2.5% of shares at State Street).
- `ABSTAIN`: no FOR or AGAINST line, at least one ABSTAIN line. ABSTAIN lines do not count toward the 5% floor.
- `NONE`: no FOR, AGAINST, WITHHOLD or ABSTAIN line (only "other" codes, e.g. a frequency vote).

**How SPLIT and NONE are treated in every rate shown in this documentation and the README
quickstart:** SPLIT and NONE items are in neither numerator nor denominator, and they are
reported beside the rate, never inside it. Support is FOR / (FOR + AGAINST). Non-support
(`not_supported`) is (AGAINST + ABSTAIN) / (FOR + AGAINST + ABSTAIN). Why: a SPLIT item means the
manager's own funds voted both ways, so counting it as support or as opposition would state a
position the manager did not take; a NONE item has no for, against or abstain vote to count.
The README quickstart ratio therefore filters to FOR, AGAINST and ABSTAIN items in its
denominator and counts SPLIT and NONE only in its `items` column.

### `votes.vote_source`

N-PX field voteSource: `ISSUER` (item put on the ballot by the issuer) or `SECURITY HOLDER`
(shareholder-sponsored proposal). Empty where the filer left it blank. `legacy_html` is a
Glasshouse tag for pre-2024 votes parsed by a single HTML parser; those votes are not
validated and are NOT in this release. Votes with `votes.legacy_format` set (`proxyedge`,
`iss_text`, `iss_html`, `issueno`, `issueno_html`, `regvoted`, `regvoted_html`, `fedflat`) are 2022-23 text filings read by two agreeing parsers and ARE in this
release (see `votes.legacy_format`).

### Kinds of vote (`COVERAGE.json` `vote_kinds`, `votes_by_kind`)

Assigned per shipped line from the filed fields, in this order: `shareholder_proposals`
(`vote_source` = SECURITY HOLDER); else `director_elections` (`category_type` = DIRECTOR
ELECTIONS); else `say_on_pay` (`category_type` = SECTION 14A SAY-ON-PAY VOTES); else
`management_other` (every other management item: auditors, capital structure, and so on). An
institution whose shipped votes are one kind only (for example `say_on_pay`) has no other kind of
vote in this release.

### `adviser_key` values

An adviser key is a short label for WHO votes a registrant's shares (and, in `policy_versions`,
whose policy a document is). Real keys (BIS, BAIS, VPM, TRPA, ...) are defined by rows of
`voting_advisers`. Special values:

- `UNRESOLVED`: the registry could not establish which adviser votes this series for these dates (BlackRock series with 2025 votes that appear in no 2025-26 policy table). Never comparable with any policy.
- `EXTERNAL`: a series advised by an outside manager, so no archived policy of the institution governs it.
- `UNDATED`: the meeting date does not parse, on a series or registrant that has a dated rule, so the adviser in force cannot be told.
- `unlabelled`: used by `votes`, `proposal_decisions` and `director_decisions` for an institution that has adviser groups, where this line resolves to no key.
- `NULL` = no adviser key recorded for that institution (empty in CSV), so nothing is split (for example UBS: in `votes`, `proposal_decisions` and `director_decisions` for its lines, and in `policy_versions` for its documents). In `votes` and the derived tables a NULL also covers an institution with only one adviser group, since there is nothing to separate.

## Joins and provenance

- `votes.accession = filings.accession` gives the N-PX filing of a vote line. `votes` rows carry no
  `source_url` or `retrieval_date`; they live on the `filings` row (`filings.source_url` is the EDGAR
  directory of the filing, `filings.retrieval_date` the day it was fetched). `holdings` and
  `fund_series` link to `filings` the same way.
- `votes.vote_series = fund_series.series_id AND votes.accession = fund_series.accession` names the
  fund series that cast the vote (series name and LEI). The pair is the key because
  `fund_series` has one row per series per filing. A line with an empty `vote_series` has no series.
- `votes.institution_id` is `filings.institution_id`, copied onto the vote at release time.
- `votes.adviser_key` is computed at release time with the same function the engine uses for a
  line (`engine.resolve_key`): the registrant CIK (`filings.cik`, matched to
  `voting_advisers.registrant_cik` without leading zeros), `vote_series` and the meeting date;
  a series rule that covers the meeting date wins, then the registrant's dated history, then
  its default key. It is set only for the institutions the engine splits by adviser (two or
  more adviser groups); for the others it is NULL. Per (institution, adviser_key) the
  director-election lines of `votes` (`vote_source` = ISSUER, `category_type` = DIRECTOR
  ELECTIONS) are the lines `director_decisions` folds into its `n_lines`, except that
  `director_decisions` also counts lines filed with an empty `how_voted` (administrative
  records that `votes` does not ship), so its `n_lines` can exceed the count in `votes`.

## Integrity of this bundle

MANIFEST.sha256 covers every file in the bundle except itself (`shasum -a 256 -c MANIFEST.sha256`
reports damage or change to any other file). To be plain: nothing signs it; there is no signature, and the
manifest's own hash is not published anywhere else, so it proves the files match the manifest,
not who made either. Anyone able to alter the files could alter the manifest too.
"""


def _derived_extra(pkg: dict, datasheet: str, notes: dict) -> str:
    """Insert the comparison warning near the top of the datasheet and document the
    new tables before the reading guide."""
    warn = [
        "## Before you compare a policy with votes", "",
        "**Read this first. Pooling votes cast by different advisers, or comparing them "
        "with another adviser's policy, produces false results.**", "",
        "- One institution's registrants can be voted by different advisers under "
        "different policies. Group votes by `adviser_key` "
        "(`proposal_decisions`, `director_decisions`, `pay_decisions` and the shipped `votes`, which carries "
        "the key resolved from `voting_advisers` by registrant CIK, `vote_series` and meeting "
        "date).",
        "- A policy version (`policy_versions`) applies only to votes with the SAME "
        "`adviser_key`, and only when the version was captured on or before the meeting date.",
        "- Keys `UNRESOLVED`, `EXTERNAL` and `UNDATED` (and `unlabelled`, no adviser on "
        "record) are never comparable with any policy. `EXTERNAL` = a series advised by "
        "an outside manager; `UNDATED` = the meeting date cannot place the vote in a "
        "dated rule.",
        "- `isin_country` is the country that ISSUED the ISIN, not where the company is run.",
        "- Read `voting_scope_notes` for each institution before pooling anything.",
        "- Never sum `shares_voted` without `is_duplicate = 0` (the shipped `votes` table "
        "already applies it).", ""]
    if notes["omitted"]:
        warn += [f"- {notes['omitted']} voting rule(s) have no source URL in the registry and "
                 "are **unverified**: they are omitted from `voting_advisers`, so a key may "
                 "appear in the derived tables without a matching rule row.", ""]
    else:
        warn += ["- Unverified voting rules (no source URL): 0 (none omitted).", ""]
    if notes["derived"]:
        warn += [f"Derived tables were built from an engine index covering ledger votes up to "
                 f"id {notes['ledger_max_vote_id']} (equal to the ledger's maximum at build).", ""]
    else:
        warn += ["**This bundle was built with `--no-derived`: `proposal_decisions`, "
                 "`director_decisions` and `pay_decisions` are NOT included.**", ""]
    # `votes` ships two columns the ledger table does not have: document them in its section.
    i = datasheet.index("### `votes`")
    j = datasheet.index("\n\n", i)
    added = "".join(f"\n- **{k}** — {VOTES_ADDED[k]}" for k in VOTES_ADDED_COLS)
    datasheet = datasheet[:j] + added + datasheet[j:]
    marker = "## Provenance guarantees"
    datasheet = datasheet.replace(marker, "\n".join(warn) + "\n" + marker, 1)

    doc = ["## Voting-adviser tables, policy versions and DERIVED tables", ""]
    for res in pkg["resources"]:
        if res["name"] not in NEW_TABLES:
            continue
        tag = " — DERIVED" if res.get("derived") else ""
        doc.append(f"### `{res['name']}`{tag} ({res['rowCount']:,} rows)")
        doc.append(res["description"])
        if res.get("derived"):
            doc += ["", "**DERIVED, not a ledger table.** It is rebuilt from `votes` by code in "
                    "this repository (`src/glasshouse/engine.py`, run as `glasshouse engine "
                    "build`) and can be regenerated at any time. "
                    + " ".join(res["methodology"])]
        for f in res["schema"]["fields"]:
            doc.append(f"- **{f['name']}** — {f['description']}")
        doc.append("")
    marker2 = "## How to read this dataset"
    return datasheet.replace(marker2, "\n".join(doc) + "\n" + CODE_LISTS_MD + "\n" + marker2, 1)


def build_release(*args, **kwargs) -> dict:
    """`_build_release` with the git state read once, when the build starts (a commit
    made during a long build must not be stamped on it)."""
    with dataset.pinned_git_state():
        return _build_release(*args, **kwargs)


def _build_release(conn: sqlite3.Connection, root: Path | str | None = None,
                   version: str | None = None, with_parquet: bool = True,
                   with_sqlite: bool = False, no_derived: bool = False,
                   engine_path: Path | str | None = None,
                   institutions: dict | None = None) -> dict:
    """Build a complete, verifiable, self-describing release bundle. Returns a
    summary dict; the bundle on disk is the deliverable.

    CSV + Parquet are the canonical consumable formats. The SQLite browse view
    (`with_sqlite`) is opt-in: it roughly doubles bundle size and duplicates the
    facts, so it ships only when a Datasette-style local browse is wanted."""
    from . import engine as engine_mod
    version = version or date.today().isoformat()
    # The version becomes a directory name we later rmtree — never let it escape
    # the releases root (no separators / traversal).
    if version in (".", "..") or any(c in version for c in "/\\"):
        raise ValueError(f"invalid release version: {version!r}")
    root = Path(root) if root else RELEASES_DIR
    # Everything that can refuse does so BEFORE the old bundle dir is removed.
    # Duplicate flags first: they concern the facts themselves, need no engine.
    blockers = ledger.promotion_blockers(conn)
    if blockers:
        raise PromotionBlockedError("legacy promotion refused: " + "; ".join(blockers))
    stale_dupes = ledger.duplicate_flags_stale(conn)
    if stale_dupes:
        raise StaleEngineError(stale_dupes)
    eng = _engine_ro(Path(engine_path) if engine_path else engine_mod.ENGINE_PATH)
    try:
        max_vote_id = None
        if not no_derived:
            max_vote_id = check_engine_current(conn, eng)
        institutions = registry.load() if institutions is None else institutions
        pv_rows = policy_versions_rows(conn, eng)
        va_rows, omitted = voting_advisers_rows(institutions)
        sn_rows = scope_notes_rows(institutions)
        eng_meta = {r[0]: r[1] for r in eng.execute("SELECT key, value FROM meta")}
        adv_ctx = adviser_context(conn, institutions)
        return _build(conn, eng, root, version, with_parquet, with_sqlite, no_derived,
                      max_vote_id, eng_meta, pv_rows, va_rows, omitted, sn_rows, adv_ctx)
    finally:
        eng.close()


def _build(conn, eng, root, version, with_parquet, with_sqlite, no_derived, max_vote_id,
           eng_meta, pv_rows, va_rows, omitted, sn_rows, adv_ctx) -> dict:
    d = root / f"v{version}"
    if d.exists():            # reproducible: the dir reflects exactly this build
        shutil.rmtree(d)
    facts = d / "facts"
    facts.mkdir(parents=True, exist_ok=True)

    public = _existing_public_tables(conn)
    tables: dict[str, dict] = {}
    formats = {"csv"}
    for table, where in public.items():
        if table == "votes":     # shipped with institution_id + adviser_key (see votes_rows)
            cols = publish.public_columns(conn, "votes")
            rows = conn.execute(f"SELECT COUNT(*) FROM votes {where}").fetchone()[0]
            csv_name, pq_name = _emit_rows(
                "votes", cols + VOTES_ADDED_COLS, votes_rows(conn, cols, where, *adv_ctx),
                rows, facts, with_parquet)
        else:
            csv_name, rows = _emit_csv(conn, table, where, facts)
            pq_name = _emit_parquet(conn, table, where, facts) if with_parquet else None
        if pq_name:
            formats.add("parquet")
        tables[table] = {"csv": f"facts/{csv_name}", "rows": rows,
                         "parquet": f"facts/{pq_name}" if pq_name else None}

    extra: list[tuple] = [
        ("voting_advisers", VOTING_ADVISERS_COLS, va_rows, None),
        ("voting_scope_notes", ["institution", "note"], sn_rows, None),
        ("policy_versions", POLICY_VERSIONS_COLS, pv_rows, None),
    ]
    if not no_derived:
        p_fn = _engine_rows(eng, "proposals", [c if c != "adviser_key" else "adviser"
                            for c in PROPOSAL_COLS], PROPOSAL_COLS, "proposal_id")
        d_fn = _engine_rows(eng, "director_votes", [c if c != "adviser_key" else "adviser"
                            for c in DIRECTOR_COLS], DIRECTOR_COLS, "director_id")
        y_fn = _engine_rows(eng, "pay_votes", [c if c != "adviser_key" else "adviser"
                            for c in PAY_COLS], PAY_COLS, "pay_id")
        extra += [
            ("proposal_decisions", PROPOSAL_COLS, p_fn,
             eng.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]),
            ("director_decisions", DIRECTOR_COLS, d_fn,
             eng.execute("SELECT COUNT(*) FROM director_votes").fetchone()[0]),
            ("pay_decisions", PAY_COLS, y_fn,
             eng.execute("SELECT COUNT(*) FROM pay_votes").fetchone()[0])]
    for name, cols, rows, n in extra:
        fn = rows if callable(rows) else (lambda r=rows: iter(r))
        n = len(rows) if n is None else n
        csv_name, pq_name = _emit_rows(name, cols, fn, n, facts, with_parquet)
        if pq_name:
            formats.add("parquet")
        tables[name] = {"csv": f"facts/{csv_name}", "rows": n,
                        "parquet": f"facts/{pq_name}" if pq_name else None}

    # Self-description, generated from the data so it cannot drift.
    pkg = dataset.build_datapackage(conn)
    pkg["derived_tables_included"] = not no_derived
    pkg["engine"] = {"ledger_max_vote_id": max_vote_id if not no_derived else
                     eng_meta.get("ledger_max_vote_id"),
                     "built_at": eng_meta.get("built_at"),
                     "current_at_release": not no_derived}
    votes_res = next(r for r in pkg["resources"] if r["name"] == "votes")
    votes_res["schema"]["fields"] += [{"name": k, "description": VOTES_ADDED[k]}
                                      for k in VOTES_ADDED_COLS]
    votes_res["description"] += (" Shipped with two columns added at release time, "
                                 "institution_id and adviser_key (see Joins).")
    for name, spec in NEW_TABLES.items():
        if name not in tables:
            continue
        res = {"name": name, "rowCount": tables[name]["rows"],
               "description": spec["_"],
               "schema": {"fields": [{"name": k, "description": v}
                                     for k, v in spec.items() if k != "_"]}}
        if name in ("proposal_decisions", "director_decisions", "pay_decisions"):
            res["derived"] = True
            res["derivation"] = ("Rebuilt from `votes` by src/glasshouse/engine.py "
                                 "(`glasshouse engine build`); not a ledger table.")
            res["methodology"] = list(METHODOLOGY_PROPOSALS if name == "proposal_decisions"
                                      else METHODOLOGY_PAY if name == "pay_decisions"
                                      else METHODOLOGY_DIRECTORS)
        pkg["resources"].append(res)
    for res in pkg["resources"]:                      # attach real paths + hashes
        t = tables.get(res["name"])
        if not t:
            continue
        res["schema"]["fields"] = _schema_in_file_order(
            res["name"], _csv_header(d / t["csv"]), res["schema"]["fields"])
        paths = [t["csv"]] + ([t["parquet"]] if t["parquet"] else [])
        res["path"] = paths
        res["format"] = "csv"
        res["sha256"] = _sha256(d / t["csv"])
        res["bytes"] = (d / t["csv"]).stat().st_size
    (d / "datapackage.json").write_text(json.dumps(pkg, indent=2))
    (d / "DATASHEET.md").write_text(_derived_extra(
        pkg, dataset.build_datasheet(conn),
        {"omitted": omitted, "derived": not no_derived, "ledger_max_vote_id": max_vote_id}))
    (d / "COVERAGE.json").write_text(json.dumps(dataset.coverage(conn), indent=2))

    # SQLite convenience view (same disclosure boundary) for Datasette/browsing —
    # opt-in, because it duplicates the facts and ~doubles the bundle.
    if with_sqlite:
        (d / "derived").mkdir(parents=True, exist_ok=True)
        publish.build_public_snapshot(conn, d / "derived" / "glasshouse.db")

    (d / "README.md").write_text(_readme(pkg, tables, version, with_sqlite))

    # Manifest LAST, over everything else — checksums make the bundle verifiable
    # without trusting us (`sha256sum -c MANIFEST.sha256`).
    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [f"{_sha256(p)}  {p.relative_to(d)}" for p in files]
    (d / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")

    total = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
    return {"version": version, "dir": str(d), "tables": tables,
            "formats": sorted(formats), "file_count": len(files) + 1,
            "bytes": total, "with_sqlite": with_sqlite}


def _readme(pkg: dict, tables: dict, version: str, with_sqlite: bool = False) -> str:
    rows = sum(t["rows"] for t in tables.values())
    has_pq = any(t["parquet"] for t in tables.values())
    dirty = pkg["git"]["dirty"]
    state = (" (the working tree was dirty at build: the bundle is not reproducible from that "
             "commit alone)" if dirty else "")
    cite = (f"Glasshouse evidence dataset, v{version} (commit {pkg['git_commit']}). "
            "CC-BY-4.0. Not yet published; no DOI, no public URL.")
    lines = [
        f"# Glasshouse evidence dataset — v{version}", "",
        pkg["description"], "",
        f"**{rows:,} public rows** across {len(tables)} tables · "
        f"formats: CSV{' + Parquet' if has_pq else ''} · license CC-BY-4.0 · "
        f"commit `{pkg['git_commit']}`", "",
        f"Built from git commit `{pkg['git']['commit']}`" + state + "; "
        "`datapackage.json` records it under `git`.", "",
        "## What this is",
        "A primary-source-cited, deduplicated, **versioned** snapshot of what major "
        "financial institutions say (archived policy documents) versus what they do "
        "(SEC N-PX proxy votes and 13-F / N-PORT holdings), plus the enforcement "
        "record. Built for researchers and journalists to find and cite insights.", "",
        "## Verify it (don't trust us)",
        "```sh",
        "sha256sum -c MANIFEST.sha256   # every file's checksum (macOS: shasum -a 256 -c)",
        "```",
        "The manifest covers every file except itself and nothing signs it (see "
        "`DATASHEET.md`, Integrity). Every row traces to its source: `filings`, "
        "`enforcement_actions` and `policy_versions` rows carry `source_url`; `votes` and "
        "`holdings` rows reach theirs through `accession` → `filings` (see `DATASHEET.md`, "
        "Joins). `datapackage.json` defines every column of every table and lists content "
        "hashes; `DATASHEET.md` documents code lists, coverage and limits.", "",
        "## Use it",
        "- `facts/*.csv[.gz]` — open everywhere (pandas, R, DuckDB, spreadsheets).",
        *(["- `facts/*.parquet` — typed, columnar, for analysis at scale."] if has_pq else []),
        *(["- `derived/glasshouse.db` — SQLite; browse with "
           "`datasette derived/glasshouse.db`."] if with_sqlite else []), "",
        "## Cite it",
        "Cite the DOI on the Zenodo record you downloaded these files from, together with "
        "the version and commit below. Files obtained any other way are an unpublished "
        "build: cite them with the version and commit only, and say so.",
        "```", cite, "```", "",
        "## Leads, not findings (read before publishing)",
        "This is a factual compilation — acts, dates, amounts, votes; never motive. "
        "Any say-vs-do gap you derive is a **lead**: theme matching is lexical, so "
        "confirm each proposal's text/intent and the in-force policy version against "
        "the linked primary source before publishing a claim.",
        "",
        "## Corrections",
        "Spotted an error? Open an issue at the project repository (or email the "
        "maintainer) with the table, the row, and the primary-source link.", "",
        "## Provenance guarantees",
        *[f"- {g}" for g in pkg["provenance_guarantees"]], "",
        "## What is NOT here (by construction)",
        "- Operator-internal tables (advisory LLM output, unsent outreach drafts, "
        "internal signals) — never published.",
        "- Findings that a human has **not** approved — the `findings` table holds "
        "approved claims only; everything else stays a private lead.",
        "- Full coverage — this is a **partial, growing** snapshot. See "
        "`COVERAGE.json` / `DATASHEET.md` for exactly what is in. Absence means no "
        "data was collected, not a clean record.", "",
    ]
    return "\n".join(lines) + "\n"
