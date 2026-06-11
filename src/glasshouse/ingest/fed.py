"""Federal Reserve Board enforcement actions (bulk CSV) → ledger.

The Fed publishes its full enforcement-action history as CSV. These cover
the BANKS THEMSELVES — an institution's own record vs. its marketing is a
first-class finding class. Fed actions are administrative (written
agreements, cease-and-desist, civil money penalties), recorded as
`administrative_action`; the CSV's own action type is preserved verbatim
in the description.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

CSV_URL = "https://www.federalreserve.gov/supervisionreg/files/enforcementactions.csv"
PUBLIC_URL = "https://www.federalreserve.gov/supervisionreg/enforcementactions.htm"


def _col(row: dict, *names: str) -> str:
    """Header-name lookup tolerant to case/spacing changes in the CSV."""
    lookup = {k.lower().strip(): (v or "").strip() for k, v in row.items() if k}
    for n in names:
        if n.lower() in lookup:
            return lookup[n.lower()]
    return ""


def fetch() -> list[EnforcementAction]:
    today = date.today().isoformat()
    try:
        text = http.get(CSV_URL, timeout=60).text
    except Exception as exc:
        logger.warning("Fed enforcement CSV fetch failed: %s", exc)
        return []
    actions: list[EnforcementAction] = []
    for row in csv.DictReader(io.StringIO(text)):
        name = _col(row, "Banking Organization", "Individual/Banking Organization",
                    "Entity", "Name")
        if not name:
            continue
        action_type = _col(row, "Action", "Action Type")
        effective = _col(row, "Effective Date", "Date")
        url = _col(row, "URL", "Action URL") or PUBLIC_URL
        note = _col(row, "Note", "Description")
        actions.append(EnforcementAction(
            agency="Federal Reserve",
            company_name=name,
            action_date=_iso(effective),
            resolution_type="administrative_action",
            primary_ref=f"FRB {action_type} {_iso(effective)}".strip(),
            description=(f"{action_type}. {note}".strip(". ") + ".")[:500],
            source_url=url,
            retrieval_date=today,
        ))
    logger.info("Federal Reserve: %d enforcement actions", len(actions))
    return actions


def _iso(d: str) -> str:
    """Normalize 'MM/DD/YYYY' or 'YYYY-MM-DD' to ISO; pass through otherwise."""
    d = d.strip()
    if "/" in d:
        parts = d.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            return f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
    return d
