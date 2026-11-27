"""Legacy (July 2022 - June 2023) N-PX votes in Federated Hermes' flat table: one HTML table
row per vote, read by header label (Issuer Name ... Vote Cast, Fund Name[, Logical Ballot
Status]). legacy_format 'fedflat', promoted into `ledger.PROMOTED_LEGACY_FORMATS` on 2026-11-27 after
a reviewer pass (no blockers), the proposal_number fix and a 12-row hand sample. Contract: docs/research/legacy-npx.md ("Contract:
Federated flat table", rules F1-F6).

Two parsers written independently from that contract (`legacy_fedflat_cells`, an
html.parser tokenizer; `legacy_fedflat_rows`, regular expressions over the markup) give rows
already in Issue No. shape (ISO meeting date, '<CUSIP|CINS> <id>', status); this wrapper maps
the printed vocabulary to the Issue No. forms and everything after is `legacy_issueno`'s:
agreement over all 14 fields, `legacy_pe.guarded`, the per-filing gate, header-only fund
mapping, validated security ids. Forms: proponent 'Management'/'Shareholder' -> Mgmt/ShrHoldr;
'One Year'/'Three Years' -> '1 Year'/'3 Years' (vote and recommendation). 'TNA', 'Do Not
Vote', 'N/A' (vote or proponent) and rec 'None' are not cast / not stated and map to '', so
the row is dropped and counted (a rec of '' only leaves the recommendation empty).

Detection: `legacy_iss.doc_format` returns 'fedflat' when the column header's labels sit in
consecutive table cells. Ingest is opt-in under `--legacy-issueno`; report types
LEGACY_FEDFLAT / LEGACY_FEDFLAT_REJECTED.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys

from . import legacy_iss, legacy_issueno
from .edgar import Filing

LEGACY_FORMAT = "fedflat"
REPORT_OK = "LEGACY_FEDFLAT"
REPORT_REJECTED = "LEGACY_FEDFLAT_REJECTED"
MAX_DISAGREEMENT = legacy_issueno.MAX_DISAGREEMENT

_PARSER_NAMES = ("legacy_fedflat_cells", "legacy_fedflat_rows")

VOTE_FORMS = {"For": "For", "Against": "Against", "Abstain": "Abstain",
              "Withhold": "Withhold", "1 Year": "1 Year", "2 Years": "2 Years",
              "3 Years": "3 Years", "One Year": "1 Year", "Three Years": "3 Years"}
PROPONENT_FORMS = {"Mgmt": "Mgmt", "Management": "Mgmt", "ShrHoldr": "ShrHoldr",
                   "Shareholder": "ShrHoldr"}

is_fedflat = legacy_iss.is_fedflat


def _load_parsers():
    return tuple(importlib.import_module(f"{__package__}.{n}") for n in _PARSER_NAMES)


def __getattr__(name):          # PARSERS resolved on first use
    if name == "PARSERS":
        return _load_parsers()
    raise AttributeError(name)


def agreed(text: str, parsers=None) -> tuple[list[dict], dict]:
    # day-first documents are rejected inside both parsers (F5); the Issue No. value-line
    # check does not apply to table cells. No issuer-order guard: the fund is a cell on
    # every row (0001623632-23-001146 prints its alphabetical runs in reverse page order).
    return legacy_issueno.agreed(text, parsers or _load_parsers(), day_first=lambda _t: 0,
                                 order_guard=False)


def translate(row: dict) -> dict:
    """One parsed row in the Issue No. forms; unknown values become '' (dropped downstream)."""
    out = dict(row)
    out["vote"] = VOTE_FORMS.get(row["vote"], "")
    out["rec"] = VOTE_FORMS.get(row["rec"], "")
    out["proponent"] = PROPONENT_FORMS.get(row["proponent"], "")
    return out


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
