"""SEC Form N-PX ingestion — proxy voting records, the spine of Glasshouse.

Votes are active choices: no "passive index" alibi. Facts validated against
live EDGAR on 2026-06-10 (see METHODOLOGY.md):

  - Vote tables are separate XML exhibits in the filing directory
    (e.g. BRDWLB_0001100663_2025.xml, 65–124 MB), NOT primary_doc.xml.
    Namespace: http://www.sec.gov/edgar/document/npxproxy/informationtable.
    Parsed with lxml iterparse — streaming, never regex, never full-DOM.
  - primary_doc.xml is the cover: reportType ("FUND NOTICE REPORT" = cover-
    only notice with zero votes → skip), series ids/names/LEIs (best
    entity-resolution key available), period of report.
  - One proxyTable may hold MULTIPLE voteRecord elements — all are parsed.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from lxml import etree

from .. import http, ledger
from .edgar import Filing, filing_directory, list_filings

logger = logging.getLogger(__name__)

NPX_FORMS = ["N-PX", "N-PX/A"]


# ── Cover page (primary_doc.xml) ─────────────────────────────────────────────

@dataclass
class NpxCover:
    report_type: str = ""
    period_of_report: str = ""
    reporting_person: str = ""
    series: list[dict] = field(default_factory=list)  # {series_id, name, lei}

    @property
    def is_notice_only(self) -> bool:
        return "NOTICE" in self.report_type.upper()


def _local(el: etree._Element) -> str:
    # Comments and processing instructions have non-string tags; QName()
    # raises on them. Vanguard covers contain XML comments (2026-06-11).
    if not isinstance(el.tag, str):
        return ""
    return etree.QName(el).localname


def parse_cover(xml_bytes: bytes) -> NpxCover:
    root = etree.fromstring(xml_bytes)
    cover = NpxCover()
    for el in root.iter():
        name = _local(el)
        text = (el.text or "").strip()
        if name == "reportType":
            cover.report_type = text
        elif name == "periodOfReport" and not cover.period_of_report:
            cover.period_of_report = text
        elif name == "seriesReports":
            entry = {"series_id": "", "name": "", "lei": ""}
            for child in el.iter():
                cname, ctext = _local(child), (child.text or "").strip()
                if cname == "idOfSeries":
                    entry["series_id"] = ctext
                elif cname == "nameOfSeries":
                    entry["name"] = ctext
                elif cname == "leiOfSeries":
                    entry["lei"] = ctext
            if entry["series_id"] or entry["name"]:
                cover.series.append(entry)
    for el in root.iter():
        if _local(el) == "reportingPerson":
            for child in el.iter():
                if _local(child) == "name":
                    cover.reporting_person = (child.text or "").strip()
                    break
            break
    return cover


# ── Vote table exhibit (streaming) ───────────────────────────────────────────

@dataclass
class VoteRow:
    issuer_name: str = ""
    cusip: str = ""
    isin: str = ""
    meeting_date: str = ""
    vote_description: str = ""
    category_type: str = ""
    vote_source: str = ""
    shares_on_loan: float = 0.0
    vote_series: str = ""
    how_voted: str = ""
    shares_voted: float = 0.0
    management_recommendation: str = ""


def _text_of(parent: etree._Element, localname: str) -> str:
    for el in parent.iter():
        if _local(el) == localname:
            return (el.text or "").strip()
    return ""


def _float_of(parent: etree._Element, localname: str) -> float:
    t = _text_of(parent, localname)
    try:
        return float(t.replace(",", "")) if t else 0.0
    except ValueError:
        return 0.0


def iter_vote_rows(xml_path: Path, max_tables: int | None = None) -> Iterator[VoteRow]:
    """Stream VoteRows from a vote-table exhibit without loading the DOM.

    Yields one row per voteRecord (a proxyTable with three voteRecords
    yields three rows). proxyTables with no voteRecord (e.g. notes-only)
    yield one row with empty vote fields so the proposal is still recorded.
    """
    n_tables = 0
    context = etree.iterparse(str(xml_path), events=("end",), tag="{*}proxyTable",
                              recover=True, huge_tree=True)
    for _event, table in context:
        base = VoteRow(
            issuer_name=_text_of(table, "issuerName"),
            cusip=_text_of(table, "cusip").upper(),
            isin=_text_of(table, "isin").upper(),
            meeting_date=_text_of(table, "meetingDate"),
            vote_description=_text_of(table, "voteDescription"),
            category_type=_text_of(table, "categoryType"),
            vote_source=_text_of(table, "voteSource"),
            shares_on_loan=_float_of(table, "sharesOnLoan"),
            vote_series=_text_of(table, "voteSeries"),
        )
        records = [el for el in table.iter() if _local(el) == "voteRecord"]
        if records:
            for rec in records:
                yield VoteRow(
                    **{**base.__dict__,
                       "how_voted": _text_of(rec, "howVoted"),
                       "shares_voted": _float_of(rec, "sharesVoted"),
                       "management_recommendation": _text_of(rec, "managementRecommendation")},
                )
        else:
            yield base

        # iterparse memory hygiene: clear the element and processed siblings
        table.clear()
        while table.getprevious() is not None:
            del table.getparent()[0]

        n_tables += 1
        if max_tables and n_tables >= max_tables:
            break
    del context


def find_vote_table_exhibits(filing: Filing) -> list[str]:
    """URLs of vote-table XML exhibits in the filing directory.

    Empty list ⇒ cover-only notice filing. The primary_doc and any
    XSLT-rendered copies are excluded.
    """
    urls = []
    for item in filing_directory(filing):
        name = item.get("name", "")
        if not name.lower().endswith(".xml"):
            continue
        if "primary_doc" in name.lower() or "xslform" in name.lower():
            continue
        urls.append(f"{filing.directory_url}/{name}")
    return urls


# ── Ledger ingestion ─────────────────────────────────────────────────────────

def ingest_npx(conn: sqlite3.Connection, cik: str, *,
               institution_id: str | None = None,
               max_filings: int | None = None,
               max_tables: int | None = None,
               legacy: bool = False) -> dict:
    """Ingest N-PX filings for a CIK into the evidence ledger.

    Idempotent: filings already in the ledger are skipped. Cover-only
    notice filings are recorded as filings (report_type) but yield no votes.

    legacy=True (opt-in): for pre-2024 filings that have no structured cover,
    parse the legacy HTML vote tables (ISS/Broadridge format) instead of
    skipping. Those votes are tagged vote_source='legacy_html' and the filing
    report_type is 'LEGACY_PARSED', so they stay out of the public release
    until validated. Default (False) preserves the safe skip behavior.
    """
    today = date.today().isoformat()
    stats = {"filings": 0, "skipped": 0, "notices": 0, "votes": 0, "failed": 0}

    filings = list_filings(cik, NPX_FORMS, limit=max_filings)
    for filing in filings:
        exists = conn.execute(
            "SELECT report_type FROM filings WHERE accession = ?", (filing.accession_number,)
        ).fetchone()
        if exists:
            # legacy mode may upgrade a filing previously skipped as
            # LEGACY_NO_COVER (no votes attached) — reprocess it. Otherwise skip.
            if legacy and exists[0] == "LEGACY_NO_COVER":
                conn.execute("DELETE FROM filings WHERE accession = ?",
                             (filing.accession_number,))
                conn.commit()
            else:
                stats["skipped"] += 1
                continue

        try:
            cover_bytes = http.get(f"{filing.directory_url}/primary_doc.xml").content
            cover = parse_cover(cover_bytes)
        except Exception as exc:
            # Only a definitive 404 means a pre-2024 legacy filing (no
            # primary_doc.xml cover existed before the vote-level XML rule).
            # Anything else — throttling, network, parse — must NOT be
            # recorded, so the filing is retried on the next run. (Found
            # 2026-06-11: SEC 403s during parallel ingests permanently
            # mislabeled three live Vanguard filings as legacy.)
            import requests as _rq
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if not (isinstance(exc, _rq.HTTPError) and status == 404):
                logger.warning("transient cover failure for %s (%s) — will retry next run",
                               filing.accession_number, exc)
                stats["skipped"] += 1
                continue
            if legacy:
                n = _ingest_legacy_filing(conn, filing, institution_id, today, stats)
                if n:
                    stats["filings"] += 1
                    logger.info("ingested LEGACY %s: %d votes", filing.accession_number, n)
                else:
                    stats["skipped"] += 1
                continue
            logger.warning("no cover for %s (404) — recording as legacy, skipping votes",
                           filing.accession_number)
            conn.execute(
                """INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                                        period_of_report, report_type, source_url, retrieval_date)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (filing.accession_number, filing.cik, institution_id, filing.form_type,
                 filing.filing_date, filing.period_of_report, "LEGACY_NO_COVER",
                 filing.directory_url, today),
            )
            conn.commit()
            stats["skipped"] += 1
            continue

        # Network first, ledger second: every exhibit is on disk before the
        # filing is recorded, so no write lock is held across a download and a
        # filing is never left in the ledger with part of its votes.
        locals_: list[Path] = []
        if not cover.is_notice_only:
            try:
                for url in find_vote_table_exhibits(filing):
                    local = (http.CACHE_DIR / "npx" / filing.accession_clean
                             / url.rsplit("/", 1)[-1])
                    http.download(url, local)
                    locals_.append(local)
            except Exception as exc:
                logger.warning("could not fetch exhibits for %s (%s) — not recorded, "
                               "will retry next run", filing.accession_number, exc)
                stats["failed"] += 1
                continue

        try:
            conn.execute(
                """INSERT INTO filings (accession, cik, institution_id, form_type,
                                        filing_date, period_of_report, report_type,
                                        source_url, retrieval_date)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (filing.accession_number, filing.cik, institution_id, filing.form_type,
                 filing.filing_date, cover.period_of_report or filing.period_of_report,
                 cover.report_type, filing.directory_url, today),
            )
            for sr in cover.series:
                conn.execute(
                    "INSERT OR IGNORE INTO fund_series (series_id, accession, name, lei) "
                    "VALUES (?,?,?,?)",
                    (sr["series_id"], filing.accession_number, sr["name"], sr["lei"]),
                )
            n_votes = 0
            for local in locals_:
                rows = []
                for row in iter_vote_rows(local, max_tables=max_tables):
                    rows.append((
                        filing.accession_number, row.issuer_name, row.cusip, row.isin,
                        row.meeting_date, row.vote_description, row.category_type,
                        row.vote_source, row.shares_on_loan, row.vote_series,
                        row.how_voted, row.shares_voted, row.management_recommendation,
                    ))
                    if len(rows) >= 5000:
                        conn.executemany(_VOTE_INSERT, rows)
                        n_votes += len(rows)
                        rows = []
                if rows:
                    conn.executemany(_VOTE_INSERT, rows)
                    n_votes += len(rows)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.warning("could not ingest %s (%s) — rolled back, will retry next run",
                           filing.accession_number, exc)
            stats["failed"] += 1
            continue

        if cover.is_notice_only:
            stats["notices"] += 1
            continue
        stats["votes"] += n_votes
        stats["filings"] += 1
        logger.info("ingested %s (%s): %d votes so far",
                    filing.accession_number, cover.report_type, stats["votes"])

    conn.commit()
    if stats["filings"] or stats["notices"]:
        # After the network loop, in its own transaction: new rows must never
        # sit unflagged (a repeated share class would be counted twice).
        ledger.dedupe_votes(conn, ciks=sorted({f.cik for f in filings}))
    return stats


_VOTE_INSERT = """INSERT INTO votes
    (accession, issuer_name, cusip, isin, meeting_date, vote_description,
     category_type, vote_source, shares_on_loan, vote_series, how_voted,
     shares_voted, management_recommendation)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _ingest_legacy_filing(conn: sqlite3.Connection, filing: Filing,
                          institution_id: str | None, today: str, stats: dict) -> int:
    """Parse a pre-2024 legacy HTML N-PX filing. Returns votes inserted.

    Votes are tagged vote_source='legacy_html' (see npx_legacy) and the filing
    is recorded as LEGACY_PARSED so the public release can quarantine them.
    """
    from .npx_legacy import find_legacy_vote_docs, iter_legacy_vote_rows

    conn.execute(
        """INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                                period_of_report, report_type, source_url, retrieval_date)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (filing.accession_number, filing.cik, institution_id, filing.form_type,
         filing.filing_date, filing.period_of_report, "LEGACY_PARSED",
         filing.directory_url, today),
    )
    inserted = 0
    for url in find_legacy_vote_docs(filing):
        try:
            content = http.get(url).content
        except Exception as exc:  # one bad doc must not abort the filing
            logger.warning("legacy doc fetch failed %s (%s)", url, exc)
            continue
        if b"MEETING DATE" not in content.upper():
            continue  # not a vote document (cover/notes page)
        rows = []
        for row in iter_legacy_vote_rows(content):
            rows.append((
                filing.accession_number, row.issuer_name, row.cusip, row.isin,
                row.meeting_date, row.vote_description, row.category_type,
                row.vote_source, row.shares_on_loan, row.vote_series,
                row.how_voted, row.shares_voted, row.management_recommendation,
            ))
            if len(rows) >= 5000:
                conn.executemany(_VOTE_INSERT, rows)
                inserted += len(rows)
                rows = []
        if rows:
            conn.executemany(_VOTE_INSERT, rows)
            inserted += len(rows)
    if inserted == 0:
        # parser couldn't handle this doc's format — leave it retryable rather
        # than claiming it's parsed, so an improved parser can revisit it.
        conn.execute("UPDATE filings SET report_type='LEGACY_NO_COVER' WHERE accession=?",
                     (filing.accession_number,))
    conn.commit()
    stats["votes"] += inserted
    return inserted
