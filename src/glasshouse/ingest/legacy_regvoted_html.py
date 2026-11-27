"""Legacy (July 2022 - June 2023) N-PX votes in the "Registrant Voted" layout printed as HTML
tables (SEI for The Advisors' Inner Circle Fund III: GQG and other advisers' series).
legacy_format 'regvoted_html', promoted into `ledger.PROMOTED_LEGACY_FORMATS` on 2026-11-27
after a reviewer pass (fix: amendments HR6-HR8; a proposal split by a page break no longer
yields its tail as a proposal) and a 16-row hand sample against the filings. Contract:
docs/research/legacy-npx.md ("Registrant Voted" HTML-table layout, rules H1-H9 and
amendments HR1-HR8).

Two parsers written independently from that contract (`legacy_regvoted_html_cells`, an
html.parser tokenizer; `legacy_regvoted_html_rows`, regular expressions over the markup)
read each document and give rows in the text layout's value forms, so everything after them
is the text wrapper's (`legacy_regvoted.translate`, then `legacy_issueno`: agreement over
all 14 fields, `legacy_pe.guarded`, the per-filing gate, header-only fund mapping, validated
security ids). This layout prints three more forms, mapped first: proponent 'Issuer' ->
Management (the XML word for a management item), 'One Year' -> '1 Year' and 'Three Years'
-> '3 Years' (vote and recommendation). 'Did Not Vote', 'Do Not Vote', 'Take No Action' and
'Non-Voting' are not in the vocabulary and are dropped and counted, as in the text layout.

Detection: `legacy_iss.doc_format` returns 'regvoted_html' when the column header's words sit
in table cells. Ingest is opt-in under `--legacy-issueno`; report types LEGACY_REGVOTED_HTML /
LEGACY_REGVOTED_HTML_REJECTED.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys

from . import legacy_issueno, legacy_regvoted
from .edgar import Filing

LEGACY_FORMAT = "regvoted_html"
REPORT_OK = "LEGACY_REGVOTED_HTML"
REPORT_REJECTED = "LEGACY_REGVOTED_HTML_REJECTED"
MAX_DISAGREEMENT = legacy_issueno.MAX_DISAGREEMENT

_PARSER_NAMES = ("legacy_regvoted_html_cells", "legacy_regvoted_html_rows")

# printed in this layout only -> the text layout's printed form
EXTRA_FORMS = {"One Year": "1 Year", "Three Years": "3 Years"}
EXTRA_PROPONENT = {"Issuer": "Management"}


def _load_parsers():
    return tuple(importlib.import_module(f"{__package__}.{n}") for n in _PARSER_NAMES)


def __getattr__(name):          # PARSERS resolved on first use
    if name == "PARSERS":
        return _load_parsers()
    raise AttributeError(name)


def agreed(text: str, parsers=None) -> tuple[list[dict], dict]:
    return legacy_issueno.agreed(text, parsers or _load_parsers())


def translate(row: dict) -> dict:
    out = dict(row)
    out["vote"] = EXTRA_FORMS.get(row["vote"], row["vote"])
    out["rec"] = EXTRA_FORMS.get(row["rec"], row["rec"])
    out["proponent"] = EXTRA_PROPONENT.get(row["proponent"], row["proponent"])
    return legacy_regvoted.translate(out)


def to_vote_rows(rows: list[dict], smap: dict[str, str], aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None,
                 fallback=None) -> tuple[list[dict], dict]:
    return legacy_issueno.to_vote_rows([translate(r) for r in rows], smap, aliases, header_sids,
                                       legacy_format=LEGACY_FORMAT, fallback=fallback)


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None,
                  series_dataset: dict | None = None) -> int:
    return legacy_issueno.ingest_filing(conn, filing, institution_id, today, docs, hdr_text,
                                        aliases, layout=sys.modules[__name__],
                                        series_dataset=series_dataset)


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int | None:
    return legacy_issueno.ingest_filing_from_sources(conn, filing, institution_id, today,
                                                     layout=sys.modules[__name__])
