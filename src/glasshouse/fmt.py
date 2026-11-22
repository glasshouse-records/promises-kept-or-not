"""User-facing formatting for vote fields that are NULL or easily mislabelled.

* ``shares_voted`` is NULL for 2022-23 legacy N-PX rows (shares not filed).
  An unknown count must never be rendered as 0 or crash a formatter.
* ``votes.management_recommendation`` records whether THIS vote went WITH
  (FOR) or AGAINST management. It does not say what management recommended.
"""
from __future__ import annotations

SHARES_NOT_FILED = "shares not filed"


def shares_known(x) -> bool:
    if x is None or x == "":
        return False
    try:
        float(x)
    except (TypeError, ValueError):
        return False
    return True


def shares_phrase(x, unit: str = "shares") -> str:
    """'1,234 shares' (or '1,234 sh'), or 'shares not filed' when unknown."""
    if not shares_known(x):
        return SHARES_NOT_FILED
    return f"{int(float(x)):,} {unit}"


def vote_vs_mgmt(x) -> str:
    """Map the stored FOR/AGAINST to 'with'/'against management'; else verbatim."""
    v = (x or "").strip() if isinstance(x, str) else x
    if not v:
        return "—"
    u = str(v).upper()
    if u == "FOR":
        return "with management"
    if u == "AGAINST":
        return "against management"
    return str(v)
