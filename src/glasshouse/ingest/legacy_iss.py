"""Legacy (July 2022 - June 2023) N-PX votes from ISS-style filings, in two layouts.

Mirrors `legacy_pe` (the ProxyEdge path). Two layouts, each read by two parsers written
independently from one contract: "FORM N-Px REPORT" text (`legacy_iss_blocks`,
`legacy_iss_lines`; legacy_format 'iss_text', LEGACY_ISS) and the Wdesk/ISS HTML table export
(`legacy_isshtml_dom`, `legacy_isshtml_lines`; 'iss_html', LEGACY_ISSHTML, detected by a
`<th>Proposal No</th>` header cell). Everything below applies to both. Each parser pair reads each document; only rows BOTH
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
  Abstain, ABSTAIN       -> ABSTAIN          (exact XML value; HTML prints upper case)
  Withhold, WITHHOLD, Withheld -> WITHHOLD         (same meaning; XML value)
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

Rows land with `legacy_format = 'iss_text'` or `'iss_html'` and `shares_voted` NULL (the format has no
share counts), quarantined by `ledger.NON_LEGACY_VOTE_SQL` until a human promotes them.
Filing storage, the gate and `legacy_parse` stats are `legacy_pe.record_filing`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter

from . import (
    legacy_iss_blocks,
    legacy_iss_lines,
    legacy_isshtml_dom,
    legacy_isshtml_lines,
    legacy_pe,
)
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
# format -> (parser pair, legacy_format tag, ok report type, rejected report type)
PARSERS = {"iss": (legacy_iss_blocks, legacy_iss_lines),
           "iss_html": (legacy_isshtml_dom, legacy_isshtml_lines)}
FORMATS = {"iss": (LEGACY_FORMAT, REPORT_OK, REPORT_REJECTED),
           "iss_html": ("iss_html", "LEGACY_ISSHTML", "LEGACY_ISSHTML_REJECTED")}

HOW_VOTED = {
    "For": "FOR", "FOR": "FOR", "Against": "AGAINST", "AGAINST": "AGAINST",
    "Abstain": "ABSTAIN", "ABSTAIN": "ABSTAIN", "Withhold": "WITHHOLD",
    "WITHHOLD": "WITHHOLD", "Withheld": "WITHHOLD",
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
    # The column header alone identifies the layout (State Street omits the banner);
    # content is still validated by the two-parser agreement gate.
    return _ISS_COLHDR.search(text) is not None


_ISS_HTML_HDR = re.compile(r"<th\b[^>]*>\s*Proposal No\s*</th>", re.I)


def is_iss_html(text: str) -> bool:
    return _ISS_HTML_HDR.search(text) is not None


def doc_format(text: str) -> str | None:
    """One document's format, checked in order: ISS text, ISS HTML, ProxyEdge."""
    if is_iss_text(text):
        return "iss"
    if is_iss_html(text):
        return "iss_html"
    if "Agenda Number:" in text:
        return "proxyedge"
    return None


def detect_format(docs: dict[str, str]) -> str | None:
    """'iss', 'iss_html', 'proxyedge', or None (none, or a mix we will not guess about)."""
    found = {f for f in map(doc_format, docs.values()) if f}
    return found.pop() if len(found) == 1 else None


# -- two-parser agreement ----------------------------------------------------

def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEYS)


def agreed(text: str, parsers=(legacy_iss_blocks, legacy_iss_lines)) -> tuple[list[dict], dict]:
    """Rows both parsers produced identically (multiset intersection, in parser A's
    order) and the agreement stats. `parsers` = a pair of modules with `parse(text)`;
    the default is the ISS text pair (see PARSERS)."""
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


def to_vote_rows(rows: list[dict], smap: dict[str, str],
                 legacy_format: str = LEGACY_FORMAT) -> tuple[list[dict], dict]:
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
            "legacy_format": legacy_format, "for_against_management": None,
        })
    info["unmapped"] = dict(unmapped)
    return out, info


# -- filings -----------------------------------------------------------------

is_candidate = legacy_pe.is_candidate


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  fmt: str = "iss") -> int:
    """Parse every document of one filing that is in format `fmt` ('iss' text or
    'iss_html'), gate it, record it. One transaction (no network inside). Returns votes
    inserted."""
    tag, report_ok, report_rejected = FORMATS[fmt]
    smap = legacy_pe.series_map(hdr_text)
    parsed = []
    for name, text in sorted(docs.items()):
        if doc_format(text) != fmt:
            continue
        rows, st = agreed(text, PARSERS[fmt])
        votes, info = to_vote_rows(rows, smap, tag)
        info["funds_unmapped"] = info["unmapped"]
        parsed.append((name, text.count("Meeting Date:"), st, votes, info))
        logger.info("%s %s: agreed=%d emitted=%d unmapped=%d contest=%d vocab=%d",
                    filing.accession_number, name, st["agreed"], len(votes),
                    sum(info["unmapped"].values()), info["contest_rows_dropped"],
                    info["dropped_vote"])
    return legacy_pe.record_filing(conn, filing, institution_id, today, parsed,
                                   report_ok, report_rejected)


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int | None:
    """Fetch (network/cache, no write lock held) then ingest one filing. Returns None,
    writing nothing, when the filing is not ISS (text or HTML)."""
    docs, hdr = legacy_pe.load_filing_texts(filing)
    fmt = detect_format(docs)
    if fmt not in PARSERS:
        return None
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, fmt)
    logger.info("ingested %s %s: %d votes", FORMATS[fmt][1], filing.accession_number, n)
    return n
