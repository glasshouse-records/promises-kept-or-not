"""Parser for the legacy (pre-XML) N-PX "Issue No." text layout.

Block-oriented design, precision over recall:

1. reduce the document to text lines (HTML / SGML-table markup removed,
   entities decoded, form feeds split into lines);
2. split into fund sections (``Fund Name : X``);
3. split each fund into meeting blocks at separator lines (20+ ``_``/``-``);
4. parse each block's fixed header lines using the column positions of the
   block's OWN header lines, then its proposal table using the positions of
   its own column-header line.

Anything that cannot be placed with certainty is dropped (never guessed),
and the drop is counted in ``parse_stats``.  Nothing carries across a
meeting or fund boundary.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import datetime

# Closed vocabularies, taken from the four real samples (Schwab, VanEck,
# Hartford, Russell).  Anything else drops the proposal.
PROPONENTS = frozenset({"Mgmt", "MGMT", "ShrHoldr", "N/A"})
RECS = frozenset({"For", "FOR", "Against", "Abstain", "Withhold", "1 Year",
                  "2 Years", "3 Years", "N/A"})
VOTES = frozenset({"For", "FOR", "Against", "Abstain", "Withhold", "1 Year",
                   "2 Years", "3 Years", "N/A", "TNA", "Echo Vote"})
FOR_AGAINST = frozenset({"For", "FOR", "Against", "N/A"})
SECURITY_ID_TYPES = frozenset({"CUSIP", "CINS", "ISIN", "SEDOL"})

_SEP = re.compile(r"^\s*(?:_{20,}|-{20,})\s*$")
_FUND = re.compile(r"^\s*Fund\s+Name\s*:\s*(.*?)\s*$", re.I)
_TAG = re.compile(r"<[^>]*>")
_MARKUP_ONLY = re.compile(r"^\s*(?:<[^>]*>\s*)+$")
_ISSUE_NO = re.compile(r"^\d+(?:\.\d+)*$")
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_ROW_FIELDS = ("proposal_id", "proposal_text", "proponent", "rec", "vote", "for_against")


def _norm(s: str) -> str:
    return " ".join(s.split())


def _has_markup(text: str) -> bool:
    return bool(re.search(r"<(?:/?(?:PRE|P|DIV|HTML|BODY|TABLE|CAPTION|S|C|PAGE|FONT|BR|TD|TR)\b)", text, re.I))


def to_lines(text: str) -> list[str]:
    """Document text to plain lines; markup-only lines are removed."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\f\n")
    markup = _has_markup(text)
    is_html = bool(re.search(r"<(?:PRE|P|DIV|HTML|BODY|BR|FONT)\b", text, re.I))
    if markup:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: list[str] = []
    for line in text.split("\n"):
        if markup:
            if _MARKUP_ONLY.match(line):
                continue
            line = _TAG.sub("", line)
            if is_html:
                line = html.unescape(line).replace("\xa0", " ")
        out.append(line.rstrip())
    return out


def _positions(line: str, labels: tuple[str, ...]) -> list[int] | None:
    """Start index of each label, in order, within a header line."""
    low = line.lower()
    pos, at = [], 0
    for lab in labels:
        i = low.find(lab, at)
        if i < 0:
            return None
        pos.append(i)
        at = i + len(lab)
    return pos


def _cells(line: str, starts: list[int], end: int | None = None) -> list[str] | None:
    """Slice a line at column starts; None if text straddles a boundary."""
    bounds = starts + [len(line) if end is None else end]
    out = []
    for k in range(len(starts)):
        a, b = bounds[k], bounds[k + 1]
        if k > 0 and a <= len(line) and line[a - 1 : a].strip() != "":
            return None
        out.append(line[a:b].strip())
    return out


class _Stats:
    def __init__(self) -> None:
        self.meetings_seen = 0
        self.meetings_dropped = 0
        self.proposals_seen = 0
        self.proposals_emitted = 0
        self.proposals_dropped = 0
        self.reasons: Counter[str] = Counter()

    def as_dict(self) -> dict:
        return {
            "meetings_seen": self.meetings_seen,
            "meetings_dropped": self.meetings_dropped,
            "proposals_seen": self.proposals_seen,
            "proposals_emitted": self.proposals_emitted,
            "proposals_dropped": self.proposals_dropped,
            "reasons": dict(self.reasons),
        }


def _split_blocks(lines: list[str]):
    """Yield (fund_heading_or_None, block_lines) for every separator block."""
    fund: str | None = None
    cur: list[str] | None = None
    for line in lines:
        m = _FUND.match(line)
        if m:
            if cur is not None:
                yield fund, cur
            cur = None
            fund = _norm(m.group(1)) or None
            continue
        if _SEP.match(line):
            if cur is not None:
                yield fund, cur
            cur = []
            continue
        if cur is not None:
            cur.append(line)
    if cur is not None:
        yield fund, cur


