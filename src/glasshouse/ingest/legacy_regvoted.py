"""Legacy (July 2022 - June 2023) N-PX votes in the "Registrant Voted" text layout (Global X:
`Proposal  Proposed by  Mgt. Position  Registrant Voted`, inside <pre> blocks). legacy_format
'regvoted', promoted into `ledger.PROMOTED_LEGACY_FORMATS` on 2026-11-27 after a reviewer pass
(fix: contract amendment R5, a bare Meeting Date inherits an issuer only after a column line or
page header) and hand samples against the filing (18 rows field by field, 6 funds of one split vote). Contract: docs/research/legacy-npx.md ("Registrant Voted" text layout).

Two parsers written independently from that contract (`legacy_regvoted_blocks`,
`legacy_regvoted_lines`) read each document; everything after them is `legacy_issueno`'s,
unchanged (multiset agreement over all 14 fields, `legacy_pe.guarded`, the per-filing gate,
contests dropped, validated security ids, fund -> series only through the SGML header and the
reviewed aliases). Only the printed vocabulary differs, so rows are translated to the Issue No.
forms before `legacy_issueno.to_vote_rows` sees them: 'Withheld' -> Withhold, Management -> Mgmt, Shareholder -> ShrHoldr, a vote is by construction 'Voted - ...' so
the meeting status is Voted, the bare printed security id is typed by its shape (9 characters
CUSIP, 12 ISIN; the shared check-digit validation still decides), and the contract's MM/DD/YYYY date becomes the ISO form the shared
code reads. Anything outside the closed vocabularies becomes '' and so is dropped. 'Take No
Action' is dropped and counted, as in legacy_iss (vote) and legacy_issueno (status): nothing was
cast, and Global X prints it on "Non-Voting Meeting Note" / "Non-Voting Agenda Item" rows.

Detection: `legacy_iss.doc_format` returns 'regvoted' on the column header. Ingest is opt-in
under the `--legacy-issueno` flag; report types LEGACY_REGVOTED / LEGACY_REGVOTED_REJECTED.
"""

from __future__ import annotations

import importlib
import re
import sqlite3
import sys

from . import legacy_issueno
from .edgar import Filing

LEGACY_FORMAT = "regvoted"
REPORT_OK = "LEGACY_REGVOTED"
REPORT_REJECTED = "LEGACY_REGVOTED_REJECTED"
MAX_DISAGREEMENT = legacy_issueno.MAX_DISAGREEMENT

_PARSER_NAMES = ("legacy_regvoted_blocks", "legacy_regvoted_lines")

# printed form -> the form legacy_issueno's closed vocabularies know
# (the closed set of printed forms; anything else is not in the dict and is dropped)
VOTE_FORMS = {"For": "For", "Against": "Against", "Abstain": "Abstain", "Withheld": "Withhold",
              "Withhold": "Withhold", "1 Year": "1 Year", "2 Years": "2 Years",
              "3 Years": "3 Years"}
PROPONENT_FORMS = {"Management": "Mgmt", "Shareholder": "ShrHoldr"}
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _load_parsers():
    return tuple(importlib.import_module(f"{__package__}.{n}") for n in _PARSER_NAMES)


def __getattr__(name):          # PARSERS resolved on first use: the package imports without them
    if name == "PARSERS":
        return _load_parsers()
    raise AttributeError(name)


def agreed(text: str, parsers=None) -> tuple[list[dict], dict]:
    return legacy_issueno.agreed(text, parsers or _load_parsers())


def _typed_id(raw: str) -> str:
    """The bare printed id as '<TYPE> <ID>' for the shared validator: 9 characters -> CUSIP,
    12 -> ISIN, by shape only; the check digits there still decide (never repaired)."""
    v = (raw or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]+", v):
        return ""
    return {9: f"CUSIP {v}", 12: f"ISIN {v}"}.get(len(v), "")


def translate(row: dict) -> dict:
    """One parsed row in the Issue No. forms; unknown values become '' (dropped downstream)."""
    out = dict(row)
    out["vote"] = VOTE_FORMS.get(row["vote"], "")
    out["rec"] = VOTE_FORMS.get(row["rec"], "")
    out["proponent"] = PROPONENT_FORMS.get(row["proponent"], "")
    out["meeting_status"] = "Voted"
    out["security_id"] = _typed_id(row["security_id"])
    m = _DATE.fullmatch(row["meeting_date"] or "")
    if m:
        out["meeting_date"] = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
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
