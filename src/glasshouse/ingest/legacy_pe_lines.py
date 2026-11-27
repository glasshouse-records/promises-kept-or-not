"""Legacy (pre-XML) N-PX "ProxyEdge" text parser, line-by-line variant.

Source: the Broadridge fixed-width text vote reports filed as plain-text N-PX
for the July 2022 - June 2023 voting year (see the parser contract in the
project notes). This module is one of two INDEPENDENT implementations of the
same contract; only rows both produce identically are meant to ship.

Approach: a line state machine driven by regular expressions. It deliberately
does NOT use column character offsets. A proposal's first line is recognised
by a leading id token at the start of the line plus a type token (Mgmt / Shr /
Non-Voting) found from the right end of the line; what follows the type is
matched against a closed vote vocabulary. Lines without a leading id are
continuation text of the proposal above them (until a blank line).

Precision over recall. A false vote is fatal, so anything ambiguous is dropped
and counted in ``parse_stats(...)["reasons"]``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

# Closed vocabularies, taken from the three 2023 sample filings.
PROPOSAL_TYPES = ("Mgmt", "Shr", "Non-Voting")
VOTE_VOCAB = (
    "For",
    "Against",
    "Abstain",
    "Withheld",
    "Withhold",
    "1 Year",
    "2 Years",
    "3 Years",
    "None",
    "Take No Action",
)
FOR_AGAINST_VOCAB = ("For", "Against", "*")  # "*" = contested, no mgmt recommendation

# A single token after the type that sits this far to the right of it can only be
# the For/Against column of a row whose vote column is empty; never read it as a vote.
AMBIGUOUS_GAP = 20

_DASH = re.compile(r"^-{20,}\s*$")
_AGENDA = re.compile(r"^\s*(.*?)\s*Agenda Number:\s*(.*?)\s*$")
_LABEL_NAMES = ("Security", "Meeting Type", "Meeting Date", "Ticker", "ISIN")
# PE-I: some filings print every capital I as a lower-case i (`iSiN:`); in a label word
# the letter i stands for I. No other tolerance. Identifier values are upper-cased below.
_LABEL_CANON = {n.replace("i", "I"): n for n in _LABEL_NAMES}
_LABEL = re.compile(
    r"^\s*(" + "|".join(re.sub(r"[iI]", "[iI]", n) for n in _LABEL_NAMES)
    + r"):(.*)$")
# Word/HTML style fragments that leak between sections; never headings, issuers or text.
_STYLE_FRAGMENT = ("mso-", "font-family", "&quot;", "height:", "justify;")
_TYPE_AT = re.compile(r"\s{2,}(" + "|".join(map(re.escape, PROPOSAL_TYPES)) + r")(?=\s|$)")
_VOTE = re.compile(
    r"(" + "|".join(map(re.escape, VOTE_VOCAB)) + r")(?: (" + "|".join(
        map(re.escape, FOR_AGAINST_VOCAB)) + r"))?"
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_DATE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")


@dataclass
class _Prop:
    pid: str
    parts: list[str]
    ptype: str
    tail: str  # raw text after the type token
    wide: bool = False
    sub: bool = False  # nominee sub-row under a heading
    closed: bool = False  # ambiguous indented sub-rows seen: take no more text


@dataclass
class _Meeting:
    fund: str
    issuer: str
    agenda: str
    labels: dict[str, str] = field(default_factory=dict)
    bad: str = ""  # reason the whole meeting is dropped
    props: list[_Prop] = field(default_factory=list)


def _label_key(word: str) -> str:
    return _LABEL_CANON[word.replace("i", "I")]


def _is_style_fragment(line: str) -> bool:
    return any(f in line for f in _STYLE_FRAGMENT)


def _iso_date(s: str) -> str:
    m = _DATE.match(s.strip())
    if not m or m.group(2).capitalize() not in _MONTHS:
        return ""
    try:
        return date(int(m.group(3)), _MONTHS[m.group(2).capitalize()], int(m.group(1))).isoformat()
    except ValueError:
        return ""


def _split_row(line: str) -> tuple[str, str, str, str] | None:
    """(id, first-line text, type, tail) for a proposal's first line, else None."""
    if not line or line[0].isspace() or line[0] == "<":
        return None
    pid = line.split(None, 1)[0]
    rest = line[len(pid):]
    found = list(_TYPE_AT.finditer(rest))
    if not found:
        return None
    m = found[-1]
    return pid, rest[: m.start()], m.group(1), rest[m.end():]


