"""Federated Hermes flat-table N-PX parser, regex flavour.

Contract: docs/research/legacy-npx.md, "Contract: Federated flat table"
(rules F1-F6). One HTML table row per vote; fields read by header label.
Where the contract is silent a row is dropped and counted, never repaired.
"""
from __future__ import annotations

import datetime
import html
import re
from collections import Counter

from .legacy_issueno import KEYS

_BASE = ["Issuer Name", "Country", "Meeting Date", "Meeting Type", "Record Date",
         "Ticker", "Security ID", "Symbol Type", "Ballot Issue Number",
         "Proposal Text", "Proponent", "Mgmt Reco", "Vote Cast", "Fund Name"]
HEADERS = (_BASE + ["Logical Ballot Status"], list(_BASE))

PROPONENTS = {"Mgmt", "ShrHoldr", "Management", "Shareholder", "N/A"}
RECS = {"For", "Against", "Abstain", "Withhold", "None", "N/A", "1 Year",
        "2 Years", "3 Years", "One Year", "Three Years"}
VOTES = {"For", "Against", "Abstain", "Withhold", "TNA", "Do Not Vote", "N/A",
         "1 Year", "2 Years", "3 Years", "One Year"}
STATUSES = {"Voted", "Take No Action"}
SYMBOL_TYPES = {"CUSIP", "CINS"}

_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.I | re.S)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _clean(raw: str) -> str:
    s = html.unescape(_TAG.sub("", raw)).replace("\xa0", " ")
    return _WS.sub(" ", s).strip()


def _iso(value: str) -> str | None:
    m = _DATE.fullmatch(value)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def _walk(text: str):
    """Yield (kind, header, cells) per <tr>; header is the list in force."""
    header: list[str] | None = None
    for tr in _TR.finditer(text):
        cells = [_clean(c) for c in _CELL.findall(tr.group(1))]
        if cells in HEADERS:
            header = cells
            yield "header", header, cells
        elif header is None:
            yield "before_header", None, cells
        elif len(cells) != len(header):
            yield ("wrong_cells_dropped" if any(cells) else "wrong_cells_ignored",
                   header, cells)
        else:
            yield "row", header, cells


def _month_first_unconfirmed(text: str) -> bool:
    for kind, header, cells in _walk(text):
        if kind == "row":
            m = _DATE.fullmatch(dict(zip(header, cells))["Meeting Date"])
            if m and int(m.group(1)) > 12:
                return True
    return False


def parse_stats(text: str) -> Counter:
    stats: Counter = Counter()
    if _month_first_unconfirmed(text):
        stats["document_rejected_day_first_date"] += 1
        return stats
    for kind, header, cells in _walk(text):
        if kind != "row":
            stats[{"header": "header_rows", "before_header": "ignored_before_header",
                   "wrong_cells_dropped": "dropped_wrong_cell_count",
                   "wrong_cells_ignored": "ignored_empty_wrong_cell_count"}[kind]] += 1
            continue
        reason = _check(dict(zip(header, cells)), header)[1]
        stats["rows" if reason is None else f"dropped_{reason}"] += 1
    return stats


def _check(r: dict, header: list[str]):
    """Return (row_or_None, drop_reason_or_None)."""
    iso = _iso(r["Meeting Date"])
    if iso is None:
        return None, "bad_meeting_date"
    if r["Proponent"] not in PROPONENTS:
        return None, "bad_proponent"
    if r["Mgmt Reco"] not in RECS:
        return None, "bad_mgmt_reco"
    if r["Vote Cast"] not in VOTES:
        return None, "bad_vote_cast"
    if r["Symbol Type"].upper() not in SYMBOL_TYPES:
        return None, "bad_symbol_type"
    if "Logical Ballot Status" in r:
        if r["Logical Ballot Status"] not in STATUSES:
            return None, "bad_status"
        status = r["Logical Ballot Status"]
    else:
        status = "Take No Action" if r["Vote Cast"] == "TNA" else "Voted"
    for label in ("Issuer Name", "Fund Name", "Proposal Text"):
        if not r[label]:
            return None, "empty_" + label.lower().replace(" ", "_")
    out = {
        "fund_heading": r["Fund Name"], "issuer_name": r["Issuer Name"],
        "ticker": r["Ticker"],
        "security_id": f"{r['Symbol Type'].upper()} {r['Security ID']}",
        "meeting_date": iso, "meeting_status": status,
        "meeting_type": r["Meeting Type"], "country": r["Country"],
        "proposal_id": r["Ballot Issue Number"], "proposal_text": r["Proposal Text"],
        "proponent": r["Proponent"], "rec": r["Mgmt Reco"], "vote": r["Vote Cast"],
        "for_against": "",
    }
    assert tuple(out) == KEYS
    return out, None


def parse(text: str) -> list[dict]:
    if _month_first_unconfirmed(text):
        return []
    rows = []
    for kind, header, cells in _walk(text):
        if kind == "row":
            out, _ = _check(dict(zip(header, cells)), header)
            if out:
                rows.append(out)
    return rows
