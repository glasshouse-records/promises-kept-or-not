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

Proxy contests: every row with a card label, a "Diss Rec" column or a contest meeting type is dropped and counted
(`contest_rows_dropped`): the same proposal appears on two cards and the management
recommendation is undefined. `management_recommendation` carries the XML meaning (whether
THIS vote went WITH = "FOR" or AGAINST management), derived only under "Mgt Rec" from the
mapped rec and vote (`with_management`); anything not clearly with or against is "".
`for_against_management` stays NULL (ProxyEdge-only).

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

import html
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
_WITH_VALUES = frozenset({"FOR", "AGAINST", "ABSTAIN", "WITHHOLD", "1 YEAR", "2 YEARS", "3 YEARS"})
_FREQ = frozenset({"1 YEAR", "2 YEARS", "3 YEARS"})


def with_management(rec: str, vote: str) -> str:
    """XML meaning from mapped (stored) rec and vote: "FOR" = with management, "AGAINST" =
    against, "" = not clear. Never guesses."""
    if rec in _WITH_VALUES and vote == rec:
        return "FOR"
    # Filers code an abstention as AGAINST management (XML: 14,091 AGAINST vs 8,980 NONE vs
    # 155 FOR); ABSTAIN against an ABSTAIN rec stays FOR (handled above).
    if rec in ("FOR", "AGAINST") and vote == "ABSTAIN":
        return "AGAINST"
    if ((rec == "FOR" and vote in ("AGAINST", "WITHHOLD"))
            or (rec in ("AGAINST", "WITHHOLD") and vote == "FOR")
            or (rec in _FREQ and vote in _FREQ and vote != rec)):
        return "AGAINST"
    return ""


VOTE_DROPPED = frozenset({"None", "N/A", "Take No Action"})
VOTE_SOURCE = {"Management": "ISSUER", "Shareholder": "SECURITY HOLDER"}

_ISS_COLHDR = re.compile(r"#\s+Proposal\s+(?:Mgt Rec|Diss Rec)\s+Vote Cast\s+Sponsor")


# -- format detection --------------------------------------------------------

def is_iss_text(text: str) -> bool:
    # The column header alone identifies the layout (State Street omits the banner);
    # content is still validated by the two-parser agreement gate.
    return _ISS_COLHDR.search(text) is not None


_WS = r"(?:\s|&nbsp;|&#160;|\xa0)+"
_ISSUENO_HDR = re.compile(
    rf"Issue{_WS}No\.{_WS}Description{_WS}Proponent{_WS}Mgmt{_WS}Rec{_WS}Vote{_WS}Cast", re.I)


def is_issueno(text: str) -> bool:
    """The legacy N-PX 'Issue No.' layout (see legacy_issueno): its column header, any case
    (Russell prints it upper case), any whitespace, `&nbsp;` allowed."""
    return _ISSUENO_HDR.search(text) is not None


# The same header exported as an HTML table (Putnam, Neuberger Berman): each label in its own
# cell, so at least one cell boundary between consecutive labels.
_CELL_GAP = r"(?:\s|&#160;|&nbsp;|<(?![tT][dDhH]\b)[^>]*>)*"   # never crosses a cell start
# One or more cell starts, each preceded by non-cell filler: the pieces cannot overlap, so a
# failed match is linear (the lazy overlapping form took 21 s on 32,000 empty cells).
_CELL_GAP = rf"(?:{_CELL_GAP}<t[dh]\b[^>]*>)+{_CELL_GAP}"
_ISSUENO_HTML_HDR = re.compile(
    rf"Issue{_WS}No\.{_CELL_GAP}Description{_CELL_GAP}Proponent{_CELL_GAP}Mgmt{_WS}Rec"
    rf"{_CELL_GAP}Vote{_WS}Cast", re.I)


def is_issueno_html(text: str) -> bool:
    """The 'Issue No.' layout as an HTML table (see legacy_issueno_html)."""
    return _ISSUENO_HTML_HDR.search(text) is not None


# Global X's "Registrant Voted" text layout (see legacy_regvoted); tags allowed between words.
_RV_WS = r"(?:\s|&nbsp;|&#160;|\xa0|<[^>]*>)+"
_REGVOTED_HDR = re.compile(
    rf"Proposal{_RV_WS}Proposed{_RV_WS}by{_RV_WS}Mgt\.{_RV_WS}Position{_RV_WS}Registrant"
    rf"{_RV_WS}Voted", re.I)


