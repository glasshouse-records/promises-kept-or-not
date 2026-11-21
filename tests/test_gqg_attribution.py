"""GQG Partners fund registrants.

Evidence (accessions in config/institutions.yaml): GQG's US funds are series of The Advisors' Inner Circle Fund III
(CIK 1593547), a shared multi-adviser trust (Brown Advisory, ARGA, KBI, MetLife and others). So the trust has NO
registrant-wide voter: only GQG's own series are keyed, series by series, and every other series stays unlabelled.
Every GQG SAI says the Board "has delegated the responsibility for decisions regarding proxy voting ... to the
Adviser", GQG Partners LLC, which "will vote such proxies in accordance with its proxy voting policies and
procedures", printed in Appendix B. Each series is keyed from the EDGAR filing date of the earliest SAI read (2021 or
later) that covers it.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["gqg"]
KEYS = {"GQG"}
INGESTED = {"1593547"}
LEFT_OUT = {"1697233"}   # GQG Partners LLC's own institutional-manager N-PX
SERIES_FROM = {
    "S000056013": "2021-11-24",   # GQG Partners Emerging Markets Equity Fund
    "S000063192": "2021-11-24",   # GQG Partners US Select Quality Equity Fund
    "S000065108": "2021-11-24",   # GQG Partners Global Quality Equity Fund
    "S000072427": "2021-06-30",   # GQG Partners Global Quality Value Fund
    "S000072428": "2021-06-30",   # GQG Partners International Quality Value Fund
    "S000072429": "2021-06-30",   # GQG Partners US Quality Value Fund
    "S000093212": "2025-07-09",   # GQG US Equity ETF
}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0001697233"
    assert "aum_usd_tr" in N


def test_exactly_the_registrants_and_no_registrant_default_in_the_shared_trust():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
    for e in N["npx_ciks"]:
        # a registrant-wide key would label every other adviser's series in the trust
        assert not e.get("adviser_key"), e["cik"]
        assert not e.get("adviser_key_history"), e["cik"]
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
        assert "<date>" not in str(e)


def test_exactly_the_gqg_series_are_keyed():
    rules = _entry("1593547")["series_adviser"]
    assert set(rules) == set(SERIES_FROM)
    for sid, rs in rules.items():
        for r in rs:
            assert r["key"] in KEYS, (sid, r)
            assert r.get("from"), (sid, "an undated rule would label meetings before the evidence")


def test_each_series_resolves_to_gqg_from_its_earliest_sai_and_not_before():
    for sid, frm in SERIES_FROM.items():
        assert _key("1593547", sid, "2026-06-30") == "GQG", sid
        assert _key("1593547", sid, frm) == "GQG", sid
        assert _key("1593547", sid, "2021-01-01") is None, sid
    assert _key("1593547", "S000056013", "2021-11-23") is None
    assert _key("1593547", "S000072427", "2021-06-29") is None
    assert _key("1593547", "S000093212", "2025-07-08") is None
    assert _key("1593547", "S000093212", "2024-06-30") is None


def test_other_advisers_series_in_the_shared_trust_stay_unlabelled():
    # Brown Advisory, ARGA, MetLife/PineBridge and Strategas series sit in the same trust.
    for sid in ("S000071338", "S000070256", "S000075077", "S000048264", "S000000000"):
        assert _key("1593547", sid, "2026-06-30") is None, sid
    assert _key("1593547", "", "2026-06-30") is None


def test_keyed_commitments_exist_for_gqg():
    keys = {d["adviser_key"] for d in N["commitments"]}
    assert keys == {"GQG"}
    for d in N["commitments"]:
        assert d["label"] and d["adviser"]
        assert d.get("sai_appendix") or d.get("url")
        if d.get("sai_appendix"):
            assert d["sai_appendix"]["cik"] == "0001593547"
            assert d["sai_appendix"]["start"] and d["sai_appendix"]["end"]
