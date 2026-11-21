"""Legacy N-PX "FORM N-Px REPORT" (ISS text) parser: STRUCTURAL approach.

The document is split into fund sections on '='-framed headings, each section
into meeting blocks on dashed separator lines, the labelled header fields of
each block are read, and proposal lines are sliced by the character offsets of
the column-header words ('#', 'Proposal', 'Mgt Rec'/'Diss Rec', 'Vote Cast',
'Sponsor').

Precision over recall: anything ambiguous (a word crossing a column boundary,
a wrapped recommendation, a value outside the closed vocabularies below, a
continuation line we cannot attribute) drops that proposal or meeting and is
counted under a reason in ``parse_stats``. Nothing is ever guessed.
"""

from __future__ import annotations

import html as _html
import re
from collections import Counter
from datetime import datetime

# Closed vocabularies (compared literally, case-sensitive), taken from the real
# FY2022-23 samples. Anything else is dropped, never normalised.
REC_VOCAB = frozenset(
    {
        "For",
        "Against",
        "Abstain",
        "Withhold",
        "None",
        "Do Not Vote",
        "Did Not Vote",
        "1 Year",
        "2 Years",
        "3 Years",
        "One Year",
        "Two Years",
        "Three Years",
        "Take No Action",
        "FOR",
        "AGAINST",
        "N/A",
        "No Vote",
    }
)
VOTE_VOCAB = REC_VOCAB | {"TNA", "Withheld"}
SPONSOR_VOCAB = frozenset({"Management", "Shareholder"})
REC_LABELS = ("Mgt Rec", "Diss Rec")

_FRAME_RE = re.compile(r"^=+\s*([^=\s].*?)\s*=+\s*$")
_END_RE = re.compile(r"^=+\s*END NPX REPORT\b")
_STAR_RE = re.compile(r"^\*+ FORM N-Px REPORT \*+\s*$")
_DASH_RE = re.compile(r"^\s*-{40,}\s*$")
_PAGE_RE = re.compile(r"^\s*<PAGE>\s*$")
_TICKER_RE = re.compile(r"^Ticker:\s*(.*?)\s*Security ID:\s*(.*?)\s*$")
_MEETING_RE = re.compile(r"^Meeting Date:\s*(.*?)\s*Meeting Type:\s*(.*?)\s*$")
_RECORD_RE = re.compile(r"^Record Date:\s*(.*?)\s*$")
_COLHDR_RE = re.compile(r"^#\s+Proposal\s+(Mgt Rec|Diss Rec)\s+Vote Cast\s+Sponsor\s*$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-()]*$")
_CARD_RE = re.compile(r"proxy card|card\)", re.I)
_HTML_RE = re.compile(r"<\s*(pre|html|body|div|br|p|font|hr)\b", re.I)
_TAG_RE = re.compile(r"<[^>]*>")


def _ws(s: str) -> str:
    return " ".join(s.split())


def _to_text(text: str) -> list[str]:
    if _HTML_RE.search(text):
        text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.I)
        text = _TAG_RE.sub("", text)
        text = _html.unescape(text)
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    return [ln.rstrip() for ln in text.split("\n")]


def _iso(s: str, fmt: str = "%b %d, %Y") -> str:
    try:
        return datetime.strptime(s.strip().title(), fmt).date().isoformat()
    except ValueError:
        return ""


# --------------------------------------------------------------------------
# Level 1: fund sections
# --------------------------------------------------------------------------
def _sections(lines: list[str]):
    """Yield (fund_heading | None, [lines]) for each fund section."""
    heading: str | None = None
    buf: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        m = _FRAME_RE.match(ln)
        if m and set(m.group(1)) != {"="}:
            parts = [m.group(1)]
            i += 1
            while i < n and (m2 := _FRAME_RE.match(lines[i])) and set(m2.group(1)) != {"="}:
                parts.append(m2.group(1))
                i += 1
            # "= Fund - =====" then an unframed, indented line naming the adviser.
            if parts[-1].endswith("-") and i < n and lines[i][:1] == " " and lines[i].strip() \
                    and not lines[i].lstrip().startswith(("=", "#", "-")):
                parts.append(lines[i])
                i += 1
            yield heading, buf
            heading, buf = _ws(" ".join(parts)), []
            continue
        if _END_RE.match(ln) or _STAR_RE.match(ln):
            yield heading, buf
            heading, buf = None, []
            i += 1
            continue
        buf.append("" if _PAGE_RE.match(ln) else ln)
        i += 1
    yield heading, buf


