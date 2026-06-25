"""Discover a manager's N-PX-filing fund trusts — turning the coverage
bottleneck from manual EDGAR archaeology into a repeatable, evidence-backed
proposal step.

N-PX is filed by fund trusts, not the manager, and a big manager spreads
votes across many trusts. This module finds candidate filer CIKs by name and
confirms each against the authoritative submissions API (real entity name,
N-PX filing count, latest date). It PROPOSES candidates with evidence — it
never auto-attributes a trust to a manager, because a wrong attribution puts
another fund family's votes in this manager's mouth (the cardinal sin). A
human confirms before any CIK enters the registry.
"""

from __future__ import annotations

import logging
import re

from .. import http

logger = logging.getLogger(__name__)

_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
_CIK_RE = re.compile(r"<cik>(\d+)</cik>", re.IGNORECASE)


def discover_npx_filers(name: str, max_candidates: int = 12) -> list[dict]:
    """Candidate N-PX filers whose company name matches *name*, each enriched
    with submissions-API evidence and sorted by N-PX filing count.

    Returns [{cik, name, npx_filings, latest, vote_filings}] — vote_filings
    excludes cover-only notices is left to ingestion; here we count all N-PX.
    Returns [] on failure (never raises — a discovery miss is not a crash).
    """
    try:
        resp = http.get(_SEARCH, params={
            "action": "getcompany", "company": name, "type": "N-PX",
            "owner": "include", "count": 40, "output": "atom"}, timeout=30)
    except Exception as exc:
        logger.warning("discover %r: company search failed: %s", name, exc)
        return []

    ciks, seen = [], set()
    for c in _CIK_RE.findall(resp.text):
        cz = c.zfill(10)
        if cz not in seen:
            seen.add(cz)
            ciks.append(cz)

    out: list[dict] = []
    for cik in ciks[:max_candidates]:
        try:
            d = http.get_json(_SUBMISSIONS.format(cik=cik), timeout=30)
        except Exception:
            continue
        recent = d.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        npx_dates = [dates[i] for i, f in enumerate(forms) if f.upper().startswith("N-PX")]
        if not npx_dates:
            continue
        out.append({
            "cik": str(int(cik)),                 # unpadded, registry style
            "name": d.get("name", ""),
            "npx_filings": len(npx_dates),
            "latest": max(npx_dates),
        })
    out.sort(key=lambda r: -r["npx_filings"])
    logger.info("discover %r: %d N-PX-filing candidates", name, len(out))
    return out
