"""Legacy (July 2022 - June 2023) N-PX votes in Dodge & Cox's table: one N-PX per fund, per
meeting an issuer paragraph, a header table (Ticker, Security ID, Meeting Date, Meeting
Type, Record Date) and a proposals table `# | Proposal | Mgt Rec | Vote Cast | Sponsor`.
legacy_format 'dodgecox', promoted into `ledger.PROMOTED_LEGACY_FORMATS` on 2026-11-27 after a
reviewer pass (no blockers) and a 12-row hand sample. Contract: docs/research/legacy-npx.md ("Contract: Dodge &
Cox table", rules D1-D9).

Two parsers written independently from that contract (`legacy_dodgecox_dom`, an html.parser
event walker; `legacy_dodgecox_rows`, regular expressions over the markup) give rows in the
printed forms; this wrapper maps them to the Issue No. forms and everything after is
`legacy_issueno`'s: agreement over all 14 fields, `legacy_pe.guarded`, the per-filing gate,
header-only fund mapping, validated security ids. Forms: Management/Shareholder ->
Mgmt/ShrHoldr; One Year/Three Years -> 1 Year/3 Years; 'None' and 'Did Not Vote' votes map
to '' and are dropped and counted (a rec of 'None' leaves the recommendation empty); the
bare security id is typed by length (9 CUSIP, 12 ISIN) and check-digit validated, never
repaired; meeting_status is 'Voted' (every printed meeting is a voted one).

Detection: `legacy_iss.doc_format` returns 'dodgecox' when the proposals column header's
labels sit in consecutive table cells. Ingest is opt-in under `--legacy-issueno`; report
types LEGACY_DODGECOX / LEGACY_DODGECOX_REJECTED.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys

from . import legacy_issueno, legacy_regvoted
from .edgar import Filing

LEGACY_FORMAT = "dodgecox"
REPORT_OK = "LEGACY_DODGECOX"
REPORT_REJECTED = "LEGACY_DODGECOX_REJECTED"
MAX_DISAGREEMENT = legacy_issueno.MAX_DISAGREEMENT

_PARSER_NAMES = ("legacy_dodgecox_dom", "legacy_dodgecox_rows")

VOTE_FORMS = {"For": "For", "Against": "Against", "Abstain": "Abstain",
              "One Year": "1 Year", "Three Years": "3 Years"}
PROPONENT_FORMS = {"Management": "Mgmt", "Shareholder": "ShrHoldr"}


def _load_parsers():
    return tuple(importlib.import_module(f"{__package__}.{n}") for n in _PARSER_NAMES)


def __getattr__(name):          # PARSERS resolved on first use
    if name == "PARSERS":
        return _load_parsers()
    raise AttributeError(name)


def agreed(text: str, parsers=None) -> tuple[list[dict], dict]:
    # dates are printed 'JAN 17, 2023' (month named): the day-first check does not apply
    return legacy_issueno.agreed(text, parsers or _load_parsers(), day_first=lambda _t: 0)


def translate(row: dict) -> dict:
    """One parsed row in the Issue No. forms; unknown values become '' (dropped downstream)."""
    out = dict(row)
    out["vote"] = VOTE_FORMS.get(row["vote"], "")
    out["rec"] = VOTE_FORMS.get(row["rec"], "")
    out["proponent"] = PROPONENT_FORMS.get(row["proponent"], "")
    out["meeting_status"] = "Voted"
    out["security_id"] = legacy_regvoted._typed_id(row["security_id"])
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
