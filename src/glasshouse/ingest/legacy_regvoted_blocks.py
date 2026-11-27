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
_SECURITY = re.compile(r"^\s*Security ID:\s*(?P<sid>(?!Ticker:)\S+)?\s*(?:Ticker:\s*(?P<tick>\S+)?)?\s*$")
_MEETING = re.compile(r"^\s*Meeting Date:\s*(?P<date>\S+)\s+Meeting Type:(?P<type>.*)$")
_DATE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{2})$")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_PROPOSAL = re.compile(r"^ ?(?P<id>\d+(?:\.\d+|\.?[A-Za-z])?) +(?=\S)")
_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
_VOTED = re.compile(r"^Voted - (?P<v>\S.*)$")
_CAST = frozenset({"For", "Against", "Abstain", "Withhold", "Withheld", "1 Year", "2 Years", "3 Years"})
# A proponent word may overrun its column start by this many characters when the proposal text
# above it is too long; the cut is then moved to the start of that word.
_OVERRUN = 3

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
    for i, ln in enumerate(lines):
        m = _HEADER.match(ln)
        if m:
            headers[i] = (m.start("p"), m.start("m"), m.start("r"))
            heading_at[i] = prev
            if prev is not None:
                consumed.add(prev)
        if ln.strip():
            prev = i
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


def _cols(line: str, offs: tuple[int, int, int]):
    """None (no columns), 'bad' (cannot be placed), or (text_end, proponent, rec, vote)."""
    c1, c2, c3 = offs
    if len(line.rstrip()) <= c1:
        return None
    if not line[c1 - 1].isspace() and not line[c1].isspace():  # inside a word
        s = c1
        while s > 0 and not line[s - 1].isspace():
            s -= 1
        if c1 - s > _OVERRUN:
            return "bad"
        c1 = s
    for c in (c2, c3):
        if c >= len(line) or (not line[c - 1].isspace() and not line[c].isspace()):
            return "bad"
    prop, rec, vote = line[c1:c2].strip(), line[c2:c3].strip(), line[c3:].strip()
    if not (prop or rec or vote):
        return None
    if not (prop and rec and vote):
        return "bad"
    # a cut that fell inside a multi-word field leaves wide gaps or a fragment: never guess
    if "  " in prop or "  " in rec or not vote[0].isalnum():
        return "bad"
    return c1, prop, rec, vote


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


def _meeting(heading: str, block: list[tuple[str, tuple[int, int, int]]], stats: Counter) -> list[dict]:
    issuer = block[0][0].strip()
    sec = _SECURITY.match(block[1][0])
    if not issuer or not sec:
        stats["dropped_bad_security_line"] += 1
        return []
    rest = [(ln, o) for ln, o in block[2:] if ln.strip()]
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
        "ticker": sec.group("tick") or "", "security_id": sec.group("sid") or "",
        "meeting_date": date, "meeting_status": "", "meeting_type": mtype, "country": "",
        "for_against": "",
    }
    props: list[dict] = []
    cur: dict | None = None
    for ln, offs in rest:
        if ln == ln.strip() and _PAGE_NUMBER.match(ln):
            stats["page_number_line"] += 1
            continue
        m = _PROPOSAL.match(ln)
        if m:
            cur = {"id": m.group("id"), "texts": [], "cols": []}
            props.append(cur)
            start = m.end()
        elif cur is not None and ln[:2].isspace():
            start = 0
        else:
            stats["dropped_unrecognised_line"] += 1
            return []
        cols = _cols(ln, offs)
        if cols == "bad":
            stats["dropped_unaligned_line"] += 1
            return []
        end = cols[0] if cols else len(ln)
        if end < start:
            stats["dropped_unaligned_line"] += 1
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
        starts = [i for i, (ln, _) in enumerate(items) if _SECURITY.match(ln) or ln.lstrip().startswith("Security ID:")]
        if any(ln.strip() for ln, _ in items[: (starts[0] - 1 if starts else len(items))]):
            stats["orphan_lines_before_first_meeting"] += 1
        for n, k in enumerate(starts):
            if k == 0 or not items[k - 1][0].strip():
                stats["dropped_no_issuer"] += 1
                continue
            stop = starts[n + 1] - 1 if n + 1 < len(starts) else len(items)
            rows.extend(_meeting(heading, items[k - 1:stop], stats))
    return rows, stats


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]
