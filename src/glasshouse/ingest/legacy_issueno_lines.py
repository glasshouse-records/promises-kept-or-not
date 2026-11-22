"""Legacy (pre-XML) N-PX 'Issue No.' text format: a line-oriented state machine.

Every line is classified (fund heading, separator, header, value line, column
header, proposal row, continuation, markup, noise) with regular expressions
and a small state machine advances. Fixed-width columns come from the column
header line of each meeting. Precision over recall: anything that cannot be
placed drops that proposal (or that meeting), never a guess.

Reduced inputs: HTML (<PRE>/<P>) and SGML-table (<TABLE>, <S>, <C>, <PAGE>)
documents are first reduced to text lines; entities are decoded, &nbsp; is
one space, markup-only lines vanish and <PAGE>/form feed become page breaks.
"""

from __future__ import annotations

import html as _html
import re
from collections import Counter
from datetime import datetime

# Closed vocabularies: every value observed in the four reference samples
# (Schwab, VanEck, Hartford, Russell); anything else drops the proposal.
PROPONENTS = frozenset({"Mgmt", "MGMT", "N/A", "ShrHoldr"})
RECS = frozenset(
    {"For", "FOR", "Against", "Abstain", "Withhold", "N/A", "1 Year", "2 Years", "3 Years"}
)
VOTES = frozenset(
    {"For", "FOR", "Against", "Abstain", "Withhold", "N/A", "TNA", "1 Year", "2 Years", "3 Years", "Echo Vote"}
)
FOR_AGAINST = frozenset({"For", "FOR", "Against", "N/A"})
SECURITY_ID_TYPES = frozenset({"CUSIP", "CINS", "ISIN", "SEDOL"})

_SEP = re.compile(r"^\s*(?:_{20,}|-{20,}|={20,})\s*$")
_FUND = re.compile(r"^Fund Name\s*:\s*(\S.*?)\s*$")
_FUND_EMPTY = re.compile(r"^Fund Name\s*:\s*$")
_HDR1 = re.compile(
    r"^(?P<t>Ticker)\s+(?P<s>Security ID:)\s+(?P<d>Meeting Date)\s+(?P<st>Meeting Status)\s*$", re.I
)
_HDR2 = re.compile(r"^(?P<t>Meeting Type)\s+(?P<c>Country of Trade)\s*$", re.I)
_COLHDR = re.compile(
    r"^\s*Issue No\.\s+(?P<d>Description)\s+(?P<p>Proponent)\s+(?P<r>Mgmt Rec)\s+"
    r"(?P<v>Vote Cast)\s+(?P<f>For/Against|For/Agnst Mgmt|Mgmt)\s*$",
    re.I,
)
_ABOVE = re.compile(r"^\s*FOR/AGNST\s*$", re.I)
_MGMT_LINE = re.compile(r"^\s*Mgmt\s*$", re.I)
_ISSUE = re.compile(r"^\d+(?:\.\d+)*$")
_DATE = re.compile(r"^(\d\d)/(\d\d)/(\d{4})$")
_SECID = re.compile(r"^([A-Z]+) (\S+)$")
_MARKUP_ONLY = re.compile(r"^(?:\s*</?[A-Za-z!][^<>]*>)+\s*$")
_INLINE_TAG = re.compile(r"</?[A-Za-z!][^<>]*>")
_HTML_DOC = re.compile(r"<(?:PRE|P|DIV|BR|HTML|BODY|FONT|SPAN)\b", re.I)
_PAGE_TAG = re.compile(r"^\s*<PAGE>\s*$", re.I)
_END_DOC = re.compile(r"^\s*(?:SIGNATURES?|</?(?:TEXT|DOCUMENT)>)\s*$", re.I)
PAGE = "\x0c"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _reduce(text: str) -> list[str]:
    """Reduce a decoded document to text lines; PAGE marks a page break."""
    html_mode = bool(_HTML_DOC.search(text))
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        parts = raw.split("\x0c")
        for k, line in enumerate(parts):
            if k > 0:
                out.append(PAGE)
            if _PAGE_TAG.match(line):
                out.append(PAGE)
                continue
            if _MARKUP_ONLY.match(line):
                continue
            if html_mode:
                line = _INLINE_TAG.sub("", line)
                line = _html.unescape(line).replace("\xa0", " ")
            out.append(line.rstrip())
    if html_mode:
        out = [ln for ln in out if not ln.startswith("<!--")]
    return out


def _cells(line: str, starts: list[int]) -> list[str] | None:
    """Slice a line at column starts; None if any cut falls inside a word."""
    for s in starts[1:]:
        if s - 1 < len(line) and line[s - 1] != " ":
            return None
    bounds = starts + [10**9]
    return [line[bounds[i] : bounds[i + 1]].strip() for i in range(len(starts))]


