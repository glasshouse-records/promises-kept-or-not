"""GLEIF LEI enrichment — identifier-grade issuer identity (free API).

N-PX votes carry ISINs; GLEIF maps ISIN → LEI, legal name, and country.
This is the corroboration layer the Aldar Properties false positive
demands: once an issuer has an LEI and country in `entities`, a name-level
enforcement match against an entity in a different jurisdiction can be
rejected (or escalated) on evidence instead of vibes.

GLEIF asks for ≤60 requests/min unauthenticated; the shared throttle plus
a per-call pause keeps us under it. Enrichment is resumable: already-known
CUSIPs are skipped.
"""

from __future__ import annotations

import logging
import sqlite3
import time

from .. import http
from ..entities import upsert_entity

logger = logging.getLogger(__name__)

GLEIF_API = "https://api.gleif.org/api/v1/lei-records"
_PAUSE = 1.1  # stay under 60 req/min


def lookup_isin(isin: str) -> dict | None:
    """ISIN → {lei, name, country} via GLEIF, or None if unmapped."""
    data = http.get_json(GLEIF_API, params={"filter[isin]": isin, "page[size]": 1},
                         timeout=30).get("data", [])
    if not data:
        return None
    att = data[0]["attributes"]
    entity = att.get("entity", {})
    return {
        "lei": att.get("lei", ""),
        "name": (entity.get("legalName") or {}).get("name", ""),
        "country": (entity.get("legalAddress") or {}).get("country", ""),
    }


def enrich_from_votes(conn: sqlite3.Connection, limit: int | None = None) -> dict:
    """Resolve voted issuers' ISINs to LEI/legal name/country in `entities`.

    Works through distinct (isin, cusip) pairs from votes, newest meetings
    first, skipping CUSIPs already linked to an entity.
    """
    pairs = conn.execute(
        """SELECT v.isin, v.cusip, MAX(v.meeting_date) AS last_meeting
           FROM votes v
           LEFT JOIN entity_cusips ec ON ec.cusip = v.cusip
           WHERE v.isin != '' AND v.cusip != '' AND ec.cusip IS NULL
           GROUP BY v.isin, v.cusip
           ORDER BY last_meeting DESC"""
    ).fetchall()
    if limit:
        pairs = pairs[:limit]

    stats = {"resolved": 0, "unmapped": 0, "errors": 0}
    for row in pairs:
        isin, cusip = row["isin"], row["cusip"]
        try:
            rec = lookup_isin(isin)
        except Exception as exc:
            logger.warning("GLEIF lookup %s failed: %s", isin, exc)
            stats["errors"] += 1
            time.sleep(_PAUSE)
            continue
        if rec and rec["lei"] and rec["name"]:
            entity_id = upsert_entity(conn, rec["name"], lei=rec["lei"], cusips=[cusip])
            conn.execute("UPDATE entities SET country = ? WHERE id = ? AND country = ''",
                         (rec["country"], entity_id))
            stats["resolved"] += 1
        else:
            stats["unmapped"] += 1
        time.sleep(_PAUSE)
    conn.commit()
    logger.info("GLEIF enrichment: %s", stats)
    return stats
