"""JPMorgan sweep: JPMorgan Trust II, J.P. Morgan ETF Trust, JP Morgan Mutual Fund Investment Trust, JP Morgan Fleming
Mutual Fund Group and JPMorgan Trust IV.

Evidence (accessions in config/institutions.yaml): the combined J.P. Morgan Funds SAI, filed under each trust, says the
Board delegated proxy voting to the Adviser and its affiliated advisers under one set of Guidelines; the only exception
it names is the Behavioral Value Fund (FullerThaler), which sits in Undiscovered Managers Funds, left out. Earliest SAI
read for every kept trust: 2022-10-25 = `from`.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG_PATH = Path(__file__).resolve().parents[1] / "config" / "institutions.yaml"
CFG = yaml.safe_load(CFG_PATH.read_text())
J = CFG["institutions"]["jpmorgan"]
FROM = "2022-10-25"
ADDED = {"763852", "1485894", "803747", "1037897", "1659326"}
LEFT_OUT = {"1047712"}


def _entry(cik):
    return next((e for e in J["npx_ciks"] if str(e["cik"]) == cik), None)


def _key(cik, day, series="S000000001"):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_added_registrants_present_with_evidence_and_valid_rules():
    for cik in ADDED:
        e = _entry(cik)
        assert e, cik
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), cik
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"], cik
        engine.validate_rules(engine.normalize_rules(e), cik)


def test_key_after_from_and_unlabelled_before():
    for cik in ADDED:
        assert _key(cik, "2023-03-01") == "JPMAM", cik
        assert _key(cik, FROM) == "JPMAM", cik
        assert _key(cik, "2022-10-24") is None, cik
        assert _key(cik, "2022-07-15") is None, cik


def test_left_out_registrants_absent_and_documented():
    ciks = {str(e["cik"]) for e in J["npx_ciks"]}
    assert not ciks & LEFT_OUT
    text = CFG_PATH.read_text()
    for cik in LEFT_OUT:
        assert cik in text


def test_original_registrants_untouched():
    assert {"1217286", "1303608"} <= {str(e["cik"]) for e in J["npx_ciks"]}
