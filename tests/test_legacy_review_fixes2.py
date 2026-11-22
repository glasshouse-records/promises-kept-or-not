"""Legacy ingest review fixes 2026-11-22: security-id hygiene (check digits)."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from glasshouse.ingest import legacy_iss, legacy_pe

SMAP = {legacy_pe._norm("Fund A"): "S000000001"}
GOOD_CUSIP = "037833100"        # Apple
GOOD_ISIN = "US0378331005"      # Apple
GB_ISIN = "GB0002634946"        # BAE Systems


@pytest.mark.parametrize("v,ok", [
    (GOOD_CUSIP, True), ("02043Q107", True), ("38259P508", True), ("594918104", True),
    ("037833101", False), ("053484101 G", False), ("90043100", False), ("", False),
    ("12345678", False), ("1234567890", False),
])
def test_cusip_valid_examples(v, ok):
    assert legacy_pe.cusip_valid(v) is ok


@pytest.mark.parametrize("v,ok", [
    (GOOD_ISIN, True), (GB_ISIN, True), ("US0378331006", False), ("US037833100", False), ("", False),
])
def test_isin_valid_examples(v, ok):
    assert legacy_pe.isin_valid(v) is ok


@given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#", min_size=8, max_size=8))
def test_cusip_check_digit_roundtrip(body):
    full = body + str(legacy_pe.cusip_check_digit(body))
    assert legacy_pe.cusip_valid(full)
    assert sum(legacy_pe.cusip_valid(body + d) for d in "0123456789") == 1


@given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=2),
       st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=9, max_size=9))
def test_isin_check_digit_roundtrip(cc, nsin):
    full = cc + nsin + str(legacy_pe.isin_check_digit(cc + nsin))
    assert legacy_pe.isin_valid(full)
    assert sum(legacy_pe.isin_valid(cc + nsin + d) for d in "0123456789") == 1


@pytest.mark.parametrize("raw,want", [
    (GOOD_CUSIP, (GOOD_CUSIP, "")), (" 037833100 ", (GOOD_CUSIP, "")),
    ("02043q107", ("02043Q107", "")),
    (GOOD_ISIN, (GOOD_CUSIP, GOOD_ISIN)),             # US ISIN: embedded valid CUSIP
    (GB_ISIN, ("", GB_ISIN)),                         # not US/CA: no cusip
    ("NONE", ("", "")), ("None", ("", "")), ("053484101 G", ("", "")), ("90043100", ("", "")),
    ("41015G168 and 41015G259", ("", "")), ("ABC123", ("", "")), ("037833101", ("", "")),
    ("US0378331006", ("", "")), ("", ("", "")),
])
def test_security_id_classification(raw, want):
    assert legacy_pe.classify_security_id(raw) == want


def _iss_row(sid):
    return {"fund_heading": "Fund A", "issuer_name": "X", "security_id": sid,
            "meeting_date": "2022-10-01", "meeting_type": "Annual", "record_date": "",
            "rec_label": "Mgt Rec", "card_label": "", "proposal_id": "1", "proposal_text": "p",
            "rec": "For", "vote": "For", "sponsor": "Management"}


def test_iss_to_vote_rows_applies_hygiene():
    rows, _ = legacy_iss.to_vote_rows(
        [_iss_row(x) for x in (GOOD_CUSIP, GOOD_ISIN, "None", "053484101 G")], SMAP, "iss")
    assert [(r["cusip"], r["isin"]) for r in rows] == [
        (GOOD_CUSIP, ""), (GOOD_CUSIP, GOOD_ISIN), ("", ""), ("", "")]


def test_pe_to_vote_rows_applies_hygiene():
    base = dict.fromkeys(legacy_pe.KEYS, "") | {
        "fund_name": "Fund A", "issuer_name": "X", "meeting_date": "2023-01-01",
        "proposal_type": "Mgmt", "vote": "For", "for_against_management": "For"}
    rows, _ = legacy_pe.to_vote_rows(
        [base | {"security_id": "41015G168 and 41015G259", "isin": ""},
         base | {"security_id": GOOD_CUSIP, "isin": GOOD_ISIN},
         base | {"security_id": "", "isin": "US0378331006"}], SMAP)
    assert [(r["cusip"], r["isin"]) for r in rows] == [
        ("", ""), (GOOD_CUSIP, GOOD_ISIN), ("", "")]