def is_regvoted(text: str) -> bool:
    return _REGVOTED_HDR.search(text) is not None


# <th>Proposal No</th>, or Franklin's <td><p ...><font ...>Proposal No</font></p></td>
_ISS_HTML_HDR = re.compile(
    r"<(t[dh])\b[^>]*>\s*(?:<(?:p|font)\b[^>]*>\s*){0,2}Proposal No\s*"
    r"(?:</(?:p|font)>\s*){0,2}</\1>", re.I)


def is_iss_html(text: str) -> bool:
    return _ISS_HTML_HDR.search(text) is not None


_P_ELEMENT = re.compile(r"<P\b[^>]*Courier New[^>]*>(.*?)</P>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>")


_P_UNSAFE = re.compile(r"<br\b|[\r\n\t]", re.I)


def courier_html_to_text(doc: str) -> str | None:
    """ISS "FORM N-Px" text printed as HTML (one Courier New <P> per line, spaces as
    `&nbsp;` mixed with literal spaces) -> the plain text both ISS parsers read: one line
    per <P>, tags removed, every entity decoded (a non-breaking space becomes exactly one
    space; literal spaces are kept, so fixed-width columns survive). None unless the ISS
    column header is absent from the raw document but present, on a single line, after
    conversion (so plain ISS text, other HTML and anything else are never touched)."""
    if is_iss_text(doc) or "<P" not in doc:
        return None
    lines = []
    for m in _P_ELEMENT.finditer(doc):
        if _P_UNSAFE.search(m.group(1)):
            return None        # a break or tab inside one line would merge/shift columns
        lines.append(html.unescape(_TAG.sub("", m.group(1))).replace("\xa0", " "))
    if not any(_ISS_COLHDR.search(ln) for ln in lines):
        return None
    return "\n".join(lines) + "\n"


def prepare(doc: str) -> str:
    """The text the ISS parsers should read: converted Courier HTML, else `doc` as is."""
    converted = courier_html_to_text(doc)
    return doc if converted is None else converted


# Federated's flat table: these header labels, each alone in its own cell, in this order.
_FEDFLAT_LABELS = ("Ballot Issue Number", "Proposal Text", "Proponent", "Mgmt Reco",
                   "Vote Cast", "Fund Name")
_CELL_GAP = r"\s*(?:</[^>]+>\s*)*</t[dh]>\s*<t[dh]\b[^>]*>\s*(?:<[^/>][^>]*>\s*)*"
_IN_LABEL = r"(?:\s|<[^>]*>)+"       # a label's words may sit in separate <p> or <b> tags
_FEDFLAT_HDR = re.compile(r"(?i)" + _CELL_GAP.join(
    _IN_LABEL.join(map(re.escape, lb.split())) for lb in _FEDFLAT_LABELS)
                         + r"\s*(?:</[^>]+>\s*)*</t[dh]>")


def is_fedflat(text: str) -> bool:
    return "Reco" in text and _FEDFLAT_HDR.search(text) is not None


def doc_format(text: str) -> str | None:
    """One document's format, checked in order: ISS text (also as Courier HTML), ISS
    HTML, 'issueno' (legacy "Issue No." layout), 'issueno_html' (the same as HTML tables),
    'regvoted' ("Registrant Voted" text), 'regvoted_html' (the same as HTML tables),
    'fedflat' (Federated's one-row-per-vote table), ProxyEdge."""
    if is_iss_text(text) or courier_html_to_text(text) is not None:
        return "iss"
    if is_iss_html(text):
        return "iss_html"
    if is_issueno(text):
        return "issueno"
    if is_issueno_html(text):
        return "issueno_html"
    m = _REGVOTED_HDR.search(text)
    if m:      # the same header words; in table cells it is the HTML-table rendering
        return "regvoted_html" if "</td" in m.group(0).lower() else "regvoted"
    if is_fedflat(text):
        return "fedflat"
    if "Agenda Number:" in text:
        return "proxyedge"
    return None


def detect_format(docs: dict[str, str]) -> str | None:
    """'iss', 'iss_html', 'issueno', 'issueno_html', 'regvoted', 'regvoted_html', 'fedflat', 'proxyedge', or None (none, or a mix we will not guess about)."""
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
    out, guard_stats = legacy_pe.guarded(out, rows_a, rows_b, ca, cb, "fund_heading", _key)
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only,
                 "disagreement_rate": (a_only + b_only) / max(1, n_agreed + a_only + b_only),
                 **guard_stats}


