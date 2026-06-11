"""The Concern Index — transparent, documented, reproducible. v0.

    concern(company) = recidivism_multiplier × Σ over resolved actions of
                       severity(resolution_type) × 0.5^(age_years / 5)

  - severity: fixed table below, anchored to the legal weight of the
    resolution (a guilty plea outweighs a civil settlement; allegations and
    unverified records score ZERO — quarantined data never moves a score)
  - recency: 5-year half-life (an action 10 years old counts a quarter)
  - recidivism: 1 + 0.15 × (n_scored_actions − 1), capped at 2.0 —
    repeat resolution is the pattern the index exists to surface
  - displayed 0–100 via 100 × (1 − e^(−raw/20)) for comparability

The full formula lives here and in METHODOLOGY.md; anyone can recompute any
score from the public ledger. The index is an analytical summary of public
records, not a legal finding and not an opinion about conduct. v0 carries
no confidence intervals — a documented limitation, not a hidden one.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date

SEVERITY: dict[str, float] = {
    "guilty_plea": 10.0,
    "sanction_designation": 9.0,
    "dpa": 7.0,
    "npa": 6.0,
    "debarment": 6.0,
    "civil_settlement": 5.0,
    "civil_violation": 4.0,
    "board_order": 4.0,
    "administrative_action": 3.0,
    "expulsion": 2.0,
    "allegation": 0.0,    # never scored — allegations are not findings
    "unverified": 0.0,    # never scored — quarantined data moves nothing
}

HALF_LIFE_YEARS = 5.0
RECIDIVISM_STEP = 0.15
RECIDIVISM_CAP = 2.0


def _age_years(action_date: str, today: date) -> float:
    try:
        d = date.fromisoformat(action_date[:10])
    except (ValueError, TypeError):
        return HALF_LIFE_YEARS * 2  # undated: discount as if 10 years old
    return max(0.0, (today - d).days / 365.25)


def concern_index(actions: list[dict], today: date | None = None) -> dict:
    """Score a company's enforcement record. `actions` rows need
    resolution_type and action_date. Returns raw and 0-100 display values
    plus the per-action breakdown so every score is auditable."""
    today = today or date.today()
    parts = []
    for a in actions:
        sev = SEVERITY.get(a["resolution_type"], 0.0)
        if sev == 0.0:
            continue
        decay = 0.5 ** (_age_years(a.get("action_date", ""), today) / HALF_LIFE_YEARS)
        parts.append({"resolution_type": a["resolution_type"],
                      "action_date": a.get("action_date", ""),
                      "severity": sev, "decay": round(decay, 3),
                      "contribution": sev * decay})
    n = len(parts)
    multiplier = min(RECIDIVISM_CAP, 1 + RECIDIVISM_STEP * max(0, n - 1))
    raw = multiplier * sum(p["contribution"] for p in parts)
    return {
        "raw": round(raw, 2),
        "score": round(100 * (1 - math.exp(-raw / 20)), 1),
        "n_scored_actions": n,
        "recidivism_multiplier": round(multiplier, 2),
        "breakdown": parts,
    }


def company_scores(conn: sqlite3.Connection, limit: int = 25) -> list[dict]:
    """Top concern-index scores across the enforcement universe (deduped,
    verified rows only)."""
    rows = conn.execute(
        """SELECT company_name, resolution_type, action_date
           FROM enforcement_actions
           WHERE is_duplicate = 0 AND resolution_type NOT IN ('allegation','unverified')
        """).fetchall()
    by_company: dict[str, list[dict]] = {}
    for r in rows:
        by_company.setdefault(r["company_name"], []).append(dict(r))
    scored = [{"company": k, **concern_index(v)} for k, v in by_company.items()]
    scored.sort(key=lambda s: -s["raw"])
    return scored[:limit]
