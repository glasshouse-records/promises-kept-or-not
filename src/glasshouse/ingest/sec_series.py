"""The SEC's own "Investment Company Series and Class Information" open dataset: one
extra, official candidate source for the legacy 2022-23 N-PX fund -> series mapping.

Used ONLY when a filing's own SGML header gives no candidate for a fund heading (see
`legacy_pe.SeriesFallback` and METHODOLOGY.md). Files are annual CSVs on sec.gov, fetched
with the shared honest-User-Agent session and cached under data/cache/sec_series/.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from .. import http
from . import legacy_pe

logger = logging.getLogger(__name__)

BASE = "https://www.sec.gov/files/investment/data/other"
# The 2022 and 2023 annual files cover the 2022-07 .. 2023-06 N-PX period; the SEC names
# the two files differently (checked against the dataset page, 2026-11-27).
FILES = {
    "investment_company_series_class_2022.csv":
        f"{BASE}/investment-company-series-and-class-information/"
        "investment_company_series_class_2022.csv",
    "investment_company_series_class_2023.csv":
        f"{BASE}/investment-company-series-class-information/"
        "investment_company_series_class_2023.csv",
}
CACHE_DIR = http.CACHE_DIR / "sec_series"


def fetch(cache_dir: Path | None = None) -> list[Path]:
    """Download (once; cached) the annual files. Returns their local paths."""
    d = cache_dir or CACHE_DIR
    return [http.download(url, d / name) for name, url in FILES.items()]


def load_dataset(paths: list[Path] | None = None) -> dict[str, dict[str, set[str]]]:
    """CIK (10 digits) -> normalised series name -> {series ids}, from the CSV files
    (fetched if no paths are given). Names are normalised with `legacy_pe._norm`, exactly
    as the header path does; a name with two series ids stays a two-element set (the
    caller treats it as ambiguous)."""
    out: dict[str, dict[str, set[str]]] = {}
    for p in paths if paths is not None else fetch():
        with Path(p).open(newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.DictReader(fh):
                sid = (row.get("Series ID") or "").strip()
                name = legacy_pe._norm(row.get("Series Name") or "")
                if not sid.startswith("S") or not name:
                    continue
                out.setdefault(legacy_pe._cik10(row.get("CIK Number") or ""), {}
                               ).setdefault(name, set()).add(sid)
    return out