def _blocks(lines: list[str]):
    cur: list[str] = []
    for ln in lines:
        if _DASH_RE.match(ln):
            yield cur
            cur = []
        else:
            cur.append(ln)
    yield cur


# --------------------------------------------------------------------------
# Level 2: one meeting block
# --------------------------------------------------------------------------
def _parse_header(pre: list[str]):
    """Read labelled fields. Returns (fields | None, reason)."""
    issuer: list[str] = []
    ticker = sec = mtype = None
    mdate = ""
    rdate_raw = None
    seen_ticker = seen_mdate = False
    last = None  # which wrapped field a bare line would belong to
    for ln in pre:
        s = ln.strip()
        if not s:
            continue
        if m := _TICKER_RE.match(s):
            if seen_ticker:
                return None, "duplicate_ticker_line"
            seen_ticker = True
            ticker, sec, last = m.group(1), m.group(2), "ticker"
        elif m := _MEETING_RE.match(s):
            if seen_mdate:
                return None, "duplicate_meeting_line"
            seen_mdate = True
            mdate, mtype, last = m.group(1), m.group(2), "mtype"
        elif m := _RECORD_RE.match(s):
            if rdate_raw is not None:
                return None, "duplicate_record_line"
            rdate_raw, last = m.group(1), "record"
        elif not seen_ticker:
            issuer.append(s)
        elif last == "mtype":
            mtype = (mtype + " " + s).strip()
        else:
            return None, "unlabelled_header_line"
    if not seen_mdate or not seen_ticker:
        return None, "missing_header_field"
    d = _iso(mdate)
    if not d:
        return None, "meeting_date_unparseable"
    if not issuer:
        return None, "issuer_missing"
    if len(issuer) > 1:
        return None, "issuer_ambiguous"
    r = ""
    if rdate_raw:
        r = _iso(rdate_raw)
        if not r:
            return None, "record_date_unparseable"
    if not mtype:
        return None, "meeting_type_missing"
    return (
        {
            "issuer_name": _ws(issuer[0]),
            "ticker": ticker.strip(),
            "security_id": sec.strip(),
            "meeting_date": d,
            "meeting_type": _ws(mtype),
            "record_date": r,
        },
        "",
    )


class _Cols:
    __slots__ = ("ip", "ir", "iv", "isp", "label")

    def __init__(self, line: str):
        self.ip = line.index("Proposal")
        m = re.search(r"Mgt Rec|Diss Rec", line)
        self.ir = m.start()
        self.label = m.group(0)
        self.iv = line.index("Vote Cast")
        self.isp = line.index("Sponsor")


def _scan_proposals(body: list[str]):
    """Return list of raw proposals (dict with fields or a 'bad' reason)."""
    out: list[dict] = []
    cols: _Cols | None = None
    card = ""
    cur: dict | None = None
    group: list[str] = []
    pre = False  # after a column header, before its first proposal

    def flush_group():
        nonlocal card, group
        if group:
            g = _ws(" ".join(group))
            if _CARD_RE.search(g):
                card = g
        group = []

    for ln in body:
        if not ln.strip():
            flush_group()
            cur = None if cur is None else cur  # blank: continuation closes below
            if cur is not None:
                cur["closed"] = True
            continue
        if _COLHDR_RE.match(ln.strip()) and ln.lstrip().startswith("#"):
            flush_group()
            cols, pre, cur = _Cols(ln), True, None
            continue
        if cols is None:
            continue  # stray text before any column header
        first = ln[: cols.ip]
        if first.strip():  # proposal line
            flush_group()
            pre = False
            cur = {
                "card": card,
                "rec_label": cols.label,
                "bad": "",
                "closed": False,
                "texts": [],
                "line": ln,
            }
            out.append(cur)
            ln_ = ln.ljust(cols.isp + 1)
            pid = ln_[: cols.ip]
            if pid[-1] != " " or not _ID_RE.match(pid.strip()):
                cur["bad"] = "bad_id"
            for idx in (cols.ir, cols.iv, cols.isp):
                if ln_[idx - 1] != " ":
                    cur["bad"] = cur["bad"] or "column_overflow"
            cur.update(
                pid=pid.strip(),
                rec=ln_[cols.ir : cols.iv].strip(),
                vote=ln_[cols.iv : cols.isp].strip(),
                sponsor=ln_[cols.isp :].strip(),
            )
            cur["texts"].append(ln_[cols.ip : cols.ir].strip())
            continue
        # no id in first column
        if pre or cur is None:
            if pre:
                group.append(ln.strip())  # heading text / card label
            elif cur is None and out:
                # continuation after a blank line: cannot attribute safely
                out[-1]["bad"] = out[-1]["bad"] or "continuation_after_blank"
            continue
        if cur["closed"]:
            cur["bad"] = cur["bad"] or "continuation_after_blank"
            continue
        ln_ = ln.ljust(cols.isp + 1)
        if ln_[cols.isp :].strip() or any(ln_[i - 1] != " " for i in (cols.ir, cols.iv)):
            cur["bad"] = cur["bad"] or "continuation_beyond_text_column"
            continue
        # A value wrapped inside its own column ("Three" / "Years") continues that column.
        for key, part in (("rec", ln_[cols.ir : cols.iv]), ("vote", ln_[cols.iv : cols.isp])):
            if part.strip():
                cur[key] = _ws(f"{cur[key]} {part}")
        if ln_[cols.ip : cols.ir].strip():
            cur["texts"].append(ln_[cols.ip : cols.ir].strip())
    flush_group()
    return out


