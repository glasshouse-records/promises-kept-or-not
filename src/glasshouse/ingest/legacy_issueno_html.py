"""Legacy (July 2022 - June 2023) N-PX votes in the "Issue No." layout exported as HTML
tables (Putnam, Neuberger Berman). QUARANTINED (legacy_format 'issueno_html', not in
`ledger.PROMOTED_LEGACY_FORMATS`) until a reviewer pass and a hand sample.

The fields are those of the text layout (`legacy_issueno`); only the reading differs. Two
parsers written independently from one contract (`legacy_issueno_html_cells`, a tokenizer
state machine; `legacy_issueno_html_rows`, row splitting) read each document; everything
after them is `legacy_issueno`'s, unchanged: multiset agreement over all 14 fields,
`legacy_pe.guarded`, the per-filing gate, Voted-only meetings, contests dropped, the closed
vote and proposer vocabularies, validated security ids, fund -> series only through the
filing's SGML header and the reviewed aliases.

Day-first dates: the same guard as the text layout, run on the table's text (tags removed,
entities decoded), so a value row 'CUSIP 901384107 | 13/06/2023' rejects the document whole.

Detection: `legacy_iss.doc_format` returns 'issueno_html' when the column labels sit in
consecutive table cells. Ingest is opt-in under the same `--legacy-issueno` flag; report
types LEGACY_ISSUENO_HTML / LEGACY_ISSUENO_HTML_REJECTED.
"""

from __future__ import annotations

import html
import re
import sqlite3
import sys

from . import legacy_issueno, legacy_issueno_html_cells, legacy_issueno_html_rows
from .edgar import Filing

LEGACY_FORMAT = "issueno_html"
REPORT_OK = "LEGACY_ISSUENO_HTML"
REPORT_REJECTED = "LEGACY_ISSUENO_HTML_REJECTED"
PARSERS = (legacy_issueno_html_cells, legacy_issueno_html_rows)
MAX_DISAGREEMENT = legacy_issueno.MAX_DISAGREEMENT

_TAG = re.compile(r"<[^>]*>")


def day_first_dates(text: str) -> int:
    """`legacy_issueno.day_first_dates` over the document's text with tags removed."""
    return legacy_issueno.day_first_dates(html.unescape(_TAG.sub(" ", text)))


def agreed(text: str, parsers=None) -> tuple[list[dict], dict]:
    return legacy_issueno.agreed(text, parsers or PARSERS, day_first=day_first_dates)


def to_vote_rows(rows: list[dict], smap: dict[str, str], aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None) -> tuple[list[dict], dict]:
    return legacy_issueno.to_vote_rows(rows, smap, aliases, header_sids,
                                       legacy_format=LEGACY_FORMAT)


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None) -> int:
    return legacy_issueno.ingest_filing(conn, filing, institution_id, today, docs, hdr_text,
                                        aliases, layout=sys.modules[__name__])


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int | None:
    return legacy_issueno.ingest_filing_from_sources(conn, filing, institution_id, today,
                                                     layout=sys.modules[__name__])
