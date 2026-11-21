"""Thornburg Investment Management: all three registrants are voted by the Advisor (Thornburg Investment Management,
Inc.) under its own Proxy Voting Policies and Procedures (key THORNBURG), dated from the earliest SAI read.

Evidence (accessions in config/institutions.yaml): every SAI says 'Thornburg is authorized by the Trust to vote proxies
respecting voting securities held by the Funds ... in accordance with written Proxy Voting Policies and Procedures
adopted by Thornburg'; ISS is research only. No sub-adviser appears in any SAI read.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["thornburg"]
CIK = "0001145020"
FIRST = {"816153": "2021-01-28", "2038383": "2025-01-17", "1820378": "2021-07-27"}
KEYS = {"THORNBURG"}
LEFT_OUT = {"1145020", "740843"}


def _entry(cik):
    return next(e for e in D["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert D.get(k), k
    assert D["cik"] == CIK
    assert "aum_usd_tr" in D


def test_exactly_the_researched_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in D["npx_ciks"]}
    assert ciks == set(FIRST)
    assert not ciks & LEFT_OUT
    for e in D["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        assert "<date>" not in str(e)
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
    for cik in LEFT_OUT:
        assert cik in D["notes"], f"left-out registrant {cik} must be listed with its reason in the notes"


def test_keyed_only_from_the_earliest_sai_read():
    for cik, first in FIRST.items():
        assert _key(cik, "S000000001", first) == "THORNBURG"
        assert _key(cik, "", "2026-06-30") == "THORNBURG"   # the closed-end trust has no series
        assert _key(cik, "S000000001", _day_before(first)) is None


def test_every_key_is_known():
    for e in D["npx_ciks"]:
        for r in e.get("adviser_key_history") or []:
            assert r["key"] in KEYS, r
        assert not e.get("series_adviser")


def test_commitments_are_keyed_to_the_voter():
    assert len(D["commitments"]) >= 2
    for c in D["commitments"]:
        assert c["label"] and c["adviser"] and c["adviser_key"] in KEYS
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"
    assert any(c.get("url", "").endswith(".pdf") for c in D["commitments"])
