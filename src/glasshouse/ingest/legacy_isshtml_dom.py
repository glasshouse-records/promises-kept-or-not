"""Legacy N-PX (ISS "Wdesk/ISS" HTML-table export) -> one dict per voted proposal.

Parser A: builds a light tree (tables -> rows -> cells) with ``html.parser`` and
walks it.  Fund names come from centred ``<p>`` elements (align=center or style text-align: center) in document order.
Precision over recall: anything ambiguous is dropped and counted in
``parse_stats()['reasons']``; nothing is inferred from neighbouring rows, typos
are never fixed and nothing is fuzzy-matched.  Pure functions, stdlib only.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections import Counter
from html.parser import HTMLParser

RECS = frozenset({
    "For", "Against", "Abstain", "Withhold", "None", "One Year", "Two Years", "Three Years",
    "1 Year", "2 Years", "3 Years", "Do Not Vote", "Did Not Vote", "Take No Action", "N/A",
    "No Vote", "FOR", "AGAINST", "ABSTAIN", "WITHHOLD",  # upper-case literals (amendment 1)
})
VOTES = RECS | {"TNA", "Withheld"}
SPONSORS = frozenset({"Management", "Shareholder"})
REC_LABELS = {"Management Recommendation": "Mgt Rec", "Dissident Recommendation": "Diss Rec"}
HEADER = ("Proposal No", "Proposal", "Proposed By")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-()]*$")
_DATE_RE = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$")
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
_CENTER_STYLE_RE = re.compile(r"(?:^|;)\s*text-align\s*:\s*center\s*(?:;|$)", re.I)
_COVER = ("form n-px", "ica file number", "registrant name", "reporting period",
          "(name and address", "annual report of proxy voting", "date of reporting period")


def _collapse(s: str) -> str:
    return " ".join(s.split())  # str.split() also splits on U+00A0


class _Cell:
    __slots__ = ("tag", "colspan", "parts")

    def __init__(self, tag: str, colspan: bool):
        self.tag, self.colspan, self.parts = tag, colspan, []

    @property
    def text(self) -> str:
        return _collapse("".join(self.parts).replace("\0", " "))

    @property
    def lines(self) -> list[str]:
        """Text split at <br> (stored as a NUL marker), each line collapsed, empties dropped."""
        return [x for x in (_collapse(p) for p in "".join(self.parts).split("\0")) if x]


class _Table:
    def __init__(self):
        self.rows: list[list[_Cell]] = []


class _Tree(HTMLParser):
    """Collects ('fund', name) and ('table', _Table) events in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, object]] = []
        self.tables: list[_Table] = []   # open-table stack
        self.row: list[list[_Cell] | None] = []  # parallel: current row per open table
        self.cell: list[_Cell | None] = []
        self.p: list[str] | None = None  # open paragraph text (outside tables)
        self.p_centred = False
        self.skip = 0

    def _close_cell(self):
        if self.cell:
            self.cell[-1] = None

    def _close_row(self):
        self._close_cell()
        if self.row:
            self.row[-1] = None

    def _close_p(self):
        if self.p is not None:
            name = _collapse("".join(self.p))
            centred, self.p, self.p_centred = self.p_centred, None, False
            low = name.lower()
            if low == "end npx report" or low.startswith("signature"):
                self.events.append(("end", ""))  # amendment 3: no fund in force after this
            elif centred and name and not low.startswith(_COVER) \
                    and "registrant" not in low and "agent for service" not in low:
                self.events.append(("fund", name))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "p":
            self._close_p()
            centred = (a.get("align") or "").strip().lower() == "center" \
                or _CENTER_STYLE_RE.search(a.get("style") or "")
            if not self.tables:
                self.p, self.p_centred = [], bool(centred)
        elif tag == "table":
            self._close_p()
            t = _Table()
            self.events.append(("table", t))
            self.tables.append(t)
            self.row.append(None)
            self.cell.append(None)
        elif tag == "tr" and self.tables:
            self._close_row()
            self.row[-1] = []
            self.tables[-1].rows.append(self.row[-1])
        elif tag in ("td", "th") and self.tables:
            self._close_cell()
            if self.row[-1] is None:  # cell without <tr>: open an implicit row
                self.row[-1] = []
                self.tables[-1].rows.append(self.row[-1])
            c = _Cell(tag, "colspan" in a)
            self.row[-1].append(c)
            self.cell[-1] = c
        elif tag == "br":
            self._text("\0")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self._text("\0")
        else:
            self.handle_starttag(tag, attrs)
            if tag in ("script", "style"):
                self.skip -= 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "p":
            self._close_p()
        elif tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table" and self.tables:
            self._close_row()
            self.tables.pop()
            self.row.pop()
            self.cell.pop()

    def _text(self, s: str):
        if self.skip:
            return
        if self.cell and self.cell[-1] is not None:
            self.cell[-1].parts.append(s)
        elif self.p is not None:
            self.p.append(" " if s == "\0" else s)

    def handle_data(self, data):
        self._text(data)


def _iso(s: str) -> str:
    m = _DATE_RE.match(_collapse(s))
    if not m or m.group(1).upper() not in _MONTHS:
        return ""
    try:
        return _dt.date(int(m.group(3)), _MONTHS[m.group(1).upper()], int(m.group(2))).isoformat()
    except ValueError:
        return ""


