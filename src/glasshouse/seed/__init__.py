"""Curated enforcement snapshots, carried from the predecessor project
(hand-verified research, extracted 2026-05-26).

All rows load with source_kind='curated_snapshot' and are quarantined from
publication until re-verified against live primary sources (see
PENDING_VERIFICATION.md). Resolution types are inferred from the verified
case descriptions by conservative keyword matching; anything ambiguous is
stored as 'unverified'.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..ledger import EnforcementAction, insert_enforcement

SNAPSHOT_DATE = "2026-05-26"  # when the predecessor project extracted/verified this data
_HERE = Path(__file__).parent

_DOJ_FCPA_URL = "https://www.justice.gov/criminal/criminal-fraud/related-enforcement-actions"
_SEC_LR_URL = "https://www.sec.gov/litigation/litreleases"
_DOJ_ATR_URL = "https://www.justice.gov/atr/antitrust-case-filings"
_WB_URL = "https://www.worldbank.org/en/projects-operations/procurement/debarred-firms"
_NLRB_URL = "https://www.nlrb.gov/cases-decisions"
_UNGC_URL = "https://www.unglobalcompact.org/participation/report/expelled"


def infer_resolution_type(description: str) -> str:
    """Conservative keyword inference; ambiguity → 'unverified' (quarantine).

    When a description mentions both a parent DPA/NPA and subsidiary guilty
    pleas (e.g. Siemens 2008), the parent's resolution governs the keyed
    company, so DPA/NPA is checked first.
    """
    d = description.lower()
    if "non-prosecution" in d or "npa" in d.split():
        return "npa"
    if "deferred prosecution" in d or "entered dpa" in d or " dpa" in d:
        return "dpa"
    if "pleaded guilty" in d or "guilty plea" in d or "pled guilty" in d:
        return "guilty_plea"
    if any(k in d for k in ("civil settlement", "settled sec", "sec settlement",
                            "consent judgment", "civil penalty", "settlement (")):
        return "civil_settlement"
    if "settlement" in d and "sec " in d:
        return "civil_settlement"
    return "unverified"


def _per_case(db: dict, agency: str, default_url: str, ref_key: str,
              fixed_resolution: str | None = None) -> list[EnforcementAction]:
    actions = []
    for key, cases in db.items():
        for case in cases:
            desc = case.get("description", "")
            actions.append(EnforcementAction(
                agency=agency,
                company_name=_company_from_description(desc) or key,
                action_date=case.get("date", ""),
                resolution_type=fixed_resolution or infer_resolution_type(desc),
                penalty_usd=int(case.get("penalty_usd", 0)),
                primary_ref=case.get(ref_key, ""),
                description=desc,
                source_url=case.get("source_url", default_url),
                retrieval_date=SNAPSHOT_DATE,
                source_kind="curated_snapshot",
            ))
    return actions


def _company_from_description(desc: str) -> str:
    # Curated descriptions lead with the company's full legal name, em-dash
    # or parenthetical delimited: "Siemens AG (parent) entered DPA; ..."
    for sep in (" — ", " — ", " ("):
        if sep in desc:
            head = desc.split(sep, 1)[0].strip()
            if 2 < len(head) < 80:
                return head
    return desc.split(" entered ")[0].strip()[:80] if desc else ""


def load_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Load every curated snapshot into the ledger. Idempotent."""
    from . import (
        doj_antitrust,
        nlrb_violations,
        sec_enforcement,
        ungc_expulsions,
        world_bank_debarment,
    )

    counts: dict[str, int] = {}

    fcpa = json.loads((_HERE / "fcpa_cases.json").read_text())
    counts["doj_sec_fcpa"] = insert_enforcement(
        conn, _per_case(fcpa, "DOJ/SEC (FCPA)", _DOJ_FCPA_URL, "doj_ref"))

    counts["sec_fraud"] = insert_enforcement(
        conn, _per_case(sec_enforcement.SEC_FRAUD_CASES, "SEC", _SEC_LR_URL, "sec_ref"))

    counts["doj_antitrust"] = insert_enforcement(
        conn, _per_case(doj_antitrust.ANTITRUST_CASES, "DOJ (Antitrust)", _DOJ_ATR_URL, "doj_ref"))

    wb = []
    for entry in world_bank_debarment.WORLD_BANK_DEBARRED.values():
        wb.append(EnforcementAction(
            agency="World Bank (debarment)",
            company_name=entry["company"],
            action_date=entry.get("debarment_date", ""),
            resolution_type="debarment",
            primary_ref=f"WB debarment {entry.get('debarment_date', '')}",
            description=(entry.get("basis", "") + " " + entry.get("note", "")).strip(),
            source_url=entry.get("source_url", _WB_URL),
            retrieval_date=SNAPSHOT_DATE,
            source_kind="curated_snapshot",
        ))
    counts["world_bank"] = insert_enforcement(conn, wb)

    nlrb = []
    for entry in nlrb_violations.NLRB_VIOLATORS.values():
        for case in entry.get("key_cases", []):
            nlrb.append(EnforcementAction(
                agency="NLRB",
                company_name=entry["company"],
                action_date=case.get("date", ""),
                resolution_type="board_order",
                primary_ref=case.get("case_ref", ""),
                description=case.get("description", ""),
                source_url=entry.get("source_url", _NLRB_URL),
                retrieval_date=SNAPSHOT_DATE,
                source_kind="curated_snapshot",
            ))
    counts["nlrb"] = insert_enforcement(conn, nlrb)

    ungc = []
    for entry in ungc_expulsions.UNGC_EXPELLED.values():
        ungc.append(EnforcementAction(
            agency="UN Global Compact",
            company_name=entry["company"],
            action_date=entry.get("withdrawal_date", ""),
            resolution_type="expulsion",
            primary_ref=f"UNGC {entry.get('withdrawal_type', 'expelled')} {entry.get('withdrawal_date', '')}",
            description=entry.get("basis", ""),
            source_url=entry.get("source_url", _UNGC_URL),
            retrieval_date=SNAPSHOT_DATE,
            source_kind="curated_snapshot",
        ))
    counts["ungc"] = insert_enforcement(conn, ungc)

    return counts
