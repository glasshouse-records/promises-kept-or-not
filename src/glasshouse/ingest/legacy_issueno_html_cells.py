"""Legacy N-PX "Issue No." layout exported as HTML tables (cell-tokenizer parser).

One regex tokenizer runs over the raw markup (row start, row end, cell start,
cell end, hr, table end, text) and feeds a small state machine; there is no
DOM. A false vote is fatal, so anything ambiguous yields nothing for that
proposal or meeting; nothing is ever carried from one meeting or fund into the
next. Standard library only.

Document shape (see the contract in the build brief): a row starts at ``<tr``
and ends at ``</tr>``, the next ``<tr`` or ``</table>``; a cell starts at
``<td``/``<th`` and ends at its close or the next cell/row start. A cell's
column position is the sum of the colspans of the cells before it in the row.
Rows with an ``<hr`` are separators.

Meeting block: issuer row (one non-empty cell), header row Ticker / Security
ID: / Meeting Date / Meeting Status, its value row, header row Meeting Type
[/ Country of Trade], its value row, the proposal header row, then proposal
rows. Every field is read at the column position of its label.

Known deviation from the brief, flagged for the orchestrator: the Neuberger
Berman sample prints a 'Meeting Type' header row WITHOUT a 'Country of Trade'
column. A strict reading would drop all 1,400+ of its meetings, so that column
is optional here and country is emitted as '' when the filer prints none. If
the column IS labelled but its value is blank, the meeting is dropped.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date

_ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
_TOKEN = re.compile(
    rf"""
    (?P<comment><!--.*?-->)
  | (?P<row_end></tr\b{_ATTRS}>)
  | (?P<row><tr\b{_ATTRS}>)
  | (?P<cell_end></t[dh]\b{_ATTRS}>)
  | (?P<cell><t[dh]\b{_ATTRS}>)
  | (?P<hr><hr\b{_ATTRS}>)
  | (?P<table_end></table\b{_ATTRS}>)
  | (?P<space></?(?:br|div|p|li)\b{_ATTRS}>)
  | (?P<tag></?[a-z!?]{_ATTRS}>)
  | (?P<text>[^<]+|<)
    """,
    re.I | re.S | re.X,
)
_COLSPAN = re.compile(r"""colspan\s*=\s*["']?\s*(\d+)""", re.I)
_FUND = re.compile(r"fund\s+name\s*:\s*(.*)\Z", re.I | re.S)
_REGISTRANT = re.compile(r"registrant\s*:", re.I)
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\Z")

# Closed vocabularies, compared case-insensitively, emitted literally.
# Derived from the two real samples (Putnam, Neuberger Berman) plus the
# contract ('Echo Vote').
PROPONENTS = frozenset({"mgmt", "shrholdr", "n/a"})
RECS = frozenset({"for", "against", "abstain", "withhold", "1 year", "2 years",
                  "3 years", "none", "n/a", "tna", "take no action"})
VOTES = frozenset({"for", "against", "abstain", "withhold", "1 year", "2 years",
                   "3 years", "n/a", "tna", "take no action", "echo vote"})
FOR_AGAINST = frozenset({"for", "against", "n/a"})

_H1 = frozenset({"ticker", "security id:", "meeting date", "meeting status"})
_H3 = frozenset({"meeting type", "country of trade"})
_H3_NO_COUNTRY = frozenset({"meeting type"})
_PROP_BASE = frozenset({"issue no.", "description", "proponent", "mgmt rec",
                        "vote cast"})
_FA_LABELS = ("for/agnst mgmt", "for/against mgmt")

_IDLE, _ISSUER, _H1V, _H3H, _H3V, _PHDR, _PROPS, _PEND = range(8)


def _norm(raw: str) -> str:
    return " ".join(html.unescape(raw).split())


