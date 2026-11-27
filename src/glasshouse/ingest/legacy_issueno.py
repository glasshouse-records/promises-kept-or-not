"""Legacy (July 2022 - June 2023) N-PX votes in the "Issue No." text layout (Schwab, VanEck,
Hartford/Wellington HTML-wrapped text, Russell's SGML-table variant). QUARANTINED.

Mirrors `legacy_iss`. Two parsers written independently from one contract
(`legacy_issueno_blocks`, `legacy_issueno_lines`) read each document; only rows BOTH produce
identically over all 14 fields (`KEYS`, multiset intersection) are kept, then
`legacy_pe.guarded` (keyed on fund_heading) drops every meeting with a disputed row and applies
the issuer-order guard. A filing is rejected outright (report_type LEGACY_ISSUENO_REJECTED,
nothing inserted) when disagreement > `MAX_DISAGREEMENT`. Stats = those of `legacy_iss.agreed`.

Detection: the column header `Issue No. Description Proponent Mgmt Rec Vote Cast` (any case,
any whitespace); `legacy_iss.doc_format` returns "issueno", so `detect_format` stays the single
entry point and a mixed filing is None. The ingest is opt-in (`--legacy-issueno`).

Fund -> series only through the filing's own SGML header and the reviewed aliases
(`legacy_iss.series_for`); unmapped headings are dropped and counted; voting-policy sections
(`legacy_iss.is_policy_section`) are dropped. No fuzzy matching.

Dates: both parsers read MM/DD/YYYY. A document whose meeting value lines hold any date
with a first part above 12 (so not month-first) is rejected whole (`day_first_dates`,
disagreement forced to 1): a DD/MM filer's days 1-12 would otherwise be misread by both.

Meeting status: only meetings printed 'Voted' (any case) give votes; every row of an
'Unvoted' or 'Take No Action' meeting is dropped and counted (`dropped_status`): the vote
column of an unvoted meeting holds instructions that were never cast.

Proxy contests: EVERY row of a meeting whose meeting_type contains "contest" (any case) is
dropped and counted (`contest_rows_dropped`).

Vote vocabulary (printed -> stored `how_voted`): For/FOR -> FOR, Against -> AGAINST,
Abstain -> ABSTAIN, Withhold -> WITHHOLD, 1 Year -> 1 YEAR, 2 Years -> 2 YEARS,
3 Years -> 3 YEARS, TNA -> TNA. Anything else (N/A, Echo Vote ...) is dropped and counted
(`dropped_vote`). Nothing is guessed.

Proposer (`vote_source`): Mgmt/MGMT -> ISSUER, ShrHoldr -> SECURITY HOLDER; any other
proponent (N/A) drops the row (`dropped_sponsor`).

`management_recommendation` has the XML meaning (`legacy_iss.with_management` of the mapped
recommendation and mapped vote; N/A -> ''). `for_against_management` is the filer's own
column: For/FOR -> 'For', Against -> 'Against', N/A -> NULL (the column ProxyEdge fills).

Security id is printed '<TYPE> <ID>': CUSIP and CINS -> `cusip` only if `legacy_pe.cusip_valid`;
ISIN -> `isin` only if `legacy_pe.isin_valid`; SEDOL and invalid values -> ''. Never repaired.

Rows land with `legacy_format = 'issueno'`, shares_voted NULL, category_type ''. 'issueno' was
promoted into `ledger.PROMOTED_LEGACY_FORMATS` on 2026-11-23 after a reviewer pass (fixes
e06dc99: unvoted meetings, dates) and a hand sample of stored rows against the filings. Filing storage, the gate and `legacy_parse` stats (with parser_version)
are `legacy_pe.record_filing`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
from collections import Counter

from . import legacy_iss, legacy_issueno_blocks, legacy_issueno_lines, legacy_pe
from .edgar import Filing

logger = logging.getLogger(__name__)

KEYS = ("fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
        "meeting_status", "meeting_type", "country", "proposal_id", "proposal_text",
        "proponent", "rec", "vote", "for_against")
MAX_DISAGREEMENT = legacy_pe.MAX_DISAGREEMENT
LEGACY_FORMAT = "issueno"
REPORT_OK = "LEGACY_ISSUENO"
REPORT_REJECTED = "LEGACY_ISSUENO_REJECTED"
PARSERS = (legacy_issueno_blocks, legacy_issueno_lines)

HOW_VOTED = {
    "For": "FOR", "FOR": "FOR", "Against": "AGAINST", "Abstain": "ABSTAIN",
    "Withhold": "WITHHOLD", "1 Year": "1 YEAR", "2 Years": "2 YEARS",
    "3 Years": "3 YEARS", "TNA": "TNA",
}
VOTE_SOURCE = {"Mgmt": "ISSUER", "MGMT": "ISSUER", "ShrHoldr": "SECURITY HOLDER"}
FOR_AGAINST = {"For": "For", "FOR": "For", "Against": "Against"}

is_issueno = legacy_iss.is_issueno
is_candidate = legacy_pe.is_candidate


def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEYS)


# A meeting's value line carries the security id ('CUSIP 88579Y101') and the meeting date.
_VALUE_LINE_DATE = re.compile(r"(?i)\b(?:CUSIP|CINS|ISIN|SEDOL)\s+\S+\s+(\d{1,2})/\d{1,2}/\d{4}\b")


def day_first_dates(text: str) -> int:
    """Meeting dates (value lines only) that cannot be month-first: first part > 12. Both
    parsers read MM/DD, so a DD/MM filer would be misread identically by both for days 1-12;
    one such date condemns the whole document."""
    return sum(1 for m in _VALUE_LINE_DATE.finditer(text) if int(m.group(1)) > 12)


def agreed(text: str, parsers=PARSERS, day_first=None) -> tuple[list[dict], dict]:
    """Rows both parsers produced identically (multiset intersection, in parser A's order),
    after the meeting-level and issuer-order guards, and the agreement stats. `day_first`
    counts the document's day-first meeting dates (default: `day_first_dates` on the text)."""
    rows_a = parsers[0].parse(text)
    rows_b = parsers[1].parse(text)
    n_day_first = (day_first or day_first_dates)(text)
    ca, cb = Counter(map(_key, rows_a)), Counter(map(_key, rows_b))
    common = ca & cb
    left = Counter(common)
    out = []
    for r in rows_a:
        k = _key(r)
        if left[k] > 0:
            left[k] -= 1
            out.append(r)
    n_agreed = sum(common.values())
    a_only, b_only = sum((ca - cb).values()), sum((cb - ca).values())
    out, guard_stats = legacy_pe.guarded(out, rows_a, rows_b, ca, cb, "fund_heading", _key)
    rate = (a_only + b_only) / max(1, n_agreed + a_only + b_only)
    if n_day_first:            # the gate rejects the filing: nothing from this document ships
        out, rate = [], 1.0
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only, "disagreement_rate": rate,
                 "day_first_dates": n_day_first, **guard_stats}


