"""Guggenheim: Rydex trusts voted by the Advisor (Security Investors, LLC, d/b/a Guggenheim Investments); two closed-end
funds voted by their sub-adviser GPIM under its own policy.

Evidence (accessions in config/institutions.yaml): every Rydex SAI says the Board delegated proxy voting to the Advisor,
whose own procedures follow; no sub-adviser is named. The closed-end funds' N-CSR says voting is delegated to the
sub-adviser Guggenheim Partners Investment Management, LLC (GPIM), whose policy is attached as an exhibit.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
G = CFG["institutions"]["guggenheim"]
KEYS = {"GUGGENHEIM", "GUGGENHEIM_GPIM", "EXTERNAL", "UNRESOLVED"}
INGESTED = {"899148": ("GUGGENHEIM", "2021-04-30"), "1064046": ("GUGGENHEIM", "2021-04-30"),
            "1092720": ("GUGGENHEIM", "2021-07-29"), "1380936": ("GUGGENHEIM_GPIM", "2021-08-06"),
            "1864208": ("GUGGENHEIM_GPIM", "2022-08-10")}
LEFT_OUT = {"88525", "217087", "1601445", "1495825", "1551949", "1310709", "1267890", "1526104", "1642563",
            "1475069", "1208211", "1280782", "1425852", "1364089", "1365662", "1435732"}


def _entry(cik):
    return next(e for e in G["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), None, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert G.get(k), k
    assert G["cik"] == "0000791185"
    assert "aum_usd_tr" in G


def test_exactly_the_registrants_and_none_left_out():
    ciks = {str(e["cik"]) for e in G["npx_ciks"]}
    assert ciks == set(INGESTED)
    assert not ciks & LEFT_OUT
    for e in G["npx_ciks"]:
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_keys_from_the_first_filing_read_and_none_before():
    for c, (key, frm) in INGESTED.items():
        assert _key(c, frm) == key, c
        assert _key(c, "2026-06-30") == key, c
        assert _key(c, "2020-12-31") is None, c
        assert _key(c, f"{int(frm[:4]) - 1}{frm[4:]}") is None, c
        assert engine.rule_keys(engine.normalize_rules(_entry(c))) <= KEYS


def test_commitments_are_keyed_and_the_sai_policy_is_configured():
    assert G["commitments"]
    for d in G["commitments"]:
        assert d["adviser_key"] in KEYS and d["label"]
    d = next(x for x in G["commitments"] if x["adviser_key"] == "GUGGENHEIM")
    cfg = d["sai_appendix"]
    assert cfg["cik"] == "0000899148" and cfg["forms"] == ["485BPOS"] and cfg["start"] and cfg["end"]
