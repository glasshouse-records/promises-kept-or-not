"""Legacy (July 2022 - June 2023) N-PX votes from ISS-style "FORM N-Px REPORT" text filings.

Mirrors `legacy_pe` (the ProxyEdge path). Two parsers written independently from one
contract (`legacy_iss_blocks`, `legacy_iss_lines`) read each document; only rows BOTH
produce identically over all 14 fields (multiset intersection) are kept, and a filing is
rejected outright (report_type LEGACY_ISS_REJECTED, nothing inserted) when they disagree
by more than `MAX_DISAGREEMENT` = (a_only + b_only) / (agreed + a_only + b_only).

Fund -> series. Only through the filing's own SGML header (`legacy_pe.series_map`): the
normalised fund heading must equal a normalised series name exactly; failing that, ONE
trailing " - SUFFIX" segment (subadviser / voting-policy label) is stripped and the match
retried. A name the header maps to two series is already removed by `series_map`, so it
never matches. No fuzzy matching, and the suffix is never used to derive an adviser (that
comes from config via series_id, as for XML rows). Unmatched headings are dropped and
counted per heading.

Proxy contests: every row with a card label or a "Diss Rec" column is dropped and counted
(`contest_rows_dropped`): the same proposal appears on two cards and the management
recommendation is undefined. Management recommendation is set only under "Mgt Rec", with
the vote mapping below; `for_against_management` stays NULL (ProxyEdge-only).

Vote vocabulary. XML rows in the ledger store the filer's words in mixed spellings (FOR,
AGAINST, WITHHOLD, ABSTAIN, ONE YEAR and 1 YEAR, DO NOT VOTE, 'Did Not Vote', TNA, 'No
Vote' ...). ISS value -> stored `how_voted` (same strings as `legacy_pe.HOW_VOTED`):
  For, FOR               -> FOR              (exact XML value)
  Against, AGAINST       -> AGAINST          (exact XML value)
  Abstain                -> ABSTAIN          (exact XML value)
  Withhold, Withheld     -> WITHHOLD         (same meaning; XML value)
  1 Year, One Year       -> 1 YEAR           (XML has both ONE YEAR and 1 YEAR; as legacy_pe)
  2 Years, Two Years     -> 2 YEARS          (as above)
  3 Years, Three Years   -> 3 YEARS          (as above)
  Do Not Vote            -> DO NOT VOTE      (XML value)
  Did Not Vote           -> Did Not Vote     (XML value as filed; not merged with Do Not Vote)
  TNA                    -> TNA              (XML stores the literal TNA)
  No Vote                -> No Vote          (XML value as filed)
Dropped and counted (`dropped_vote`): None (no vote word, XML 'NONE' is a different
filer-specific state), N/A (not a vote), Take No Action (the brief withholds it from the
closed set: the XML spellings of it are four different strings and no single one is the
obvious counterpart). Nothing is guessed.

Sponsor: Management -> ISSUER, Shareholder -> SECURITY HOLDER (the proposer, as legacy_pe).

Rows land with `legacy_format = 'iss_text'` and `shares_voted` NULL (the format has no
share counts), quarantined by `ledger.NON_LEGACY_VOTE_SQL` until a human promotes them.
Filing storage, the gate and `legacy_parse` stats are `legacy_pe.record_filing`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter

from . import legacy_iss_blocks, legacy_iss_lines, legacy_pe
from .edgar import Filing

logger = logging.getLogger(__name__)

KEYS = ("fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
        "meeting_type", "record_date", "rec_label", "card_label", "proposal_id",
        "proposal_text", "rec", "vote", "sponsor")
MAX_DISAGREEMENT = legacy_pe.MAX_DISAGREEMENT
PERIOD = legacy_pe.PERIOD
REPORT_OK = "LEGACY_ISS"
REPORT_REJECTED = "LEGACY_ISS_REJECTED"
LEGACY_FORMAT = "iss_text"

HOW_VOTED = {
    "For": "FOR", "FOR": "FOR", "Against": "AGAINST", "AGAINST": "AGAINST",
    "Abstain": "ABSTAIN", "Withhold": "WITHHOLD", "Withheld": "WITHHOLD",
    "1 Year": "1 YEAR", "One Year": "1 YEAR", "2 Years": "2 YEARS", "Two Years": "2 YEARS",
    "3 Years": "3 YEARS", "Three Years": "3 YEARS",
    "Do Not Vote": "DO NOT VOTE", "Did Not Vote": "Did Not Vote",
    "TNA": "TNA", "No Vote": "No Vote",
}
VOTE_DROPPED = frozenset({"None", "N/A", "Take No Action"})
VOTE_SOURCE = {"Management": "ISSUER", "Shareholder": "SECURITY HOLDER"}

_ISS_COLHDR = re.compile(r"#\s+Proposal\s+(?:Mgt Rec|Diss Rec)\s+Vote Cast\s+Sponsor")


# -- format detection --------------------------------------------------------

def is_iss_text(text: str) -> bool:
    return "FORM N-Px REPORT" in text and _ISS_COLHDR.search(text) is not None


def detect_format(docs: dict[str, str]) -> str | None:
    """'iss', 'proxyedge', or None (neither, or a mix we will not guess about)."""
    iss = any(is_iss_text(t) for t in docs.values())
    pe = any("Agenda Number:" in t for t in docs.values())
    if iss and not pe:
        return "iss"
    if pe and not iss:
        return "proxyedge"
    return None


# -- two-parser agreement ----------------------------------------------------

def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEYS)


def agreed(text: str) -> tuple[list[dict], dict]:
    """Rows both parsers produced identically (multiset intersection, in parser A's
    order) and the agreement stats."""
    rows_a = legacy_iss_blocks.parse(text)
    rows_b = legacy_iss_lines.parse(text)
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
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only,
                 "disagreement_rate": (a_only + b_only) / max(1, n_agreed + a_only + b_only)}


# -- ledger rows -------------------------------------------------------------

def series_for(heading: str, smap: dict[str, str]) -> str | None:
    """Exact normalised match, else exactly one trailing ' - SUFFIX' stripped. Else None."""
    sid = smap.get(legacy_pe._norm(heading))
    if sid is None and " - " in heading:
        sid = smap.get(legacy_pe._norm(heading.rsplit(" - ", 1)[0]))
    return sid


def to_vote_rows(rows: list[dict], smap: dict[str, str]) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts, plus drop counters."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"contest_rows_dropped": 0, "dropped_vote": 0, "dropped_date": 0,
            "dropped_sponsor": 0}
    for r in rows:
        sid = series_for(r["fund_heading"], smap)
        if sid is None:
            unmapped[r["fund_heading"]] += 1
            continue
        if r["card_label"] or r["rec_label"] == "Diss Rec":
            info["contest_rows_dropped"] += 1
            continue
        source = VOTE_SOURCE.get(r["sponsor"])
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
        rec = HOW_VOTED.get(r["rec"], "") if r["rec_label"] == "Mgt Rec" else ""
        out.append({
            "issuer_name": r["issuer_name"], "cusip": r["security_id"], "isin": None,
            "meeting_date": f"{m.group(2)}/{m.group(3)}/{m.group(1)}",
            "vote_description": r["proposal_text"], "category_type": "",
            "vote_source": source, "shares_on_loan": None, "vote_series": sid,
            "how_voted": how, "shares_voted": None, "management_recommendation": rec,
            "legacy_format": LEGACY_FORMAT, "for_against_management": None,
        })
    info["unmapped"] = dict(unmapped)
    return out, info


# -- filings -----------------------------------------------------------------

is_candidate = legacy_pe.is_candidate


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str) -> int:
    """Parse every ISS-text document of one filing, gate it, record it. One transaction
    (no network inside). Returns votes inserted."""
    smap = legacy_pe.series_map(hdr_text)
    parsed = []
    for name, text in sorted(docs.items()):
        if not is_iss_text(text):
            continue
        rows, st = agreed(text)
        votes, info = to_vote_rows(rows, smap)
        info["funds_unmapped"] = info["unmapped"]
        parsed.append((name, text.count("Meeting Date:"), st, votes, info))
        logger.info("%s %s: agreed=%d emitted=%d unmapped=%d contest=%d vocab=%d",
                    filing.accession_number, name, st["agreed"], len(votes),
                    sum(info["unmapped"].values()), info["contest_rows_dropped"],
                    info["dropped_vote"])
    return legacy_pe.record_filing(conn, filing, institution_id, today, parsed,
                                   REPORT_OK, REPORT_REJECTED)


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int | None:
    """Fetch (network/cache, no write lock held) then ingest one filing. Returns None,
    writing nothing, when the filing is not ISS text."""
    docs, hdr = legacy_pe.load_filing_texts(filing)
    if detect_format(docs) != "iss":
        return None
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr)
    logger.info("ingested LEGACY_ISS %s: %d votes", filing.accession_number, n)
    return n
