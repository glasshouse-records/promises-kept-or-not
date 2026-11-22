"""ISS "Wdesk/ISS" HTML-table N-PX (2022-23 legacy filings) -> one dict per voted proposal.

Parser B of two independent implementations of the same contract.  No HTML
parser: a regex tokenizer cuts the document into ``<p>`` paragraphs, ``<table``
starts and ``<tr>`` rows, and a small state machine (fund / meeting / header /
card label) walks the stream.

Precision over recall: anything ambiguous is dropped and counted in
``parse_stats()['reasons']``; no value is inferred, repaired or fuzzy-matched.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import re
from collections import Counter

RECS = frozenset({
    "For", "Against", "Abstain", "Withhold", "None", "One Year", "Two Years", "Three Years",
    "1 Year", "2 Years", "3 Years", "Do Not Vote", "Did Not Vote", "Take No Action", "N/A",
    "No Vote", "FOR", "AGAINST", "ABSTAIN", "WITHHOLD",   # amendment 1: literal upper case
})
VOTES = RECS | {"TNA", "Withheld"}
SPONSORS = frozenset({"Management", "Shareholder"})
REC_LABELS = {"Management Recommendation": "Mgt Rec", "Dissident Recommendation": "Diss Rec"}
HEADER = ("Proposal No", "Proposal", "Proposed By")
_COVER = ("FORM N-PX", "ICA File Number", "Registrant Name", "Reporting Period")
_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}

# One pass over the document; alternatives are tried left to right at each position.
_TOKEN = re.compile(
    r"(?P<p><p(?=[\s>])[^>]*>.*?</p\s*>)"
    r"|(?P<table><table(?=[\s>]))"
    r"|(?P<tr><tr(?=[\s>])[^>]*>(?:(?!<tr[\s>]|</tr).)*(?:</tr\s*>)?)",
    re.I | re.S)
_CELL = re.compile(
    r"<(?P<tag>td|th)(?=[\s>])(?P<attrs>[^>]*)>(?P<body>.*?)"
    r"(?:</(?P=tag)\s*>|(?=<t[dh][\s>])|\Z)", re.I | re.S)
_BR = re.compile(r"<br\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
# Centred = align=center (any quoting/case) OR an inline style declaring text-align: center.
_CENTER = re.compile(
    r"\balign\s*=\s*[\"']?center\b"
    r"|\bstyle\s*=\s*(?:\"[^\"]*|'[^']*)(?<![\w-])text-align\s*:\s*center\b", re.I)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-()]*")
_DATE = re.compile(r"([A-Za-z]{3})\s+(\d{1,2})\s*,\s*(\d{4})")
_WORD = re.compile(r"[^\W\d_]+")


def _clean(raw: str) -> str:
    """Fragment of HTML -> one line of text: tags gone, entities unescaped, whitespace collapsed."""
    s = _html.unescape(_TAG.sub("", _BR.sub(" ", raw)))
    return _WS.sub(" ", s.replace(" ", " ")).strip()


def _lines(raw: str) -> list[str]:
    """Cell body split on <br> into cleaned, non-empty lines."""
    return [t for t in (_clean(x) for x in _BR.split(raw)) if t]


def _cells(row: str) -> list[tuple[str, str, str]]:
    return [(m["tag"].lower(), m["attrs"], m["body"]) for m in _CELL.finditer(row)]


def _iso(text: str) -> str:
    """'MAY 18, 2023' -> '2023-05-18'; '' if not exactly that shape or not a real date."""
    m = _DATE.fullmatch(text.strip())
    if not m or m[1].upper() not in _MONTHS:
        return ""
    try:
        return _dt.date(int(m[3]), _MONTHS[m[1].upper()], int(m[2])).isoformat()
    except ValueError:
        return ""


def _title(s: str) -> str:
    return _WORD.sub(lambda m: m[0].capitalize(), s)


def _label(lines: list[str], name: str) -> str | None:
    pre = name.lower() + ":"
    for ln in lines:
        if ln.lower().startswith(pre):
            return ln[len(pre):].strip()
    return None


def _run(text: str) -> tuple[list[dict], Counter, dict]:
    rows: list[dict] = []
    reasons: Counter = Counter()
    n = {"funds": 0, "meetings": 0, "proposal_rows": 0}
    fund: str | None = None
    meeting: dict | None = None      # None -> rows under it are dropped
    in_table = False
    rec_label = ""                   # "" -> no header in force
    card = ""

    def reset_table() -> None:
        nonlocal meeting, rec_label, card
        meeting, rec_label, card = None, "", ""

    for tok in _TOKEN.finditer(text):
        kind = tok.lastgroup
        if kind == "p":
            m = re.match(r"<p[^>]*>", tok[0], re.I)
            if not _CENTER.search(m[0]):
                continue
            name = _clean(tok[0][m.end():-len("</p>")] if tok[0].lower().endswith("</p>")
                          else tok[0][m.end():])
            if not name or name.startswith(_COVER):
                continue
            fund = name
            n["funds"] += 1
            in_table = False
            reset_table()
        elif kind == "table":
            in_table = True
            reset_table()
        else:
            if not in_table:
                continue
            cells = _cells(tok[0])
            if not cells:
                continue
            tags = {c[0] for c in cells}
            if len(cells) == 1:
                tag, attrs, body = cells[0]
                lines = _lines(body)
                if tag == "td" and _label(lines, "Meeting Date") is not None:
                    reset_table()
                    n["meetings"] += 1
                    meeting = _meeting(lines, fund, reasons)
                elif tag == "td" and (_label(lines, "Ticker") is not None
                                      or _label(lines, "Security ID") is not None):
                    if meeting is not None:
                        meeting["ticker"] = _label(lines, "Ticker") or ""
                        meeting["security_id"] = _label(lines, "Security ID") or ""
                elif "colspan" in attrs.lower() and "proxy card" in _clean(body).lower():
                    card = _clean(body)
                continue
            if tags == {"th"} and len(cells) == 5:
                texts = [_clean(c[2]) for c in cells]
                if tuple(texts[:3]) == HEADER and texts[3] in REC_LABELS and texts[4] == "Vote Cast":
                    rec_label, card = REC_LABELS[texts[3]], ""
                else:
                    rec_label, card = "", ""
                    reasons["unrecognised_header"] += 1
                continue
            if "th" in tags or not rec_label:
                continue                      # filler rows, or rows before any header
            n["proposal_rows"] += 1
            if len(cells) != 5:
                reasons["bad_cell_count"] += 1
                continue
            if meeting is None:
                reasons["no_meeting"] += 1
                continue
            pid, ptext, sponsor, rec, vote = (_clean(c[2]) for c in cells)
            if not _ID.fullmatch(pid):
                reasons["bad_proposal_id"] += 1
            elif not ptext:
                reasons["empty_proposal_text"] += 1
            elif sponsor not in SPONSORS:
                reasons["bad_sponsor"] += 1
            elif rec not in RECS:
                reasons["bad_rec"] += 1
            elif vote not in VOTES:
                reasons["bad_vote"] += 1
            else:
                rows.append({**meeting, "rec_label": rec_label, "card_label": card,
                             "proposal_id": pid, "proposal_text": ptext, "rec": rec,
                             "vote": vote, "sponsor": sponsor})
    return rows, reasons, n


def _meeting(lines: list[str], fund: str | None, reasons: Counter) -> dict | None:
    if fund is None:
        reasons["no_fund"] += 1
        return None
    issuer = lines[0] if lines else ""
    if not issuer or issuer.lower().startswith("meeting date:"):
        reasons["no_issuer"] += 1
        return None
    md = _iso(_label(lines, "Meeting Date") or "")
    if not md:
        reasons["bad_meeting_date"] += 1
        return None
    return {"fund_heading": fund, "issuer_name": issuer, "ticker": "", "security_id": "",
            "meeting_date": md, "record_date": _iso(_label(lines, "Record Date") or ""),
            "meeting_type": _title(_label(lines, "Meeting Type") or "")}


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> dict:
    rows, reasons, n = _run(text)
    return {"rows": len(rows), "dropped": sum(reasons.values()), **n, "reasons": reasons}
