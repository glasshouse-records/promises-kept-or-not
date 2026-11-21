"""Morgan Stanley sweep of 2026-11-21: Calvert registrants added under their own key CALVERT.

Evidence (accessions in config/institutions.yaml): every Calvert SAI says the Board delegated proxy voting to the
investment adviser, Calvert Research and Management (CRM, a Morgan Stanley subsidiary), and prints CRM's own Proxy Voting
Policies and Procedures (Global Proxy Voting Guidelines) as an appendix. That is not the MSIM Equity Proxy Voting Policy,
so the votes are keyed CALVERT, never MSIM. The Eaton Vance registrants are left out: see the block's notes.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
INSTS = CFG["institutions"]
M = INSTS["morgan_stanley"]
BEFORE = {"836487", "741375", "1011378", "860720", "1002427", "1368493", "916618", "1676326"}
# registrant -> first date a CRM-delegation SAI was read
ADDED = {
    "356682": "2022-01-28",    # Calvert Social Investment Fund
    "708950": "2022-04-28",    # Calvert Variable Series, Inc.
    "1121624": "2022-01-28",   # Calvert Impact Fund, Inc.
    "319676": "2022-01-28",    # Calvert Management Series
    "884110": "2022-01-28",    # Calvert World Values Fund, Inc.
    "1105446": "2022-01-28",   # Calvert Responsible Index Series, Inc.
    "743773": "2023-04-27",    # Calvert Variable Trust, Inc. (the 2022 SAI delegates to adviser AND sub-adviser)
}
LEFT_OUT = {
    "701039",                                                                    # Calvert Fund: bond funds, one incidental issuer
    "102818", "1002667",                                                         # Tax-Managed Growth feeder and master
    "1475712", "933188", "1116914", "1928846",                                   # master portfolios (notice-only or loans)
    "779991", "1121746", "1552324",                                              # Eaton Vance open-end trusts (no equity votes)
    "1300391", "1308335", "1253327", "1270523", "1281926", "1322436", "1322435", "1379438",   # Eaton Vance equity closed-end funds
    "1395325", "1308927", "1340736", "1316051", "1480999",                       # Eaton Vance CEFs: notice-only or gone
}


def _entry(cik):
    return next(e for e in M["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, day, series=None):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_the_earlier_registrants_are_untouched_and_the_added_ones_present():
    ciks = {str(e["cik"]) for e in M["npx_ciks"]}
    assert ciks == BEFORE | set(ADDED)


def test_left_out_registrants_are_absent_everywhere():
    ciks = {str(e["cik"]) for inst in INSTS.values() for e in inst.get("npx_ciks") or []}
    for c in LEFT_OUT:
        assert c not in {str(e["cik"]) for e in M["npx_ciks"]}, c
    # the Tax-Managed Growth master and feeder report the same 1,640 ballots; neither may be ingested without the other check
    assert not ({"102818", "1002667"} & ciks)


def test_added_registrants_are_in_no_other_institution():
    for c in ADDED:
        owners = [k for k, inst in INSTS.items() if any(str(e["cik"]) == c for e in inst.get("npx_ciks") or [])]
        assert owners == ["morgan_stanley"], (c, owners)


def test_added_registrants_are_keyed_calvert_from_the_sai_and_unlabelled_before():
    for c, frm in ADDED.items():
        e = _entry(c)
        engine.validate_rules(engine.normalize_rules(e), c)
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), c
        assert e["name"] and e["adviser"] and e["adviser_verified"] and e["voting_note"] and e["validated"], c
        assert "Calvert Research and Management" in e["adviser"], c
        assert _key(c, "2026-06-30") == "CALVERT", c
        assert _key(c, frm) == "CALVERT", c
        assert _key(c, "2020-01-01") is None, c
        before_day = f"{int(frm[:4]) - 1}{frm[4:]}"
        assert _key(c, before_day) is None, c
        assert engine.rule_keys(engine.normalize_rules(e)) == {"CALVERT"}, c


def test_calvert_key_does_not_leak_into_the_msim_registrants():
    for c in BEFORE:
        assert "CALVERT" not in engine.rule_keys(engine.normalize_rules(_entry(c))), c


def test_the_calvert_policy_commitment_is_keyed_calvert():
    docs = [d for d in M["commitments"] if d["adviser_key"] == "CALVERT"]
    assert len(docs) == 1
    d = docs[0]
    assert d["label"] == "calvert-proxy-voting-policies-as-printed-in-sai"
    cfg = d["sai_appendix"]
    assert cfg["cik"] == "0001105446" and cfg["forms"] == ["485BPOS"] and cfg["start"] and cfg["end"]
    # the MSIM commitment is still the only other one and stays MSIM
    others = [x for x in M["commitments"] if x is not d]
    assert others and all(x["adviser_key"] == "MSIM" for x in others)