def _classify(tail: str) -> tuple[str, str, str]:
    """(reason, vote, for_against); reason is '' when the vote is usable."""
    norm = " ".join(tail.split())
    if not norm:
        return "empty_vote", "", ""
    if norm.lower() == "no vote":
        return "no_vote", "", ""
    if norm.startswith("Split"):
        return "split_vote", "", ""
    m = _VOTE.fullmatch(norm)
    if not m:
        return "unknown_vote", "", ""
    vote, fa = m.group(1), m.group(2) or ""
    gap = len(tail) - len(tail.lstrip())
    if vote in ("For", "Against") and not fa and gap >= AMBIGUOUS_GAP:
        return "ambiguous_vote", "", ""
    return "", vote, ("" if fa == "*" else fa)  # "*" = management position unknown


def _is_fund_heading(lines: list[str], i: int) -> bool:
    line = lines[i]
    if not line.strip() or line[0].isspace() or line[0] == "<" or _DASH.match(line):
        return False
    if i + 1 >= len(lines) or not _DASH.match(lines[i + 1]):
        return False
    if i > 0 and _DASH.match(lines[i - 1]):
        return False
    if _LABEL.match(line) or "Agenda Number:" in line or _split_row(line):
        return False
    return not line.startswith("Prop.#")


def _walk(text: str, rows: list[dict] | None, stats: Counter, reasons: Counter) -> None:
    lines = text.splitlines()
    n = len(lines)
    fund = ""
    meeting: _Meeting | None = None
    cur: _Prop | None = None
    heading: list[str] | None = None  # [id, text] of a type-less heading row

    def close_prop() -> None:
        nonlocal cur
        if cur is not None and meeting is not None:
            meeting.props.append(cur)
        cur = None

    def close_meeting() -> None:
        nonlocal meeting
        close_prop()
        if meeting is not None:
            _finish(meeting, rows, stats, reasons)
        meeting = None

    i = 0
    while i < n:
        line = lines[i]
        if _DASH.match(line):
            close_meeting()
            if i + 2 < n and _AGENDA.match(lines[i + 1]) and _DASH.match(lines[i + 2]):
                a = _AGENDA.match(lines[i + 1])
                assert a is not None
                meeting = _Meeting(fund, " ".join(a.group(1).split()), a.group(2))
                j = i + 3
                while j < n and not _DASH.match(lines[j]):
                    ln = lines[j]
                    lab = _LABEL.match(ln)
                    if lab:
                        k = _label_key(lab.group(1))
                        if k in meeting.labels:
                            meeting.bad = "duplicate_label"
                        meeting.labels[k] = lab.group(2).strip()
                    elif _is_style_fragment(ln):
                        pass
                    elif ln.strip():
                        meeting.bad = "malformed_header"
                    if ln.startswith("<"):
                        meeting.bad = "malformed_header"
                        break
                    j += 1
                if j >= n:
                    meeting.bad = "malformed_header"
                i = j + 1
                continue
            i += 1
            continue
        if line.startswith("<"):
            close_meeting()
        elif _is_style_fragment(line):
            close_prop()  # never text: and never attach later wrap lines across it
            heading = None
        elif not line.strip():
            close_prop()
            heading = None
        elif _is_fund_heading(lines, i):
            close_meeting()
            fund = " ".join(line.split())
        elif meeting is not None:
            if line.startswith("Prop.#"):
                close_prop()
                if i + 1 < n and "Type" in lines[i + 1] and "Management" in lines[i + 1]:
                    i += 1
            elif (row := _split_row(line)) is not None:
                close_prop()
                heading = None
                cur = _Prop(row[0], [row[1]], row[2], row[3])
            elif not line[0].isspace():
                close_prop()  # never attach this line's wrap lines elsewhere
                parts = line.split(None, 1)
                if len(parts) == 2:
                    heading = [parts[0], parts[1]]  # type-less heading: nominee rows follow
                else:
                    heading = None
                    stats["proposals_seen"] += 1
                    stats["proposals_dropped"] += 1
                    reasons["unrecognised_row"] += 1
            else:
                sub = _TYPE_AT.search(line)
                if heading is not None and sub is not None and line[: sub.start()].strip():
                    close_prop()
                    name = line[: sub.start()].strip()
                    cur = _Prop(heading[0], [heading[1], name], sub.group(1),
                                line[sub.end():], sub=True)
                elif cur is not None and sub is not None and not cur.sub:
                    cur.closed = True  # heading row has its own vote: sub-rows ambiguous
                elif cur is not None:
                    body = line.strip()
                    if cur.closed:
                        pass
                    elif re.search(r"\s{3,}", body):
                        cur.wide = True  # something column-like inside wrapped text
                    cur.parts.append(body)
                elif heading is not None:
                    heading[1] += " " + line.strip()
                else:
                    stats["orphan_lines"] += 1
        i += 1
    close_meeting()


