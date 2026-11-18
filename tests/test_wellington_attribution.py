"""Wellington-voted Hartford series are attributed per series, never per trust.

Evidence: each keyed series' own SAI names Wellington Management as its sole
sub-adviser and delegates proxy voting to the sub-adviser (see the comments in
config/institutions.yaml). The contract is pinned here so a registrant-level
default can never silently label a Schroders- or HFMC-voted series WELLINGTON.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
WL = CFG["institutions"]["wellington"]
TRUSTS = {"1053425", "1006415", "49905"}


def _entry(cik):
    return next(e for e in WL["npx_ciks"] if str(e["cik"]) == cik)


def test_trusts_have_series_rules_and_no_registrant_default():
    assert {str(e["cik"]) for e in WL["npx_ciks"]} == TRUSTS
    for cik in TRUSTS:
        e = _entry(cik)
        assert not e.get("adviser_key"), "a registrant default would mislabel Schroders/HFMC-voted series"
        assert any(r[0]["key"] == "WELLINGTON" for r in e["series_adviser"].values())


def test_every_rule_is_dated_and_cited():
    for cik in TRUSTS:
        for sid, rules in _entry(cik)["series_adviser"].items():
            assert sid.startswith("S") and len(rules) == 1
            assert rules[0]["key"] == "WELLINGTON" and rules[0]["from"]


def test_series_resolve_only_from_evidence_window():
    rules = engine.normalize_rules(_entry("1053425"))
    assert engine.resolve_key(rules, "S000003205", "2026-03-01") == "WELLINGTON"
    assert engine.resolve_key(rules, "S000003205", "2024-03-01") is None


def test_schroders_and_fund_of_funds_series_are_not_attributed():
    sch = engine.normalize_rules(_entry("49905"))
    assert engine.resolve_key(sch, "S000054851", "2026-03-01") is None   # Hartford Schroders US MidCap Opportunities
    assert engine.resolve_key(sch, "S000004013", "2026-03-01") == "WELLINGTON"  # Growth Opportunities
    hmf = engine.normalize_rules(_entry("1006415"))
    assert engine.resolve_key(hmf, "S000003579", "2026-03-01") is None   # Moderately Aggressive Allocation: HFMC
    assert engine.resolve_key(hmf, "S000003604", "2026-03-01") == "WELLINGTON"  # Capital Appreciation


def test_policy_document_is_keyed():
    docs = {d["label"]: d for d in WL["commitments"]}
    assert docs, "Wellington policy documents must be archived"
    for d in docs.values():
        assert d["adviser_key"] == "WELLINGTON"
        if d.get("sai_appendix"):   # read from EDGAR: no URL of its own
            assert d["label"].endswith("-as-printed-in-sai") and d["sai_appendix"]["cik"]
        else:
            assert d["url"].startswith("https://www.wellington.com/")
