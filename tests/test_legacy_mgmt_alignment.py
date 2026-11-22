"""Legacy rows carry the XML meaning of management_recommendation: FOR = this vote went WITH
management, AGAINST = against, "" = not clear."""
import pytest

from glasshouse.ingest import legacy_iss, legacy_pe

SMAP = {legacy_pe._norm("Fund A"): "S000000001"}


@pytest.mark.parametrize("rec,vote,want", [
    ("FOR", "FOR", "FOR"), ("AGAINST", "AGAINST", "FOR"), ("ABSTAIN", "ABSTAIN", "FOR"),
    ("WITHHOLD", "WITHHOLD", "FOR"), ("1 YEAR", "1 YEAR", "FOR"), ("3 YEARS", "3 YEARS", "FOR"),
    ("FOR", "AGAINST", "AGAINST"), ("FOR", "WITHHOLD", "AGAINST"),
    ("AGAINST", "FOR", "AGAINST"), ("WITHHOLD", "FOR", "AGAINST"),
    ("1 YEAR", "3 YEARS", "AGAINST"), ("2 YEARS", "1 YEAR", "AGAINST"),
    ("FOR", "ABSTAIN", "AGAINST"), ("FOR", "DO NOT VOTE", ""), ("FOR", "TNA", ""),
    ("FOR", "No Vote", ""), ("FOR", "Did Not Vote", ""), ("", "FOR", ""),
    ("ABSTAIN", "FOR", ""), ("AGAINST", "ABSTAIN", "AGAINST"), ("1 YEAR", "FOR", ""),
    ("DO NOT VOTE", "DO NOT VOTE", ""), ("TNA", "TNA", ""),
])
def test_with_management_table(rec, vote, want):
    assert legacy_iss.with_management(rec, vote) == want


def _iss_row(rec, vote, label="Mgt Rec"):
    return {"fund_heading": "Fund A", "issuer_name": "X", "security_id": "123456789",
            "meeting_date": "2022-10-01", "meeting_type": "Annual", "record_date": "",
            "rec_label": label, "card_label": "", "proposal_id": "1", "proposal_text": "p",
            "rec": rec, "vote": vote, "sponsor": "Management"}


@pytest.mark.parametrize("rec,vote,want", [
    ("For", "Against", "AGAINST"), ("Against", "Against", "FOR"), ("None", "For", ""),
    ("N/A", "For", ""), ("For", "Abstain", "AGAINST"), ("Abstain", "For", ""), ("Abstain", "Abstain", "FOR"),
])
def test_iss_to_vote_rows_maps_raw_values(rec, vote, want):
    rows, _ = legacy_iss.to_vote_rows([_iss_row(rec, vote)], SMAP, "iss")
    assert rows[0]["management_recommendation"] == want
    assert rows[0]["for_against_management"] is None


@pytest.mark.parametrize("fa,want", [("For", "FOR"), ("Against", "AGAINST"), ("", "")])
@pytest.mark.parametrize("vote", ["For", "Against", "Abstain"])
def test_pe_copies_printed_for_against_management(vote, fa, want):
    row = {"fund_name": "Fund A", "issuer_name": "X", "security_id": "1", "isin": "",
           "meeting_date": "2022-10-01", "proposal_text": "p", "proposal_type": "Mgmt",
           "vote": vote, "for_against_management": fa}
    rows, _ = legacy_pe.to_vote_rows([row], SMAP)
    assert rows[0]["management_recommendation"] == want
    assert rows[0]["for_against_management"] == fa
