"""Virtus Investment Partners open-end fund registrants.

Evidence (accessions in config/institutions.yaml): every Virtus SAI says that, "in the absence of a specific direction to the
contrary from the Board, the Adviser or the subadviser that is managing a Fund is responsible for voting proxies", then prints
one proxy paragraph per subadviser, and its glossary names the subadviser of each fund ("KAR ... subadviser to the Capital
Growth Fund, Equity Income Fund, ..."). So there is no registrant-wide voter: each series is keyed by its subadviser.
Kayne Anderson Rudnick (KAR) votes its funds under its own policy, archived here (key KAR). Every other subadviser (Duff &
Phelps, SGA, NFJ, Westchester, AlphaSimplex, the Virtus Advisers divisions) has no archived policy, so its series are
UNRESOLVED; Voya IM (unaffiliated) is EXTERNAL. Bond-only series and the closed-end funds are left out.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
V = CFG["institutions"]["virtus"]
KEYS = {"KAR", "EXTERNAL", "UNRESOLVED"}
INGESTED = {"34273", "1005020", "1423227", "1589756", "1572617"}
LEFT_OUT = {"1260563", "1778114", "1214935", "1227857", "1636289", "1383441", "836412", "1528811", "1501103", "883237"}


def _entry(cik):
    return next(e for e in V["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert V.get(k), k
    assert V["cik"] == "0000883237"
    assert "aum_usd_tr" in V
    assert "<date>" not in str(V)


def test_exactly_the_registrants_and_no_registrant_default():
    ciks = {str(e["cik"]) for e in V["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
    for e in V["npx_ciks"]:
        assert not e.get("adviser_key"), e["cik"]
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_every_rule_uses_a_known_key_and_a_date():
    n = 0
    for e in V["npx_ciks"]:
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                n += 1
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from"), (sid, "an undated rule would label meetings before the evidence")
        assert not e.get("adviser_key_history")
    assert n >= 25


def test_kar_series_resolve_after_the_sai_that_names_them():
    assert _key("34273", "S000021173", "2025-06-30") == "KAR"                  # KAR Capital Growth
    assert _key("34273", "S000001386", "2025-06-30") == "KAR"                  # KAR Global Quality Dividend
    assert _key("1005020", "S000042963", "2025-06-30") == "KAR"                # KAR Emerging Markets Small-Cap
    assert _key("1005020", "S000072168", "2025-06-30") == "KAR"                # KAR Developing Markets
    assert _key("1589756", "S000063645", "2024-06-30") == "KAR"                # KAR Long/Short Equity
    assert _key("34273", "S000021173", "2021-01-25") is None
    assert _key("34273", "S000021173", "2021-01-26") == "KAR"
    assert _key("34273", "S000072656", "2021-08-01") is None                   # Small-Mid Cap Value: first SAI 2021-08-02
    assert _key("34273", "S000072656", "2021-08-02") == "KAR"
    assert _key("1005020", "S000072168", "2021-06-20") is None                 # Developing Markets: first SAI 2021-06-21


def test_non_kar_series_are_unresolved_or_external_never_kar():
    assert _key("34273", "S000064774", "2025-06-30") == "UNRESOLVED"           # SGA Global Growth
    assert _key("34273", "S000021179", "2025-06-30") == "UNRESOLVED"           # Tactical Allocation: Virtus FI + KAR
    assert _key("1005020", "S000018002", "2025-06-30") == "UNRESOLVED"         # Duff & Phelps Real Estate
    assert _key("1005020", "S000055178", "2025-06-30") == "UNRESOLVED"         # Vontobel then SGA EM
    assert _key("1423227", "S000021463", "2025-06-30") == "UNRESOLVED"         # Duff & Phelps Water
    assert _key("1423227", "S000028359", "2025-06-30") == "EXTERNAL"           # Convertible: Voya IM
    assert _key("1589756", "S000050625", "2025-06-30") == "UNRESOLVED"         # D&P Select MLP
    assert _key("1572617", "S000040968", "2025-06-30") == "UNRESOLVED"         # Westchester Event-Driven


def test_bond_and_unknown_series_stay_unlabelled():
    assert _key("1005020", "S000001336", "2025-06-30") is None                 # Newfleet Core Plus Bond
    assert _key("34273", "S000000000", "2025-06-30") is None


def test_keyed_commitment_exists_for_kar():
    keys = {d["adviser_key"] for d in V["commitments"]}
    assert keys == {"KAR"}
    for d in V["commitments"]:
        assert d["label"] and d["adviser"] and (d.get("url") or d.get("sai_appendix"))
