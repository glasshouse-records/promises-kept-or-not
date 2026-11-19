"""Dodge & Cox (Dodge & Cox, the adviser; CIK 200217 the 13-F filer) fund registrant.

Evidence (accessions in config/institutions.yaml): every Dodge & Cox Funds SAI says "The Dodge & Cox Funds have
authorized Dodge & Cox to vote proxies on behalf of the Dodge & Cox Funds pursuant to the following Dodge & Cox Proxy
Voting Policies and Procedures" (Appendix B). The Form N-CEN of FY2020 to FY2025 names Dodge & Cox as the only adviser
and no sub-adviser for any of the trust's series. The rule is DATED from the EDGAR filing date of the earliest SAI read
(485BPOS 0001193125-21-005003, 2021-01-08).
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["dodge_cox"]
FIRST = {"29440": "2021-01-08"}     # Dodge & Cox Funds, 485BPOS 0001193125-21-005003
# Left out on purpose: the adviser's own institutional-manager N-PX (overlaps the fund tables).
LEFT_OUT = {"200217"}


def _entry(cik):
    return next(e for e in D["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert D.get(k), k
    assert D["cik"] == "0000200217"       # Dodge & Cox, the 13-F filer
    assert "aum_usd_tr" in D


def test_exactly_the_fund_trust_and_no_open_default():
    ciks = {str(e["cik"]) for e in D["npx_ciks"]}
    assert ciks == set(FIRST)
    assert not ciks & LEFT_OUT
    for e in D["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        rules = engine.normalize_rules(e)
        engine.validate_rules(rules, e["cik"])
        for key, _lo, _hi in rules["history"]:
            assert key == "DODGE_COX"
        assert not rules["series"], "no sub-adviser in any N-CEN: no series exception"


def test_dodge_cox_keyed_only_from_the_earliest_sai_read():
    for cik, first in FIRST.items():
        assert _key(cik, "S000011202", first) == "DODGE_COX"
        assert _key(cik, "S000011202", "2026-06-30") == "DODGE_COX"
        before = (date.fromisoformat(first) - timedelta(days=1)).isoformat()
        assert _key(cik, "S000011202", before) is None


def test_the_policy_labels_are_dodge_cox():
    labels = {c["label"]: c for c in D["commitments"]}
    assert labels
    for c in labels.values():
        assert c["adviser_key"] == "DODGE_COX"
