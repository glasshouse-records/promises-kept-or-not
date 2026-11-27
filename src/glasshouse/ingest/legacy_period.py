"""Which legacy N-PX filings are 2022-23 reports when the SGML header period is wrong.

Some filers put a wrong <PERIOD> in the EDGAR header (JPMorgan 0001438934-23-000406 says
20220630 for a July 2022 - June 2023 report). A filing whose header period is not 2023-06-30
is treated as a 2022-23 report ONLY if BOTH hold:
  1. its document states a reporting period of July 1, 2022 through June 30, 2023, and
  2. at least 99% of its parseable meeting dates fall in 2022-07-01..2023-06-30 and none
     fall after 2023-06-30.
Otherwise it is left alone (late refilings of 2021-22 and earlier fail both tests). The
accepted filing's effective period is 2023-06-30; the header value and the evidence are
kept in `filings.notes`. A document is only fetched for a filing in `in_filing_window`.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace
from datetime import date

from .edgar import Filing
from .legacy_pe import PERIOD

WINDOW = (date(2022, 7, 1), date(2023, 6, 30))
FILED_WINDOW = ("2023-07-01", "2024-06-30")
MIN_SHARE = 0.99

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_NAME = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_D = rf"(?:{_NAME}\s+\d{{1,2}},?\s+20\d{{2}}|\d{{1,2}}[/-]\d{{1,2}}[/-](?:20)?\d{{2}})"
_STATED = re.compile(
    rf"(?i)reporting\s+period\s*:?\s*({_D})\s*(?:through|thru|to|-|–|—)\s*({_D})")
_MEETING = re.compile(r"(?i)meeting\s+date\s*:?\s*([A-Za-z0-9,/\- ]{6,14})")


def _clean(text: str) -> str:
    t = re.sub(r"<[^>]*>", " ", text)
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t)


def _ymd(s: str) -> date | None:
    """A printed date -> date, or None. Month-name and numeric (m/d/y, m-d-y) forms, plus
    d-Mon-yyyy; two-digit years are 20yy."""
    s = s.strip().rstrip(".,")
    try:
        m = re.match(rf"(?i)({_NAME})\s+(\d{{1,2}}),?\s+(20\d{{2}})", s)
        if m:
            return date(int(m[3]), _MONTHS[m[1][:3].lower()], int(m[2]))
        m = re.match(rf"(?i)(\d{{1,2}})-({_NAME})-(20\d{{2}})", s)
        if m:
            return date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1]))
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](?:20)?(\d{2})\b", s)
        if m:
            return date(2000 + int(m[3]), int(m[1]), int(m[2]))
    except (ValueError, KeyError):
        return None
    return None


def states_period(text: str) -> str:
    """The quoted 'reporting period' phrase when it is exactly 2022-07-01..2023-06-30, else ''."""
    for m in _STATED.finditer(_clean(text)):
        if _ymd(m[1]) == WINDOW[0] and _ymd(m[2]) == WINDOW[1]:
            return m[0]
    return ""


def meeting_dates(text: str) -> list[date | None]:
    return [_ymd(m[1]) for m in _MEETING.finditer(_clean(text))]


@dataclass
class Resolution:
    filing: Filing
    accepted: bool
    stated: str          # the quoted statement ('' = none found)
    share: float | None  # share of parseable meeting dates inside the window
    n_dates: int
    n_after: int


def is_candidate(filing: Filing) -> bool:
    return filing.form_type in ("N-PX", "N-PX/A") and filing.period_of_report == PERIOD


def in_filing_window(filing: Filing) -> bool:
    return filing.form_type in ("N-PX", "N-PX/A") and bool(filing.filing_date) and \
        FILED_WINDOW[0] <= filing.filing_date <= FILED_WINDOW[1]


def resolve(filing: Filing, docs: dict[str, str]) -> Resolution:
    """Apply the rule. A header-2023-06-30 filing is returned unchanged and accepted."""
    if is_candidate(filing):
        return Resolution(filing, True, "", None, 0, 0)
    stated = ""
    for name in sorted(docs):
        stated = states_period(docs[name])
        if stated:
            break
    dates = [d for text in docs.values() for d in meeting_dates(text) if d]
    inside = sum(WINDOW[0] <= d <= WINDOW[1] for d in dates)
    after = sum(d > WINDOW[1] for d in dates)
    share = inside / len(dates) if dates else None
    ok = bool(stated) and share is not None and share >= MIN_SHARE and after == 0
    if not ok:
        return Resolution(filing, False, stated, share, len(dates), after)
    note = (f"header period {filing.period_of_report} overridden to {PERIOD}: document states "
            f"'{stated}'; {inside}/{len(dates)} meeting dates in 2022-07-01..2023-06-30, "
            f"none after (legacy_period rule)")
    return Resolution(replace(filing, period_of_report=PERIOD, period_note=note),
                      True, stated, share, len(dates), after)
