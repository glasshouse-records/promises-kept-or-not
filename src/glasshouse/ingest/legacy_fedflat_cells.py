"""Federated Hermes flat N-PX table: tokenizer parser (contract F1-F6).

Contract: docs/research/legacy-npx.md, "Contract: Federated flat table". An
html.parser tokenizer yields rows of cell values; fields are then read by the
header's labels. Nothing is repaired: a row failing any check is dropped and
counted. Where the contract is silent the row is dropped and counted.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from html.parser import HTMLParser

from glasshouse.ingest.legacy_issueno import KEYS

H15 = ("Issuer Name", "Country", "Meeting Date", "Meeting Type", "Record Date",
       "Ticker", "Security ID", "Symbol Type", "Ballot Issue Number",
       "Proposal Text", "Proponent", "Mgmt Reco", "Vote Cast", "Fund Name",
       "Logical Ballot Status")
HEADERS = (H15, H15[:14])

PROPONENT = {"Mgmt", "ShrHoldr", "Management", "Shareholder", "N/A"}
RECO = {"For", "Against", "Abstain", "Withhold", "None", "N/A", "1 Year", "2 Years",
        "3 Years", "One Year", "Three Years"}
VOTE = {"For", "Against", "Abstain", "Withhold", "TNA", "Do Not Vote", "N/A", "1 Year",
        "2 Years", "3 Years", "One Year"}
STATUS = {"Voted", "Take No Action"}
SYMBOL = {"CUSIP", "CINS"}
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _clean(s: str) -> str:
    return " ".join(s.replace(" ", " ").split())


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def _end_cell(self):
        if self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
        self._cell = None

    def _end_row(self):
        self._end_cell()
        if self._row is not None:
            self.rows.append(self._row)
        self._row = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._end_row()
            self._row = []
        elif tag in ("td", "th"):
            self._end_cell()
            if self._row is None:
                self._row = []
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._end_cell()
        elif tag == "tr":
            self._end_row()

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def close(self):
        super().close()
        self._end_row()


def _rows(text: str) -> list[list[str]]:
    p = _Rows()
    p.feed(text)
    p.close()
    return p.rows


def _iso(s: str):
    mt = _DATE.match(s)
    if not mt:
        return None
    mo, d, y = (int(x) for x in mt.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _scan(text: str):
    """Return (records, stats)."""
    st: Counter = Counter()
    out: list[dict] = []
    header = None
    for cells in _rows(text):
        if tuple(cells) in HEADERS:
            header = tuple(cells)
            st["header_rows"] += 1
            continue
        if header is None:
            st["ignored_before_header"] += 1
            continue
        if len(cells) != len(header):
            if any(cells):
                st["dropped_cell_count"] += 1
            else:
                st["ignored_empty_row"] += 1
            continue
        f = dict(zip(header, cells))
        mt = _DATE.match(f["Meeting Date"])
        if mt and int(mt.group(1)) > 12:
            st["day_first_date"] += 1
        iso = _iso(f["Meeting Date"])
        reason = None
        if iso is None:
            reason = "bad_meeting_date"
        elif f["Proponent"] not in PROPONENT:
            reason = "bad_proponent"
        elif f["Mgmt Reco"] not in RECO:
            reason = "bad_mgmt_reco"
        elif f["Vote Cast"] not in VOTE:
            reason = "bad_vote_cast"
        elif "Logical Ballot Status" in f and f["Logical Ballot Status"] not in STATUS:
            reason = "bad_ballot_status"
        elif f["Symbol Type"].upper() not in SYMBOL:
            reason = "bad_symbol_type"
        elif not (f["Issuer Name"] and f["Fund Name"] and f["Proposal Text"]):
            reason = "empty_required"
        if reason:
            st["dropped_" + reason] += 1
            continue
        status = f.get("Logical Ballot Status") or (
            "Take No Action" if f["Vote Cast"] == "TNA" else "Voted")
        out.append({
            "fund_heading": f["Fund Name"], "issuer_name": f["Issuer Name"],
            "ticker": f["Ticker"],
            "security_id": f"{f['Symbol Type'].upper()} {f['Security ID']}",
            "meeting_date": iso, "meeting_status": status,
            "meeting_type": f["Meeting Type"], "country": f["Country"],
            "proposal_id": f["Ballot Issue Number"], "proposal_text": f["Proposal Text"],
            "proponent": f["Proponent"], "rec": f["Mgmt Reco"], "vote": f["Vote Cast"],
            "for_against": "",
        })
        st["rows"] += 1
    if st["day_first_date"]:
        st["rejected_day_first_document"] += 1
        st["rows_discarded"] = len(out)
        out = []
        st["rows"] = 0
    assert all(set(r) == set(KEYS) for r in out)
    return out, st


def parse(text: str) -> list[dict]:
    return _scan(text)[0]


def parse_stats(text: str) -> Counter:
    return _scan(text)[1]
