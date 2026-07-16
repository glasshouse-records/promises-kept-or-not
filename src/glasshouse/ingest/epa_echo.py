"""EPA ECHO — environmental enforcement cases (bulk, weekly).

Source: https://echo.epa.gov/files/echodownloads/case_downloads.zip — EPA's
own weekly CSV dump of ICIS FE&C enforcement cases (free, public, no key).
Honest access: one bulk download, standard UA with contact.

SCOPE, precision-first (a false data point is fatal):
  • Only defendants whose normalized name EXACTLY equals one of the curated
    fossil-fuel companies (fossil.py — the hand-verified seed). Subsidiaries
    ("BP PRODUCTS NORTH AMERICA") do NOT match parents ("BP plc"): parent
    attribution is a human judgment, so we undercount rather than guess.
  • Only CONCLUDED cases: an assessed penalty > 0 AND a case-status date AND
    the defendant named in the settlement. This excludes open matters and the
    multi-PRP Superfund pileups where a major appears among dozens of parties
    with no penalty of its own (seen on the first live row inspected).
  • Judicial → civil_violation; Administrative → administrative_action
    (METHODOLOGY's legal table lists EPA under civil violation). Criminal and
    anything else is SKIPPED — outcome semantics are ambiguous in bulk.
  • company_name is the defendant AS FILED (verbatim provenance); every row
    carries the ECHO case-report URL and the case number as primary_ref.

The real CSVs contain NUL bytes; the reader strips them.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from .. import fossil
from ..entities import normalize_name
from ..http import DATA_DIR, get
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

ECHO_ZIP_URL = "https://echo.epa.gov/files/echodownloads/case_downloads.zip"
CACHE = DATA_DIR / "echo" / "case_downloads.zip"
CASE_REPORT = "https://echo.epa.gov/enforcement-case-report?id={aid}"

# Curated targets: normalized names of the hand-verified fossil companies.
_TARGETS = {normalize_name(n) for n in fossil.FOSSIL_FUEL_CUSIPS.values()}


def _rows(zf: zipfile.ZipFile, member: str):
    """Stream a CSV member, tolerating the NUL bytes present in real files."""
    with zf.open(member) as fh:
        text = io.TextIOWrapper(fh, encoding="latin-1", errors="replace")
        yield from csv.DictReader(line.replace("\0", "") for line in text)


def _iso(mdY: str) -> str:
    try:
        return datetime.strptime((mdY or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return ""


def parse(zip_path: Path) -> list[EnforcementAction]:
    with zipfile.ZipFile(zip_path) as zf:
        # Pass 1 — defendants: which activities name a curated company IN THE
        # SETTLEMENT, and how many defendants each activity has (for context).
        matched: dict[str, list[str]] = {}    # activity_id -> [defendant names as filed]
        n_defs: dict[str, int] = {}
        for r in _rows(zf, "CASE_DEFENDANTS.csv"):
            aid = (r.get("ACTIVITY_ID") or "").strip()
            if not aid:
                continue
            n_defs[aid] = n_defs.get(aid, 0) + 1
            if (r.get("NAMED_IN_SETTLEMENT_FLAG") or "").strip() != "Y":
                continue
            name = (r.get("DEFENDANT_NAME") or "").strip()
            if name and normalize_name(name) in _TARGETS:
                matched.setdefault(aid, []).append(name)

        # Pass 2 — the cases themselves, precision-filtered.
        out: list[EnforcementAction] = []
        for r in _rows(zf, "CASE_ENFORCEMENTS.csv"):
            aid = (r.get("ACTIVITY_ID") or "").strip()
            names = matched.get(aid)
            if not names:
                continue
            typ = (r.get("ACTIVITY_TYPE_DESC") or "").strip()
            if typ == "Judicial":
                resolution = "civil_violation"
            elif typ.startswith("Administrative"):
                resolution = "administrative_action"
            else:
                continue                       # criminal / other: skipped (ambiguous)
            try:
                penalty = int(float(r.get("TOTAL_PENALTY_ASSESSED_AMT") or 0))
            except ValueError:
                penalty = 0
            date = _iso(r.get("CASE_STATUS_DATE") or "")
            if penalty <= 0 or not date:
                continue                       # not a concluded, penalized case
            case_no = (r.get("CASE_NUMBER") or "").strip()
            summary = (r.get("ENF_SUMMARY_TEXT") or r.get("CASE_NAME") or "").strip()
            multi = (f" [case total across {n_defs.get(aid, 1)} defendants]"
                     if n_defs.get(aid, 1) > 1 else "")
            for name in names:
                out.append(EnforcementAction(
                    agency="EPA (ECHO)", company_name=name,
                    resolution_type=resolution, action_date=date,
                    penalty_usd=penalty, primary_ref=case_no,
                    description=(summary[:350] + multi),
                    source_url=CASE_REPORT.format(aid=aid)))
    return out


def fetch() -> list[EnforcementAction]:
    """Download (or reuse) the weekly bulk zip and parse it."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not CACHE.exists():
        logger.info("downloading %s", ECHO_ZIP_URL)
        CACHE.write_bytes(get(ECHO_ZIP_URL).content)
    return parse(CACHE)
