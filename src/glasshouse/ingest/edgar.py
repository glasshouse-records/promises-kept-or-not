"""SEC EDGAR filing discovery via the public submissions API.

All endpoints are free public records; SEC requires a User-Agent and
≤10 req/s, both handled by glasshouse.http.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .. import http

logger = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


@dataclass
class Filing:
    cik: str
    company_name: str
    form_type: str
    filing_date: str
    period_of_report: Optional[str]
    accession_number: str

    @property
    def accession_clean(self) -> str:
        return self.accession_number.replace("-", "")

    @property
    def directory_url(self) -> str:
        return f"{ARCHIVES_BASE}/{int(self.cik)}/{self.accession_clean}"

    @property
    def index_url(self) -> str:
        return f"{self.directory_url}/index.json"


def list_filings(cik: str, form_types: list[str], limit: int | None = None) -> list[Filing]:
    """Newest-first filings of the given form types for a CIK.

    Follows the submissions API's pagination files so older filings are
    included when the recent window isn't enough.
    """
    cik10 = cik.zfill(10)
    data = http.get_json(SUBMISSIONS_URL.format(cik=cik10))
    company_name = data.get("name", "Unknown")
    filings = data.get("filings", {})
    recent = filings.get("recent", {})

    wanted = {f.upper() for f in form_types}
    results: list[Filing] = []

    def scan(block: dict) -> None:
        forms = block.get("form", [])
        for i, form in enumerate(forms):
            if form.upper() not in wanted:
                continue
            results.append(Filing(
                cik=cik10,
                company_name=company_name,
                form_type=form,
                filing_date=block["filingDate"][i],
                period_of_report=(block.get("reportDate") or [None] * len(forms))[i] or None,
                accession_number=block["accessionNumber"][i],
            ))

    scan(recent)
    if limit is None or len(results) < limit:
        for extra in filings.get("files", []):
            extra_block = http.get_json(f"https://data.sec.gov/submissions/{extra['name']}")
            scan(extra_block)
            if limit is not None and len(results) >= limit:
                break

    logger.info("CIK %s: %d %s filings", cik10, len(results), "/".join(form_types))
    return results[:limit] if limit else results


def filing_directory(filing: Filing) -> list[dict]:
    """List the files inside a filing directory (name, size)."""
    data = http.get_json(filing.index_url)
    return data.get("directory", {}).get("item", [])
