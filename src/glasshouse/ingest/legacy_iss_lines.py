"""Legacy N-PX ("FORM N-Px REPORT", ISS text layout) -> one dict per voted proposal.

LINE-BY-LINE state machine, no column character offsets.  A proposal's first
line is recognised by a leading id token at the start of the line plus a
trailing run of (rec, vote, sponsor) tokens matched from the RIGHT end against
closed vocabularies; an indented line is continuation text.

Precision over recall: anything ambiguous is dropped and counted, never
guessed.  Source of truth for the vocabularies: the July 2022 - June 2023
filings in data/legacy_cache (Vanguard, BlackRock, ...).  A value outside the
vocabulary drops the proposal and shows up in ``parse_stats()['reasons']``.

Known limit (documented, not guessed around): a proposal line whose Vote Cast
column is empty, and whose text happens to end in a word of RECS, would read
that text word as the rec.  The sponsor/vote closed sets make this vanishingly
rare, and no such line exists in the sampled filings.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import re
from collections import Counter

SPONSORS = ("Management", "Shareholder")
# What the manager voted (observed in the samples).
VOTES = frozenset({
    "For", "Against", "Abstain", "Withhold", "Withheld", "None", "One Year", "1 Year",
    "Two Years", "2 Years", "Three Years", "3 Years", "Three", "Do Not Vote",
    "Did Not Vote", "TNA", "No Vote", "FOR", "AGAINST", "N/A",
})
# What the issuer (Mgt Rec) or dissident (Diss Rec) recommended.
RECS = frozenset({
    "For", "Against", "Abstain", "Withhold", "None", "One Year", "1 Year", "Two Years",
    "2 Years", "Three Years", "3 Years", "Three", "FOR", "AGAINST", "N/A",
    "No Vote",
})
_VOTES_LONGEST_FIRST = sorted(VOTES, key=len, reverse=True)
_RECS_LONGEST_FIRST = sorted(RECS, key=len, reverse=True)

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
_DATE = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.()\-]{0,11}$")
_DASHES = re.compile(r"^-{5,}\s*$")
_HEADER = re.compile(r"^#\s+Proposal\s+(Mgt Rec|Diss Rec)\s+Vote Cast\s+Sponsor\s*$")
_TICKER = re.compile(r"^Ticker:(.*?)Security ID:(.*)$")
_MEETING = re.compile(r"^Meeting Date:\s*(.*?)(?:\s+Meeting Type:\s*(.*))?$")
_STRUCT_PREFIXES = ("Ticker:", "Meeting Date:", "Record Date:", "#", "-", "=")


def _norm(s: str) -> str:
    return " ".join(s.split())


def _iso(s: str) -> str:
    m = _DATE.match(s.strip())
    if not m or m.group(1).upper() not in _MONTHS:
        return ""
    try:
        return _dt.date(int(m.group(3)), _MONTHS[m.group(1).upper()], int(m.group(2))).isoformat()
    except ValueError:
        return ""


def _to_lines(text: str) -> list[str]:
    if re.search(r"<\s*(pre|html|body)\b", text, re.I):
        text = _html.unescape(re.sub(r"<[^>]*>", "", text))
        lines = text.split("\n")
    else:  # SGML wrapper lines (<PAGE>, <TEXT>, ...) are not content
        lines = ["" if re.match(r"^\s*</?[A-Za-z][^>]*>\s*$", ln) else ln for ln in text.split("\n")]
    return [ln.rstrip("\r").expandtabs(8).rstrip() for ln in lines]


def _suffix_token(rest: str, vocab_longest_first: list[str]) -> tuple[str, str] | None:
    """Longest vocabulary token at the right end of ``rest`` (token-aligned)."""
    for tok in vocab_longest_first:
        if rest.endswith(tok) and (len(rest) == len(tok) or rest[-len(tok) - 1].isspace()):
            return tok, rest[: -len(tok)]
    return None


def _split_tail(body: str) -> tuple[str, str, str, str] | str:
    """body = line minus its id.  -> (text, rec, vote, sponsor) or a drop reason."""
    sp = next((s for s in SPONSORS if body.endswith(s) and (len(body) == len(s) or body[-len(s) - 1].isspace())), None)
    if sp is None:
        return "unknown_sponsor"
    rest = body[: -len(sp)]
    if not rest or not rest[-1].isspace():
        return "unknown_vote"  # sponsor glued to the vote, or nothing before it
    v = _suffix_token(rest.rstrip(), _VOTES_LONGEST_FIRST)
    if v is None:
        return "unknown_vote"
    vote, before_vote = v
    gap = len(before_vote) - len(before_vote.rstrip())
    r = _suffix_token(before_vote.rstrip(), _RECS_LONGEST_FIRST)
    if r is None or gap == 0:
        return "unknown_rec"
    rec, before_rec = r
    if gap == 1 and " " not in rec:  # a lone-word rec is always column-padded from the vote
        return "unknown_rec"
    return _norm(before_rec), rec, vote, sp


class _Meeting:
    def __init__(self, fund: str | None, issuer: str, ticker: str, security_id: str) -> None:
        self.fund = fund
        self.issuer = issuer
        self.ticker = ticker
        self.security_id = security_id
        self.date = ""
        self.mtype = ""
        self.record = ""
        self.error = ""
        self.date_lines = 0
        self.record_seen = False
        self.rec_label = ""
        self.card = ""
        self.pre: list[str] = []
        self.cur: dict | None = None
        self.props: list[dict] = []

    def fail(self, reason: str) -> None:
        if not self.error:
            self.error = reason

    def flush_pre(self) -> None:
        text = _norm(" ".join(self.pre))
        self.pre = []
        if not text:
            return
        if re.search(r"\bProxy\b", text) and re.search(r"\bCard\b", text, re.I):
            m = re.match(r"^(.*?\bCard\b[^()]*\))", text)
            if m:
                self.card = m.group(1)
            elif re.search(r"\bCard$", text):
                self.card = text
            else:
                self.fail("bad_card_label")
        # anything else is heading text: neither emitted nor appended


def _heading_at(lines: list[str], i: int) -> tuple[str, int] | None:
    """A '='-framed heading starting at line i (and its wrapped lines) -> (text, next_i)."""
    first = lines[i]
    if not first.startswith("=") or "END NPX REPORT" in first:
        return None
    parts: list[str] = []
    j = i
    while j < len(lines) and lines[j].strip():
        ln = lines[j]
        if "END NPX REPORT" in ln or not (ln.startswith("=") or ln[0].isspace()):
            break
        parts.append(ln.strip("= \t"))
        j += 1
    text = _norm(" ".join(p for p in parts if p))
    return (text, j) if text else None


def _run(text: str) -> tuple[list[dict], dict]:
    lines = _to_lines(text)
    n = len(lines)
    rows: list[dict] = []
    reasons: Counter[str] = Counter()
    stats = {"meetings_seen": 0, "meetings_dropped": 0, "proposals_seen": 0,
             "proposals_emitted": 0, "proposals_dropped": 0}
    fund: str | None = None
    mtg: _Meeting | None = None

    def next_nonblank(k: int) -> str:
        while k < n and not lines[k].strip():
            k += 1
        return lines[k] if k < n else ""

    def finish() -> None:
        nonlocal mtg
        m = mtg
        mtg = None
        if m is None:
            return
        m.flush_pre()
        if not m.error and not m.date:
            m.fail("bad_date")
        if m.error:
            stats["meetings_dropped"] += 1
            reasons[f"meeting:{m.error}"] += 1
        for p in m.props:
            stats["proposals_seen"] += 1
            reason = "meeting_dropped" if m.error else p["reason"]
            ptext = _norm(" ".join(p["text"]))
            if not reason and not ptext:
                reason = "empty_text"
            if reason:
                stats["proposals_dropped"] += 1
                reasons[f"proposal:{reason}"] += 1
                continue
            stats["proposals_emitted"] += 1
            rows.append({
                "fund_heading": m.fund, "issuer_name": m.issuer, "ticker": m.ticker,
                "security_id": m.security_id, "meeting_date": m.date, "meeting_type": m.mtype,
                "record_date": m.record, "rec_label": p["rec_label"], "card_label": p["card"],
                "proposal_id": p["id"], "proposal_text": ptext, "rec": p["rec"],
                "vote": p["vote"], "sponsor": p["sponsor"],
            })

    i = 0
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if "END NPX REPORT" in line and line.startswith("="):
            finish()
            fund = None
            i += 1
            continue
        h = _heading_at(lines, i)
        if h is not None:
            finish()
            fund, i = h[0], h[1]
            continue
        if _DASHES.match(line):
            finish()
            i += 1
            continue
        t = _TICKER.match(line)
        if t:
            finish()
            stats["meetings_seen"] += 1
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            issuer = ""
            if j >= 0 and not lines[j][0].isspace() and not lines[j].startswith(_STRUCT_PREFIXES):
                issuer = _norm(lines[j])
                prev = lines[j - 1] if j > 0 else ""
                if prev.strip() and not _DASHES.match(prev) and not prev.startswith("="):
                    issuer = ""  # issuer name spans several lines: ambiguous
            mtg = _Meeting(fund, issuer, _norm(t.group(1)), _norm(t.group(2)))
            if fund is None:
                mtg.fail("no_fund_heading")
            elif not issuer:
                mtg.fail("no_issuer")
            i += 1
            continue
        if mtg is None:
            i += 1
            continue
        m = mtg
        if line.startswith("Meeting Date:") and m.rec_label == "" and not m.pre:
            md = _MEETING.match(line)
            m.date_lines += 1
            d = _iso(md.group(1)) if md else ""
            if m.date_lines > 1:
                m.fail("duplicate_meeting_date")
            elif not d:
                m.fail("bad_date")
            else:
                m.date = d
                m.mtype = _norm(md.group(2) or "")
            i += 1
            continue
        if line.startswith("Record Date:") and m.rec_label == "":
            m.record = _iso(line[len("Record Date:"):])
            m.record_seen = True
            i += 1
            continue
        if line.startswith("#"):
            hm = _HEADER.match(line)
            m.flush_pre()
            m.cur = None
            if hm:
                m.rec_label = hm.group(1)
            else:
                m.fail("unknown_header")
            i += 1
            continue
        if m.date and not m.rec_label and not m.record_seen:
            m.mtype = _norm(f"{m.mtype} {line}")  # Meeting Type wrapped onto the next line
        elif not line[0].isspace():
            if not m.rec_label:
                m.fail("unexpected_line")
            elif next_nonblank(i + 1).startswith("Ticker:"):
                pass  # issuer line of the next meeting (no dashed separator seen)
            elif line.startswith(("Meeting Date:", "Record Date:")):
                m.fail("unexpected_line")
            else:
                m.flush_pre()
                parts = line.split(None, 1)
                prop: dict = {"id": parts[0], "text": [], "reason": "", "rec_label": m.rec_label,
                              "card": m.card, "rec": "", "vote": "", "sponsor": ""}
                m.props.append(prop)
                m.cur = prop
                if len(parts) < 2 or not _ID.match(parts[0]):
                    prop["reason"] = "bad_id"
                else:
                    res = _split_tail(parts[1])
                    if isinstance(res, str):
                        prop["reason"] = res
                    else:
                        prop["text"].append(res[0])
                        prop["rec"], prop["vote"], prop["sponsor"] = res[1], res[2], res[3]
        else:  # indented: continuation of the current proposal, or pre-proposal text
            if m.cur is not None:
                m.cur["text"].append(line.strip())
            elif m.rec_label:
                m.pre.append(line.strip())
            else:
                m.fail("unexpected_line")
        i += 1
    finish()
    stats["reasons"] = dict(reasons)
    return rows, stats


def parse(text: str) -> list[dict]:
    """One dict per VOTED proposal; ambiguous proposals/meetings are omitted."""
    return _run(text)[0]


def parse_stats(text: str) -> dict:
    """meetings_seen/dropped, proposals_seen/emitted/dropped and a reason counter."""
    return _run(text)[1]