class _Meeting:
    def __init__(self, fund: str | None):
        self.fund = fund
        self.issuer = ""
        self.cols1: list[int] = []
        self.cols2: list[int] = []
        self.info: dict[str, str] = {}
        self.cols: list[int] = []
        self.above: int | None = None
        self.rows: list[dict | None] = []  # None entries are dropped proposals
        self.open: dict | None = None
        self.gap = False
        self.lost = False


def _run(text: str):
    """Events in document order: seen | meeting(drop reason) | proposal(reason|None) | row."""
    lines = _reduce(text)
    fund: str | None = None
    state = "START"  # START FUND ISSUER HDR1 VAL1 HDR2 VAL2 COLHDR COLHDR2 ROWS LOST
    mt: _Meeting | None = None
    events: list[tuple[str, object]] = []

    def flush():
        nonlocal mt
        if mt is None:
            return
        for r in mt.rows:
            if r is None:
                continue
            if r.get("pend"):
                events.append(("proposal", "incomplete_row"))
            elif "bad" in r:
                events.append(("proposal", r["bad"]))
            else:
                events.append(("proposal", None))
                events.append(("row", r["out"]))
        mt = None

    def drop_meeting(reason: str):
        nonlocal mt, state
        events.append(("meeting", reason))
        mt = None
        state = "LOST"

    for line in lines:
        is_page = line == PAGE
        blank = is_page or not line.strip()
        fm = None if is_page else _FUND.match(line)
        if fm or (not is_page and _FUND_EMPTY.match(line)):
            if state in {"ISSUER", "HDR1", "VAL1", "HDR2", "VAL2", "COLHDR", "COLHDR2"}:
                events.append(("meeting", "truncated"))
                mt = None
            flush()
            if fm is None:
                fund, state = None, "LOST"
            else:
                fund, state = _norm(fm.group(1)), "FUND"
            continue
        if not is_page and _SEP.match(line):
            if state in {"ISSUER", "HDR1", "VAL1", "HDR2", "VAL2", "COLHDR", "COLHDR2"}:
                events.append(("meeting", "truncated"))
                mt = None
            flush()
            events.append(("seen", None))
            if fund is None:
                drop_meeting("before_fund_heading")
            else:
                mt = _Meeting(fund)
                state = "ISSUER"
            continue
        if not is_page and _END_DOC.match(line) and state in {"ROWS", "FUND", "LOST", "START"}:
            flush()
            state = "LOST"
            continue
        if state in {"START", "FUND", "LOST"}:
            continue
        assert mt is not None
        if state == "ROWS":
            _rows_line(mt, line, blank, is_page)
            if mt.lost:
                flush()
                state = "LOST"
            continue
        if blank:
            continue
        if state == "ISSUER":
            if _HDR1.match(line.strip()) or _HDR2.match(line.strip()):
                drop_meeting("missing_issuer")
                continue
            mt.issuer = _norm(line)
            state = "HDR1"
        elif state == "HDR1":
            m = _HDR1.match(line.rstrip())
            if not m or line[0] == " ":
                drop_meeting("bad_header1")
                continue
            mt.cols1 = [m.start("t"), m.start("s"), m.start("d"), m.start("st")]
            state = "VAL1"
        elif state == "VAL1":
            c = _cells(line, mt.cols1)
            if c is None:
                drop_meeting("bad_value1")
                continue
            ticker, sid, date, status = c
            dm = _DATE.match(date)
            try:
                if not dm:
                    raise ValueError
                iso = datetime(int(dm.group(3)), int(dm.group(1)), int(dm.group(2))).date()
            except ValueError:
                drop_meeting("bad_meeting_date")
                continue
            sm = _SECID.match(_norm(sid))
            if not sm or sm.group(1) not in SECURITY_ID_TYPES:
                drop_meeting("bad_security_id")
                continue
            if not status or " " in ticker:
                drop_meeting("bad_value1")
                continue
            mt.info.update(
                ticker=ticker, security_id=_norm(sid), meeting_date=iso.isoformat(),
                meeting_status=_norm(status),
            )
            state = "HDR2"
        elif state == "HDR2":
            m = _HDR2.match(line.rstrip())
            if not m or line[0] == " ":
                drop_meeting("bad_header2")
                continue
            mt.cols2 = [m.start("t"), m.start("c")]
            state = "VAL2"
        elif state == "VAL2":
            c = _cells(line, mt.cols2)
            if c is None or not c[0] or not c[1]:
                drop_meeting("bad_value2")
                continue
            mt.info.update(meeting_type=_norm(c[0]), country=_norm(c[1]))
            state = "COLHDR"
        elif state == "COLHDR":
            if _ABOVE.match(line):
                mt.above = len(line) - len(line.lstrip())
                continue
            m = _COLHDR.match(line)
            if not m:
                drop_meeting("bad_column_header")
                continue
            mt.cols = [m.start("d"), m.start("p"), m.start("r"), m.start("v"), m.start("f")]
            if mt.cols[3] - mt.cols[2] < 3:
                drop_meeting("bad_column_header")
                continue
            if mt.above is not None:
                mt.cols[4] = min(mt.cols[4], mt.above)
            if m.group("f").lower() == "mgmt" and mt.above is None:
                # 'Mgmt' ending the line without a FOR/AGNST line above is Russell-like
                # only; plain layouts put it on its own line, so treat as ambiguous.
                drop_meeting("bad_column_header")
                continue
            state = "COLHDR2" if m.group("f").lower() == "for/against" else "ROWS"
        elif state == "COLHDR2":
            if not _MGMT_LINE.match(line):
                drop_meeting("bad_column_header")
                continue
            state = "ROWS"
    flush()
    return events


