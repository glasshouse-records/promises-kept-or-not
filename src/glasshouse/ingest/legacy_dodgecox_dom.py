"""Dodge & Cox N-PX (2022-23) table parser, DOM/event-walker flavour.

Implements the contract D1-D9 in docs/research/legacy-npx.md using
html.parser as a tag-event walker (no regexes over markup).  The document is
reduced to an ordered stream of items: ``("block", text)`` for text outside
tables and ``("table", rows)`` with each row a list of cleaned cell texts.

Choices where the contract is silent (drop and count, never repair):
  * rows with no non-empty cell are ignored (the width-spacer rows);
  * a meeting header whose Ticker/Security ID/Meeting Date label is present
    but has an empty value is `bad_meeting_header`;
  * the issuer block is only searched since the previous table ended;
  * a continuation following a proposal row that was dropped for a closed-list
    violation is absorbed and counted `continuation_of_dropped`;
  * a row failing several closed lists is counted once (number, rec, vote,
    sponsor, in that order);
  * a continuation is a row whose only non-empty cell is raw cell index 2
    (the text column of the # | spacer | text | ... layout);
  * unknown/empty-heading cases: if no issuer block exists for the first
    meeting the heading is the second-to-last block before the table.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser

from .legacy_issueno import KEYS

LABELS = ("Ticker:", "Security ID:", "Meeting Date:", "Meeting Type:", "Record Date:")
REQUIRED = ("Ticker:", "Security ID:", "Meeting Date:")
COLUMN_HEADER = ["#", "Proposal", "Mgt Rec", "Vote Cast", "Sponsor"]
RECS = {"For", "Against", "None", "One Year", "Three Years"}
VOTES = {"For", "Against", "Abstain", "Did Not Vote", "None", "One Year", "Three Years"}
SPONSORS = {"Management", "Shareholder"}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
BLOCK_TAGS = {"p", "br", "div"}
NUMBER_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.")


def _clean(s: str) -> str:
    return " ".join(s.replace("\xa0", " ").split())


class _Walker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple] = []
        self._buf: list[str] = []
        self._depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def _flush_block(self) -> None:
        t = _clean("".join(self._buf))
        self._buf = []
        if t:
            self.items.append(("block", t))

    def _close_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
        self._cell = None

    def _close_row(self) -> None:
        self._close_cell()
        if self._row is not None:
            self._rows.append(self._row)
        self._row = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            if self._depth == 0:
                self._flush_block()
                self._rows = []
            self._depth += 1
        elif self._depth:
            if tag == "tr":
                self._close_row()
                self._row = []
            elif tag in ("td", "th"):
                self._close_cell()
                if self._row is None:
                    self._row = []
                self._cell = []
        elif tag in BLOCK_TAGS:
            self._flush_block()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "table" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self._close_row()
                self.items.append(("table", self._rows))
                self._rows = []
        elif self._depth:
            if tag == "tr":
                self._close_row()
            elif tag in ("td", "th"):
                self._close_cell()
        elif tag in BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data):
        if self._skip:
            return
        if self._depth:
            if self._cell is not None:
                self._cell.append(data)
        else:
            self._buf.append(data)

    def finish(self):
        self.close()
        if self._depth:  # unterminated table: close it
            self._depth = 0
            self._close_row()
            self.items.append(("table", self._rows))
        self._flush_block()
        return self.items


def _is_page_marker(t: str) -> bool:
    return t.startswith("Page ") and t[5:].isdigit() and t[5:].isascii()


def _header_cells(rows):
    return [c for r in rows for c in r if c]


def _is_meeting_header(rows) -> bool:
    return any(c == "Ticker:" for r in rows for c in r)


def _is_signature(rows) -> bool:
    return any("(Registrant)" in c for r in rows for c in r)


def _parse_header(rows):
    """-> dict of label->value, or None when D2 drops the meeting."""
    cells = _header_cells(rows)
    seen: dict[str, str] = {}
    for i, c in enumerate(cells):
        if c in LABELS:
            if c in seen:
                return None
            nxt = cells[i + 1] if i + 1 < len(cells) else ""
            seen[c] = "" if nxt in LABELS else nxt
    if any(not seen.get(k) for k in REQUIRED):
        return None
    return seen


def _iso_date(s: str):
    parts = s.split(" ")
    if len(parts) != 3:
        return None
    mon, day, year = parts
    if not (day.endswith(",") and mon in MONTHS):
        return None
    day = day[:-1]
    if not (day.isascii() and day.isdigit() and 1 <= len(day) <= 2):
        return None
    if not (year.isascii() and year.isdigit() and len(year) == 4):
        return None
    d = int(day)
    if not 1 <= d <= 31:
        return None
    return f"{year}-{MONTHS[mon]:02d}-{d:02d}"


def _run(text: str):
    items = _Walker()
    items.feed(text)
    items = items.finish()
    stats: Counter = Counter()
    out: list[dict] = []
    first = next((i for i, it in enumerate(items)
                  if it[0] == "table" and _is_meeting_header(it[1])), None)
    if first is None:
        return out, stats

    # D1: heading = last non-empty block before the first issuer block.
    pre = [it[1] for it in items[:first] if it[0] == "block"]
    last_tbl = max((i for i, it in enumerate(items[:first]) if it[0] == "table"), default=-1)
    gap = [it[1] for it in items[last_tbl + 1:first]]
    ids = [i for i, b in enumerate(gap) if not _is_page_marker(b)]
    if ids:
        k = len(pre) - len(gap) + ids[-1]
        heading = pre[k - 1] if k >= 1 else ""
    else:
        heading = pre[-2] if len(pre) >= 2 else ""
    if not (heading.startswith("Dodge & Cox ") and heading.endswith("Fund")):
        stats["no_fund_heading"] += 1
        return out, stats

    meeting = None  # dict while a meeting is open; None otherwise
    gap = []
    for kind, val in items:
        if kind == "block":
            gap.append(val)
            continue
        rows, blocks, gap = val, gap, []
        if _is_meeting_header(rows):
            if meeting is not None:
                _close(meeting, out, stats)
            meeting = _open(rows, blocks, heading, stats)
            continue
        if meeting is None:
            continue
        if _is_signature(rows):
            _close(meeting, out, stats)
            meeting = None
            continue
        if meeting["dead"]:
            continue
        for r in rows:
            _row(meeting, r, stats)
            if meeting["dead"]:
                break
    if meeting is not None:
        _close(meeting, out, stats)
    return out, stats


def _open(rows, blocks, heading, stats):
    m = {"dead": False, "rows": [], "last": None, "base": None, "seen": False}
    hdr = _parse_header(rows)
    if hdr is None:
        stats["bad_meeting_header"] += 1
        m["dead"] = True
        return m
    issuer = ""
    for b in reversed(blocks):
        if not _is_page_marker(b):
            issuer = b
            break
    if not issuer:
        stats["no_issuer"] += 1
        m["dead"] = True
        return m
    date = _iso_date(hdr["Meeting Date:"])
    if date is None:
        stats["bad_meeting_date"] += 1
        m["dead"] = True
        return m
    m["base"] = {
        "fund_heading": heading, "issuer_name": issuer, "ticker": hdr["Ticker:"],
        "security_id": hdr["Security ID:"], "meeting_date": date,
        "meeting_status": "", "meeting_type": hdr.get("Meeting Type:", ""),
        "country": "", "for_against": "",
    }
    return m


def _drop_meeting(m, key, stats):
    stats[key] += 1
    m["dead"] = True
    m["rows"] = []


def _row(m, raw, stats):
    cells = [c for c in raw if c]
    if not cells or cells == COLUMN_HEADER:
        return
    if len(cells) == 5:
        num, text, rec, vote, sponsor = cells
        m["seen"] = True
        if not num or not set(num) <= NUMBER_CHARS:
            key = "bad_number"
        elif rec not in RECS:
            key = "bad_rec"
        elif vote not in VOTES:
            key = "bad_vote"
        elif sponsor not in SPONSORS:
            key = "bad_sponsor"
        else:
            full = dict(m["base"], proposal_id=num, proposal_text=text,
                        proponent=sponsor, rec=rec, vote=vote)
            row = {k: full[k] for k in KEYS}
            m["rows"].append(row)
            m["last"] = row
            return
        stats[key] += 1
        m["last"] = None
        return
    # D6 continuation: the single non-empty cell is the text column (raw
    # cell index 2 of the spacer layout: # | sp | text | sp | rec ...).
    if len(cells) == 1 and raw.index(cells[0]) == 2 and raw[2] == cells[0]:
        if m["last"] is not None:
            m["last"]["proposal_text"] += " " + cells[0]
        elif m["seen"]:
            stats["continuation_of_dropped"] += 1
        else:
            _drop_meeting(m, "orphan_continuation", stats)
        return
    _drop_meeting(m, "bad_row", stats)


def _close(m, out, stats):
    if m["dead"]:
        return
    out.extend(m["rows"])
    stats["rows"] += len(m["rows"])


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]


__all__ = ["parse", "parse_stats", "KEYS"]
