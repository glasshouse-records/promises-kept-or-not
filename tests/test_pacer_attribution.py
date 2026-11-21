"""Pacer: Pacer Funds Trust. Every multi-fund SAI says the Funds delegated proxy voting to the Adviser (Pacer Advisors), which
adopted the Glass Lewis Investment Manager Guidelines (printed as the SAI appendix). The SAIs name the exceptions: FLRT (Pacific
Asset Management, later Aristotle Pacific), INDQ (ActiveAlpha, single-fund SAI of 2025-12-22) and the Barings funds AAAP / PBSC
(SAI of 2026-06-04). Those are EXTERNAL; before their first SAI they are UNRESOLVED."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["pacer"]
CIK = "0001616667"
FIRST = {"1616668": "2021-02-23"}
KEYS = {"PACER", "EXTERNAL", "UNRESOLVED"}
LEFT_OUT = {"1616667"}


def _entry(cik):
    return next(e for e in D["npx_ciks"] if str(e["cik"]) == cik)


def _key(series, day):
    return engine.resolve_key(engine.normalize_rules(_entry("1616668")), series, day)


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
        assert "<date>" not in (e["adviser_verified"], e["validated"])
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_left_out_registrants_are_documented_in_the_notes():
    for cik in LEFT_OUT:
        assert cik in D["notes"], cik


def test_trust_keyed_pacer_only_from_the_earliest_filing_read():
    first = FIRST["1616668"]
    for sid in ("S000055466", "S000072257", "S000101423"):   # COWZ, QDPL, PSAI
        assert _key(sid, first) == "PACER"
        assert _key(sid, "2026-06-30") == "PACER"
        assert _key(sid, _day_before(first)) is None


def test_sub_adviser_voted_series_are_external_with_unresolved_before_their_sai():
    assert _key("S000073714", "2022-06-30") == "EXTERNAL"      # FLRT: Pacific Asset Management / Aristotle Pacific
    assert _key("S000073714", "2026-06-30") == "EXTERNAL"
    assert _key("S000097528", "2025-12-22") == "EXTERNAL"      # INDQ: ActiveAlpha
    assert _key("S000097528", "2026-03-01") == "EXTERNAL"
    assert _key("S000097528", "2025-12-21") == "UNRESOLVED"
    assert _key("S000101891", "2026-06-04") == "EXTERNAL"      # AAAP: Barings
    assert _key("S000101892", "2026-06-03") == "UNRESOLVED"    # PBSC before its SAI


def test_every_key_is_known():
    for e in D["npx_ciks"]:
        for r in e.get("adviser_key_history") or []:
            assert r["key"] in KEYS, r
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from") or r.get("until")


def test_commitment_labels_carry_the_institution_keys():
    assert D["commitments"]
    for c in D["commitments"]:
        assert c["label"] and c["adviser_key"] == "PACER"
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"