def _is_meeting_block(block: list[str]) -> bool:
    return any(re.search(r"security\s+id", b, re.I) or re.match(r"\s*issue\s+no", b, re.I)
               for b in block)


def _parse_header(block: list[str]):
    """Return (meeting dict, index of first line after the column header,
    column starts) or (None, reason, None)."""
    n = len(block)
    i = 0

    def next_nonblank(j: int) -> int:
        while j < n and not block[j].strip():
            j += 1
        return j

    if any("\t" in b for b in block):
        return None, "tab_in_block", None
    i = next_nonblank(0)
    if i >= n:
        return None, "empty_block", None
    issuer = _norm(block[i])
    if re.match(r"(?i)ticker\s+security\s+id", issuer) or not issuer:
        return None, "missing_issuer", None
    i = next_nonblank(i + 1)
    if i + 1 >= n:
        return None, "truncated_header", None
    h1 = _positions(block[i], ("ticker", "security id:", "meeting date", "meeting status"))
    if h1 is None:
        return None, "header1_shape", None
    v1 = block[i + 1]
    cells = _cells(v1, h1)
    if cells is None:
        return None, "value1_misaligned", None
    ticker, sec, mdate, status = cells
    if not _DATE.match(mdate):
        return None, "bad_date", None
    try:
        iso = datetime.strptime(mdate, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None, "bad_date", None
    sec = _norm(sec)
    parts = sec.split(" ")
    if len(parts) != 2 or parts[0] not in SECURITY_ID_TYPES:
        return None, "bad_security_id", None
    if not status or " " in ticker:
        return None, "bad_status_or_ticker", None
    i = next_nonblank(i + 2)
    if i + 1 >= n:
        return None, "truncated_header", None
    h2 = _positions(block[i], ("meeting type", "country of trade"))
    if h2 is None:
        return None, "header2_shape", None
    cells2 = _cells(block[i + 1], h2)
    if cells2 is None or not cells2[0] or not cells2[1]:
        return None, "value2_shape", None
    mtype, country = _norm(cells2[0]), _norm(cells2[1])
    i = next_nonblank(i + 2)
    if i >= n:
        return None, "truncated_header", None
    # column header: Schwab style (label line then 'Mgmt') or Russell style
    # ('FOR/AGNST' line above, 'ISSUE NO. ... MGMT' below).
    first = block[i]
    fa_label = None
    if first.strip().upper() == "FOR/AGNST":
        fa_label = first.upper().index("FOR/AGNST")
        i += 1
        if i >= n:
            return None, "truncated_header", None
        colline = block[i]
        if not colline.rstrip().upper().endswith("MGMT"):
            return None, "colheader_shape", None
        cols = _positions(colline, ("issue no.", "description", "proponent", "mgmt rec", "vote cast"))
        if cols is None or fa_label <= cols[4]:
            return None, "colheader_shape", None
        cols.append(fa_label)
        nxt = i + 1
    else:
        colline = first
        low = colline.lower()
        label = "for/against" if "for/against" in low else ("for/agnst" if "for/agnst" in low else None)
        if label is None:
            return None, "colheader_shape", None
        cols = _positions(colline, ("issue no.", "description", "proponent", "mgmt rec", "vote cast", label))
        if cols is None:
            return None, "colheader_shape", None
        rest = colline.lower().split(label, 1)[1].strip()
        nxt = i + 1
        if rest == "mgmt":
            pass
        else:
            if rest or nxt >= n or block[nxt].strip().lower() != "mgmt":
                return None, "colheader_shape", None
            nxt += 1
    if cols[0] != 0 or sorted(cols) != cols:
        return None, "colheader_shape", None
    meeting = {
        "issuer_name": issuer, "ticker": ticker, "security_id": sec,
        "meeting_date": iso, "meeting_status": _norm(status),
        "meeting_type": mtype, "country": country,
    }
    return meeting, nxt, cols


def _parse_row(line: str, cols: list[int]):
    """Classify one table line: ('row', dict) / ('cont', text) / ('bad', reason)."""
    desc_s, prop_s = cols[1], cols[2]
    if not line.strip():
        return "blank", None
    lead = line[:desc_s]
    if not lead.strip():
        # continuation candidate: description text, no issue number.  Some
        # layouts (Russell) print the value columns on the LAST description
        # line instead of the first.
        if not line[prop_s:].strip():
            if len(line) >= prop_s and line[prop_s - 1 : prop_s].strip():
                return "bad", "continuation_shape"
            return "cont", _norm(line[desc_s:prop_s])
        cells = _cells(line, cols)
        if cells is None:
            return "bad", "row_misaligned"
        _, desc, prop, rec, vote, fa = (_norm(c) for c in cells)
        if not (prop and rec and vote and fa):
            return "bad", "continuation_shape"
        return "cont_cells", {"proposal_text": desc, "proponent": prop,
                              "rec": rec, "vote": vote, "for_against": fa}
    cells = _cells(line, cols)
    if cells is None:
        return "bad", "row_misaligned"
    iid, desc, prop, rec, vote, fa = (_norm(c) for c in cells)
    if not _ISSUE_NO.match(iid):
        return "bad", "issue_no_shape"
    return "row", {"proposal_id": iid, "proposal_text": desc, "proponent": prop,
                   "rec": rec, "vote": vote, "for_against": fa}


def _validate(p: dict) -> str | None:
    if not p["proposal_text"]:
        return "empty_text"
    if p["proponent"] not in PROPONENTS:
        return "proponent_vocab"
    if p["rec"] not in RECS:
        return "rec_vocab"
    if p["vote"] not in VOTES:
        return "vote_vocab"
    if p["for_against"] not in FOR_AGAINST:
        return "for_against_vocab"
    return None


def _run(text: str) -> tuple[list[dict], _Stats]:
    stats = _Stats()
    rows: list[dict] = []
    lines = to_lines(text)
    for fund, block in _split_blocks(lines):
        if not _is_meeting_block(block):
            continue
        stats.meetings_seen += 1
        if fund is None:
            stats.meetings_dropped += 1
            stats.reasons["meeting:no_fund_heading"] += 1
            continue
        meeting, nxt, cols = _parse_header(block)
        if meeting is None:
            stats.meetings_dropped += 1
            stats.reasons[f"meeting:{nxt}"] += 1
            continue
        meeting = {"fund_heading": fund, **meeting}
        # proposal table: each entry is [dict|None(dropped), reason|None]
        props: list[list] = []
        cur: list | None = None
        gap = False  # a blank line since the last row/continuation
        for line in block[nxt:]:
            if "\f" in line:
                line = line.replace("\f", "")
                gap = True
                if not line.strip():
                    continue
            kind, val = _parse_row(line, cols)
            if kind == "blank":
                gap = True
                continue
            if kind == "cont_cells":
                # value columns printed on a later description line: only
                # valid if the row so far had none, and nothing follows.
                if cur is None:
                    stats.reasons["proposal:orphan_continuation"] += 1
                elif gap or cur[1] is not None:
                    cur[1] = cur[1] or "continuation_after_gap"
                elif cur[0]["proponent"] or cur[0]["rec"] or cur[0]["vote"] or cur[0]["for_against"]:
                    cur[1] = "duplicate_value_columns"
                else:
                    d = cur[0]
                    d["proposal_text"] = _norm(d["proposal_text"] + " " + val["proposal_text"])
                    for k in ("proponent", "rec", "vote", "for_against"):
                        d[k] = val[k]
                    cur[2] = True
                gap = False
            elif kind == "row":
                cur = [dict(val), None, False]
                props.append(cur)
                gap = False
            elif kind == "cont":
                if cur is None:
                    stats.reasons["proposal:orphan_continuation"] += 1
                elif gap:
                    cur[1] = cur[1] or "continuation_after_gap"
                elif cur[2]:
                    cur[1] = "text_after_value_columns"
                elif cur[1] is None:
                    cur[0]["proposal_text"] = _norm(cur[0]["proposal_text"] + " " + val)
                gap = False
            else:  # bad line
                if cur is not None and not gap:
                    cur[1] = cur[1] or val
                else:
                    # an unplaceable line that may have been a whole row
                    stats.proposals_seen += 1
                    stats.proposals_dropped += 1
                    stats.reasons[f"proposal:stray_line_{val}"] += 1
                cur = None
                gap = False
        for p, reason, _closed in props:
            stats.proposals_seen += 1
            reason = reason or _validate(p)
            if reason:
                stats.proposals_dropped += 1
                stats.reasons[f"proposal:{reason}"] += 1
                continue
            stats.proposals_emitted += 1
            rows.append({**meeting, **p})
    return rows, stats


def parse(text: str) -> list[dict]:
    """Return one dict per cleanly-parsed proposal row (see module docs)."""
    return _run(text)[0]


def parse_stats(text: str) -> dict:
    """Counts of meetings/proposals seen, emitted, dropped, with reasons."""
    return _run(text)[1].as_dict()
