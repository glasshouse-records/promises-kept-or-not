"""Parser for the legacy N-PX "Registrant Voted" text layout (Global X style).

Block-oriented design, precision over recall (contract: docs/research/legacy-npx.md):

1. reduce the document to text lines (tags removed, entities unescaped);
2. split into fund sections at the column-header line
   ``Proposal  Proposed by  Mgt. Position  Registrant Voted`` (the heading is the
   non-empty line above it; a repeat with the same heading continues the fund);
3. split each fund into meeting blocks at the ``Security ID:`` lines (the issuer is
   the line above);
4. read each proposal's three right-hand columns by the character offsets of the
   column header that governs the line (the header repeats at every page break and
   its offsets drift by a few characters from page to page).

Anything that cannot be placed with certainty is dropped, never guessed, and the drop is
counted in ``parse_stats``.  Nothing carries across a meeting or fund boundary.
"""

from __future__ import annotations

import html
import re
from collections import Counter

_TAG = re.compile(r"<[^>]*>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADER = re.compile(
    r"^\s*Proposal\s+(?P<p>Proposed\s+by)\s+(?P<m>Mgt\.\s+Position)\s+(?P<r>Registrant\s+Voted)\s*$", re.I)
_SECURITY = re.compile(r"^\s*Security ID:(?P<sid>.*?)(?:Ticker:\s*(?P<tick>\S+)?)?\s*$")
_SUB_ADVISER = re.compile(r"^\s*Sub-Adviser:")
_MEETING = re.compile(r"^\s*Meeting Date:\s*(?P<date>\S+)\s+Meeting Type:(?P<type>.*)$")
_DATE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{2})$")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_PROPOSAL = re.compile(r"^ ?(?P<id>\d+(?:\.\d+(?:\.\d+)?|\.?[A-Za-z])?) +(?=\S)")
_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
_VOTED = re.compile(r"^Voted - (?P<v>\S.*)$")
_CAST = frozenset({"For", "Against", "Abstain", "Withhold", "Withheld", "1 Year", "2 Years", "3 Years"})

KEYS = ("fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
        "meeting_status", "meeting_type", "country", "proposal_id", "proposal_text",
        "proponent", "rec", "vote", "for_against")


def to_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = _TAG.sub("", _COMMENT.sub("", text))
    text = html.unescape(text).replace("\xa0", " ")
    return [ln.rstrip() for ln in text.split("\n")]


def _sections(lines: list[str]) -> list[tuple[str | None, list[tuple[str, tuple[int, int, int]]]]]:
    """(heading, [(line, header offsets)]) per fund; lines before the first header are dropped."""
    headers: dict[int, tuple[int, int, int]] = {}
    heading_at: dict[int, int | None] = {}
    consumed: set[int] = set()
    prev = None
    subs: list[int] = []  # Sub-Adviser lines since the last real line (R2: ignored)
    for i, ln in enumerate(lines):
        m = _HEADER.match(ln)
        if m:
            consumed.update(subs)
            headers[i] = (m.start("p"), m.start("m"), m.start("r"))
            heading_at[i] = prev
            if prev is not None:
                consumed.add(prev)
        if _SUB_ADVISER.match(ln):
            subs.append(i)
        elif ln.strip():
            prev = i
            subs = []
    sections: list[tuple[str | None, list]] = []
    cur_head: str | None = None
    offs = None
    for i, ln in enumerate(lines):
        if i in headers:
            hi = heading_at[i]
            head = lines[hi].strip() if hi is not None else None
            if offs is None or head != cur_head:
                sections.append((head, []))
                cur_head = head
            offs = headers[i]
            continue
        if offs is None or i in consumed:
            continue
        sections[-1][1].append((ln, offs))
    return sections


_VOTE = (r"Voted - For|Voted - Against|Voted - Abstain|Voted - Withhold|Voted - Withheld|Voted - Split|"
         r"Voted - 1 Year|Voted - 2 Years|Voted - 3 Years|Voted -Abstain|Voted -- For|Voted|"
         r"Take No Action|Non-Voting")
_COLS = re.compile(
    r"(?:^|\s)(?P<prop>Management|Shareholder|N/A)\s+"
    r"(?P<rec>For|Against|Abstain|Withhold|None|N/A|1 Year|2 Years|3 Years)\s+"
    rf"(?P<vote>{_VOTE})$")


def _cols(line: str):
    """None (not a column line) or (text_end, proponent, rec, vote), read from the END of the
    line with closed lists (R3); header offsets are not used."""
    m = _COLS.search(line)
    if not m:
        return None
    return m.start("prop"), m.group("prop"), m.group("rec"), m.group("vote")


def _vote(v: str) -> str:
    """'Voted - X' -> X only for the cast-vote vocabulary; everything else stays verbatim."""
    m = _VOTED.match(v)
    return m.group("v") if m and m.group("v") in _CAST else v


