"""Dodge & Cox legacy N-PX table, regex-over-markup parser (contract D1-D9).

Contract: docs/research/legacy-npx.md, "Contract: Dodge & Cox table (2026-11-27)".
The document is split with regular expressions into table and non-table segments,
tables into rows (`<tr>`) and cells (`<td>`/`<th>`); no HTML parser is used.

Where the contract is silent the choice is to drop and count, never to repair:
  * no `Ticker:` table -> [] with no counter (D9); no usable heading -> `no_fund_heading`.
  * a meeting is checked in the order header, issuer, date; the first failure is its one counter.
  * a dropped proposal row checks number, rec, vote, sponsor, in that order (one counter).
  * a continuation after a dropped proposal row attaches to it and is silently lost.
  * per-row counters of a meeting that is later dropped are not reported; `rows` counts kept rows.
  * the text column of a continuation is the raw cell index of `Proposal` in the table's
    last column-header row (fallback: raw index 2).
  * calendar-invalid dates (FEB 30) are `bad_meeting_date`.
"""
from __future__ import annotations

import collections
import datetime
import html
import re

from glasshouse.ingest.legacy_issueno import KEYS

_TABLE = re.compile(r"<table\b.*?</table\s*>", re.I | re.S)
_STRIP = re.compile(r"<(script|style)\b.*?</\1\s*>|<!--.*?-->", re.I | re.S)
_BLOCK_SPLIT = re.compile(r"</?(?:p|br|div)\b[^>]*>", re.I)
_TR = re.compile(r"<tr\b[^>]*>", re.I)
_TD = re.compile(r"<t[dh]\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_PAGE = re.compile(r"Page [0-9]+")
_DATE = re.compile(r"([A-Z]{3}) ([0-9]{1,2}), ([0-9]{4})")
_NUMBER = re.compile(r"[0-9A-Za-z.]+")
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
_LABELS = ("Ticker:", "Security ID:", "Meeting Date:", "Meeting Type:", "Record Date:")
_HEADER_ROW = ["#", "Proposal", "Mgt Rec", "Vote Cast", "Sponsor"]
_RECS = {"For", "Against", "None", "One Year", "Three Years"}
_VOTES = {"For", "Against", "Abstain", "Did Not Vote", "None", "One Year", "Three Years"}
_SPONSORS = {"Management", "Shareholder"}


def _clean(s: str) -> str:
    s = html.unescape(_TAG.sub("", s)).replace("\xa0", " ")
    return " ".join(s.split())


def _segments(text: str):
    """Yield ('block', str) and ('table', [row, ...]); a row is its list of raw cleaned cells."""
    text = _STRIP.sub("", text)
    pos = 0
    for m in _TABLE.finditer(text):
        yield from _blocks(text[pos:m.start()])
        rows = []
        for chunk in _TR.split(m.group(0))[1:]:
            rows.append([_clean(c) for c in _TD.split(chunk)[1:]])
        yield "table", rows
        pos = m.end()
    yield from _blocks(text[pos:])


def _blocks(frag: str):
    for part in _BLOCK_SPLIT.split(frag):
        c = _clean(part)
        if c:
            yield "block", c


def _header(rows):
    """Return the meeting-header dict, or None when the table has no `Ticker:` cell,
    or False when it is a header that must drop (duplicate/missing labels)."""
    cells = [c for r in rows for c in r if c]
    if "Ticker:" not in cells:
        return None
    vals: dict[str, str] = {}
    for i, c in enumerate(cells):
        if c in _LABELS:
            if c in vals:
                return False
            nxt = cells[i + 1] if i + 1 < len(cells) else ""
            vals[c] = "" if nxt in _LABELS else nxt
    if not all(k in vals for k in ("Ticker:", "Security ID:", "Meeting Date:")):
        return False
    return vals


def _meeting_date(s: str):
    m = _DATE.fullmatch(s)
    if not m or m.group(1) not in _MONTHS:
        return None
    try:
        return datetime.date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2))).isoformat()
    except ValueError:
        return None


def _proposals(tables):
    """Rows of a meeting's proposal tables -> (list of [num,text,rec,vote,sponsor], error)."""
    out: list[list[str]] = []
    for rows in tables:
        text_col = 2
        for raw in rows:
            ne = [c for c in raw if c]
            if not ne:
                continue
            if ne == _HEADER_ROW:
                text_col = raw.index("Proposal")
                continue
            if len(ne) == 5:
                out.append(ne[:])
            elif len(ne) == 1 and len(raw) > text_col and raw[text_col]:
                if not out:
                    return out, "orphan_continuation"
                out[-1][1] += " " + ne[0]
            else:
                return out, "bad_row"
    return out, None


def _walk(text: str):
    """Returns (rows, stats)."""
    stats: collections.Counter = collections.Counter()
    blocks: list[str] = []
    meetings = []  # (issuer_ctx_blocks_len, header, tables)
    cur = None
    heading_checked = False
    heading = None
    for kind, item in _segments(text):
        if kind == "block":
            blocks.append(item)
            continue
        h = _header(item)
        if h is None:
            if cur is not None:
                if any("(Registrant)" in c for r in item for c in r):
                    cur = None
                else:
                    cur["tables"].append(item)
            continue
        issuer = next((b for b in reversed(blocks) if not _PAGE.fullmatch(b)), "")
        if not heading_checked:
            heading_checked = True
            idx = next((i for i in range(len(blocks) - 1, -1, -1)
                        if not _PAGE.fullmatch(blocks[i])), -1)
            cand = blocks[idx - 1] if idx >= 1 else ""
            if cand.startswith("Dodge & Cox ") and cand.endswith("Fund"):
                heading = cand
            else:
                stats["no_fund_heading"] += 1
                return [], stats
        cur = {"issuer": issuer, "header": h, "tables": []}
        meetings.append(cur)
    if not heading_checked:
        return [], stats  # D9

    out = []
    for m in meetings:
        h = m["header"]
        if h is False:
            stats["bad_meeting_header"] += 1
            continue
        if not m["issuer"]:
            stats["no_issuer"] += 1
            continue
        date = _meeting_date(h["Meeting Date:"])
        if date is None:
            stats["bad_meeting_date"] += 1
            continue
        props, err = _proposals(m["tables"])
        if err:
            stats[err] += 1
            continue
        local: collections.Counter = collections.Counter()
        rows = []
        for num, ptxt, rec, vote, sponsor in props:
            if not _NUMBER.fullmatch(num) or not num.isascii():
                local["bad_number"] += 1
            elif rec not in _RECS:
                local["bad_rec"] += 1
            elif vote not in _VOTES:
                local["bad_vote"] += 1
            elif sponsor not in _SPONSORS:
                local["bad_sponsor"] += 1
            else:
                rows.append(dict(zip(KEYS, (
                    heading, m["issuer"], h["Ticker:"], h["Security ID:"], date, "",
                    h.get("Meeting Type:", ""), "", num, ptxt, sponsor, rec, vote, ""))))
        stats.update(local)
        out.extend(rows)
    stats["rows"] = len(out)
    return out, stats


def parse(text: str) -> list[dict]:
    return _walk(text)[0]


def parse_stats(text: str) -> collections.Counter:
    return _walk(text)[1]