def _rows_line(mt: _Meeting, line: str, blank: bool, is_page: bool) -> None:
    if blank:
        mt.gap = True
        return
    s = line.strip()
    if _HDR1.match(s) or _HDR2.match(s):
        _taint(mt, "header_in_rows")
        mt.lost = True
        return
    if _COLHDR.match(line) or _ABOVE.match(line) or _MGMT_LINE.match(line):
        # repeated running header: ignore, but it is a gap in the row stream
        mt.gap = True
        return
    d, p, r, v, f = mt.cols
    head = line[:d]
    rest = line[d:]
    if not head.strip() and rest.strip():
        # candidate continuation: description text, no issue number
        c = _cells(line, mt.cols)
        if c is None or not c[0]:
            _taint(mt, "unplaced_line")
            return
        cur = mt.open
        if cur is None or mt.gap:
            _taint(mt, "continuation_after_gap")
            return
        cur["out"]["proposal_text"] += " " + _norm(c[0])
        if any(c[1:]):
            # Russell-style: the columns sit on the LAST line of a wrapped row
            if not cur.get("pend") or not _vocab_ok(*c[1:]):
                _taint(mt, "unplaced_line")
                return
            cur["out"].update(proponent=c[1], rec=c[2], vote=c[3], for_against=c[4])
            cur["pend"] = False
            mt.open = None
        return
    c = _cells(line, [0] + mt.cols)
    if c is None or not _ISSUE.match(c[0]):
        if mt.gap and line[:d].strip() and not (mt.open or {}).get("pend"):
            # unindented prose after a gap (section heading, signature block): it
            # cannot be description text, so the meeting ends; nothing is tainted
            mt.lost = True
            return
        _taint(mt, "unplaced_line")
        return
    iss, desc, prop, rec, vote, fa = c
    row: dict = {}
    if not desc:
        row["bad"] = "empty_text"
    elif not any((prop, rec, vote, fa)):
        row["pend"] = True
    elif not _vocab_ok(prop, rec, vote, fa):
        row["bad"] = "vocab"
    mt.gap = False
    if "bad" in row:
        mt.rows.append(row)
        mt.open = None
        return
    row["out"] = {
        "fund_heading": mt.fund, "issuer_name": mt.issuer, "ticker": mt.info["ticker"],
        "security_id": mt.info["security_id"], "meeting_date": mt.info["meeting_date"],
        "meeting_status": mt.info["meeting_status"], "meeting_type": mt.info["meeting_type"],
        "country": mt.info["country"], "proposal_id": iss, "proposal_text": _norm(desc),
        "proponent": prop, "rec": rec, "vote": vote, "for_against": fa,
    }
    mt.rows.append(row)
    mt.open = row


def _vocab_ok(prop: str, rec: str, vote: str, fa: str) -> bool:
    return prop in PROPONENTS and rec in RECS and vote in VOTES and fa in FOR_AGAINST


def _taint(mt: _Meeting, why: str) -> None:
    if mt.rows and mt.rows[-1] is not None and "bad" not in mt.rows[-1]:
        mt.rows[-1] = {"bad": why}
    mt.open = None
    mt.gap = True


def parse(text: str) -> list[dict]:
    return [p for ev, p in _run(text) if ev == "row"]  # type: ignore[misc]


def parse_stats(text: str) -> dict:
    reasons: Counter = Counter()
    seen = dropped = ps = pe = pd = 0
    for ev, p in _run(text):
        if ev == "seen":
            seen += 1
        elif ev == "meeting":
            dropped += 1
            reasons[str(p)] += 1
        elif ev == "proposal":
            ps += 1
            if p is None:
                pe += 1
            else:
                pd += 1
                reasons[str(p)] += 1
    return {
        "meetings_seen": seen, "meetings_dropped": dropped, "proposals_seen": ps,
        "proposals_emitted": pe, "proposals_dropped": pd, "reasons": dict(reasons),
    }
