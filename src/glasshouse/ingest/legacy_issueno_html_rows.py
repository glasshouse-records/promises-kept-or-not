"""Legacy N-PX 'Issue No.' layout exported as HTML tables (row-walker parser).

Row-oriented implementation: the document is first split into row strings, each
row becomes a list of (column_position, text) cells, then explicit per-block
functions walk the row list (fund heading, meeting header, proposals).

Precision over recall: anything ambiguous yields no rows for that proposal or
meeting. Standard library only; linear in document size.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date

# Closed vocabularies, taken from the real samples (Putnam, Neuberger Berman).
# A proposal whose value falls outside them is dropped, never guessed.
PROPONENTS = frozenset({"Mgmt", "MGMT", "ShrHoldr", "N/A"})
MGMT_RECS = frozenset({"For", "Against", "Abstain", "Withhold", "1 Year", "2 Years", "3 Years",
                       "N/A", "None"})
VOTES = frozenset({"For", "Against", "Abstain", "Withhold", "1 Year", "2 Years", "3 Years",
                   "TNA", "N/A", "Echo Vote"})
FOR_AGAINST = frozenset({"For", "Against", "N/A"})

KEYS = ("fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
        "meeting_status", "meeting_type", "country", "proposal_id", "proposal_text",
        "proponent", "rec", "vote", "for_against")

_ROW_START = re.compile(r"(?i)(?=<tr[\s>/])|(?=</table)")
_CELL_START = re.compile(r"(?i)<t[dh](?=[\s>/])")
_ROW_END = re.compile(r"(?i)</tr")
_TAG = re.compile(r"<!--.*?-->|<[^>]*>", re.S)
_COLSPAN = re.compile(r"(?i)\bcolspan\s*=\s*[\"']?\s*(\d+)")
_FUND = re.compile(r"(?i)^fund name\s*:\s*(.*)$")
_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")

_TICKER_LABELS = {"ticker": "ticker", "security id:": "security_id",
                  "meeting date": "date", "meeting status": "status"}
_TYPE_LABELS = {"meeting type": "type", "country of trade": "country"}
_PROP_LABELS = {"issue no.": "id", "description": "text", "proponent": "proponent",
                "mgmt rec": "rec", "vote cast": "vote",
                "for/agnst mgmt": "for_against", "for/against mgmt": "for_against"}

Cells = list  # list[tuple[int, str]] of non-empty cells; (column_position, text)


class _Row:
    __slots__ = ("cells", "sep")

    def __init__(self, cells: Cells, sep: bool):
        self.cells = cells
        self.sep = sep


def _norm(s: str) -> str:
    return " ".join(html.unescape(_TAG.sub("", s)).split())


# ------------------------------------------------------------------ rows

def _split_rows(text: str) -> list:
    """Row strings; None marks a table end (between-block boundary)."""
    out: list = []
    for piece in _ROW_START.split(text):
        if piece[:7].lower() == "</table":
            out.append(None)
            continue
        if piece[:3].lower() != "<tr":
            continue
        end = _ROW_END.search(piece)
        out.append(piece[:end.start()] if end else piece)
    return out


def _cells(row: str) -> Cells:
    cells: Cells = []
    pos = 0
    chunks = _CELL_START.split(row)
    for chunk in chunks[1:]:
        gt = chunk.find(">")
        attrs, body = chunk[:gt], chunk[gt + 1:]
        txt = _norm(body)
        if txt:
            cells.append((pos, txt))
        span = _COLSPAN.search(attrs)
        pos += max(int(span.group(1)), 1) if span else 1
    return cells


def _rows(text: str) -> list:
    rows: list = []
    for raw in _split_rows(text):
        if raw is None:
            rows.append(None)
        else:
            rows.append(_Row(_cells(raw), "<hr" in raw.lower()))
    return rows


# ---------------------------------------------------------------- blocks

def _fund_heading(row: _Row):
    """Return the heading text ('' if unreadable) or None when not a fund row."""
    cells = row.cells
    for i, (_, txt) in enumerate(cells):
        mt = _FUND.match(txt)
        if not mt:
            continue
        if mt.group(1).strip():
            return mt.group(1).strip()
        return cells[i + 1][1] if i + 1 < len(cells) else ""
    return None


def _label_map(row: _Row, labels: dict, required: set, optional: set = frozenset()):
    """{field: column} if the row is exactly such a header row, else None."""
    found: dict = {}
    for pos, txt in row.cells:
        field = labels.get(txt.lower())
        if field is None or field in found:
            return None
        found[field] = pos
    if not required <= set(found) or not set(found) <= required | optional:
        return None
    return found


def _is_issuer(row: _Row) -> bool:
    return not row.sep and len(row.cells) == 1


def _values(row: _Row, cols: dict):
    """Field -> text by column; None if a non-empty cell sits in an unlabelled column."""
    by_pos = dict(row.cells)
    if not set(by_pos) <= set(cols.values()):
        return None
    return {f: by_pos.get(p, "") for f, p in cols.items()}


def _meeting_date(s: str):
    mt = _DATE.match(s)
    if not mt:
        return None
    try:
        return date(int(mt.group(3)), int(mt.group(1)), int(mt.group(2))).isoformat()
    except ValueError:
        return None


def _starts_block(row) -> bool:
    return row is None or row.sep or not row.cells or _is_issuer(row) \
        or _fund_heading(row) is not None


def _meeting_block(rows: list, i: int, fund, stats: dict, out: list) -> int:
    """Parse the meeting whose issuer row is rows[i]; return the next index to examine."""
    r = rows[i:i + 6]
    if len(r) < 2 or r[1] is None:
        return i + 1
    tcols = _label_map(r[1], _TICKER_LABELS, {"ticker", "security_id", "date", "status"})
    if tcols is None:
        return i + 1          # issuer-like row without a ticker header: not a meeting
    stats["meetings_seen"] += 1

    def drop(reason: str) -> int:
        stats["meetings_dropped"] += 1
        stats["reasons"]["meeting:" + reason] += 1
        return i + 1

    if not fund:
        return drop("no_fund_heading")
    if len(r) < 6 or any(x is None for x in r):
        return drop("incomplete_header")
    tv = _values(r[2], tcols)
    if tv is None:
        return drop("stray_value_in_meeting_row")
    iso = _meeting_date(tv["date"])
    if iso is None:
        return drop("bad_meeting_date")
    if not tv["security_id"] or not tv["status"]:
        return drop("missing_security_id_or_status")
    ycols = _label_map(r[3], _TYPE_LABELS, {"type"}, {"country"})
    if ycols is None:
        return drop("no_meeting_type_header")
    yv = _values(r[4], ycols)
    if yv is None or not yv["type"]:
        return drop("bad_meeting_type_row")
    pcols = _label_map(r[5], _PROP_LABELS, set(_PROP_LABELS.values()))
    if pcols is None:
        return drop("no_proposal_header")

    base = {
        "fund_heading": fund, "issuer_name": r[0].cells[0][1], "ticker": tv["ticker"],
        "security_id": tv["security_id"], "meeting_date": iso,
        "meeting_status": tv["status"], "meeting_type": yv["type"],
        "country": yv.get("country", ""),
    }
    j = i + 6
    while j < len(rows) and not _starts_block(rows[j]):
        _proposal_row(rows[j], pcols, base, stats, out)
        j += 1
    return j


def _proposal_row(row: _Row, pcols: dict, base: dict, stats: dict, out: list) -> None:
    stats["proposals_seen"] += 1
    v = _values(row, pcols)
    reason = None
    if v is None:
        reason = "unlabelled_column"
    elif not v["id"] or not v["text"]:
        reason = "missing_issue_no_or_description"
    elif v["proponent"] not in PROPONENTS:
        reason = "proponent_vocab"
    elif v["rec"] not in MGMT_RECS:
        reason = "rec_vocab"
    elif v["vote"] not in VOTES:
        reason = "vote_vocab"
    elif v["for_against"] not in FOR_AGAINST:
        reason = "for_against_vocab"
    if reason:
        stats["proposals_dropped"] += 1
        stats["reasons"][reason] += 1
        return
    stats["proposals_emitted"] += 1
    out.append({**base, "proposal_id": v["id"], "proposal_text": v["text"],
                "proponent": v["proponent"], "rec": v["rec"], "vote": v["vote"],
                "for_against": v["for_against"]})


def _walk(text: str):
    stats = {"meetings_seen": 0, "meetings_dropped": 0, "proposals_seen": 0,
             "proposals_emitted": 0, "proposals_dropped": 0, "reasons": Counter()}
    out: list = []
    rows = _rows(text)
    fund = None
    i = 0
    while i < len(rows):
        row = rows[i]
        if row is None or row.sep or not row.cells:
            i += 1
            continue
        heading = _fund_heading(row)
        if heading is not None:
            fund = heading
            i += 1
        elif _is_issuer(row):
            i = _meeting_block(rows, i, fund, stats, out)
        else:
            i += 1
    return out, stats


def parse(text: str) -> list[dict]:
    """One dict per accepted proposal row (keys: see KEYS)."""
    return _walk(text)[0]


def parse_stats(text: str) -> dict:
    stats = _walk(text)[1]
    stats["reasons"] = dict(stats["reasons"])
    return stats
