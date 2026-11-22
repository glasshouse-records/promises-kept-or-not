"""Public snapshot builder — the disclosure-control boundary.

`glasshouse export` and the MCP server must expose ONLY publishable data,
never the operator's working state. A raw `VACUUM INTO` copies the whole
ledger — including triage/llm_log (advisory LLM output), outreach (unsent
drafts), signals, match_log, and pending/rejected findings with reviewer
notes. For a project whose first rule is "nothing is published without
human approval," shipping those through the public API is a leak.

This module copies a curated subset: public primary-source tables in full,
votes/enforcement filtered to non-duplicate rows, and findings filtered to
status='approved' ONLY. Operator-internal tables are never copied.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from .ledger import NON_LEGACY_VOTE_SQL

# Table → WHERE clause (empty = whole table). Anything NOT listed here is
# operator-internal and never leaves the working ledger.
PUBLIC_TABLES: dict[str, str] = {
    "institutions": "",
    "filings": "",
    "fund_series": "",
    # Single-parser `legacy_html` votes and any legacy_format not in
    # ledger.PROMOTED_LEGACY_FORMATS stay out (precision over recall); the promoted 2022-23
    # two-parser rows ship, identifiable by votes.legacy_format.
    # IFNULL: structured votes may have NULL/'' vote_source and must stay in.
    # how_voted != '' drops administrative N-PX rows (postal-meeting notices,
    # no-vote records) that aren't actual votes — a "proxy votes" table should
    # only contain cast votes.
    "votes": f"WHERE is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL} "
             "AND IFNULL(how_voted,'') != ''",
    "holdings": "",
    "enforcement_actions": "WHERE is_duplicate = 0",
    "entities": "",
    "entity_cusips": "",
    "commitments": "WHERE superseded = 0",
    "findings": "WHERE status = 'approved'",   # only human-approved findings are public
}

# Explicitly never published (here for the test that asserts the boundary).
OPERATOR_ONLY = ("triage", "llm_log", "outreach", "signals", "match_log", "runs",
                 "capture_attempts", "ingest_runs")

# Columns dropped from otherwise-public tables: operator-internal artifacts that
# are useless to consumers and leak local structure (content_path is the
# maintainer's local cache path for a commitment doc).
# votes: legacy_format / for_against_management SHIP (a promoted 2022-23 row must be
# identifiable); both are documented in dataset.DATA_DICTIONARY.
PUBLIC_DROP_COLS: dict[str, set[str]] = {
    "commitments": {"content_path"},
}


def public_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Public column list for a table — its columns minus PUBLIC_DROP_COLS."""
    drop = PUBLIC_DROP_COLS.get(table, set())
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[1] not in drop]


def build_public_snapshot(conn: sqlite3.Connection, dest: Path | str) -> Path:
    """Write a new SQLite file at *dest* containing only publishable data."""
    dest = Path(dest)
    dest.unlink(missing_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(dest)
    try:
        for table, where in PUBLIC_TABLES.items():
            ddl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if not ddl or not ddl[0]:
                continue
            out.execute(ddl[0])
            for col in PUBLIC_DROP_COLS.get(table, ()):   # drop operator-only columns
                with contextlib.suppress(sqlite3.OperationalError):
                    out.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
            cols = public_columns(conn, table)
            collist = ",".join(cols)
            placeholders = ",".join("?" * len(cols))
            cur = conn.execute(f"SELECT {collist} FROM {table} {where}")
            while rows := cur.fetchmany(100_000):     # streamed: votes is ~51M rows
                out.executemany(f"INSERT INTO {table} ({collist}) VALUES ({placeholders})",
                                [tuple(r) for r in rows])
            # carry the table's indexes for query performance on the mirror
            for (idx_sql,) in conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
                    "AND sql IS NOT NULL", (table,)).fetchall():
                out.execute(idx_sql)
        out.commit()
    finally:
        out.close()
    return dest


def newest_snapshot(exports_dir: Path) -> Path | None:
    """Most recent published snapshot, or None if the operator hasn't
    exported one yet. The MCP/public surface serves this, never the
    working ledger."""
    if not exports_dir.exists():
        return None
    snaps = sorted(exports_dir.glob("glasshouse-public-*.db"))
    return snaps[-1] if snaps else None
