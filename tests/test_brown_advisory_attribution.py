"""Brown Advisory Funds: the Board delegates proxy voting 'to the Adviser or Sub-Advisers, as applicable' and the SAI attaches the
policies of Brown Advisory LLC / Brown Advisory Limited and of each unaffiliated sub-adviser (Wellington, Pzena, Beutel Goodman).
Funds without an unaffiliated sub-adviser (the Adviser, or its affiliate Brown Advisory Limited under the shared policy) are
BROWN_ADVISORY; funds with one unaffiliated sub-adviser are EXTERNAL; Emerging Markets Select (Wellington and Pzena) is UNRESOLVED."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["brown_advisory"]
CIK = "0001114667"
FIRST = {"1548609": "2021-10-29"}
KEYS = {"BROWN_ADVISORY", "EXTERNAL", "UNRESOLVED"}
LEFT_OUT = {"1114667", "1345929", "1742040"}
# series -> (key, from)
SUBADVISED = {
    "S000042683": ("EXTERNAL", "2021-10-29"),     # WMC Strategic European Equity (Wellington)
    "S000061323": ("EXTERNAL", "2021-10-29"),     # Beutel Goodman Large-Cap Value
    "S000088082": ("EXTERNAL", "2024-09-27"),     # WMC Japan Equity (Wellington), first SAI 2024-09-27
    "S000039101": ("UNRESOLVED", "2021-10-29"),   # Emerging Markets Select (Wellington + Pzena)
}


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
        assert "<date>" not in (e["adviser_verified"], e["validated"])
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_left_out_registrants_are_documented_in_the_notes():
    for cik in LEFT_OUT:
        assert cik in D["notes"], cik


def test_own_series_keyed_only_from_the_earliest_filing_read():
    first = FIRST["1548609"]
    for sid in ("S000038479", "S000058723", "S000049137", "S000075346"):   # Growth Equity, Mid-Cap Growth, Global Leaders, Sust. Intl Leaders
        assert _key("1548609", sid, first) == "BROWN_ADVISORY"
        assert _key("1548609", sid, "2026-06-30") == "BROWN_ADVISORY"
        assert _key("1548609", sid, _day_before(first)) is None


def test_subadvised_series_follow_their_sub_adviser():
    for sid, (key, frm) in SUBADVISED.items():
        assert _key("1548609", sid, "2026-06-30") == key, sid
        assert _key("1548609", sid, frm) == key, sid
        assert _key("1548609", sid, _day_before(frm)) in (None, "BROWN_ADVISORY"), sid
    assert _key("1548609", "S000042683", "2021-10-28") is None
    assert _key("1548609", "S000042683", "2021-10-29") == "EXTERNAL"


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
        assert c["label"] and c["adviser_key"] == "BROWN_ADVISORY"
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"
