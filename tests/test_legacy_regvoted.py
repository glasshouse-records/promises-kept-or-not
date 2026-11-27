"""'Registrant Voted' 2022-23 layout (Global X): detection, the layout-level vote and
proponent vocabulary, npx dispatch, and that the format is quarantined (never shipped).
The two parser modules are replaced by stand-ins: this tests the wrapper only."""

from __future__ import annotations

import types

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_issueno, legacy_pe, legacy_regvoted, npx

FUND = "Global X Uranium ETF"
SID = "S000000042"
HDR_TEXT = f"<SERIES-ID>{SID}\n<SERIES-NAME>{FUND}\n"
COLHDR = " Proposal      Proposed by Mgt. Position Registrant Voted"


def _row(**kw):
    base = {"fund_heading": FUND, "issuer_name": "ABBVIE INC.", "ticker": "ABBV",
            "security_id": "CUSIP 00287Y109", "meeting_date": "05/05/2023",
            "meeting_status": "", "meeting_type": "Annual", "country": "",
            "proposal_id": "1", "proposal_text": "Elect X", "proponent": "Management",
            "rec": "For", "vote": "For", "for_against": ""}
    base.update(kw)
    return base


def _votes(rows):
    return legacy_regvoted.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})


# -- detection ----------------------------------------------------------------

def test_detects_the_column_header_any_spacing_and_tags():
    assert legacy_iss.doc_format(f"<pre>\n{FUND}\n{COLHDR}\n</pre>") == "regvoted"
    tagged = ("<pre>Proposal<b> </b>Proposed&nbsp;by\nMgt.  Position</pre>"
              "<i>Registrant   Voted</i>")
    assert legacy_iss.doc_format(tagged) == "regvoted"


def test_other_formats_keep_their_detection():
    assert legacy_iss.doc_format("Issue No.  Description  Proponent  Mgmt Rec  Vote Cast") == "issueno"
    assert legacy_iss.doc_format("Agenda Number: 1") == "proxyedge"
    assert legacy_iss.doc_format("Proposal  Proposed by  Registrant Voted") is None


# -- vocabulary / proponent ---------------------------------------------------

@pytest.mark.parametrize("printed,how", [
    ("For", "FOR"), ("Against", "AGAINST"), ("Abstain", "ABSTAIN"), ("Withheld", "WITHHOLD"),
    ("Withhold", "WITHHOLD"), ("1 Year", "1 YEAR"), ("2 Years", "2 YEARS"),
    ("3 Years", "3 YEARS")])
def test_vote_vocabulary(printed, how):
    votes, info = _votes([_row(vote=printed)])
    assert [v["how_voted"] for v in votes] == [how]
    assert votes[0]["legacy_format"] == "regvoted" and votes[0]["vote_series"] == SID
    assert votes[0]["meeting_date"] == "05/05/2023"
    assert votes[0]["vote_source"] == "ISSUER"


# 'Take No Action' is dropped, as in legacy_iss (vote) and legacy_issueno (status): nothing was
# cast, and Global X prints it on "Non-Voting Meeting Note" agenda rows (1,017 in 0001135428-23-000255).
@pytest.mark.parametrize("vote", ["Non-Voting", "Voted - Split", "Voted", "N/A", "",
                                  "Take No Action"])
def test_other_votes_are_dropped_and_counted(vote):
    votes, info = _votes([_row(vote=vote)])
    assert votes == [] and info["dropped_vote"] == 1


def test_proponent_mapping():
    votes, info = _votes([_row(proponent="Shareholder"), _row(proponent="Other"),
                          _row(proponent="Mgmt")])
    assert [v["vote_source"] for v in votes] == ["SECURITY HOLDER"]
    assert info["dropped_sponsor"] == 2


def test_contest_meeting_type_still_dropped():
    votes, info = _votes([_row(meeting_type="Proxy Contest")])
    assert votes == [] and info["contest_rows_dropped"] == 1


def test_issueno_vocabulary_is_unchanged():
    assert "Withheld" not in legacy_issueno.HOW_VOTED
    assert "Take No Action" not in legacy_issueno.HOW_VOTED
    assert "Management" not in legacy_issueno.VOTE_SOURCE


# -- agreement via the parser pair --------------------------------------------

def _fake(rows):
    return types.SimpleNamespace(parse=lambda t: list(rows), parse_stats=lambda t: {})


def test_agreed_uses_the_parser_pair():
    r = _row()
    rows, st = legacy_regvoted.agreed("x", (_fake([r]), _fake([r])))
    assert rows == [r] and st["disagreement_rate"] == 0
    rows, st = legacy_regvoted.agreed("x", (_fake([r]), _fake([_row(vote="Against")])))
    assert rows == [] and st["disagreement_rate"] == 1.0


# -- identity, quarantine, dispatch -------------------------------------------

def test_constants_and_quarantine():
    assert legacy_regvoted.LEGACY_FORMAT == "regvoted"
    assert legacy_regvoted.REPORT_OK == "LEGACY_REGVOTED"
    assert legacy_regvoted.REPORT_REJECTED == "LEGACY_REGVOTED_REJECTED"
    assert "regvoted" not in ledger.PROMOTED_LEGACY_FORMATS
    assert "regvoted" not in ledger.NON_LEGACY_VOTE_SQL


def test_regvoted_votes_are_excluded_from_shipped_votes(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('A','1','x','N-PX','u','2026-01-01')")
    for fmt in ("regvoted", "issueno"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, shares_voted, vote_source, legacy_format, "
                  "is_duplicate) VALUES ('A','Acme','C1','06/30/2025','x','FOR',NULL,"
                  "'legacy_text',?,0)", (fmt,))
    got = c.execute(f"SELECT legacy_format FROM votes WHERE {ledger.NON_LEGACY_VOTE_SQL}"
                    ).fetchall()
    assert [g[0] for g in got] == ["issueno"]


def test_npx_dispatches_the_format(monkeypatch):
    src = open(npx.__file__).read()
    assert 'fmt == "regvoted" and legacy_issueno_flag' in src
    assert 'fam == "regvoted" and fmt == "regvoted"' in src
    assert "LEGACY_REGVOTED_REJECTED" in src


def test_ingest_filing_delegates_with_this_layout(monkeypatch):
    seen = {}
    monkeypatch.setattr(legacy_issueno, "ingest_filing",
                        lambda *a, **k: seen.update(layout=k["layout"]) or 7)
    assert legacy_regvoted.ingest_filing(None, None, None, "d", {}, "") == 7
    assert seen["layout"] is legacy_regvoted
