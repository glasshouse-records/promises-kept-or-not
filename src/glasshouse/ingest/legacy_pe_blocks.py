"""Structural parser for legacy N-PX "ProxyEdge" (Broadridge) fixed-width text.

The document is split into fund sections and meeting blocks on the dashed
separator lines.  Each meeting carries a column-header line
('Prop.# Proposal  Proposal  Proposal Vote  For/Against' + 'Type ... Management');
the character offsets of those header words are used to slice every proposal
line into its columns.

Precision over recall: anything ambiguous (misaligned columns, unknown vote
words, missing date or issuer, unknown fund heading) yields NO row, and the
reason is counted in ``parse_stats``.

Row shapes handled:
- id line:       '1a.    Election of Director: X     Mgmt   For   For'
- wrapped text:  continuation lines (no id, no type) join the text with spaces
- sub-rows:      '       Jane Doe                    Mgmt   For   For' under a
                 parent '1.     DIRECTOR'.  Emitted with the parent's id and
                 text 'DIRECTOR Jane Doe' (parent head text + sub-row text).
"""

from __future__ import annotations

import calendar
import re
from collections import Counter

KEYS = (
    "fund_name",
    "issuer_name",
    "agenda_number",
    "security_id",
    "ticker",
    "isin",
    "meeting_type",
    "meeting_date",
    "proposal_id",
    "proposal_text",
    "proposal_type",
    "vote",
    "for_against_management",
)

# Closed vocabularies, taken from the three real samples plus the contract.
# 'No vote' and 'Split NN% For ...' are deliberately NOT here (not a single
# vote, or no vote cast): such proposals are dropped, never guessed.
VOTE_VOCAB = frozenset(
    {"For", "Against", "Abstain", "Withheld", "Withhold", "1 Year", "2 Years", "3 Years",
     "None", "Take No Action"}
)
VOTED_TYPES = frozenset({"Mgmt", "Shr"})
NONVOTING_TYPE = "Non-Voting"
FA_VOCAB = frozenset({"For", "Against", ""})

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
_DASH = re.compile(r"^-{20,}\s*$")
_AGENDA = re.compile(r"^\s*(.*?)\s*Agenda Number:\s*(.*?)\s*$")
_LABEL = re.compile(r"^\s*(Security|Meeting Type|Meeting Date|Ticker|ISIN):(.*)$")
_DATE = re.compile(r"^(\d{2})-([A-Z][a-z]{2})-(\d{4})$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*\)?$")
_HEADER_RE = re.compile(r"^Prop\.#\s+Proposal\s+Proposal\s+Proposal Vote\s+For/Against\s*$")
_HEADER2_RE = re.compile(r"^\s+Type\s+Management\s*$")


def _iso_date(s: str) -> str:
    m = _DATE.match(s.strip())
    if not m:
        return ""
    d, mon, y = int(m.group(1)), _MONTHS.get(m.group(2)), int(m.group(3))
    if mon is None or not (1900 <= y <= 2100) or d < 1:
        return ""
    if d > calendar.monthrange(y, mon)[1]:
        return ""
    return f"{y:04d}-{mon:02d}-{d:02d}"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _is_dash(line: str) -> bool:
    return bool(_DASH.match(line))


class _Row:
    def __init__(self) -> None:
        self.pid = ""
        self.head: list[str] = []
        self.type = ""
        self.vote = ""
        self.fa = ""
        self.bad = ""
        self.parent_head = ""


def parse_stats(text: str) -> dict:
    return _run(text, None)


def parse(text: str) -> list[dict]:
    out: list[dict] = []
    _run(text, out)
    return out


def _run(text: str, out: list[dict] | None) -> dict:
    lines = [x.rstrip("\r").expandtabs(8) for x in text.split("\n")]
    n = len(lines)
    st: dict = {
        "meetings_seen": 0, "meetings_dropped": 0, "meetings_dropped_reasons": Counter(),
        "proposals_seen": 0, "proposals_emitted": 0, "proposals_dropped": 0,
        "dropped_reasons": Counter(), "nonvoting_skipped": 0, "stray_lines": 0,
        "unknown_headings": 0,
    }
    fund: str | None = None
    i = 0
    while i < n:
        line = lines[i]
        # fund heading: text line directly followed by a dash line
        if (i + 1 < n and line.strip() and not _is_dash(line) and _is_dash(lines[i + 1])
                and not _LABEL.match(line) and "Agenda Number:" not in line):
            nxt = lines[i + 2] if i + 2 < n else ""
            if "Agenda Number:" in nxt or "held no voting" in nxt:
                fund = _norm(line)
            else:
                fund = None  # unknown structure: never attribute votes to a stale fund
                st["unknown_headings"] += 1
            i += 1
            continue
        if ("Agenda Number:" in line and i > 0 and _is_dash(lines[i - 1])
                and i + 1 < n and _is_dash(lines[i + 1])):
            i = _meeting(lines, i, fund, st, out)
            continue
        i += 1
    st["meetings_dropped_reasons"] = dict(st["meetings_dropped_reasons"])
    st["dropped_reasons"] = dict(st["dropped_reasons"])
    return st


def _drop_meeting(st: dict, reason: str) -> None:
    st["meetings_dropped"] += 1
    st["meetings_dropped_reasons"][reason] += 1


