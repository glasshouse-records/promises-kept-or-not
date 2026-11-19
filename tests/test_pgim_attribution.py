"""PGIM (PGIM Investments LLC and its subadvisers) fund registrants.

Evidence (accessions in config/institutions.yaml): every PGIM SAI says "The Board has delegated to the Manager the
responsibility for voting any proxies ... The Manager delegates to the Fund's subadviser(s) the responsibility for voting
proxies", and each SAI prints the subadviser's own policy in "Appendix I: Proxy voting policies of the subadviser". So a
registrant has NO single voter: each series is keyed by its voting subadviser, read from the trust's own Form N-CEN
(Item C.3, sub-advisers per series, filed 2023-2026). JENNISON, PGIM_QUANT and PGIM_INC (PGIM, Inc.'s investment groups:
PGIM Fixed Income, PGIM Real Estate) vote under their OWN policies; any unaffiliated subadviser makes the series EXTERNAL;
two different PGIM voters, or a subadviser change inside the window, make it UNRESOLVED; a series with no subadviser stays
unlabelled. Rules are DATED from the filing date of the first N-CEN read for that series.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
P = CFG["institutions"]["pgim"]
KEYS = {"JENNISON", "PGIM_QUANT", "PGIM_INC", "EXTERNAL", "UNRESOLVED"}
# Closed-end / interval funds: one fund = one registrant, so the registrant carries its (dated) subadviser key.
CLOSED_END = {"1554697", "1534880", "1812923", "1875084", "1989582"}
# Registrants ingested (N-PX vote tables 2024-26). Left out on purpose: muni-only and money-market trusts, the private /
# collective-trust / offshore PGIM funds (no N-PX vote table) and PGIM Investments / PGIM, Inc. institutional-manager filings.
INGESTED = {
    "1052118", "949512", "1099692", "1104631", "807394", "1090155", "746518", "803191", "887991", "1070287", "1035018",
    "1051562", "717819", "278187", "1067442", "929523", "356683", "1022624", "816753", "318531", "834126", "793159",
    "741350", "352665", "890339", "1727074", "1992104", "711175", "814679", "1554697", "1534880", "1812923", "1875084",
    "1989582",
}
LEFT_OUT = {"1038001", "946754", "1316541", "53417", "67590", "311561", "314612", "1666044", "1923622"}


def _entry(cik):
    return next(e for e in P["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert P.get(k), k
    assert P["cik"] == "0000946754"           # PGIM, Inc., the parent
    assert "aum_usd_tr" in P


def test_exactly_the_registrants_and_no_registrant_default():
    ciks = {str(e["cik"]) for e in P["npx_ciks"]}
    assert ciks == INGESTED
    assert not ciks & LEFT_OUT
    for e in P["npx_ciks"]:
        # No registrant has one voter: an undated or registrant-wide key would mislabel every other series.
        assert not e.get("adviser_key"), e["cik"]
        hist = e.get("adviser_key_history") or []
        if e["cik"] in CLOSED_END:
            assert [h["key"] for h in hist] == ["PGIM_INC"] and hist[0]["from"] >= "2023-01-01", e["cik"]
        else:
            assert not hist, e["cik"]
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_every_series_rule_uses_a_known_key_and_a_date():
    n = 0
    for e in P["npx_ciks"]:
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                n += 1
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from"), (sid, "an undated rule would label meetings before the evidence")
    assert n > 150


def test_jennison_series_are_keyed_jennison():
    assert _key("1052118", "S000043468", "2024-10-01") == "JENNISON"      # Jennison Energy Infrastructure (MLP)
    assert _key("1022624", "S000004657", "2025-01-01") == "JENNISON"      # Jennison Mid-Cap Growth


def test_quant_and_pgim_inc_series():
    assert _key("1070287", "S000004644", "2024-10-01") == "PGIM_QUANT"    # Quant Solutions Large-Cap Core
    assert _key("1051562", "S000045516", "2024-10-01") == "PGIM_INC"      # Short Duration Muni (PGIM, Inc.)
    assert _key("1051562", "S000004628", "2024-10-01") == "PGIM_INC"      # Global Real Estate: PGIM, Inc. + PGIM RE (UK)


def test_two_pgim_voters_are_unresolved_not_guessed():
    assert _key("1067442", "S000004703", "2024-10-01") == "UNRESOLVED"    # Income Builder: Jennison + Quant Solutions


def test_unaffiliated_subadviser_is_external():
    # Prudential Series Fund / Advanced Series Trust portfolios run by outside managers
    ext = [(c, s) for c in ("711175", "814679")
           for s, rules in (_entry(c).get("series_adviser") or {}).items()
           if any(r["key"] == "EXTERNAL" for r in rules)]
    assert len(ext) >= 40


def test_a_subadviser_change_in_the_window_is_unresolved_throughout():
    # Target Date 2055: Quant Solutions in the N-CEN of 2023, PGIM DC Solutions from 2024
    assert _key("1090155", "S000055689", "2025-01-01") == "UNRESOLVED"
    assert _key("711175", "S000002197", "2025-01-01") == "UNRESOLVED"    # PSF Global Portfolio: outside -> Quant 2026


def test_meetings_before_the_evidence_stay_unlabelled():
    assert _key("1052118", "S000043468", "2021-06-01") is None


def test_closed_end_funds_are_keyed_from_their_first_n_cen():
    assert _key("1554697", "", "2024-06-30") == "PGIM_INC"           # PGIM Global High Yield Fund
    assert _key("1554697", "", "2023-06-30") is None


def test_unknown_series_stays_unlabelled():
    assert _key("1052118", "S000000000", "2024-10-01") is None


def test_keyed_commitments_exist_for_the_affiliate_voters():
    docs = {(d["adviser_key"]): d for d in P["commitments"]}
    assert {"JENNISON", "PGIM_QUANT", "PGIM_INC"} <= set(docs)
    for d in P["commitments"]:
        assert d["label"] and d["adviser"]
