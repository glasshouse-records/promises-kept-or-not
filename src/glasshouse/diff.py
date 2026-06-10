"""The diff engine — the heartbeat. State is a database; change is a story.

Every run can compare the ledger against the last recorded run and report
the deltas: new votes, new enforcement actions, new commitment versions.
DELTAS ARE THE PUBLISHABLE UNIT; this module is what turns a quarterly
ingest into something a feed can carry.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Delta:
    since: str | None                    # ts of the previous run, None = first run
    new_votes: int = 0
    new_enforcement: int = 0
    new_commitment_versions: int = 0
    enforcement_samples: list[dict] = field(default_factory=list)
    commitment_samples: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.new_votes or self.new_enforcement or self.new_commitment_versions)


def _maxid(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0]


def compute(conn: sqlite3.Connection) -> Delta:
    last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if last is None:
        return Delta(since=None,
                     new_votes=_maxid(conn, "votes"),
                     new_enforcement=_maxid(conn, "enforcement_actions"),
                     new_commitment_versions=_maxid(conn, "commitments"))

    d = Delta(since=last["ts"])
    d.new_votes = conn.execute(
        "SELECT COUNT(*) FROM votes WHERE id > ?", (last["votes_maxid"],)).fetchone()[0]
    d.new_enforcement = conn.execute(
        "SELECT COUNT(*) FROM enforcement_actions WHERE id > ?", (last["enf_maxid"],)).fetchone()[0]
    d.new_commitment_versions = conn.execute(
        "SELECT COUNT(*) FROM commitments WHERE id > ?", (last["commitments_maxid"],)).fetchone()[0]

    d.enforcement_samples = [dict(r) for r in conn.execute(
        "SELECT agency, company_name, action_date, resolution_type, primary_ref "
        "FROM enforcement_actions WHERE id > ? ORDER BY id DESC LIMIT 10",
        (last["enf_maxid"],)).fetchall()]
    d.commitment_samples = [dict(r) for r in conn.execute(
        "SELECT institution_id, doc_label, retrieval_date, wayback_timestamp "
        "FROM commitments WHERE id > ? ORDER BY id DESC LIMIT 10",
        (last["commitments_maxid"],)).fetchall()]
    return d


def record_run(conn: sqlite3.Connection) -> str:
    """Snapshot the current ledger frontier as a run; future diffs are
    computed against the most recent run."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO runs (ts, votes_maxid, enf_maxid, commitments_maxid) VALUES (?,?,?,?)",
        (ts, _maxid(conn, "votes"), _maxid(conn, "enforcement_actions"),
         _maxid(conn, "commitments")),
    )
    conn.commit()
    return ts
