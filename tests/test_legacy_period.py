"""A legacy filing whose SGML header period is not 2023-06-30 counts as a 2022-23 report
only when its document states that period AND its meeting dates sit in the window."""

from __future__ import annotations

import pytest

from glasshouse.ingest import legacy_period
from glasshouse.ingest.edgar import Filing


def _filing(period="2022-06-30", filed="2023-09-01"):
    return Filing(cik="0001485894", company_name="X", form_type="N-PX", filing_date=filed,
                  period_of_report=period, accession_number="0001438934-23-000406")


def _doc(stated, dates):
    body = "\n".join(f"Meeting Date: {d}   Meeting Type: Annual" for d in dates)
    return f"Date of reporting period: {stated}\n{body}\n"


GOOD = ["30-May-2023", "JUL 05, 2022", "03/15/2023"]


@pytest.mark.parametrize("stated", [
    "July 1, 2022 through June 30, 2023", "07/01/2022 - 06/30/2023",
    "07/01/22 - 06/30/23", "07-01-2022 - 06-30-2023", "July 1, 2022 to June 30, 2023",
    "July 1, 2022 - June 30, 2023"])
def test_stated_and_dates_pass(stated):
    r = legacy_period.resolve(_filing(), {"a.txt": _doc(stated, GOOD)})
    assert r.accepted and r.stated and r.share == 1.0
    assert r.filing.period_of_report == "2023-06-30"
    assert "20220630" in r.filing.period_note or "2022-06-30" in r.filing.period_note


def test_stated_but_dates_in_2021_22_fail():
    docs = {"a.txt": _doc("July 1, 2022 through June 30, 2023",
                          ["JUL 05, 2021", "NOV 02, 2021", "MAY 05, 2022"])}
    r = legacy_period.resolve(_filing(), docs)
    assert not r.accepted and r.share == 0.0
    assert r.filing.period_of_report == "2022-06-30" and r.filing.period_note == ""


def test_one_date_after_window_fails():
    dates = GOOD * 200 + ["JUL 05, 2023"]
    assert not legacy_period.resolve(
        _filing(), {"a.txt": _doc("July 1, 2022 through June 30, 2023", dates)}).accepted


def test_under_99_percent_fails():
    dates = GOOD * 30 + ["JUL 05, 2021"]            # 1/91 outside = 98.9%
    assert not legacy_period.resolve(
        _filing(), {"a.txt": _doc("07/01/2022 - 06/30/2023", dates)}).accepted


def test_dates_fine_but_no_statement_fails():
    r = legacy_period.resolve(_filing(), {"a.txt": "\n".join(
        f"Meeting Date: {d}" for d in GOOD)})
    assert not r.accepted and not r.stated and r.share == 1.0


def test_stated_other_year_fails():
    r = legacy_period.resolve(_filing(), {"a.txt": _doc(
        "July 1, 2021 through June 30, 2022", GOOD)})
    assert not r.accepted


def test_no_parseable_dates_fails():
    assert not legacy_period.resolve(
        _filing(), {"a.txt": "Date of reporting period: 07/01/2022 - 06/30/2023"}).accepted


def test_header_period_2023_06_30_unchanged():
    f = _filing(period="2023-06-30")
    assert legacy_period.is_candidate(f)
    assert legacy_period.resolve(f, {}).filing is f


def test_outside_filing_window_not_considered():
    assert not legacy_period.in_filing_window(_filing(filed="2022-09-01"))
    assert legacy_period.in_filing_window(_filing(filed="2023-09-01"))
