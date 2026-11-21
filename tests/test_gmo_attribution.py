"""GMO (Grantham, Mayo, Van Otterloo) fund registrant.

Evidence (accessions in config/institutions.yaml): every GMO Trust SAI says "The Trust has adopted a proxy voting
policy under which responsibility to vote proxies related to its portfolio securities has been delegated to GMO"
and prints GMO's own proxy voting policies and procedures in Appendix C. GMO Trust (CIK 772129) is a single-adviser
trust: the mutual funds, the asset-allocation funds and the ETFs are all series of it, so one registrant, keyed GMO
from the EDGAR filing date of the earliest SAI read (2021-06-30). The one exception the SAI states is the feeder
fund, Emerging Country Debt Shares Fund (S000068930), whose GMO votes the underlying fund's shares by pass-through
instructions or in proportion with other holders; that is not GMO's policy, so it is UNRESOLVED.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["gmo"]
KEYS = {"GMO", "UNRESOLVED"}
INGESTED = {"772129"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0001070039"
    assert "aum_usd_tr" in N


def test_exactly_the_registrants():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert ciks == INGESTED
    for e in N["npx_ciks"]:
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
        assert "<date>" not in str(e)


def test_every_rule_uses_a_known_key_and_a_date():
    e = _entry("772129")
    assert e["adviser_key_history"] == [{"key": "GMO", "from": "2021-06-30"}]
    for rs in (e.get("series_adviser") or {}).values():
        for r in rs:
            assert r["key"] in KEYS, r
            assert r.get("from"), r


def test_gmo_votes_every_series_from_the_earliest_sai_and_not_before():
    # operating-company series, an asset-allocation series and an ETF series
    for sid in ("S000004081", "S000036091", "S000065268", "S000012211", "S000079719"):
        assert _key("772129", sid, "2026-06-30") == "GMO", sid
        assert _key("772129", sid, "2021-06-30") == "GMO", sid
        assert _key("772129", sid, "2021-06-29") is None, sid
        assert _key("772129", sid, "2020-06-30") is None, sid


def test_feeder_fund_is_unresolved_not_gmo():
    assert _key("772129", "S000068930", "2026-06-30") == "UNRESOLVED"
    assert _key("772129", "S000068930", "2021-06-29") is None


def test_keyed_commitments_exist_for_gmo():
    keys = {d["adviser_key"] for d in N["commitments"]}
    assert keys == {"GMO"}
    for d in N["commitments"]:
        assert d["label"] and d["adviser"]
        assert d.get("sai_appendix") or d.get("url")
        if d.get("sai_appendix"):
            assert d["sai_appendix"]["cik"] == "0000772129"
            assert d["sai_appendix"]["start"] and d["sai_appendix"]["end"]
