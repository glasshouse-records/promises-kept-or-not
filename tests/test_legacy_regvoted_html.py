"""'Registrant Voted' 2022-23 layout as HTML tables (The Advisors' Inner Circle Fund III,
GQG and other advisers): detection, the extra printed vocabulary, npx dispatch, and that the
format is quarantined. The parser pair is tested in its own files; this tests the wrapper."""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.ingest import (
    legacy_iss,
    legacy_issueno,
    legacy_pe,
    legacy_regvoted,
    legacy_regvoted_html,
    npx,
)

FUND = "GQG Partners Emerging Markets Equity Fund"
SID = "S000047193"
HTML_HDR = ("<table><tr><td colspan=2><b>Proposal</b>&#160;</td><td>&#160;</td>"
            "<td><b>Proposed by</b>&#160;</td><td><b>Mgt. Position</b>&#160;</td>"
            "<td><b>Registrant Voted</b>&#160;</td></tr></table>")
DIV_HDR = ("<table><tr><td>&#160;</td><td><div>Proposal</div></td><td><div>Proposed by</div>"
           "</td><td><div>Mgt. Position</div></td><td><div>Registrant Voted</div></td></tr>"
           "</table>")
TEXT_HDR = "<pre>\n Proposal      Proposed by Mgt. Position Registrant Voted\n</pre>"


def _row(**kw):
    base = {"fund_heading": FUND, "issuer_name": "ABB LTD.", "ticker": "ABBN",
            "security_id": "H0010V101", "meeting_date": "09/07/2022",
            "meeting_status": "", "meeting_type": "Special", "country": "",
            "proposal_id": "1", "proposal_text": "Approve Spin-Off", "proponent": "Management",
            "rec": "For", "vote": "For", "for_against": ""}
    base.update(kw)
    return base


def _votes(rows):
    return legacy_regvoted_html.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})


# -- detection ----------------------------------------------------------------

@pytest.mark.parametrize("doc", [HTML_HDR, DIV_HDR])
def test_html_tables_detect_as_regvoted_html(doc):
    assert legacy_iss.doc_format(doc) == "regvoted_html"


def test_text_layout_keeps_its_detection():
    assert legacy_iss.doc_format(TEXT_HDR) == "regvoted"


# -- vocabulary ---------------------------------------------------------------

@pytest.mark.parametrize("field,printed,col,stored", [
    ("proponent", "Issuer", "vote_source", "ISSUER"),
    ("proponent", "Management", "vote_source", "ISSUER"),
    ("proponent", "Shareholder", "vote_source", "SECURITY HOLDER"),
    ("vote", "One Year", "how_voted", "1 YEAR"),
    ("vote", "Three Years", "how_voted", "3 YEARS"),
    ("vote", "Withheld", "how_voted", "WITHHOLD")])
def test_printed_forms_map(field, printed, col, stored):
    kw = {field: printed}
    if field == "vote" and "Year" in printed:
        kw["rec"] = printed
    votes, info = _votes([_row(**kw)])
    assert [v[col] for v in votes] == [stored]
    assert votes[0]["legacy_format"] == "regvoted_html"


def test_one_year_rec_compares_with_management():
    votes, _ = _votes([_row(rec="One Year", vote="1 Year")])
    assert votes[0]["management_recommendation"] == "FOR"


@pytest.mark.parametrize("vote", ["Did Not Vote", "Do Not Vote", "Take No Action",
                                  "Non-Voting", "Split", ""])
def test_not_cast_votes_are_dropped_and_counted(vote):
    votes, info = _votes([_row(vote=vote)])
    assert votes == [] and info["dropped_vote"] == 1


def test_unknown_proponent_dropped():
    votes, info = _votes([_row(proponent="Non-Voting")])
    assert votes == []


# -- quarantine, constants, dispatch -------------------------------------------

def test_constants_and_quarantine():
    assert legacy_regvoted_html.LEGACY_FORMAT == "regvoted_html"
    assert legacy_regvoted_html.REPORT_OK == "LEGACY_REGVOTED_HTML"
    assert legacy_regvoted_html.REPORT_REJECTED == "LEGACY_REGVOTED_HTML_REJECTED"
    assert "regvoted_html" not in ledger.PROMOTED_LEGACY_FORMATS
    assert "regvoted_html" not in ledger.NON_LEGACY_VOTE_SQL


def test_parser_pair():
    a, b = legacy_regvoted_html.PARSERS
    assert {a.__name__.rsplit(".", 1)[1], b.__name__.rsplit(".", 1)[1]} == {
        "legacy_regvoted_html_cells", "legacy_regvoted_html_rows"}


def test_npx_dispatches_the_format():
    src = open(npx.__file__).read()
    assert 'fmt == "regvoted_html" and legacy_issueno_flag' in src
    assert 'fam == "regvoted_html" and fmt == "regvoted_html"' in src
    assert "LEGACY_REGVOTED_HTML_REJECTED" in src


def test_ingest_filing_delegates_with_this_layout(monkeypatch):
    seen = {}
    monkeypatch.setattr(legacy_issueno, "ingest_filing",
                        lambda *a, **k: seen.update(layout=k["layout"]) or 5)
    assert legacy_regvoted_html.ingest_filing(None, None, None, "d", {}, "") == 5
    assert seen["layout"] is legacy_regvoted_html


def test_text_wrapper_vocabulary_unchanged():
    assert "Issuer" not in legacy_regvoted.PROPONENT_FORMS
    assert "One Year" not in legacy_regvoted.VOTE_FORMS