# -- ledger rows -------------------------------------------------------------

def series_for(heading: str, smap: dict[str, str], aliases: dict[str, str] | None = None,
               header_sids: set[str] | None = None) -> str | None:
    """Exact normalised match, else exactly one trailing ' - SUFFIX' stripped, else the
    reviewed alias (only if its series is in the filing's own header). Else None."""
    return _series_for(heading, smap, aliases, header_sids)[0]


def is_policy_section(heading: str) -> bool:
    """A Vanguard 'FUND - <name> POLICY' voting-policy section: its votes follow a policy
    other than the fund's own, so they must not be merged into the fund's record."""
    if " - " not in heading:
        return False
    words = heading.rsplit(" - ", 1)[1].split()
    return bool(words) and words[-1].upper() == "POLICY"


def _series_for(heading, smap, aliases, header_sids, fallback=None, info=None
                ) -> tuple[str | None, bool]:
    if is_policy_section(heading):
        return None, False
    sid = smap.get(legacy_pe._norm(heading))
    if sid is None and " - " in heading:
        sid = smap.get(legacy_pe._norm(heading.rsplit(" - ", 1)[0]))
    if sid is not None:
        return sid, False
    sid, bad = legacy_pe.alias_series(heading, aliases, header_sids)
    if sid is None and fallback and legacy_pe._heading(heading) not in (aliases or {}):
        sid = fallback.lookup(heading, suffix=True)
        if sid and info is not None:
            legacy_pe.note_fallback(info, heading, sid)
    return sid, bad


def to_vote_rows(rows: list[dict], smap: dict[str, str],
                 legacy_format: str = LEGACY_FORMAT,
                 aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None,
                 fallback=None) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts, plus drop counters."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"contest_rows_dropped": 0, "dropped_vote": 0, "dropped_date": 0,
            "dropped_sponsor": 0, "alias_not_in_header": 0, "policy_section_dropped": 0}
    for r in rows:
        sid, bad = _series_for(r["fund_heading"], smap, aliases, header_sids, fallback, info)
        info["alias_not_in_header"] += bad
        if sid is None and is_policy_section(r["fund_heading"]):
            info["policy_section_dropped"] += 1
            continue
        if sid is None:
            unmapped[r["fund_heading"]] += 1
            continue
        if (r["card_label"] or r["rec_label"] == "Diss Rec"
                or "contest" in (r.get("meeting_type") or "").lower()):
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
        rec = (with_management(HOW_VOTED.get(r["rec"], ""), how)
               if r["rec_label"] == "Mgt Rec" else "")
        cusip, isin = legacy_pe.classify_security_id(r["security_id"])
        out.append({
            "issuer_name": r["issuer_name"], "cusip": cusip, "isin": isin,
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
                  fmt: str = "iss",
                  aliases: dict[tuple[str, str], str] | None = None,
                  series_dataset: dict | None = None) -> int:
    """Parse every document of one filing that is in format `fmt` ('iss' text or
    'iss_html'), gate it, record it. One transaction (no network inside). Returns votes
    inserted."""
    tag, report_ok, report_rejected = FORMATS[fmt]
    smap = legacy_pe.series_map(hdr_text)
    fa = legacy_pe.filing_aliases(aliases, filing.cik)
    sids = legacy_pe.header_series_ids(hdr_text)
    fb = legacy_pe.build_fallback(series_dataset, filing.cik, hdr_text)
    ag = []
    for name, text in sorted(docs.items()):
        if doc_format(text) != fmt:
            continue
        text = prepare(text)  # Courier-HTML ISS text -> plain lines, for BOTH parsers
        ag.append((name, text, *agreed(text, PARSERS[fmt])))
    single = legacy_pe.single_fund_map(
        hdr_text, (r["fund_heading"] for _, _, rows, _ in ag for r in rows))
    smap = {**smap, **single}
    parsed = []
    for name, text, rows, st in ag:
        votes, info = to_vote_rows(rows, smap, tag, fa, sids, fb)
        legacy_pe.note_single_fund(info, single, (r["fund_heading"] for r in rows))
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
    from . import sec_series
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, fmt,
                      legacy_pe.load_aliases(), sec_series.load_dataset())
    logger.info("ingested %s %s: %d votes", FORMATS[fmt][1], filing.accession_number, n)
    return n