def _finish(m: _Meeting, rows: list[dict] | None, stats: Counter, reasons: Counter) -> None:
    stats["meetings_seen"] += 1
    iso = _iso_date(m.labels.get("Meeting Date", ""))
    bad = m.bad
    if not bad and not m.fund:
        bad = "no_fund"
    if not bad and not iso:
        bad = "bad_meeting_date"
    if not bad and not m.issuer:
        bad = "no_issuer"
    if bad:
        stats["meetings_dropped"] += 1
    for p in m.props:
        stats["proposals_seen"] += 1
        if p.ptype == "Non-Voting":
            stats["non_voting"] += 1
            continue
        if bad:
            stats["proposals_dropped"] += 1
            reasons[bad] += 1
            continue
        reason, vote, fa = _classify(p.tail)
        text = " ".join(" ".join(p.parts).split())
        if not reason and p.wide:
            reason = "wide_continuation"
        if not reason and not text:
            reason = "empty_text"
        if reason:
            stats["proposals_dropped"] += 1
            reasons[reason] += 1
            continue
        stats["proposals_emitted"] += 1
        if rows is not None:
            rows.append({
                "fund_name": m.fund,
                "issuer_name": m.issuer,
                "agenda_number": m.agenda,
                "security_id": m.labels.get("Security", "").upper(),
                "ticker": m.labels.get("Ticker", "").upper(),
                "isin": m.labels.get("ISIN", "").upper(),
                "meeting_type": m.labels.get("Meeting Type", ""),
                "meeting_date": iso,
                "proposal_id": p.pid,
                "proposal_text": text,
                "proposal_type": p.ptype,
                "vote": vote,
                "for_against_management": fa,
            })


def parse(text: str) -> list[dict]:
    """One dict per voted proposal (see module docstring for the precision rules)."""
    rows: list[dict] = []
    _walk(text, rows, Counter(), Counter())
    return rows


def parse_stats(text: str) -> dict:
    """Counts so a reviewer can see what was dropped and why."""
    stats: Counter = Counter()
    reasons: Counter = Counter()
    _walk(text, None, stats, reasons)
    return {
        "meetings_seen": stats["meetings_seen"],
        "meetings_dropped": stats["meetings_dropped"],
        "proposals_seen": stats["proposals_seen"],
        "proposals_emitted": stats["proposals_emitted"],
        "proposals_dropped": stats["proposals_dropped"],
        "non_voting": stats["non_voting"],
        "orphan_lines": stats["orphan_lines"],
        "reasons": reasons,
    }
