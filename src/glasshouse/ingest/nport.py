"""SEC Form N-PORT ingestion — monthly mutual-fund holdings.

Extends coverage beyond 13-F filers to retail funds. NPORT-P's primary_doc
carries the full portfolio as <invstOrSec> elements (name, LEI, CUSIP,
ISIN, balance, USD value, % of portfolio). Parsed with the same streaming
discipline as N-PX; rows land in the shared holdings table with the filing
recording form_type NPORT-P, so 13-F and N-PORT positions are queryable
together but never confused.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from lxml import etree

from .. import http
from .edgar import Filing, list_filings

logger = logging.getLogger(__name__)

NPORT_FORMS = ["NPORT-P"]


def _local(el) -> str:
    if not isinstance(el.tag, str):
        return ""
    return etree.QName(el).localname


def _text(el, localname: str) -> str:
    for child in el.iter():
        if _local(child) == localname:
            return (child.text or "").strip()
    return ""


def _num(el, localname: str) -> float:
    t = _text(el, localname)
    try:
        return float(t.replace(",", "")) if t else 0.0
    except ValueError:
        return 0.0


def iter_positions(xml_path: Path):
    """Stream portfolio positions from an NPORT-P primary document."""
    context = etree.iterparse(str(xml_path), events=("end",), tag="{*}invstOrSec",
                              recover=True, huge_tree=True)
    for _event, sec in context:
        isin = ""
        for child in sec.iter():
            if _local(child) == "isin":
                isin = (child.get("value") or child.text or "").strip()
                break
        yield {
            "issuer_name": _text(sec, "name"),
            "lei": _text(sec, "lei"),
            "title_class": _text(sec, "title"),
            "cusip": _text(sec, "cusip").upper(),
            "isin": isin.upper(),
            "shares": _num(sec, "balance"),
            "value_usd": int(_num(sec, "valUSD")),
            "pct_val": _num(sec, "pctVal"),
        }
        sec.clear()
        while sec.getprevious() is not None:
            del sec.getparent()[0]
    del context


def ingest_nport(conn: sqlite3.Connection, cik: str, *,
                 institution_id: str | None = None,
                 max_filings: int | None = 1) -> dict:
    """Ingest NPORT-P portfolios for a CIK. Idempotent per accession."""
    today = date.today().isoformat()
    stats = {"filings": 0, "skipped": 0, "positions": 0}
    for filing in list_filings(cik, NPORT_FORMS, limit=max_filings):
        if conn.execute("SELECT 1 FROM filings WHERE accession = ?",
                        (filing.accession_number,)).fetchone():
            stats["skipped"] += 1
            continue
        url = f"{filing.directory_url}/primary_doc.xml"
        local = http.CACHE_DIR / "nport" / filing.accession_clean / "primary_doc.xml"
        try:
            http.download(url, local)
        except Exception as exc:
            logger.warning("NPORT %s download failed (%s) — will retry next run",
                           filing.accession_number, exc)
            stats["skipped"] += 1
            continue
        conn.execute(
            """INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                                    period_of_report, source_url, retrieval_date)
               VALUES (?,?,?,?,?,?,?,?)""",
            (filing.accession_number, filing.cik, institution_id, filing.form_type,
             filing.filing_date, filing.period_of_report, filing.directory_url, today))
        rows = [
            (filing.accession_number, p["issuer_name"], p["cusip"], p["title_class"],
             p["value_usd"], p["shares"], "SH", "", "", 0, 0, 0)
            for p in iter_positions(local)
        ]
        conn.executemany(
            """INSERT INTO holdings (accession, issuer_name, cusip, title_class, value_usd,
                                     shares, shares_type, put_call, discretion,
                                     voting_sole, voting_shared, voting_none)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        conn.commit()
        stats["filings"] += 1
        stats["positions"] += len(rows)
        logger.info("NPORT-P %s: %d positions", filing.accession_number, len(rows))
    return stats
