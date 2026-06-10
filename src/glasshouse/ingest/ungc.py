"""UN Global Compact expelled participants (public API) → ledger.

Expulsion is a membership action (usually for failure to communicate
progress), not a legal finding — resolution_type 'expulsion' and the basis
is always quoted.
"""

from __future__ import annotations

import logging
import time
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

API_URL = "https://www.unglobalcompact.org/api/v1/participants.json"
PUBLIC_URL = "https://www.unglobalcompact.org/participation/report/expelled"


def fetch() -> list[EnforcementAction]:
    today = date.today().isoformat()
    actions: list[EnforcementAction] = []
    page = 1
    try:
        while True:
            data = http.get_json(
                API_URL, params={"status": "expelled", "page": page, "per_page": 500},
                timeout=30,
            )
            items = data if isinstance(data, list) else data.get("organizations", [])
            if not items:
                break
            for item in items:
                name = item.get("name") or item.get("organization_name", "")
                if not name:
                    continue
                actions.append(EnforcementAction(
                    agency="UN Global Compact",
                    company_name=name,
                    action_date=str(item.get("expelled_on") or item.get("updated_at", ""))[:10],
                    resolution_type="expulsion",
                    primary_ref=f"UNGC participant id {item.get('id', '')}",
                    description="Expelled from the UN Global Compact (typically for failure to communicate progress).",
                    source_url=PUBLIC_URL,
                    retrieval_date=today,
                ))
            if len(items) < 500:
                break
            page += 1
            time.sleep(0.3)
    except Exception as exc:
        logger.warning("UNGC fetch failed: %s", exc)
    if not actions:
        # Observed 2026-06-11: the v1 JSON endpoint now redirects to the HTML
        # site. The curated snapshot remains the fallback; revisit via the
        # participant-search CSV export.
        logger.warning("UNGC: 0 expulsions — endpoint likely changed; "
                       "relying on curated snapshot")
    else:
        logger.info("UNGC: %d expulsions", len(actions))
    return actions
