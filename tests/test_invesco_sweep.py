"""Invesco sweep: nine candidate registrants checked, all nine added.

Evidence (accessions in config/institutions.yaml): every Invesco SAI says the Board delegated proxy voting to the
Adviser (Invesco Advisers, Inc. for the mutual fund trusts, Invesco Capital Management LLC for the ETF trusts), voting
under Invesco's Policy Statement on Global Corporate Governance and Proxy Voting (SAI Appendix E / Appendix A). The
mutual fund SAIs add that "the Adviser and each sub-adviser rely on this policy"; their fund-by-fund tables name only
Invesco affiliates. So each registrant carries one registrant-level key from the filing date of its earliest SAI read.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["invesco"]
KEY = "INVESCO"
# cik -> from date (filing date of the earliest SAI read)
ADDED = {
    "1209466": "2022-08-25",
    "1112996": "2022-12-15",
    "725781": "2022-08-25",
    "105377": "2022-02-25",
    "880859": "2022-02-25",
    "896435": "2022-04-28",
    "1378872": "2022-02-25",
    "202032": "2022-04-28",
    "1657201": "2022-09-01",
}
LEFT_OUT = {"1067839"}   # Invesco QQQ Trust, Series 1 (UIT): not a candidate; voter not established


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, day, series="S000000001"):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _day_before(day):
    from datetime import date, timedelta
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_every_added_registrant_is_present_with_provenance():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert set(ADDED) <= ciks
    assert not ciks & LEFT_OUT
    for cik in ADDED:
        e = _entry(cik)
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), cik)
        assert "<date>" not in str(e)


def test_key_from_the_sai_date_and_unlabelled_before():
    for cik, frm in ADDED.items():
        assert _key(cik, frm) == KEY, cik
        assert _key(cik, "2026-06-30") == KEY, cik
        assert _key(cik, _day_before(frm)) is None, cik
        assert _key(cik, "2021-06-30") is None, cik


def test_the_archived_policy_carries_the_same_key():
    assert any(c.get("adviser_key") == KEY for c in N["commitments"])


def test_the_original_etf_trust_entry_is_untouched():
    assert _entry("1418144")["name"] == "Invesco Actively Managed Exchange-Traded Fund Trust"
