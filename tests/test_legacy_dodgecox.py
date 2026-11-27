"""Dodge & Cox 2022-23 table layout: detection, the printed vocabulary, npx dispatch, and
that the format starts quarantined. The parser pair is tested in its own files."""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_dodgecox, legacy_iss, legacy_issueno, legacy_pe, npx

FUND = "Dodge & Cox Stock Fund"
SID = "S000011202"
_SP = '<TD VALIGN="bottom">&nbsp;&nbsp;</TD>'
HDR = ("<TABLE><TR><TD>&nbsp;</TD>" + _SP + "<TD><P><B>#</B></P></TD>" + _SP
       + "<TD><P><B>Proposal</B></P></TD>" + _SP + "<TD><P><B>Mgt Rec</B></P></TD>" + _SP
       + "<TD><P><B>Vote&nbsp;Cast</B></P></TD>" + _SP + "<TD><P><B>Sponsor</B></P></TD>"
       + "</TR></TABLE>")


def _row(**kw):
    base = {"fund_heading": FUND, "issuer_name": "AEGON NV", "ticker": "AGN",
            "security_id": "007924103", "meeting_date": "2023-01-17", "meeting_status": "",
            "meeting_type": "Extraordinary Shareholders", "country": "",
            "proposal_id": "2", "proposal_text": "Approve Sale of Aegon Nederland",
            "proponent": "Management", "rec": "For", "vote": "For", "for_against": ""}
    base.update(kw)
    return base


def _votes(rows):
    return legacy_dodgecox.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})


def test_header_cells_detect_as_dodgecox():
    assert legacy_iss.doc_format(HDR) == "dodgecox"


REAL_HDR = ("<TR>\n<TD VALIGN=\"bottom\" NOWRAP> <P><B>#</B></P><HR WIDTH=\"4.05\" NOSHADE></TD>\n"
            "<TD>&nbsp;&nbsp;</TD>\n<TD> <P><B>Proposal</B></P><HR NOSHADE ALIGN=\"left\"></TD>\n"
            "<TD>&nbsp;&nbsp;</TD>\n<TD> <P ALIGN=\"center\"><B>Mgt Rec</B></P><HR NOSHADE></TD>\n"
            "<TD>&nbsp;&nbsp;</TD>\n<TD> <P><B>Vote Cast</B></P><HR NOSHADE></TD>\n"
            "<TD>&nbsp;&nbsp;</TD>\n<TD> <P><B>Sponsor</B></P><HR NOSHADE></TD></TR>")


def test_the_filed_header_markup_detects():          # 0001193125-23-219201: <HR> in cells
    assert legacy_iss.doc_format(REAL_HDR) == "dodgecox"


def test_header_words_in_one_text_line_do_not_detect():
    text = "<pre># Proposal Mgt Rec Vote Cast Sponsor</pre>"     # the ISS text header
    assert not legacy_iss.is_dodgecox(text) and legacy_iss.doc_format(text) == "iss"


@pytest.mark.parametrize("field,printed,col,stored", [
    ("proponent", "Management", "vote_source", "ISSUER"),
    ("proponent", "Shareholder", "vote_source", "SECURITY HOLDER"),
    ("vote", "Abstain", "how_voted", "ABSTAIN"),
    ("vote", "One Year", "how_voted", "1 YEAR"),
    ("vote", "Against", "how_voted", "AGAINST")])
def test_printed_forms_map(field, printed, col, stored):
    votes, _ = _votes([_row(**{field: printed})])
    assert [v[col] for v in votes] == [stored]
    assert votes[0]["legacy_format"] == "dodgecox"
    assert votes[0]["proposal_number"] == "2"


def test_three_years_rec_against_one_year_vote():
    votes, _ = _votes([_row(rec="Three Years", vote="One Year")])
    assert votes[0]["management_recommendation"] == "AGAINST"


def test_bare_security_id_typed_and_validated():
    votes, _ = _votes([_row()])
    assert votes[0]["cusip"] == "007924103"
    votes, _ = _votes([_row(security_id="N00927298")])
    assert votes[0]["cusip"] == "N00927298"
    votes, _ = _votes([_row(security_id="007924104")])        # bad check digit
    assert votes[0]["cusip"] == "" and votes[0]["isin"] == ""


@pytest.mark.parametrize("vote", ["Did Not Vote", "None", ""])
def test_not_cast_votes_are_dropped(vote):
    votes, info = _votes([_row(vote=vote)])
    assert votes == [] and info["dropped_vote"] == 1


def test_rec_none_leaves_recommendation_empty():
    votes, _ = _votes([_row(rec="None")])
    assert votes[0]["management_recommendation"] in ("", None)


def test_constants_and_quarantine():
    assert legacy_dodgecox.LEGACY_FORMAT == "dodgecox"
    assert legacy_dodgecox.REPORT_OK == "LEGACY_DODGECOX"
    assert legacy_dodgecox.REPORT_REJECTED == "LEGACY_DODGECOX_REJECTED"
    # Promoted 2026-11-27 after review (no blockers) and a 12-row hand sample (plus the
    # reviewer's 12) against the filings.
    assert "dodgecox" in ledger.PROMOTED_LEGACY_FORMATS
    assert "'dodgecox'" in ledger.NON_LEGACY_VOTE_SQL
    assert "LEGACY_DODGECOX" in ledger.LEGACY_ACCEPTED_REPORT_TYPES


def test_parser_pair():
    names = {p.__name__.rsplit(".", 1)[1] for p in legacy_dodgecox.PARSERS}
    assert names == {"legacy_dodgecox_dom", "legacy_dodgecox_rows"}


def test_npx_dispatches_the_format():
    src = open(npx.__file__).read()
    assert 'fmt == "dodgecox" and legacy_issueno_flag' in src
    assert 'fam == "dodgecox" and fmt == "dodgecox"' in src
    assert "LEGACY_DODGECOX_REJECTED" in src


def test_ingest_filing_delegates_with_this_layout(monkeypatch):
    seen = {}
    monkeypatch.setattr(legacy_issueno, "ingest_filing",
                        lambda *a, **k: seen.update(layout=k["layout"]) or 5)
    assert legacy_dodgecox.ingest_filing(None, None, None, "d", {}, "") == 5
    assert seen["layout"] is legacy_dodgecox
