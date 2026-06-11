"""GDELT news trigger — daily scan input, NEVER a citable source.

GDELT (free DOC 2.0 API) surfaces news mentioning tracked institutions or
enforcement-flagged companies alongside enforcement-flavored terms. Every
hit is a TRIGGER for primary-source verification: the alert it produces
says so in its first line, and nothing from GDELT enters the evidence
ledger. Rate limit: one request per 5 seconds (API-enforced); failures
degrade to an empty result.
"""

from __future__ import annotations

import logging
import time

from .. import http

logger = logging.getLogger(__name__)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
_ENFORCEMENT_TERMS = '(settlement OR charges OR indictment OR fine OR probe OR "enforcement action")'
_PAUSE = 5.5  # API enforces 1 req / 5 s


def news_triggers(names: list[str], timespan: str = "1d",
                  max_per_name: int = 5) -> list[dict]:
    """News articles pairing each name with enforcement terms.

    Returns [{name, title, url, seendate, domain}]. Anything here is a lead
    to chase to a primary source — DOJ/SEC/court records — never to cite.
    """
    out: list[dict] = []
    for name in names:
        try:
            data = http.get_json(DOC_API, params={
                "query": f'"{name}" {_ENFORCEMENT_TERMS} sourcelang:english',
                "mode": "artlist", "maxrecords": max_per_name,
                "timespan": timespan, "format": "json",
            }, timeout=30)
        except Exception as exc:
            logger.warning("GDELT query for %r failed: %s", name, exc)
            time.sleep(_PAUSE)
            continue
        for art in (data or {}).get("articles", []):
            out.append({
                "name": name,
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "seendate": art.get("seendate", ""),
                "domain": art.get("domain", ""),
            })
        time.sleep(_PAUSE)
    logger.info("GDELT: %d news triggers across %d names", len(out), len(names))
    return out
