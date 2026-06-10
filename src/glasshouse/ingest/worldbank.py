"""World Bank debarred-firms list (public REST API) → ledger."""

from __future__ import annotations

import logging
import time
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

API_URL = "https://apigwext.worldbank.org/acrexternal/debarment-api/v2/debarredFirms"
PUBLIC_URL = "https://www.worldbank.org/en/projects-operations/procurement/debarred-firms"


def fetch() -> list[EnforcementAction]:
    today = date.today().isoformat()
    actions: list[EnforcementAction] = []
    page = 1
    try:
        while True:
            data = http.get_json(API_URL, params={"pageSize": 500, "pageNumber": page}, timeout=30)
            firms = data.get("debarredFirms") or data.get("content") or []
            if not firms:
                break
            for firm in firms:
                name = firm.get("firmName") or firm.get("name", "")
                if not name:
                    continue
                actions.append(EnforcementAction(
                    agency="World Bank (debarment)",
                    company_name=name,
                    action_date=firm.get("fromDate") or firm.get("debarmentDate", ""),
                    resolution_type="debarment",
                    primary_ref=f"WB debarment {name} from {firm.get('fromDate', '?')}",
                    description=(
                        f"Grounds: {firm.get('grounds') or firm.get('basis', '')}. "
                        f"Until: {firm.get('toDate') or firm.get('releaseDate', '')}. "
                        f"Cross-debarred: {bool(firm.get('crossDebarred', False))}. "
                        f"Country: {firm.get('countryOfRegistration', '')}"
                    ),
                    source_url=PUBLIC_URL,
                    retrieval_date=today,
                ))
            if len(firms) < 500:
                break
            page += 1
            time.sleep(0.5)
    except Exception as exc:
        logger.warning("World Bank debarment fetch failed: %s", exc)
    if not actions:
        # Observed 2026-06-11: the API is behind a Cloudflare challenge and
        # rejects non-browser clients. The curated snapshot remains the
        # fallback; revisit with the published XLSX from the public page.
        logger.warning("World Bank: 0 debarments — endpoint likely blocked/changed; "
                       "relying on curated snapshot")
    else:
        logger.info("World Bank: %d debarments", len(actions))
    return actions