def _meeting(lines: list[str], i: int, fund: str | None, st: dict,
             out: list[dict] | None) -> int:
    """Parse one meeting block whose issuer line is lines[i]; return next index."""
    n = len(lines)
    st["meetings_seen"] += 1
    m = _AGENDA.match(lines[i])
    issuer = _norm(m.group(1)) if m else ""
    agenda = _norm(m.group(2)) if m else ""
    j = i + 2
    labels: dict[str, str] = {}
    dup = False
    while j < n and not _is_dash(lines[j]):
        lm = _LABEL.match(lines[j])
        if lm:
            if lm.group(1) in labels:
                dup = True
            labels[lm.group(1)] = _norm(lm.group(2))
        elif lines[j].strip():
            dup = True  # unexpected line inside the header block
        j += 1
    j += 1  # past the closing dashes
    while j < n and not lines[j].strip():
        j += 1
    if not (j + 1 < n and _HEADER_RE.match(lines[j]) and _HEADER2_RE.match(lines[j + 1])):
        _drop_meeting(st, "no_column_header")
        return max(j, i + 1)
    h = lines[j]
    c_text = h.index("Proposal")
    c_type = h.index("Proposal", c_text + 1)
    c_vote = h.index("Proposal Vote")
    c_fa = h.index("For/Against")
    j += 2

    date = _iso_date(labels.get("Meeting Date", ""))
    reason = ""
    if fund is None:
        reason = "no_fund_heading"
    elif not issuer:
        reason = "missing_issuer"
    elif not date:
        reason = "bad_meeting_date"
    elif dup:
        reason = "ambiguous_header_block"
    if reason:
        _drop_meeting(st, reason)
    meta = {
        "fund_name": fund or "", "issuer_name": issuer, "agenda_number": agenda,
        "security_id": labels.get("Security", ""), "ticker": labels.get("Ticker", ""),
        "isin": labels.get("ISIN", ""), "meeting_type": labels.get("Meeting Type", ""),
        "meeting_date": date,
    }

    rows: list[_Row] = []
    cur: _Row | None = None  # row currently accepting continuation lines
    parent: _Row | None = None
    while j < n:
        line = lines[j]
        if _is_dash(line):
            break
        if not line.strip():
            j += 1
            continue
        if j + 1 < n and _is_dash(lines[j + 1]) and line[:1] != " ":
            break  # next fund heading
        idtok = line[:c_text].strip()
        has_type_zone = len(line) > c_type and line[c_type:c_vote].strip() != ""
        if idtok:
            if line[c_text - 1] != " " or not _ID.match(idtok):
                st["stray_lines"] += 1
                break
            r = _Row()
            r.pid = idtok
            parent = cur = r
            rows.append(r)
            _fill(r, line, c_text, c_type, c_vote, c_fa)
        elif has_type_zone:
            r = _Row()  # sub-row under the parent id (if any)
            if parent is None:
                r.bad = "subrow_without_parent"
            else:
                r.pid = parent.pid
                r.parent_head = _norm(" ".join(parent.head))
                if parent.type or parent.vote or parent.fa:
                    r.bad = "ambiguous_subrow"  # parent is itself a voted row
            cur = r
            rows.append(r)
            _fill(r, line, c_text, c_type, c_vote, c_fa)
        elif cur is not None:
            # continuation line: must lie wholly inside the text column
            if len(line) > c_type and line[c_type:].strip():
                cur.bad = cur.bad or "continuation_overflow"
            cur.head.append(line[c_text:c_type].strip())
        else:
            st["stray_lines"] += 1
            break
        j += 1

    for r in rows:
        if r.type == NONVOTING_TYPE:
            st["nonvoting_skipped"] += 1
            continue
        if not r.type and not r.vote and not r.fa and not r.bad:
            continue  # parent label row ('1.  DIRECTOR'): not itself a proposal
        st["proposals_seen"] += 1
        why = reason or r.bad
        text_ = _norm(((r.parent_head + " ") if r.parent_head else "") + " ".join(r.head))
        if not why:
            if r.type not in VOTED_TYPES:
                why = "unknown_type"
            elif r.vote not in VOTE_VOCAB:
                why = "vote_not_in_vocab" if r.vote else "empty_vote"
            elif r.fa not in FA_VOCAB:
                why = "for_against_not_in_vocab"
            elif not text_:
                why = "empty_text"
        if why:
            st["proposals_dropped"] += 1
            st["dropped_reasons"][why] += 1
            continue
        st["proposals_emitted"] += 1
        if out is not None:
            d = dict(meta)
            d.update(proposal_id=r.pid, proposal_text=text_, proposal_type=r.type,
                     vote=r.vote, for_against_management=r.fa)
            out.append({k: d[k] for k in KEYS})
    return max(j, i + 1)


def _fill(r: _Row, line: str, c_text: int, c_type: int, c_vote: int, c_fa: int) -> None:
    """Slice one physical line into columns, flagging bleed across a column edge."""
    misaligned = any(len(line) > c and line[c - 1] != " " and line[c] != " "
                     for c in (c_type, c_vote, c_fa))
    r.head.append(line[c_text:c_type].strip())
    r.bad = r.bad or ("misaligned_columns" if misaligned else "")
    r.type = line[c_type:c_vote].strip()
    r.vote = line[c_vote:c_fa].strip()
    r.fa = line[c_fa:].strip()
    if r.type == NONVOTING_TYPE:
        r.vote = r.fa = ""
