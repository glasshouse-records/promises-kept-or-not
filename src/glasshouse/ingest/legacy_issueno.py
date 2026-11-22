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

Rows land with `legacy_format = 'issueno'`, shares_voted NULL, category_type ''. 'issueno' is
NOT in `ledger.PROMOTED_LEGACY_FORMATS`: `NON_LEGACY_VOTE_SQL` excludes the rows until a human
promotes the format. Filing storage, the gate and `legacy_parse` stats (with parser_version)
are `legacy_pe.record_filing`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
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


def agreed(text: str, parsers=PARSERS) -> tuple[list[dict], dict]:
    """Rows both parsers produced identically (multiset intersection, in parser A's order),
    after the meeting-level and issuer-order guards, and the agreement stats."""
    rows_a = parsers[0].parse(text)
    rows_b = parsers[1].parse(text)
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
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only,
                 "disagreement_rate": (a_only + b_only) / max(1, n_agreed + a_only + b_only),
                 **guard_stats}


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
                 header_sids: set[str] | None = None) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts, plus drop counters."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"contest_rows_dropped": 0, "dropped_vote": 0, "dropped_date": 0,
            "dropped_sponsor": 0, "alias_not_in_header": 0, "policy_section_dropped": 0}
    for r in rows:
        sid, bad = legacy_iss._series_for(r["fund_heading"], smap, aliases, header_sids)
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
            "legacy_format": LEGACY_FORMAT,
            "for_against_management": FOR_AGAINST.get(r["for_against"]),
        })
    info["unmapped"] = dict(unmapped)
    return out, info


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None) -> int:
    """Parse every 'issueno' document of one filing, gate it, record it. One transaction
    (no network inside). Returns votes inserted."""
    smap = legacy_pe.series_map(hdr_text)
    fa = legacy_pe.filing_aliases(aliases, filing.cik)
    sids = legacy_pe.header_series_ids(hdr_text)
    parsed = []
    for name, text in sorted(docs.items()):
        if legacy_iss.doc_format(text) != LEGACY_FORMAT:
            continue
        rows, st = agreed(text)
        votes, info = to_vote_rows(rows, smap, fa, sids)
        info["funds_unmapped"] = info["unmapped"]
        parsed.append((name, len(re.findall(r"(?i)meeting\s+date", text)), st, votes, info))
        logger.info("%s %s: agreed=%d emitted=%d unmapped=%d contest=%d vocab=%d",
                    filing.accession_number, name, st["agreed"], len(votes),
                    sum(info["unmapped"].values()), info["contest_rows_dropped"],
                    info["dropped_vote"])
    return legacy_pe.record_filing(conn, filing, institution_id, today, parsed,
                                   REPORT_OK, REPORT_REJECTED)


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int | None:
    """Fetch (network/cache, no write lock held) then ingest one filing. Returns None,
    writing nothing, when the filing is not in the Issue No. layout."""
    docs, hdr = legacy_pe.load_filing_texts(filing)
    if legacy_iss.detect_format(docs) != LEGACY_FORMAT:
        return None
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, legacy_pe.load_aliases())
    logger.info("ingested %s %s: %d votes", REPORT_OK, filing.accession_number, n)
    return n