def _walk(text: str):
    """Yield (meeting_fields | None, reason, fund_heading, [proposals])."""
    for heading, lines in _sections(_to_text(text)):
        for blk in _blocks(lines):
            hdr_i = next((i for i, ln in enumerate(blk) if _COLHDR_RE.match(ln.strip())), None)
            is_meeting = hdr_i is not None or any(
                _TICKER_RE.match(ln.strip()) or _MEETING_RE.match(ln.strip()) for ln in blk
            )
            if not is_meeting:
                continue
            if hdr_i is None:
                yield None, "no_column_header", heading, []
                continue
            props = _scan_proposals(blk[hdr_i:])
            fields, reason = _parse_header(blk[:hdr_i])
            if heading is None:
                fields, reason = None, "no_fund_heading"
            yield fields, reason, heading, props


def _row(fields, heading, p) -> tuple[dict | None, str]:
    if p["bad"]:
        return None, p["bad"]
    text = _ws(" ".join(p["texts"]))
    if not text:
        return None, "empty_text"
    if not p["vote"]:
        return None, "empty_vote"
    if p["vote"] not in VOTE_VOCAB:
        return None, "vote_not_in_vocab"
    if p["rec"] not in REC_VOCAB:
        return None, "rec_not_in_vocab"
    if p["sponsor"] not in SPONSOR_VOCAB:
        return None, "sponsor_not_in_vocab"
    return (
        {
            "fund_heading": heading,
            **{k: fields[k] for k in ("issuer_name", "ticker", "security_id", "meeting_date", "meeting_type", "record_date")},
            "rec_label": p["rec_label"],
            "card_label": p["card"],
            "proposal_id": p["pid"],
            "proposal_text": text,
            "rec": p["rec"],
            "vote": p["vote"],
            "sponsor": p["sponsor"],
        },
        "",
    )


def parse(text: str) -> list[dict]:
    rows: list[dict] = []
    for fields, _reason, heading, props in _walk(text):
        if fields is None:
            continue
        for p in props:
            row, _r = _row(fields, heading, p)
            if row:
                rows.append(row)
    return rows


def parse_stats(text: str) -> dict:
    st = {
        "meetings_seen": 0,
        "meetings_dropped": 0,
        "proposals_seen": 0,
        "proposals_emitted": 0,
        "proposals_dropped": 0,
        "reasons": Counter(),
    }
    for fields, reason, heading, props in _walk(text):
        st["meetings_seen"] += 1
        st["proposals_seen"] += len(props)
        if fields is None:
            st["meetings_dropped"] += 1
            st["reasons"]["meeting:" + reason] += 1
            st["proposals_dropped"] += len(props)
            if props:
                st["reasons"]["proposal:meeting_dropped"] += len(props)
            continue
        for p in props:
            row, r = _row(fields, heading, p)
            if row:
                st["proposals_emitted"] += 1
            else:
                st["proposals_dropped"] += 1
                st["reasons"]["proposal:" + r] += 1
    return st