def _security_id(raw: str) -> tuple[str, str]:
    """(cusip, isin) from '<TYPE> <ID>'; validated, never repaired."""
    parts = (raw or "").split()
    if len(parts) != 2:
        return "", ""
    kind, value = parts[0].upper(), parts[1].upper()
    if kind in ("CUSIP", "CINS"):
        return (value, "") if legacy_pe.cusip_valid(value) else ("", "")
    if kind == "ISIN" and legacy_pe.isin_valid(value):
        inner = value[2:11]
        return (inner if value[:2] in ("US", "CA") and legacy_pe.cusip_valid(inner) else ""), value
    return "", ""


def to_vote_rows(rows: list[dict], smap: dict[str, str],
                 aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None,
                 legacy_format: str = LEGACY_FORMAT,
                 fallback=None) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts (tagged `legacy_format`), plus drop counters."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"contest_rows_dropped": 0, "dropped_vote": 0, "dropped_date": 0,
            "dropped_sponsor": 0, "alias_not_in_header": 0, "policy_section_dropped": 0,
            "dropped_status": 0}
    for r in rows:
        sid, bad = legacy_iss._series_for(r["fund_heading"], smap, aliases, header_sids,
                                       fallback, info)
        info["alias_not_in_header"] += bad
        if sid is None and legacy_iss.is_policy_section(r["fund_heading"]):
            info["policy_section_dropped"] += 1
            continue
        if sid is None:
            unmapped[r["fund_heading"]] += 1
            continue
        if "contest" in (r.get("meeting_type") or "").lower():
            info["contest_rows_dropped"] += 1
            continue
        if (r.get("meeting_status") or "").strip().lower() != "voted":
            info["dropped_status"] += 1      # 'Unvoted', 'Take No Action': nothing was cast
            continue
        source = VOTE_SOURCE.get(r["proponent"])
        if source is None:
            info["dropped_sponsor"] += 1
            continue
        how = HOW_VOTED.get(r["vote"])
        if how is None:
            info["dropped_vote"] += 1
            continue
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", r["meeting_date"])
        if not m:
            info["dropped_date"] += 1
            continue
        cusip, isin = _security_id(r["security_id"])
        out.append({
            "issuer_name": r["issuer_name"], "cusip": cusip, "isin": isin,
            "meeting_date": f"{m.group(2)}/{m.group(3)}/{m.group(1)}",
            "vote_description": r["proposal_text"], "category_type": "",
            "vote_source": source, "shares_on_loan": None, "vote_series": sid,
            "how_voted": how, "shares_voted": None,
            "management_recommendation": legacy_iss.with_management(
                HOW_VOTED.get(r["rec"], ""), how),
            "legacy_format": legacy_format,
            "for_against_management": FOR_AGAINST.get(r["for_against"]),
        })
    info["unmapped"] = dict(unmapped)
    return out, info


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None, layout=None,
                  series_dataset: dict | None = None) -> int:
    """Parse every document of one filing in this layout, gate it, record it. One
    transaction (no network inside). Returns votes inserted. `layout` = a module with
    LEGACY_FORMAT, REPORT_OK, REPORT_REJECTED, agreed and to_vote_rows (default: this one;
    legacy_issueno_html passes itself)."""
    layout = layout or sys.modules[__name__]
    smap = legacy_pe.series_map(hdr_text)
    fa = legacy_pe.filing_aliases(aliases, filing.cik)
    sids = legacy_pe.header_series_ids(hdr_text)
    fb = legacy_pe.build_fallback(series_dataset, filing.cik, hdr_text)
    ag = [(name, text, *layout.agreed(text)) for name, text in sorted(docs.items())
          if legacy_iss.doc_format(text) == layout.LEGACY_FORMAT]
    single = legacy_pe.single_fund_map(
        hdr_text, (r["fund_heading"] for _, _, rows, _ in ag for r in rows))
    smap = {**smap, **single}
    parsed = []
    for name, text, rows, st in ag:
        votes, info = layout.to_vote_rows(rows, smap, fa, sids, fallback=fb)
        legacy_pe.note_single_fund(info, single, (r["fund_heading"] for r in rows))
        info["funds_unmapped"] = info["unmapped"]
        parsed.append((name, len(re.findall(r"(?i)meeting\s+date", text)), st, votes, info))
        logger.info("%s %s: agreed=%d emitted=%d unmapped=%d contest=%d vocab=%d",
                    filing.accession_number, name, st["agreed"], len(votes),
                    sum(info["unmapped"].values()), info["contest_rows_dropped"],
                    info["dropped_vote"])
    return legacy_pe.record_filing(conn, filing, institution_id, today, parsed,
                                   layout.REPORT_OK, layout.REPORT_REJECTED)


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str,
                               layout=None) -> int | None:
    """Fetch (network/cache, no write lock held) then ingest one filing. Returns None,
    writing nothing, when the filing is not in this layout."""
    layout = layout or sys.modules[__name__]
    docs, hdr = legacy_pe.load_filing_texts(filing)
    if legacy_iss.detect_format(docs) != layout.LEGACY_FORMAT:
        return None
    from . import sec_series
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, legacy_pe.load_aliases(),
                      layout=layout, series_dataset=sec_series.load_dataset())
    logger.info("ingested %s %s: %d votes", layout.REPORT_OK, filing.accession_number, n)
    return n
