"""New York Life Investments (NYLIM) fund registrants.

Evidence (accessions in config/institutions.yaml): every MainStay / NYLI / NYLIM SAI says the Board delegated all proxy
voting to the Manager, which "may delegate proxy voting authority to the Subadvisor"; the SAI then names, fund by fund,
the subadviser it delegated to, and the funds the Manager retained. So the open-end trusts have NO registrant-wide
voter: each series is keyed by the voter the SAI names (earliest naming SAI = `from`). Affiliates (MacKay Shields, NYL
Investors, Candriam, IndexIQ Advisors, Ausbil) vote under their OWN policies; unaffiliated subadvisers are EXTERNAL;
series with several voters, series the SAI never names and the gaps between SAIs at a change of voter are UNRESOLVED.
The ETF trust has one voter, the Advisor: IndexIQ Advisors until the SAI of 2024-08-27, then NYLIM.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["new_york_life"]
KEYS = {"NYLIM", "MACKAY_SHIELDS", "NYL_INVESTORS", "CANDRIAM", "INDEXIQ", "AUSBIL", "EXTERNAL", "UNRESOLVED"}
INGESTED = {"787441", "1469192", "887340", "1415995", "1426439", "1855066"}
LEFT_OUT = {"1995668", "1518557", "1133639", "1415996", "1127612", "868307", "1427789", "1135510"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert N.get(k), k
    assert N["cik"] == "0001133639"
    assert "aum_usd_tr" in N


def test_exactly_the_registrants_and_no_registrant_default_for_subadvised_trusts():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
    for e in N["npx_ciks"]:
        assert not e.get("adviser_key"), e["cik"]
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
        assert "<date>" not in str(e)


def test_every_rule_uses_a_known_key_and_a_date():
    n = 0
    for e in N["npx_ciks"]:
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                n += 1
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from") or r.get("until"), (sid, "an undated rule would label meetings before the evidence")
        for r in e.get("adviser_key_history") or []:
            assert r["key"] in KEYS, r
    assert n > 80


def test_one_series_per_key_resolves_as_researched():
    assert _key("787441", "S000006894", "2025-06-30") == "MACKAY_SHIELDS"   # MacKay Strategic Bond
    assert _key("1469192", "S000028529", "2025-06-30") == "NYL_INVESTORS"   # Floating Rate
    assert _key("1469192", "S000059215", "2025-06-30") == "CANDRIAM"        # Candriam EM Equity
    assert _key("1469192", "S000028525", "2023-06-30") == "INDEXIQ"         # S&P 500 Index, IndexIQ window
    assert _key("1426439", "S000101653", "2026-06-30") == "AUSBIL"          # Intl Small-Mid Cap ETF
    assert _key("1469192", "S000028532", "2025-06-30") == "NYLIM"           # Conservative Allocation, Manager retained
    assert _key("787441", "S000006905", "2025-06-30") == "EXTERNAL"         # Winslow Large Cap Growth
    assert _key("787441", "S000006900", "2025-06-30") == "UNRESOLVED"       # Income Builder: two voters


def test_unnamed_series_are_unresolved_not_guessed():
    assert _key("787441", "S000006906", "2025-06-30") == "UNRESOLVED"       # WMC Value: never named in the SAI
    assert _key("1469192", "S000036715", "2025-06-30") == "UNRESOLVED"      # WMC Small Companies
    assert _key("1469192", "S000036714", "2025-06-30") == "UNRESOLVED"      # Balanced: three voters


def test_sp500_index_voter_changes_with_gaps_unresolved():
    assert _key("1469192", "S000028525", "2022-06-30") == "UNRESOLVED"      # between the 2022-03-29 and 2022-08-29 SAIs
    assert _key("1469192", "S000028525", "2024-06-30") == "UNRESOLVED"      # between 2024-05-01 and 2024-08-28
    assert _key("1469192", "S000028525", "2025-06-30") == "NYLIM"
    assert _key("887340", "S000009443", "2023-06-30") == "INDEXIQ"
    assert _key("887340", "S000009443", "2025-06-30") == "NYLIM"


def test_etf_trust_switches_from_indexiq_to_nylim_with_an_unresolved_gap():
    # The SAI of 2024-08-27 names NYLIM; NYLIM's Form ADV dates the change 2024-09-12.
    # Meetings between the two dates are not attributed (precision over recall).
    assert _key("1415995", "S000050195", "2024-08-26") == "INDEXIQ"
    assert _key("1415995", "S000050195", "2024-08-27") == "UNRESOLVED"
    assert _key("1415995", "S000050195", "2024-09-11") == "UNRESOLVED"
    assert _key("1415995", "S000050195", "2024-09-12") == "NYLIM"
    assert _key("1415995", "S000050195", "2025-06-30") == "NYLIM"
    assert _key("1415995", "S000050195", "2021-08-29") is None              # before the first multi-fund SAI


def test_closed_end_cbre_fund_is_external():
    assert _key("1855066", "", "2025-06-30") == "EXTERNAL"
    assert _key("1855066", "", "2021-01-01") is None


def test_unknown_series_stays_unlabelled():
    assert _key("787441", "S000000000", "2025-06-30") is None


def test_keyed_commitments_exist_for_the_affiliate_voters():
    keys = {d["adviser_key"] for d in N["commitments"]}
    assert {"NYLIM", "NYL_INVESTORS", "INDEXIQ", "MACKAY_SHIELDS"} <= keys
    assert not keys & {"EXTERNAL", "UNRESOLVED"}
    for d in N["commitments"]:
        assert d["label"] and d["adviser"]
