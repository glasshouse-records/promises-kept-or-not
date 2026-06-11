"""SEC Form 13-F ingestion — quarterly institutional holdings.

Weakest finding class on its own (the index alibi applies to holdings),
but required for "who holds it" event alerts and value-weighted claims.
Parser logic carried from the predecessor project; values are full dollars
since the SEC's 2024 Form 13-F amendment.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from lxml import etree

from .. import http
from .edgar import Filing, filing_directory, list_filings

logger = logging.getLogger(__name__)

FORMS_13F = ["13F-HR", "13F-HR/A"]


def find_infotable_url(filing: Filing) -> str | None:
    """The holdings info-table XML inside the filing directory (not the
    cover primary_doc.xml, not the XSLT-rendered copies)."""
    for item in filing_directory(filing):
        name = item.get("name", "")
        low = name.lower()
        if not low.endswith(".xml") or "primary_doc" in low or "xslform" in low:
            continue
        return f"{filing.directory_url}/{name}"
    return None


def _text(el, localname: str) -> str:
    for child in el.iter():
        if etree.QName(child).localname == localname:
            return (child.text or "").strip()
    return ""


def _num(el, localname: str) -> float:
    t = _text(el, localname)
    try:
        return float(t.replace(",", "")) if t else 0.0
    except ValueError:
        return 0.0


def iter_holdings(xml_path: Path):
    """Stream holding rows from a 13-F info table."""
    context = etree.iterparse(str(xml_path), events=("end",), tag="{*}infoTable",
                              recover=True, huge_tree=True)
    for _event, info in context:
        yield {
            "issuer_name": _text(info, "nameOfIssuer"),
            "cusip": _text(info, "cusip").upper(),
            "title_class": _text(info, "titleOfClass"),
            "value_usd": int(_num(info, "value")),
            "shares": _num(info, "sshPrnamt"),
            "shares_type": _text(info, "sshPrnamtType") or "SH",
            "put_call": _text(info, "putCall"),
            "discretion": _text(info, "investmentDiscretion"),
            "voting_sole": int(_num(info, "Sole")),
            "voting_shared": int(_num(info, "Shared")),
            "voting_none": int(_num(info, "None")),
        }
        info.clear()
        while info.getprevious() is not None:
            del info.getparent()[0]
    del context


def ingest_13f(conn: sqlite3.Connection, cik: str, *, institution_id: str | None = None,
               max_filings: int | None = 1) -> dict:
    """Ingest 13-F holdings for a CIK. Idempotent per accession."""
    today = date.today().isoformat()
    stats = {"filings": 0, "skipped": 0, "holdings": 0}
    for filing in list_filings(cik, FORMS_13F, limit=max_filings):
        if conn.execute("SELECT 1 FROM filings WHERE accession = ?",
                        (filing.accession_number,)).fetchone():
            stats["skipped"] += 1
            continue
        url = find_infotable_url(filing)
        if not url:
            logger.warning("no info table XML in %s", filing.accession_number)
            continue
        conn.execute(
            """INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                                    period_of_report, source_url, retrieval_date)
               VALUES (?,?,?,?,?,?,?,?)""",
            (filing.accession_number, filing.cik, institution_id, filing.form_type,
             filing.filing_date, filing.period_of_report, filing.directory_url, today))
        local = http.CACHE_DIR / "13f" / filing.accession_clean / url.rsplit("/", 1)[-1]
        http.download(url, local)
        rows = [
            (filing.accession_number, h["issuer_name"], h["cusip"], h["title_class"],
             h["value_usd"], h["shares"], h["shares_type"], h["put_call"],
             h["discretion"], h["voting_sole"], h["voting_shared"], h["voting_none"])
            for h in iter_holdings(local)
        ]
        conn.executemany(
            """INSERT INTO holdings (accession, issuer_name, cusip, title_class, value_usd,
                                     shares, shares_type, put_call, discretion,
                                     voting_sole, voting_shared, voting_none)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        conn.commit()
        stats["filings"] += 1
        stats["holdings"] += len(rows)
        logger.info("13-F %s: %d holdings", filing.accession_number, len(rows))
    return stats
