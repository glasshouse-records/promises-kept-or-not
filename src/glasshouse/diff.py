"""The diff engine — the heartbeat. State is a database; change is a story.

Every run can compare the ledger against the last recorded run and report
the deltas: new votes, new enforcement actions, new commitment versions.
DELTAS ARE THE PUBLISHABLE UNIT; this module is what turns a quarterly
ingest into something a feed can carry.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from glasshouse import ledger


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
                     new_votes=conn.execute(
                         f"SELECT COUNT(*) FROM votes WHERE {ledger.NON_LEGACY_VOTE_SQL}"
                     ).fetchone()[0],
                     new_enforcement=_maxid(conn, "enforcement_actions"),
                     new_commitment_versions=_maxid(conn, "commitments"))

    d = Delta(since=last["ts"])
    d.new_votes = conn.execute(
        f"SELECT COUNT(*) FROM votes WHERE id > ? AND {ledger.NON_LEGACY_VOTE_SQL}",
        (last["votes_maxid"],)).fetchone()[0]
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


def holdings_changes(conn: sqlite3.Connection, institution_id: str,
                     min_value_usd: int = 10_000_000) -> dict:
    """Positions opened / closed / materially changed between the two most
    recent 13-F periods on record for an institution. Position-level deltas
    are the publishable unit of the holdings story."""
    periods = [r[0] for r in conn.execute(
        """SELECT DISTINCT f.period_of_report FROM filings f
           WHERE f.institution_id = ? AND f.form_type LIKE '13F%'
           ORDER BY f.period_of_report DESC LIMIT 2""", (institution_id,))]
    if len(periods) < 2:
        return {"periods": periods, "opened": [], "closed": [], "changed": []}
    new_p, old_p = periods[0], periods[1]

    def positions(period):
        return {r["cusip"]: dict(r) for r in conn.execute(
            """SELECT h.cusip, h.issuer_name, SUM(h.value_usd) AS value_usd,
                      SUM(h.shares) AS shares
               FROM holdings h JOIN filings f ON f.accession = h.accession
               WHERE f.institution_id = ? AND f.period_of_report = ? AND h.cusip != ''
               GROUP BY h.cusip""", (institution_id, period))}

    new, old = positions(new_p), positions(old_p)
    opened = sorted((v for k, v in new.items() if k not in old),
                    key=lambda v: -v["value_usd"])
    closed = sorted((v for k, v in old.items() if k not in new),
                    key=lambda v: -v["value_usd"])
    changed = []
    for k in new.keys() & old.keys():
        ds = new[k]["shares"] - old[k]["shares"]
        if old[k]["shares"] and abs(ds) / old[k]["shares"] >= 0.10 \
                and max(new[k]["value_usd"], old[k]["value_usd"]) >= min_value_usd:
            changed.append({**new[k], "shares_delta": ds,
                            "pct": 100 * ds / old[k]["shares"]})
    changed.sort(key=lambda v: -abs(v["shares_delta"] * v["value_usd"] / (v["shares"] or 1)))
    return {"periods": [new_p, old_p],
            "opened": [o for o in opened if o["value_usd"] >= min_value_usd],
            "closed": [c for c in closed if c["value_usd"] >= min_value_usd],
            "changed": changed}


def record_run(conn: sqlite3.Connection) -> str:
    """Snapshot the current ledger frontier as a run; future diffs are
    computed against the most recent run."""
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO runs (ts, votes_maxid, enf_maxid, commitments_maxid) VALUES (?,?,?,?)",
        (ts, _maxid(conn, "votes"), _maxid(conn, "enforcement_actions"),
         _maxid(conn, "commitments")),
    )
    conn.commit()
    return ts
