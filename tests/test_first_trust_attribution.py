"""First Trust (First Trust Advisors L.P.; CIK 1125816 the 13-F filer) fund registrants.

Evidence (accessions in config/institutions.yaml): every SAI of the twelve open-end trusts says "The Board has
delegated to First Trust the proxy voting responsibilities for the Fund[s]" and "First Trust has adopted the ISS Proxy
Voting Guidelines". Until the SAI that first says "The First Trust Proxy Voting Guidelines [Policies and Procedures]
are attached hereto" the exhibit is ISS's own guideline book, so the votes are keyed FIRST_TRUST_ISS (not pretending the
policy is First Trust's own); from that SAI they are FIRST_TRUST. A series whose OWN single-fund SAI says the Board
delegated day-to-day voting to a sub-adviser is EXTERNAL.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
F = CFG["institutions"]["first_trust"]
# cik: (earliest SAI read, SAI that first attaches First Trust's own written policy)
EVIDENCE = {
    "1329377": ("2021-04-29", "2022-10-19"), "1364608": ("2021-01-28", "2022-09-30"),
    "1424212": ("2021-02-26", "2022-11-28"), "1517936": ("2021-02-26", "2023-02-28"),
    "1549548": ("2021-04-29", "2023-04-28"), "1552740": ("2021-01-28", "2023-01-27"),
    "1561785": ("2021-04-29", "2023-04-28"), "1667919": ("2021-01-15", "2022-12-29"),
    "1383496": ("2021-11-24", "2022-11-28"), "1510337": ("2021-04-29", "2023-04-28"),
    "1497778": ("2021-02-26", "2023-02-28"), "1537395": ("2021-04-19", "2023-04-28"),
}
# Left out on purpose: First Trust Advisors' own institutional-manager N-PX and the closed-end funds.
LEFT_OUT = {"1125816", "1604488", "1403275", "1291334", "1284940", "1513789", "1319183", "1556336", "1494530"}
SUB_ADVISED = {  # cik: {series: (from, until)} EXTERNAL
    "1329377": {"S000086663": ("2024-10-02", None), "S000086665": ("2024-10-02", None)},
    "1424212": {"S000067481": ("2023-11-16", "2026-06-17")},
    "1517936": {"S000070911": ("2021-02-26", None), "S000077877": ("2022-10-27", None)},
    "1497778": {"S000086667": ("2024-10-02", None)},
    "1537395": {"S000080226": ("2023-08-09", None)},
    "1667919": {"S000081234": ("2023-11-16", None)},
}


def _entry(cik):
    return next(e for e in F["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert F.get(k), k
    assert F["cik"] == "0001125816"
    assert "aum_usd_tr" in F


def test_exactly_the_twelve_open_end_trusts_and_no_open_default():
    ciks = {str(e["cik"]) for e in F["npx_ciks"]}
    assert ciks == set(EVIDENCE)
    assert not ciks & LEFT_OUT
    for e in F["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        rules = engine.normalize_rules(e)
        engine.validate_rules(rules, e["cik"])
        keys = engine.rule_keys(rules)
        assert {"FIRST_TRUST_ISS", "FIRST_TRUST"} <= keys
        assert keys <= {"FIRST_TRUST_ISS", "FIRST_TRUST", "EXTERNAL"}


def test_two_eras_per_trust_dated_from_the_sai():
    for cik, (first, cut) in EVIDENCE.items():
        before_cut = (date.fromisoformat(cut) - timedelta(days=1)).isoformat()
        before_first = (date.fromisoformat(first) - timedelta(days=1)).isoformat()
        assert _key(cik, "S000000000", before_first) is None
        assert _key(cik, "S000000000", first) == "FIRST_TRUST_ISS"
        assert _key(cik, "S000000000", before_cut) == "FIRST_TRUST_ISS"
        assert _key(cik, "S000000000", cut) == "FIRST_TRUST"
        assert _key(cik, "S000000000", "2026-06-30") == "FIRST_TRUST"


def test_series_whose_own_sai_delegates_to_a_sub_adviser_are_external():
    for cik, series in SUB_ADVISED.items():
        for sid, (lo, hi) in series.items():
            assert _key(cik, sid, lo) == "EXTERNAL"
            before = (date.fromisoformat(lo) - timedelta(days=1)).isoformat()
            assert _key(cik, sid, before) != "EXTERNAL"
            if hi:
                assert _key(cik, sid, hi) == "EXTERNAL"
                assert _key(cik, sid, (date.fromisoformat(hi) + timedelta(days=1)).isoformat()) == "FIRST_TRUST"
            else:
                assert _key(cik, sid, "2026-06-30") == "EXTERNAL"
    # a sub-advised series whose SAIs all say First Trust votes keeps the registrant key
    assert _key("1424212", "S000052736", "2025-06-30") == "FIRST_TRUST"


def test_policy_labels_carry_the_era_keys_and_never_archive_iss_guidelines():
    labels = {c["label"]: c for c in F["commitments"]}
    assert {c["adviser_key"] for c in labels.values()} == {"FIRST_TRUST_ISS", "FIRST_TRUST"}
    for c in labels.values():
        assert "url" not in c, "ISS's copyrighted guideline book must not be fetched or archived"
        assert c["sai_appendix"]["cik"] == "0001549548"
