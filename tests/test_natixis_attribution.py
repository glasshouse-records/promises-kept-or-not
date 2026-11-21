"""Natixis Investment Managers US fund registrants.

Evidence (accessions in config/institutions.yaml): the Natixis / Loomis Sayles / Gateway SAIs say the Board adopted a Proxy
Voting Policy and that "proxy voting responsibility and authority are delegated to a Fund's subadviser" (Natixis Advisors
retains it only where it has no subadviser), then print a paragraph per voting party. So NO registrant has a registrant-wide
voter: each series is keyed by the party that votes it. Loomis Sayles (adviser of every Loomis Sayles Funds I / II series,
subadviser of the Loomis ETFs) votes under its own, archived policy; Harris Associates votes the Oakmark series under its own
policy (key HARRIS_ASSOCIATES, archived under the harris_oakmark institution); affiliates whose policy is not archived here
(Vaughan Nelson, Gateway, AEW) are UNRESOLVED. Fund-of-funds series (Natixis Sustainable Future target-date funds) are left out.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["natixis"]
KEYS = {"LOOMIS_SAYLES", "HARRIS_ASSOCIATES", "UNRESOLVED"}
INGESTED = {"52136", "1095726", "1526787", "1728860", "872649", "917469", "1406305"}
LEFT_OUT = {"949683", "1053187"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0001053187"
    assert "aum_usd_tr" in N
    assert "<date>" not in str(N)


def test_exactly_the_registrants_and_no_registrant_default():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
    for e in N["npx_ciks"]:
        assert not e.get("adviser_key"), e["cik"]
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_every_rule_uses_a_known_key_and_a_date():
    n = 0
    for e in N["npx_ciks"]:
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                n += 1
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from"), (sid, "an undated rule would label meetings before the evidence")
        assert not e.get("adviser_key_history")
    assert n >= 25


def test_series_resolve_as_researched():
    assert _key("52136", "S000008033", "2025-06-30") == "HARRIS_ASSOCIATES"   # Natixis Oakmark Fund
    assert _key("52136", "S000030600", "2025-06-30") == "LOOMIS_SAYLES"        # Loomis Sayles Strategic Alpha
    assert _key("52136", "S000053353", "2025-06-30") == "LOOMIS_SAYLES"        # Loomis Sayles Global Growth
    assert _key("52136", "S000023783", "2025-06-30") == "UNRESOLVED"           # Vaughan Nelson Mid Cap: no policy archived
    assert _key("872649", "S000006699", "2025-06-30") == "LOOMIS_SAYLES"       # Loomis Sayles Growth Fund
    assert _key("872649", "S000070337", "2025-06-30") == "LOOMIS_SAYLES"       # International Growth (first SAI 2021-04-29)
    assert _key("917469", "S000006647", "2025-06-30") == "LOOMIS_SAYLES"       # Small Cap Value
    assert _key("1728860", "S000080571", "2025-06-30") == "LOOMIS_SAYLES"      # Loomis Sayles Focused Growth ETF
    assert _key("1728860", "S000068960", "2025-06-30") == "UNRESOLVED"         # Vaughan Nelson Select ETF
    assert _key("1526787", "S000083143", "2025-06-30") == "UNRESOLVED"         # Gateway Quality Income ETF
    assert _key("1406305", "S000019169", "2025-06-30") == "UNRESOLVED"         # Gateway Fund
    assert _key("1095726", "S000008059", "2025-06-30") == "UNRESOLVED"         # AEW Global Focused Real Estate


def test_none_before_the_first_sai_read():
    assert _key("52136", "S000008033", "2021-04-28") is None
    assert _key("52136", "S000008033", "2021-04-29") == "HARRIS_ASSOCIATES"
    assert _key("52136", "S000053353", "2021-03-28") is None
    assert _key("872649", "S000006699", "2021-01-27") is None
    assert _key("872649", "S000070337", "2021-04-28") is None
    assert _key("1728860", "S000080571", "2023-06-08") is None                 # launched 2023
    assert _key("1526787", "S000083143", "2023-12-06") is None


def test_fund_of_funds_and_unknown_series_stay_unlabelled():
    assert _key("1095726", "S000056583", "2025-06-30") is None                 # Natixis Sustainable Future 2015 (fund of funds)
    assert _key("52136", "S000000000", "2025-06-30") is None


def test_keyed_commitment_exists_for_loomis_sayles():
    keys = {d["adviser_key"] for d in N["commitments"]}
    assert keys == {"LOOMIS_SAYLES"}
    for d in N["commitments"]:
        assert d["label"] and d["adviser"] and (d.get("url") or d.get("sai_appendix"))
