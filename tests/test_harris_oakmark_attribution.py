"""Harris Associates / Oakmark fund registrants.

Evidence (accessions in config/institutions.yaml): every Oakmark SAI says "The Adviser ... is responsible for exercising
all voting rights with respect to the Funds' portfolio securities in accordance with the Adviser's proxy voting policies
and procedures" (Adviser = Harris Associates L.P.). Later SAIs add that the Adviser may delegate a PARTICULAR ISSUER to a
third party to comply with the Bank Holding Company Act; that is issuer-specific, not a series voter. No sub-adviser
exists in either trust, so each registrant carries one voter, HARRIS_ASSOCIATES, from its earliest SAI read.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["harris_oakmark"]
KEYS = {"HARRIS_ASSOCIATES", "EXTERNAL", "UNRESOLVED"}
INGESTED = {"872323", "2035827"}
LEFT_OUT = {"813917"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0000813917"
    assert "aum_usd_tr" in N
    assert "813917" in N["notes"]  # the left-out institutional-manager N-PX is named


def test_exactly_the_registrants():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
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
    assert _key("872323", "S000002758", "2025-06-30") == "HARRIS_ASSOCIATES"   # Oakmark Fund
    assert _key("872323", "S000002762", "2022-06-30") == "HARRIS_ASSOCIATES"   # Oakmark International
    assert _key("872323", "S000002758", "2021-09-30") is None                  # before the earliest SAI read
    assert _key("2035827", "S000088867", "2026-06-30") == "HARRIS_ASSOCIATES"  # Oakmark U.S. Large Cap ETF
    assert _key("2035827", "S000088867", "2024-10-01") is None


def test_commitments_are_keyed_to_the_voter():
    assert N["commitments"]
    for d in N["commitments"]:
        assert d["label"] and d["adviser"]
        assert d["adviser_key"] == "HARRIS_ASSOCIATES"
        assert d.get("url") or d.get("sai_appendix")
