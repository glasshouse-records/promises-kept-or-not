"""Parser for the 2022-23 N-PX 'Registrant Voted' HTML-table layout (tokenizer variant).

Contract: docs/research/legacy-npx.md, "Contract: "Registrant Voted" HTML-table layout"
(rules H1-H9). An html.parser tokenizer builds rows of non-empty cell values; a row-level
state machine reads meetings and proposals from them. Anything the contract leaves open is
DROPPED and counted, never guessed (see the `# DECISION` comments).

    parse(text) -> list[dict]       exactly the 14 keys of legacy_issueno.KEYS
    parse_stats(text) -> Counter    named drop counters
"""
from __future__ import annotations

import datetime as _dt
import re
from collections import Counter
from html.parser import HTMLParser

from glasshouse.ingest.legacy_issueno import KEYS

HEADER = ["Proposal", "Proposed by", "Mgt. Position", "Registrant Voted"]
VOTES = {"Voted - " + v for v in ("For", "Against", "Abstain", "Withheld", "Withhold", "Split",
                                  "1 Year", "One Year", "2 Years", "3 Years", "Three Years")}
VOTES |= {"Did Not Vote", "Do Not Vote", "Take No Action", "Non-Voting"}
RECS = {"For", "Against", "Abstain", "Withhold", "None", "N/A", "1 Year", "One Year",
        "2 Years", "3 Years", "Three Years", "Undetermined", "Non-Voting"}
PROPS = {"Management", "Issuer", "Shareholder", "N/A", "Non-Voting"}
ANY_COL = VOTES | RECS | PROPS
ID_RE = re.compile(r"\d+(?:\.(?:\d+|[A-Za-z]))*[A-Za-z]?\.?")
MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE_RE = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})")


def _clean(s: str) -> str:
    return " ".join(s.replace("\xa0", " ").split())


