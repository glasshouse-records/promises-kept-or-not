"""CourtListener / RECAP — federal dockets for PENDING matters.

HARD RULE, enforced in code: every row from this source is created with
resolution_type='allegation', which (a) auto-sets is_allegation, (b) scores
ZERO in the concern index, and (c) can never leave quarantine into a
finding. A docket is a question, not an answer.

Free REST API; anonymous access is rate-limited, so this module queries
only the tracked institutions (one request per name, throttled).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"
_PAUSE = 2.0


def fetch_for(names: list[str], max_per_name: int = 10) -> list[EnforcementAction]:
    today = date.today().isoformat()
    actions: list[EnforcementAction] = []
    for name in names:
        try:
            data = http.get_json(SEARCH_URL, params={
                "q": f'"{name}"', "type": "r",  # RECAP dockets
                "order_by": "dateFiled desc",
            }, timeout=30)
        except Exception as exc:
            logger.warning("CourtListener query for %r failed: %s", name, exc)
            time.sleep(_PAUSE)
            continue
        for hit in (data.get("results") or [])[:max_per_name]:
            case = hit.get("caseName") or ""
            if not case:
                continue
            actions.append(EnforcementAction(
                agency=f"Federal docket ({hit.get('court', 'unknown court')})",
                company_name=name,
                action_date=str(hit.get("dateFiled") or "")[:10],
                resolution_type="allegation",   # NEVER a finding
                primary_ref=f"Docket {hit.get('docketNumber', '?')}",
                description=f"PENDING MATTER — allegation only. {case}"[:400],
                source_url="https://www.courtlistener.com" + (hit.get("absolute_url") or ""),
                retrieval_date=today,
            ))
        time.sleep(_PAUSE)
    logger.info("CourtListener: %d docket rows (all allegations)", len(actions))
    return actions


def tracked_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT display_name FROM institutions WHERE id IN "
        "(SELECT DISTINCT institution_id FROM filings WHERE institution_id IS NOT NULL)")]
