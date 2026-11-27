"""Single-fund registrant rule: a filing whose SGML header lists NO series at all and whose
agreed rows (across all documents) carry exactly ONE fund heading maps that heading to
vote_series "" (closed-end funds have no series; same as the XML-era rows). Any header
series, or two or more headings, leaves everything unmapped as before."""

from __future__ import annotations

import pytest
from test_legacy_iss import MGMT
from test_legacy_iss import make_doc as iss_doc
from test_legacy_issueno import make_doc as no_doc
from test_legacy_pe import BASIC as PE_BASIC
from test_legacy_pe import FUND as PE_FUND
from test_legacy_pe import _filing

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_issueno, legacy_pe
from glasshouse.ingest.edgar import Filing

NOSERIES = "<ACCESSION-NUMBER>0001081400-23-000465\n<FILER>\n"
ONESERIES = "<SERIES-ID>S000000001\n<SERIES-NAME>Some Other Fund\n"
ROW = ("Mgmt", "For", "For", "For")


def _conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    return c


def _iss_filing():
    return Filing(cik="0000100001", company_name="V", form_type="N-PX",
                  filing_date="2023-08-30", period_of_report="2023-06-30",
                  accession_number="0001104659-23-095672")


def _pe(c, docs, hdr):
    return legacy_pe.ingest_filing(c, _filing(), "x", "2026-11-27", docs, hdr)


def _iss(c, docs, hdr):
    return legacy_iss.ingest_filing(c, _iss_filing(), "x", "2026-11-27", docs, hdr)


def _no(c, docs, hdr):
    return legacy_issueno.ingest_filing(c, _iss_filing(), "x", "2026-11-27", docs, hdr)


PE_DOC2 = PE_BASIC.replace(PE_FUND, "JPMorgan Other Closed End Fund")
CASES = {
    "pe": (_pe, {"a.txt": PE_BASIC}, {"a.txt": PE_BASIC, "b.txt": PE_DOC2}, PE_FUND),
    "iss": (_iss, {"a": iss_doc("ACME INCOME FUND", [MGMT] * 2)},
            {"a": iss_doc("ACME INCOME FUND", [MGMT] * 2),
             "b": iss_doc("ACME OTHER FUND", [MGMT] * 2)}, "ACME INCOME FUND"),
    "no": (_no, {"a": no_doc([ROW] * 2, fund="Acme Income Fund")},
           {"a": no_doc([ROW] * 2, fund="Acme Income Fund"),
            "b": no_doc([ROW] * 2, fund="Acme Other Fund")}, "Acme Income Fund"),
}


@pytest.mark.parametrize("k", CASES)
def test_zero_series_one_heading_kept_with_empty_series_and_recorded(tmp_path, k):
    fn, one, _two, heading = CASES[k]
    c = _conn(tmp_path)
    n = fn(c, one, NOSERIES)
    assert n > 0
    assert {r[0] for r in c.execute("SELECT vote_series FROM votes")} == {""}
    fb = c.execute("SELECT series_fallback FROM legacy_parse").fetchone()[0]
    assert fb == repr([(heading, "", n)])
    assert c.execute("SELECT funds_unmapped FROM legacy_parse").fetchone()[0] == ""


@pytest.mark.parametrize("k", CASES)
def test_zero_series_two_headings_all_unmapped(tmp_path, k):
    fn, _one, two, _h = CASES[k]
    c = _conn(tmp_path)
    assert fn(c, two, NOSERIES) == 0
    assert c.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0
    rows = c.execute("SELECT funds_unmapped, series_fallback FROM legacy_parse").fetchall()
    assert all(r[0] for r in rows) and all(r[1] == "" for r in rows)


@pytest.mark.parametrize("k", CASES)
def test_header_with_a_series_never_applies(tmp_path, k):
    fn, one, _two, _h = CASES[k]
    c = _conn(tmp_path)
    assert fn(c, one, ONESERIES) == 0
    assert c.execute("SELECT funds_unmapped FROM legacy_parse").fetchone()[0] != ""
    assert c.execute("SELECT series_fallback FROM legacy_parse").fetchone()[0] == ""


def test_helper_contract():
    f = legacy_pe.single_fund_map
    assert f(NOSERIES, ["A  Fund(R)", "a fund"]) == {"a fund": ""}
    assert f(NOSERIES, ["A", "B"]) == {}
    assert f(NOSERIES, []) == {}
    assert f(ONESERIES, ["A"]) == {}