def _iso(s: str) -> str | None:
    m = _DATE.match(s)
    if not m:
        return None
    mo, d, y = int(m[1]), int(m[2]), int(m[3])
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _rows(text: str):
    """Yield (cells, has_hr); cells = [(column_position, text)] non-empty only."""
    cells: list[tuple[int, str]] = []
    in_row = False
    has_hr = False
    pos = 0
    parts: list[str] | None = None
    span = 1
    cell_pos = 0

    def close_cell():
        nonlocal parts, pos
        if parts is None:
            return
        t = _norm("".join(parts))
        if t:
            cells.append((cell_pos, t))
        pos = cell_pos + span
        parts = None

    for m in _TOKEN.finditer(text):
        k = m.lastgroup
        if k == "text":
            if parts is not None:
                parts.append(m.group())
        elif k == "space":
            if parts is not None:
                parts.append(" ")
        elif k == "cell":
            if in_row:
                close_cell()
                cs = _COLSPAN.search(m.group())
                span = max(int(cs.group(1)), 1) if cs else 1
                cell_pos = pos
                parts = []
        elif k == "cell_end":
            close_cell()
        elif k == "row":
            if in_row:
                close_cell()
                yield cells, has_hr
            cells, in_row, has_hr, pos = [], True, False, 0
        elif k in ("row_end", "table_end"):
            if in_row:
                close_cell()
                yield cells, has_hr
            cells, in_row, has_hr, pos = [], False, False, 0
        elif k == "hr":
            if in_row:
                has_hr = True
    if in_row:
        close_cell()
        yield cells, has_hr


def _label_map(cells):
    return {t.lower(): p for p, t in cells}


def _fund_value(cells):
    """None if not a fund heading row; '' if heading without a usable value."""
    first = _FUND.match(cells[0][1]) if cells else None
    if not first:
        return None
    if any(_FUND.match(t) for _, t in cells[1:]):
        return ""
    rest = first.group(1).strip()
    if rest:
        return rest
    return cells[1][1] if len(cells) > 1 else ""


