"""Legacy N-PX 'Registrant Voted' text layout: a line-by-line regex state machine.

Contract: the last section of docs/research/legacy-npx.md. Every line is classified
(fund heading + column header, issuer line, Security ID line, Meeting Date line,
numbered proposal line, indented continuation, page number, end marker) and a small
state machine advances. Precision over recall: a line that fits no rule inside a
meeting drops that meeting (counted), never a silent skip; a proposal whose three
right-hand columns are not on exactly one line is dropped (counted).

`parse(text)` returns rows with exactly the 14 keys of `legacy_issueno.KEYS`;
`parse_stats(text)` returns a Counter of everything dropped.
"""

from __future__ import annotations

import html as _html
import re
from collections import Counter
from datetime import datetime

KEYS = ("fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
        "meeting_status", "meeting_type", "country", "proposal_id", "proposal_text",
        "proponent", "rec", "vote", "for_against")

_TAG = re.compile(r"</?[A-Za-z!][^<>]*>")
_COLHDR = re.compile(r"^\s*Proposal\s+Proposed\s+by\s+Mgt\.?\s+Position\s+Registrant\s+Voted\s*$", re.I)
_SECID_LINE = re.compile(r"^\s*Security ID:")
_SECID = re.compile(r"^\s*Security ID:\s*(?P<sid>(?!Ticker:)\S*)(?:\s+Ticker:\s*(?P<tk>\S*))?\s*$")
_MEETING = re.compile(r"^\s*Meeting Date:\s*(?P<d>\S*)(?:\s+Meeting Type:\s*(?P<t>.*?))?\s*$")
_DATE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2})$")
_PAGE_NO = re.compile(r"^\d{1,4}$")
_END = re.compile(r"^\s*SIGNATURES?\s*$")
_ID = r"\d+(?:\.[0-9A-Za-z]+)*[A-Za-z]?"
# The contract says "two or more spaces" after the id, but the id column is padded to the
# widest id of the page: "10 Shareholder ..." has ONE space in the real filing (36k lines).
_PROPOSAL = re.compile(rf"^ ?(?P<id>{_ID})\s+(?P<rest>\S.*)$")
_CONTINUATION = re.compile(r"^ {2,}\S")
# Right-hand columns, anchored at the end of the line. The proponent is one of the
# known words, or any one token set off from the text by two or more spaces.
_COLS = re.compile(
    r"^(?P<head>.*?)(?:(?<=\s)|^)"
    r"(?:(?P<prop>Management|Shareholder|N/A)|(?<=\s\s)(?P<prop2>\S+))"
    r"\s+(?P<rec>\S+(?: Years?)?)\s+"
    r"(?P<vote>Voted\b.*|Take No Action|Non-Voting)$"
)


def _lines(text: str) -> list[str]:
    out = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _html.unescape(_TAG.sub("", raw)).replace("\xa0", " ")
        out.append(line.rstrip())
    return out


def _date(s: str) -> str | None:
    m = _DATE.match(s)
    if not m:
        return None
    try:
        d = datetime.strptime(f"{m.group(1)}-{m.group(2).title()}-{m.group(3)}", "%d-%b-%y")
    except ValueError:
        return None
    return d.strftime("%m/%d/%Y")


# 'Voted - X' loses its prefix only when X is a real vote; 'Voted - Split' and the
# malformed spellings ('Voted -Abstain', 'Voted -- For', bare 'Voted') stay verbatim.
_VOTED = {"For", "Against", "Abstain", "Withhold", "Withheld", "N/A",
          "1 Year", "2 Years", "3 Years"}


def _vote(v: str) -> str:
    v = v.strip()
    if v.startswith("Voted - ") and v[8:] in _VOTED:
        return v[8:]
    return v


class _Meeting:
    def __init__(self, fund: str, issuer: str):
        self.fund, self.issuer = fund, issuer
        self.ticker = self.sid = self.date = self.mtype = ""
        self.bad = False
        self.stage = "secid"  # secid -> date -> body
        self.blocks: list[dict] = []

    def row(self, b: dict) -> dict:
        return {
            "fund_heading": self.fund, "issuer_name": self.issuer, "ticker": self.ticker,
            "security_id": self.sid, "meeting_date": self.date, "meeting_status": "",
            "meeting_type": self.mtype, "country": "", "proposal_id": b["id"],
            "proposal_text": " ".join(b["text"]), "proponent": b["cols"][0],
            "rec": b["cols"][1], "vote": _vote(b["cols"][2]), "for_against": "",
        }