def _date(s: str) -> str | None:
    m = _DATE.match(s)
    if not m or m.group(2) not in _MONTHS:
        return None
    day, mon = int(m.group(1)), _MONTHS[m.group(2)]
    if not 1 <= day <= 31:
        return None
    return f"{mon:02d}/{day:02d}/20{m.group(3)}"


def _meeting(heading: str, ident: tuple[str, str, str], rest: list[tuple[str, tuple[int, int, int]]],
             stats: Counter) -> list[dict]:
    """`rest` = the block's non-blank lines from the `Meeting Date:` line on."""
    issuer, sid, tick = ident
    mt = _MEETING.match(rest[0][0]) if rest else None
    if not mt:
        stats["dropped_no_meeting_date"] += 1
        return []
    rest = rest[1:]
    date = _date(mt.group("date"))
    if date is None:
        stats["dropped_bad_date"] += 1
        return []
    mtype = mt.group("type").strip()
    if "contest" in mtype.lower():
        stats["dropped_contest"] += 1
        return []
    base = {
        "fund_heading": heading, "issuer_name": issuer,
        "ticker": tick, "security_id": sid,
        "meeting_date": date, "meeting_status": "", "meeting_type": mtype, "country": "",
        "for_against": "",
    }
    props: list[dict] = []
    cur: dict | None = None
    for ln, _offs in rest:
        if ln == ln.strip() and _PAGE_NUMBER.match(ln):
            stats["page_number_line"] += 1
            continue
        m = _PROPOSAL.match(ln)
        if m:
            cur = {"id": m.group("id"), "texts": [], "cols": []}
            props.append(cur)
            start = m.end()
        elif cur is None and not _cols(ln):
            stats["ignored_preamble_line"] += 1  # R3: note line before the first proposal
            continue
        elif cur is not None and ln[:2].isspace():
            start = 0
        else:
            stats["dropped_unrecognised_line"] += 1
            return []
        cols = _cols(ln)
        end = cols[0] if cols else len(ln)
        if end < start:
            stats["dropped_unrecognised_line"] += 1
            return []
        piece = ln[start:end].strip()
        if piece:
            cur["texts"].append(piece)
        if cols:
            cur["cols"].append(cols[1:])
    ids = [p["id"] for p in props]
    if len(set(ids)) != len(ids):
        stats["dropped_duplicate_proposal_id"] += 1
        return []
    rows = []
    for p in props:
        if len(p["cols"]) != 1:
            stats["dropped_no_columns" if not p["cols"] else "dropped_columns_on_two_lines"] += 1
            continue
        text = " ".join(p["texts"])
        if not text:
            stats["dropped_no_text"] += 1
            continue
        prop, rec, vote = p["cols"][0]
        rows.append({**base, "proposal_id": p["id"], "proposal_text": text,
                     "proponent": prop, "rec": rec, "vote": _vote(vote)})
    stats["meetings"] += 1
    return rows


def _run(text: str) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    rows: list[dict] = []
    for heading, items in _sections(to_lines(text)):
        stats["fund_sections"] += 1
        if not heading or _PAGE_NUMBER.match(heading):
            stats["dropped_bad_heading"] += 1
            continue
        starts: list[tuple[int, int, str]] = []  # (first line of block, Security ID / Meeting Date index, kind)
        prev_sid = -2
        last_nb = -1
        for i, (ln, _) in enumerate(items):
            if not ln.strip():
                continue
            if ln.lstrip().startswith("Security ID:"):
                prev_sid = i
                starts.append((last_nb, i, "sid"))
            elif _MEETING.match(ln) and last_nb != prev_sid:
                starts.append((i, i, "bare"))
            last_nb = i
        first = starts[0][0] if starts else len(items)
        orphans = [ln for ln, _ in items[:max(first, 0)] if ln.strip() and not _PAGE_NUMBER.match(ln.strip())]
        if orphans:
            stats["orphan_lines_before_first_meeting"] += len(orphans)
        ident = None  # (issuer, security_id, ticker) of the previous meeting of this fund
        for n, (k, sk, kind) in enumerate(starts):
            stop = starts[n + 1][0] if n + 1 < len(starts) else len(items)
            if kind == "sid":
                if k < 0:
                    stats["dropped_no_issuer"] += 1
                    ident = None
                    continue
                sec = _SECURITY.match(items[sk][0])
                issuer = items[k][0].strip()
                if not sec or not issuer:
                    stats["dropped_bad_security_line"] += 1
                    ident = None
                    continue
                ident = (issuer, sec.group("sid").strip(), sec.group("tick") or "")
                lines = [(ln, o) for ln, o in items[sk + 1:stop] if ln.strip()]
            else:
                if ident is None:
                    stats["dropped_bare_meeting_without_previous"] += 1
                    continue
                lines = [(ln, o) for ln, o in items[k:stop] if ln.strip()]
            rows.extend(_meeting(heading, ident, lines, stats))
    return rows, stats


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]
