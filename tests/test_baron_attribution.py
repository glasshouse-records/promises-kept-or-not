"""Baron Capital / BAMCO fund registrants.

Evidence (accessions in config/institutions.yaml): every Baron SAI says "The Funds have delegated all decision making on
proxy voting to the Adviser. The Adviser makes its own independent voting decisions" and the Adviser is BAMCO, Inc.,
voting under the Baron Capital Management / BAMCO Proxy Voting Policies and Procedures. No sub-adviser exists, so each
registrant carries one voter, BAMCO, from its earliest SAI read.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["baron"]
KEYS = {"BAMCO", "EXTERNAL", "UNRESOLVED"}
INGESTED = {"810902", "1217673", "2081199"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0001017918"
    assert "aum_usd_tr" in N
    assert "WealthBuilder" in N["notes"]  # the fund-of-funds series is documented as having no votes


def test_exactly_the_registrants():
    assert {str(e["cik"]) for e in N["npx_ciks"]} == INGESTED
    for e in N["npx_ciks"]:
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_every_key_is_known_and_dated():
    for e in N["npx_ciks"]:
        hist = e.get("adviser_key_history") or []
        assert hist, e["cik"]
        for r in hist:
            assert r["key"] in KEYS, r
            assert r.get("from"), r


def test_keys_resolve_after_from_and_not_before():
    assert _key("810902", "S000000582", "2025-06-30") == "BAMCO"    # Baron Asset Fund
    assert _key("810902", "S000000582", "2021-01-27") is None
    assert _key("1217673", "S000000588", "2025-06-30") == "BAMCO"   # Baron Partners Fund
    assert _key("1217673", "S000000588", "2021-04-29") is None
    assert _key("2081199", "S000096485", "2026-06-30") == "BAMCO"   # Baron Technology ETF
    assert _key("2081199", "S000096485", "2025-12-04") is None


def test_commitments_are_keyed_to_the_voter():
    assert N["commitments"]
    for d in N["commitments"]:
        assert d["label"] and d["adviser"]
        assert d["adviser_key"] == "BAMCO"
        assert d.get("url") or d.get("sai_appendix")
