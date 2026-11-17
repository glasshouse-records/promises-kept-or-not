"""Geode-voted Fidelity index series are attributed per series, never per trust.

Evidence: each series' own SAI proxy-voting section is Geode's voting policy
(see config/institutions.yaml comments). These tests pin the contract so a
registrant-level default can never silently label an FMR-voted series GEODE.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
FID = CFG["institutions"]["fidelity"] if "institutions" in CFG else CFG["fidelity"]
GEODE_TRUSTS = {"819118", "35315", "831016"}


def _entry(cik):
    return next(e for e in FID["npx_ciks"] if str(e["cik"]) == cik)


def test_geode_trusts_have_series_rules_and_no_registrant_default():
    for cik in GEODE_TRUSTS:
        e = _entry(cik)
        assert not e.get("adviser_key"), "a registrant default would mislabel FMR-voted series"
        assert any(r[0]["key"] == "GEODE" for r in e["series_adviser"].values())


def test_series_resolve_to_geode_only_from_evidence_window():
    rules = engine.normalize_rules(_entry("819118"))
    assert engine.resolve_key(rules, "S000006027", "2026-03-01") == "GEODE"   # Fidelity 500 Index
    assert engine.resolve_key(rules, "S000055364", "2026-03-01") is None       # Large Cap Stock: FMR
    assert engine.resolve_key(rules, "S000006027", "2024-03-01") is None       # before the evidence window


def test_vip_index_500_is_not_attributed():
    rules = engine.normalize_rules(_entry("831016"))
    assert engine.resolve_key(rules, "S000007726", "2026-03-01") is None
    assert engine.resolve_key(rules, "S000061714", "2026-03-01") == "GEODE"


def test_geode_policy_document_is_keyed():
    docs = {d["label"]: d for d in FID["commitments"]}
    d = docs["geode-proxy-voting-policy"]
    assert d["adviser_key"] == "GEODE"
    assert d["url"].startswith("https://www.geodecapital.com/")