def _scan(text: str):
    out: list[dict] = []
    reasons: Counter = Counter()
    vocab_seen: Counter = Counter()
    st = Counter()
    state = _IDLE
    fund: str | None = None
    meet: dict = {}
    pos_map: dict[str, int] = {}
    meet_idx = 0
    pend = ""

    def bad_meeting(reason: str):
        if not meet.get("bad"):
            meet["bad"] = reason
            st["meetings_dropped"] += 1
            reasons["meeting:" + reason] += 1

    def values(cells, positions):
        """Value-row cells by label position; None if a stray cell exists."""
        by_pos = dict(cells)
        if any(p not in positions.values() for p in by_pos):
            return None
        return {name: by_pos.get(p, "") for name, p in positions.items()}

    def unplace():
        """A3: drop the whole current meeting, proposals already read included."""
        nonlocal state
        if not meet.get("bad"):
            meet["bad"] = "unplaced_row"
            st["meetings_dropped"] += 1
            reasons["meeting:unplaced_row"] += 1
        removed = len(out) - meet_idx
        if removed > 0:
            del out[meet_idx:]
            st["proposals_emitted"] -= removed
            st["proposals_dropped"] += removed
            reasons["unplaced_row"] += removed
        state = _IDLE

    def fail(reason: str):
        nonlocal state
        bad_meeting(reason)
        state = _IDLE

    for cells, has_hr in _rows(text):
        if has_hr:
            if state == _PEND:
                unplace()
            if state in (_H1V, _H3H, _H3V, _PHDR):
                bad_meeting("separator_inside_header")
            state = _IDLE
            continue
        fv = _fund_value(cells)
        if fv is not None:
            if state == _PEND:
                unplace()
            if state in (_H1V, _H3H, _H3V, _PHDR):
                bad_meeting("fund_heading_inside_header")
            fund = fv or None
            state = _IDLE
            continue
        if cells and _REGISTRANT.match(cells[0][1]):
            fund = None  # A1: a registrant change ends the fund
            if state == _PEND:
                unplace()
            if state in (_H1V, _H3H, _H3V, _PHDR):
                bad_meeting("registrant_inside_header")
            state = _IDLE
            continue

        n = len(cells)
        if state == _PEND:
            if n == 0:
                continue
            if n == 4 and set(_label_map(cells)) == _H1:
                meet = {"issuer": pend, "bad": None}
                state = _ISSUER
            else:
                unplace()
        if state == _PROPS:
            if n == 0:
                state = _IDLE
                continue
            if n > 1:
                st["proposals_seen"] += 1
                if meet.get("bad"):
                    st["proposals_dropped"] += 1
                    reasons["meeting_dropped"] += 1
                    continue
                by_pos = dict(cells)
                if any(p not in pos_map.values() for p in by_pos):
                    st["proposals_dropped"] += 1
                    reasons["stray_cell"] += 1
                    continue
                v = {name: by_pos.get(p, "") for name, p in pos_map.items()}
                if not v["issue"]:
                    st["proposals_dropped"] += 1
                    reasons["empty_issue_no"] += 1
                    continue
                if not v["desc"]:
                    st["proposals_dropped"] += 1
                    reasons["empty_description"] += 1
                    continue
                bad = None
                for fld, allowed in (("proponent", PROPONENTS), ("rec", RECS),
                                     ("vote", VOTES), ("fa", FOR_AGAINST)):
                    if v[fld].lower() not in allowed:
                        bad = fld
                        vocab_seen[f"{fld}={v[fld]}"] += 1
                        break
                if bad:
                    st["proposals_dropped"] += 1
                    reasons["vocab_" + bad] += 1
                    continue
                st["proposals_emitted"] += 1
                out.append({
                    "fund_heading": meet["fund"],
                    "issuer_name": meet["issuer"],
                    "ticker": meet["ticker"],
                    "security_id": meet["security_id"],
                    "meeting_date": meet["date"],
                    "meeting_status": meet["status"],
                    "meeting_type": meet["type"],
                    "country": meet["country"],
                    "proposal_id": v["issue"],
                    "proposal_text": v["desc"],
                    "proponent": v["proponent"],
                    "rec": v["rec"],
                    "vote": v["vote"],
                    "for_against": v["fa"],
                })
                continue
            pend = cells[0][1]  # A3: a meeting only if the next row is the header
            state = _PEND
            continue
        if state != _IDLE:
            labels = _label_map(cells)
            if state == _ISSUER:
                if n == 4 and set(labels) == _H1:
                    st["meetings_seen"] += 1
                    meet["fund"] = fund
                    meet["bad"] = None
                    if fund is None:
                        bad_meeting("no_fund")
                    pos_map = {"ticker": labels["ticker"],
                               "security_id": labels["security id:"],
                               "date": labels["meeting date"],
                               "status": labels["meeting status"]}
                    state = _H1V
                    continue
                state = _IDLE
            elif state == _H1V:
                v = values(cells, pos_map) if n else None
                if v is None:
                    fail("bad_value_row")
                elif not (v["security_id"] and v["date"] and v["status"]):
                    fail("missing_value")
                else:
                    iso = _iso(v["date"])
                    if iso is None:
                        bad_meeting("bad_date")
                    meet.update(ticker=v["ticker"], security_id=v["security_id"],
                                date=iso, status=v["status"])
                    state = _H3H
                    continue
                if state == _IDLE and n != 1:
                    continue
            elif state == _H3H:
                if n and set(labels) in (_H3, _H3_NO_COUNTRY) and len(labels) == n:
                    pos_map = {"type": labels["meeting type"]}
                    if "country of trade" in labels:
                        pos_map["country"] = labels["country of trade"]
                    state = _H3V
                    continue
                fail("no_meeting_type_header")
                if n != 1:
                    continue
            elif state == _H3V:
                v = values(cells, pos_map) if n else None
                if v is None or not v["type"] or not v.get("country", "x"):
                    fail("bad_meeting_type_row")
                else:
                    meet.update(type=v["type"], country=v.get("country", ""))
                    state = _PHDR
                    continue
                if n != 1:
                    continue
            elif state == _PHDR:
                fa = [x for x in _FA_LABELS if x in labels]
                if n == 6 and len(fa) == 1 and set(labels) == _PROP_BASE | {fa[0]}:
                    pos_map = {"issue": labels["issue no."],
                               "desc": labels["description"],
                               "proponent": labels["proponent"],
                               "rec": labels["mgmt rec"],
                               "vote": labels["vote cast"],
                               "fa": labels[fa[0]]}
                    state = _PROPS
                    meet_idx = len(out)
                    continue
                fail("no_proposal_header")
                if n != 1:
                    continue
        if n == 1:
            meet = {"issuer": cells[0][1], "bad": None}
            state = _ISSUER
        else:
            state = _IDLE

    if state == _PEND:
        unplace()
    if state in (_H1V, _H3H, _H3V, _PHDR):
        bad_meeting("incomplete")
    return out, st, reasons, vocab_seen


def parse(text: str) -> list[dict]:
    """One dict per proposal row (14 fields, see module docstring)."""
    return _scan(text)[0]


def parse_stats(text: str) -> dict:
    """Counts for a document: meetings/proposals seen, emitted, dropped, why."""
    _, st, reasons, vocab_seen = _scan(text)
    return {
        "meetings_seen": st["meetings_seen"],
        "meetings_dropped": st["meetings_dropped"],
        "proposals_seen": st["proposals_seen"],
        "proposals_emitted": st["proposals_emitted"],
        "proposals_dropped": st["proposals_dropped"],
        "reasons": dict(reasons),
        "vocab_values": dict(vocab_seen),
    }
