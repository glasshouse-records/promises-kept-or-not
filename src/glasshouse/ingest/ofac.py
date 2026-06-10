"""OFAC SDN + consolidated sanctions lists (Treasury bulk CSV) → ledger.

Public domain, ~2 MB. Entity rows only (SDN_Type == "-" means entity in the
legacy CSV format; individuals are excluded — Glasshouse tracks entities).
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
CONSOLIDATED_URL = "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv"


def _parse(csv_text: str, source_url: str, list_name: str) -> list[EnforcementAction]:
    today = date.today().isoformat()
    actions = []
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) < 4 or not row[0].strip().isdigit():
            continue
        ent_num, name, sdn_type, program = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
        # Legacy CSV: entities have SDN_Type "-" ; individuals say "individual"
        if sdn_type.lower() == "individual":
            continue
        actions.append(EnforcementAction(
            agency=f"OFAC ({list_name})",
            company_name=name,
            resolution_type="sanction_designation",
            primary_ref=f"OFAC Ent_num {ent_num}",
            description=f"Designated under program(s): {program}",
            source_url=source_url,
            retrieval_date=today,
        ))
    return actions


def fetch() -> list[EnforcementAction]:
    actions: list[EnforcementAction] = []
    for url, label in ((SDN_URL, "SDN"), (CONSOLIDATED_URL, "Consolidated")):
        try:
            text = http.get(url, timeout=60).text
            batch = _parse(text, url, label)
            logger.info("OFAC %s: %d entity designations", label, len(batch))
            actions.extend(batch)
        except Exception as exc:
            logger.warning("OFAC %s fetch failed: %s", label, exc)
    return actions