def _run(text: str) -> tuple[list[dict], Counter]:
    L = _lines(text)
    n = len(L)
    stats: Counter = Counter()
    rows: list[dict] = []

    def next_nonempty(i: int) -> int | None:
        for j in range(i + 1, n):
            if L[j].strip():
                return j
        return None

    def close(m: _Meeting | None) -> None:
        if m is None or m.bad:
            return
        ids = [b["id"] for b in m.blocks]
        if len(set(ids)) != len(ids):
            stats["meeting_duplicate_proposal_id"] += 1
            return
        if "contest" in m.mtype.lower():
            stats["meeting_contest"] += 1
            return
        for b in m.blocks:
            if b["ncols"] == 0:
                stats["proposal_without_columns"] += 1
            elif b["ncols"] > 1:
                stats["proposal_multiple_column_lines"] += 1
            else:
                rows.append(m.row(b))

    def spoil(m: _Meeting, why: str) -> None:
        m.bad = True
        stats[why] += 1

    fund: str | None = None
    ident: tuple[str, str, str] | None = None  # issuer, security id, ticker of the fund's last meeting
    meet: _Meeting | None = None
    prev_ne: int | None = None  # index of the last non-empty line
    i = 0
    while i < n:
        line = L[i]
        if not line.strip():
            i += 1
            continue
        cur_prev, prev_ne = prev_ne, i
        if _END.match(line):
            break
        if _COLHDR.match(line):
            # heading handled at the line above; a bare header with no heading is stray
            if fund is None or cur_prev is None:
                stats["stray_line"] += 1
            i += 1
            continue
        nxt = next_nonempty(i)
        if nxt is not None and _COLHDR.match(L[nxt]):
            if line.strip() != fund:
                close(meet)
                meet = None
                ident = None
                fund = line.strip()
            i += 1
            continue
        if fund is None:
            i += 1  # leading "Non-Voting Funds" list and cover pages: nothing counts
            continue
        if _PAGE_NO.match(line):
            stats["page_number"] += 1
            i += 1
            continue
        if nxt is not None and _SECID_LINE.match(L[nxt]) and not _SECID_LINE.match(line):
            close(meet)
            meet = _Meeting(fund, line.strip())
            ident = None
            i += 1
            continue
        if _MEETING.match(line) and not (meet is not None and meet.stage == "date"):
            # R1: a Meeting Date line not below a Security ID line is another meeting of the
            # same issuer (identity of the fund's previous meeting), else it is dropped
            close(meet)
            if ident is None:
                meet = _Meeting(fund, "")
                spoil(meet, "meeting_date_without_issuer")
            else:
                meet = _Meeting(fund, ident[0])
                meet.sid, meet.ticker = ident[1], ident[2]
                meet.stage = "date"
                continue  # same line again, now below a (inherited) identity
            i += 1
            continue
        if meet is None:
            stats["proposal_without_meeting" if _PROPOSAL.match(line) else "stray_line"] += 1
            i += 1
            continue
        if meet.bad:
            i += 1
            continue
        if meet.stage == "secid":
            m = _SECID.match(line)
            if not m:
                spoil(meet, "meeting_unplaced_line")
            else:
                meet.sid, meet.ticker = m.group("sid"), m.group("tk") or ""
                meet.stage = "date"
                ident = (meet.issuer, meet.sid, meet.ticker)
            i += 1
            continue
        if meet.stage == "date":
            m = _MEETING.match(line)
            d = _date(m.group("d")) if m else None
            if not m:
                spoil(meet, "meeting_unplaced_line")
            elif d is None:
                spoil(meet, "meeting_bad_date")
            else:
                meet.date, meet.mtype = d, (m.group("t") or "").strip()
                meet.stage = "body"
            i += 1
            continue
        p = _PROPOSAL.match(line)
        if p:
            block = {"id": p.group("id"), "text": [], "cols": None, "ncols": 0}
            meet.blocks.append(block)
            body = p.group("rest")
        elif _CONTINUATION.match(line) and meet.blocks:
            block = meet.blocks[-1]
            body = line.strip()
        else:
            spoil(meet, "meeting_unplaced_line")
            i += 1
            continue
        c = _COLS.match(body)
        if c:
            block["ncols"] += 1
            block["cols"] = (c.group("prop") or c.group("prop2"), c.group("rec"), c.group("vote").strip())
            body = c.group("head").strip()
        if body:
            block["text"].append(" ".join(body.split()))
        i += 1
    close(meet)
    return rows, stats


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]