class _Tok(HTMLParser):
    """Collects (table_index, [non-empty cell values]) for every <tr> of every <table>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[int, list[str]]] = []
        self.table = 0
        self.depth = 0
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.skip = 0

    def _end_cell(self):
        if self.cell is not None and self.row is not None:
            v = _clean("".join(self.cell))
            if v:
                self.row.append(v)
        self.cell = None

    def _end_row(self):
        self._end_cell()
        if self.row:
            self.rows.append((self.table, self.row))
        self.row = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self._end_row()
            self.depth += 1
            self.table += 1
        elif tag == "tr" and self.depth:
            self._end_row()
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self._end_cell()
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "table":
            self._end_row()
            self.depth = max(0, self.depth - 1)
            self.table += 1
        elif tag == "tr":
            self._end_row()
        elif tag in ("td", "th"):
            self._end_cell()

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell.append(data)

    def close(self):
        super().close()
        self._end_row()


def _is_col(v: list[str]) -> bool:
    return len(v) >= 3 and v[-1] in VOTES and v[-2] in RECS and v[-3] in PROPS


def _date(s: str) -> str | None:
    m = DATE_RE.fullmatch(s.strip())
    if not m or m.group(2).lower() not in MONTHS:
        return None
    try:
        d = _dt.date(2000 + int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


class _Meeting:
    def __init__(self, fund, issuer="", sec="", ticker="", date="", mtype="", dropped=False):
        self.fund, self.issuer, self.sec, self.ticker = fund, issuer, sec, ticker
        self.date, self.mtype, self.dropped = date, mtype, dropped
        self.props: list[dict] = []
        self.open: list | None = None  # [proposal_id, [text pieces]]


def _date_row(v: list[str]):
    """-> (meeting_date or None, meeting_type) for a row whose first value is 'Meeting Date:'."""
    first = v[0][len("Meeting Date:"):]
    mtype = ""
    if "Meeting Type:" in first:
        first, _, mtype = first.partition("Meeting Type:")
    elif len(v) > 1 and v[1].startswith("Meeting Type:"):
        mtype = v[1][len("Meeting Type:"):]
    return _date(first), mtype.strip()


def _security(v: list[str]):
    rest = v[0][len("Security ID:"):]
    ticker = ""
    if "Ticker:" in rest:
        rest, _, ticker = rest.partition("Ticker:")
    elif len(v) > 1 and v[1].startswith("Ticker:"):
        ticker = v[1][len("Ticker:"):]
    return rest.strip(), ticker.strip()


def _run(text: str) -> tuple[list[dict], Counter]:
    st: Counter = Counter()
    tok = _Tok()
    tok.feed(text)
    tok.close()
    rows = tok.rows
    n = len(rows)
    out: list[dict] = []

    def vals(i):
        return rows[i][1] if 0 <= i < n else []

    def is_header(i):
        return vals(i) == HEADER

    def is_sec(i):
        v = vals(i)
        return bool(v) and v[0].startswith("Security ID:")

    def is_date(i):
        v = vals(i)
        return bool(v) and v[0].startswith("Meeting Date:")

    def drop_open(m):
        if m.open is not None:
            st["proposal_unclosed"] += 1
            m.open = None

    def finalize(m):
        if m is None or m.dropped:
            return
        drop_open(m)
        ids = [p["proposal_id"] for p in m.props if p["proposal_id"]]
        texts = [p["proposal_text"] for p in m.props]
        low = " ".join(texts).lower()
        if ("contest" in m.mtype.lower() or len(ids) != len(set(ids))
                or "dissident" in low or "management nominee" in low
                or len(texts) != len(set(texts))):
            st["meeting_dropped_contest"] += 1
            m.dropped = True
            return
        out.extend(m.props)
        st["meetings_kept"] += 1

    def kill(m, reason):
        st[reason] += 1
        m.dropped = True
        m.open = None

    fund = None
    cur: _Meeting | None = None
    inherit_ok = False  # the previous row closed a proposal, or was a repeated header
    last_table = None
    i = 0
    while i < n:
        table, v = rows[i]
        if last_table is not None and table != last_table and cur is not None and not cur.dropped:
            drop_open(cur)
        last_table = table
        # heading row: a one-value row directly before the column header (handled there)
        if len(v) == 1 and is_header(i + 1):
            i += 1
            continue
        if v == HEADER:
            prev = vals(i - 1)
            if len(prev) != 1:
                st["doc_rejected_heading"] += 1
                return [], st
            if prev[0] == fund and cur is not None:
                if not cur.dropped:
                    drop_open(cur)
                inherit_ok = True
            else:
                finalize(cur)
                cur, fund, inherit_ok = None, prev[0], False
            i += 1
            continue
        if fund is None:
            st["row_before_header"] += 1
            i += 1
            continue
        # issuer row + Security ID row (+ Meeting Date row)
        if len(v) == 1 and is_sec(i + 1):
            finalize(cur)
            sec, ticker = _security(vals(i + 1))
            inherit_ok = False
            if not sec:
                # DECISION: an empty Security ID is not an identity; drop the meeting.
                cur = _Meeting(fund, dropped=True)
                st["meeting_dropped_no_security_id"] += 1
                i += 2
            elif not is_date(i + 2):
                cur = _Meeting(fund, dropped=True)
                st["meeting_dropped_no_date_row"] += 1
                i += 2
            else:
                d, mt = _date_row(vals(i + 2))
                cur = _Meeting(fund, v[0], sec, ticker, d or "", mt, dropped=d is None)
                if d is None:
                    st["meeting_dropped_bad_date"] += 1
                i += 3
            continue
        if is_sec(i):
            if cur is not None and not cur.dropped:
                kill(cur, "meeting_dropped_stray_security_row")
            else:
                st["stray_security_row_ignored"] += 1
            inherit_ok = False
            i += 1
            continue
        if is_date(i):
            prev = cur
            finalize(prev)
            d, mt = _date_row(v)
            if prev is None or prev.dropped or not inherit_ok:
                cur = _Meeting(fund, dropped=True)
                st["meeting_dropped_bare_date"] += 1
            elif d is None:
                cur = _Meeting(fund, dropped=True)
                st["meeting_dropped_bad_date"] += 1
            else:
                cur = _Meeting(fund, prev.issuer, prev.sec, prev.ticker, d, mt)
            inherit_ok = False
            i += 1
            continue
        if cur is None or cur.dropped:
            st["row_outside_live_meeting"] += 1
            i += 1
            continue
        # proposal rows (H6)
        col = _is_col(v)
        body = v[:-3] if col else v
        id_start = bool(ID_RE.fullmatch(v[0])) and len(v) > 1 and v[1] not in ANY_COL
        if id_start:
            drop_open(cur)
            cur.open = [v[0].rstrip("."), list(body[1:])]
        elif cur.open is not None:
            cur.open[1].extend(body)
        elif col and not body:
            kill(cur, "meeting_dropped_orphan_column_row")
            inherit_ok = False
            i += 1
            continue
        else:
            cur.open = ["", list(body)]
        inherit_ok = False
        if col:
            pid, pieces = cur.open
            cur.open = None
            ptext = _clean(" ".join(pieces))
            if not ptext:
                st["proposal_empty_text"] += 1
            else:
                vote = v[-1]
                if vote.startswith("Voted - "):
                    vote = vote[len("Voted - "):]
                cur.props.append({
                    "fund_heading": cur.fund, "issuer_name": cur.issuer, "ticker": cur.ticker,
                    "security_id": cur.sec, "meeting_date": cur.date, "meeting_status": "",
                    "meeting_type": cur.mtype, "country": "", "proposal_id": pid,
                    "proposal_text": ptext, "proponent": v[-3], "rec": v[-2], "vote": vote,
                    "for_against": ""})
            inherit_ok = True
        i += 1
    finalize(cur)
    st["rows_emitted"] = len(out)
    assert all(tuple(r) == KEYS for r in out)
    return out, st


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]
