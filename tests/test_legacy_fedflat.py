"""Federated Hermes flat-table 2022-23 layout: detection, the printed vocabulary, npx
dispatch, and that the format starts quarantined. The parser pair is tested in its own
files; this tests the wrapper."""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_fedflat, legacy_iss, legacy_issueno, legacy_pe, npx

FUND = "Federated Hermes Capital Income Fund"
SID = "S000009749"
_COLS = ["Issuer Name", "Country", "Meeting Date", "Meeting Type", "Record Date", "Ticker",
         "Security ID", "Symbol Type", "Ballot Issue Number", "Proposal Text", "Proponent",
         "Mgmt Reco", "Vote Cast", "Fund Name", "Logical Ballot Status"]
HDR = "<table><tr>" + "".join(
    f'<TD STYLE="width: 6%"><FONT STYLE="font-size: 9pt"><B>{c}</B></FONT></TD>\n'
    for c in _COLS) + "</tr></table>"


def _row(**kw):
    base = {"fund_heading": FUND, "issuer_name": "Bank of America Corporation",
            "ticker": "BAC", "security_id": "CUSIP 060505104", "meeting_date": "2023-04-25",
            "meeting_status": "Voted", "meeting_type": "Annual", "country": "United States",
            "proposal_id": "1", "proposal_text": "Elect Sharon L. Allen",
            "proponent": "Mgmt", "rec": "For", "vote": "For", "for_against": ""}
    base.update(kw)
    return base


def _votes(rows):
    return legacy_fedflat.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})


# -- detection ----------------------------------------------------------------

def test_flat_table_header_detects_as_fedflat():
    assert legacy_iss.doc_format(HDR) == "fedflat"


def test_without_logical_ballot_status_still_detects():
    assert legacy_iss.doc_format(HDR.replace("Logical Ballot Status", "")) == "fedflat"


def test_labels_split_across_paragraphs_detect():
    split = "<table><tr>" + "".join(
        "<TD>" + "".join(f"<P><B>{w}</B></P>\n" for w in c.split()) + "</TD>\n"
        for c in _COLS) + "</tr></table>"
    assert legacy_iss.doc_format(split) == "fedflat"


def test_header_words_in_prose_do_not_detect():
    assert legacy_iss.doc_format("<p>Mgmt Reco and Vote Cast and Fund Name</p>") is None


# -- vocabulary ---------------------------------------------------------------

@pytest.mark.parametrize("field,printed,col,stored", [
    ("proponent", "Mgmt", "vote_source", "ISSUER"),
    ("proponent", "Management", "vote_source", "ISSUER"),
    ("proponent", "ShrHoldr", "vote_source", "SECURITY HOLDER"),
    ("proponent", "Shareholder", "vote_source", "SECURITY HOLDER"),
    ("vote", "One Year", "how_voted", "1 YEAR"),
    ("vote", "3 Years", "how_voted", "3 YEARS"),
    ("vote", "Withhold", "how_voted", "WITHHOLD")])
def test_printed_forms_map(field, printed, col, stored):
    votes, _ = _votes([_row(**{field: printed})])
    assert [v[col] for v in votes] == [stored]
    assert votes[0]["legacy_format"] == "fedflat"


def test_three_years_rec_compares_with_vote():
    votes, _ = _votes([_row(rec="Three Years", vote="3 Years")])
    assert votes[0]["management_recommendation"] == "FOR"


def test_cusip_and_cins_ids_kept():
    votes, _ = _votes([_row()])
    assert votes[0]["cusip"] == "060505104"


@pytest.mark.parametrize("vote", ["TNA", "Do Not Vote", "N/A", ""])
def test_not_cast_votes_are_dropped(vote):
    votes, info = _votes([_row(vote=vote)])
    assert votes == [] and info["dropped_vote"] == 1


def test_take_no_action_status_dropped():
    votes, info = _votes([_row(meeting_status="Take No Action")])
    assert votes == [] and info["dropped_status"] == 1


def test_na_proponent_dropped():
    votes, info = _votes([_row(proponent="N/A")])
    assert votes == [] and info["dropped_sponsor"] == 1


def test_rec_none_gives_no_recommendation():
    votes, _ = _votes([_row(rec="None")])
    assert votes[0]["management_recommendation"] in ("", None)


# -- quarantine, constants, dispatch -------------------------------------------

def test_constants_and_quarantine():
    assert legacy_fedflat.LEGACY_FORMAT == "fedflat"
    assert legacy_fedflat.REPORT_OK == "LEGACY_FEDFLAT"
    assert legacy_fedflat.REPORT_REJECTED == "LEGACY_FEDFLAT_REJECTED"
    assert "fedflat" not in ledger.PROMOTED_LEGACY_FORMATS


def test_parser_pair():
    names = {p.__name__.rsplit(".", 1)[1] for p in legacy_fedflat.PARSERS}
    assert names == {"legacy_fedflat_cells", "legacy_fedflat_rows"}


def test_npx_dispatches_the_format():
    src = open(npx.__file__).read()
    assert 'fmt == "fedflat" and legacy_issueno_flag' in src
    assert 'fam == "fedflat" and fmt == "fedflat"' in src
    assert "LEGACY_FEDFLAT_REJECTED" in src


def test_ingest_filing_delegates_with_this_layout(monkeypatch):
    seen = {}
    monkeypatch.setattr(legacy_issueno, "ingest_filing",
                        lambda *a, **k: seen.update(layout=k["layout"]) or 5)
    assert legacy_fedflat.ingest_filing(None, None, None, "d", {}, "") == 5
    assert seen["layout"] is legacy_fedflat


# -- guards --------------------------------------------------------------------

class _Stub:
    def __init__(self, rows):
        self.rows = rows

    def parse(self, _text):
        return [dict(r) for r in self.rows]


def test_issuer_order_is_not_guarded_every_row_names_its_fund():
    # 001146 prints its alphabetical runs in reverse page order; the fund is a cell on
    # every row, so a reset cannot mean a missed fund heading
    rows = [_row(issuer_name=n) for n in ("Pfizer", "Kimberly", "Exxon", "Abbvie", "Verizon")]
    out, st = legacy_fedflat.agreed("", (_Stub(rows), _Stub(rows)))
    assert [r["issuer_name"] for r in out] == ["Pfizer", "Kimberly", "Exxon", "Abbvie",
                                               "Verizon"]
    assert st["rows_dropped_order"] == 0


def test_disputed_meetings_still_dropped():
    rows = [_row(proposal_id="1"), _row(proposal_id="2"), _row(issuer_name="Other")]
    other = [dict(r) for r in rows]
    other[1]["vote"] = "Against"
    out, st = legacy_fedflat.agreed("", (_Stub(rows), _Stub(other)))
    assert [r["issuer_name"] for r in out] == ["Other"]


def test_other_layouts_keep_the_order_guard():
    rows = [_row(issuer_name=n) for n in ("Pfizer", "Kimberly", "Exxon", "Abbvie", "Verizon")]
    _, st = legacy_issueno.agreed("", (_Stub(rows), _Stub(rows)))
    assert st["rows_dropped_order"] > 0
