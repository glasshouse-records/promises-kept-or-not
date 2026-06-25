"""Self-measurement for the self-improvement loop.

"Best dataset possible" is only a direction until it's a number. This module
computes a transparent **balanced index** (0-100) from four components and
snapshots it over time, so the tool can see whether it is getting better or
worse — the prerequisite for any self-improvement.

The index is deliberately simple and documented (transparency is a core
value): a weighted blend of coverage, completeness, provenance, and
freshness. Weights and targets are constants here, not hidden.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

# Documented weights and targets. Change them here, in the open.
WEIGHTS = {"coverage": 0.30, "completeness": 0.25, "provenance": 0.25, "freshness": 0.20}
FRESHNESS_FULL_DAYS = 90        # data refreshed within this many days = 1.0
FRESHNESS_ZERO_DAYS = 540       # older than this = 0.0

# Coverage is AUM-WEIGHTED (decided 2026-06-17, skeptic-panel rec): it is the
# share of tracked assets-under-management that have FULL say+do data, so the
# index rewards covering the managers that actually move markets (Fidelity,
# T. Rowe, Pimco) and can't be gamed by adding small, easy fund trusts.


def compute(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Compute the balanced index and its components from the live ledger."""
    today = today or date.today()

    from . import registry
    aum = {iid: float(v.get("aum_usd_tr") or 0) for iid, v in registry.load().items()}
    total_aum = sum(aum.values()) or 1.0

    n_registered = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0] or 1
    n_with_votes = conn.execute(
        "SELECT COUNT(DISTINCT f.institution_id) FROM filings f JOIN votes v "
        "ON v.accession=f.accession WHERE v.is_duplicate=0").fetchone()[0]
    n_with_commit = conn.execute(
        "SELECT COUNT(DISTINCT institution_id) FROM commitments").fetchone()[0]
    full_ids = [r[0] for r in conn.execute(
        "SELECT i.id FROM institutions i WHERE "
        "EXISTS(SELECT 1 FROM filings f JOIN votes v ON v.accession=f.accession "
        "  WHERE f.institution_id=i.id AND v.is_duplicate=0) AND "
        "EXISTS(SELECT 1 FROM commitments c WHERE c.institution_id=i.id)").fetchall()]
    n_full = len(full_ids)
    n_any = conn.execute(
        "SELECT COUNT(*) FROM institutions i WHERE "
        "EXISTS(SELECT 1 FROM filings f WHERE f.institution_id=i.id) OR "
        "EXISTS(SELECT 1 FROM commitments c WHERE c.institution_id=i.id)").fetchone()[0] or 1
    covered_aum = sum(aum.get(iid, 0.0) for iid in full_ids)

    # provenance: share of public evidence rows carrying source_url+retrieval_date
    prov_ok = conn.execute(
        "SELECT COUNT(*) FROM enforcement_actions WHERE source_url!='' AND retrieval_date!=''"
    ).fetchone()[0]
    prov_tot = conn.execute("SELECT COUNT(*) FROM enforcement_actions").fetchone()[0] or 1

    # freshness: most recent live retrieval across enforcement + commitments
    last = conn.execute(
        "SELECT MAX(d) FROM (SELECT MAX(retrieval_date) d FROM enforcement_actions "
        "WHERE source_kind='live' UNION ALL SELECT MAX(retrieval_date) FROM commitments)"
    ).fetchone()[0]

    coverage = min(1.0, covered_aum / total_aum)   # AUM-weighted, not headcount
    completeness = n_full / n_any            # of institutions with any data, share with full say+do
    provenance = prov_ok / prov_tot
    freshness = _freshness(last, today)

    comps = {"coverage": round(coverage, 3), "completeness": round(completeness, 3),
             "provenance": round(provenance, 3), "freshness": round(freshness, 3)}
    index = round(100 * sum(WEIGHTS[k] * comps[k] for k in WEIGHTS), 1)
    raw = {"registered": n_registered, "with_votes": n_with_votes,
           "with_commitments": n_with_commit, "full_say_do": n_full,
           "any_data": n_any, "last_refresh": last,
           "covered_aum_tr": round(covered_aum, 1), "total_aum_tr": round(total_aum, 1)}
    return {"balanced_index": index, "components": comps, "raw": raw}


def _freshness(last: str | None, today: date) -> float:
    if not last:
        return 0.0
    try:
        d = date.fromisoformat(last[:10])
    except ValueError:
        return 0.0
    age = (today - d).days
    if age <= FRESHNESS_FULL_DAYS:
        return 1.0
    if age >= FRESHNESS_ZERO_DAYS:
        return 0.0
    return 1.0 - (age - FRESHNESS_FULL_DAYS) / (FRESHNESS_ZERO_DAYS - FRESHNESS_FULL_DAYS)


def snapshot(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Compute and record a metrics snapshot (trend memory)."""
    m = compute(conn, today=today)
    conn.execute(
        "INSERT INTO metrics (ts, balanced_index, components, raw) VALUES (?,?,?,?)",
        (datetime.now(UTC).isoformat(timespec="seconds"), m["balanced_index"],
         json.dumps(m["components"]), json.dumps(m["raw"])))
    conn.commit()
    return m


def trend(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, balanced_index, components FROM metrics ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    return [{"ts": r["ts"], "balanced_index": r["balanced_index"],
             "components": json.loads(r["components"])} for r in rows]


def delta(conn: sqlite3.Connection) -> float | None:
    """Change in the balanced index since the previous snapshot (None if <2)."""
    rows = conn.execute(
        "SELECT balanced_index FROM metrics ORDER BY id DESC LIMIT 2").fetchall()
    return round(rows[0][0] - rows[1][0], 1) if len(rows) == 2 else None