def _title(s: str) -> str:
    return re.sub(r"[A-Za-z]+", lambda m: m.group().capitalize(), s)


def _parse_meeting(lines: list[str]):
    """-> (meeting dict | None, reason).  Needs an issuer line and a good Meeting Date."""
    labels = {"meeting date:": "md", "record date:": "rd", "meeting type:": "mt"}
    found: dict[str, str] = {}
    issuer: list[str] = []
    for ln in lines:
        low = ln.lower()
        for lab, key in labels.items():
            if low.startswith(lab):
                if key in found:
                    return None, "dup_meeting_label"
                found[key] = _collapse(ln[len(lab):])
                break
        else:
            if not found:
                issuer.append(ln)
    if not issuer:
        return None, "no_issuer"
    if _iso(found.get("md", "")) == "":
        return None, "bad_meeting_date"
    return {
        "issuer_name": _collapse(" ".join(issuer)),
        "meeting_date": _iso(found["md"]),
        "record_date": _iso(found.get("rd", "")),
        "meeting_type": _title(found.get("mt", "")),
        "ticker": "", "security_id": "",
    }, ""


def _run(text: str) -> tuple[list[dict], dict]:
    tree = _Tree()
    tree.feed(text)
    tree.close()
    reasons: Counter = Counter()
    meeting_reasons: Counter = Counter()
    out: list[dict] = []
    stats = {"funds": 0, "tables": 0, "meetings": 0, "bad_meetings": 0, "proposal_rows": 0,
             "ignored_colspan_rows": 0}
    fund = ""
    for kind, obj in tree.events:
        if kind == "end":
            fund = ""
            continue
        if kind == "fund":
            fund = obj  # type: ignore[assignment]
            stats["funds"] += 1
            continue
        stats["tables"] += 1
        meeting: dict | None = None
        meeting_bad = ""          # reason, when the current meeting was dropped
        rec_label = ""
        card = ""
        for row in obj.rows:  # type: ignore[attr-defined]
            ths = [c for c in row if c.tag == "th"]
            if len(row) == 1 and row[0].colspan:
                c = row[0]
                lines = c.lines
                if any(ln.lower().startswith("meeting date:") for ln in lines):
                    stats["meetings"] += 1
                    meeting, why = _parse_meeting(lines)
                    meeting_bad = why
                    rec_label, card = "", ""
                    if meeting is None:
                        stats["bad_meetings"] += 1
                        meeting_reasons[why] += 1
                elif any(ln.lower().startswith(("ticker:", "security id:")) for ln in lines):
                    if meeting is not None:
                        for ln in lines:
                            low = ln.lower()
                            if low.startswith("ticker:"):
                                meeting["ticker"] = _collapse(ln[7:])
                            elif low.startswith("security id:"):
                                meeting["security_id"] = _collapse(ln[12:])
                elif "proxy card" in c.text.lower():
                    card = c.text
                else:
                    stats["ignored_colspan_rows"] += 1
            elif len(ths) == len(row) and row:
                texts = tuple(c.text for c in row)
                if len(texts) == 5 and texts[:3] == HEADER and texts[4] == "Vote Cast" \
                        and texts[3] in REC_LABELS:
                    rec_label, card = REC_LABELS[texts[3]], ""
                else:
                    rec_label, card = "", ""  # unknown column layout: nothing below is trusted
                    reasons["bad_header"] += 1
            elif len(row) == 5 and all(c.tag == "td" for c in row):
                stats["proposal_rows"] += 1
                _row(row, fund, meeting, meeting_bad, rec_label, card, out, reasons)
            elif any(c.text for c in row):
                reasons["unrecognised_row_shape"] += 1
    stats["rows"] = len(out)
    stats["reasons"] = dict(reasons)
    stats["meeting_reasons"] = dict(meeting_reasons)
    return out, stats


def _row(row, fund, meeting, meeting_bad, rec_label, card, out, reasons):
    if not fund:
        reasons["no_fund"] += 1
        return
    if meeting is None:
        reasons[meeting_bad_reason(meeting_bad)] += 1
        return
    if not rec_label:
        reasons["no_header"] += 1
        return
    pid, ptxt, sponsor, rec, vote = (c.text for c in row)
    if sponsor not in SPONSORS:
        reasons["bad_sponsor"] += 1
    elif not _ID_RE.match(pid):
        reasons["bad_proposal_id"] += 1
    elif not ptxt:
        reasons["empty_proposal_text"] += 1
    elif rec not in RECS:
        reasons["bad_rec"] += 1
    elif vote not in VOTES:
        reasons["bad_vote"] += 1
    else:
        out.append({
            "fund_heading": fund, "issuer_name": meeting["issuer_name"],
            "ticker": meeting["ticker"], "security_id": meeting["security_id"],
            "meeting_date": meeting["meeting_date"], "record_date": meeting["record_date"],
            "meeting_type": meeting["meeting_type"], "rec_label": rec_label,
            "card_label": card, "proposal_id": pid, "proposal_text": ptxt, "rec": rec,
            "vote": vote, "sponsor": sponsor,
        })


def meeting_bad_reason(why: str) -> str:
    return {"bad_meeting_date": "bad_meeting_date", "": "no_meeting"}.get(why, "bad_meeting")


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> dict:
    return _run(text)[1]
