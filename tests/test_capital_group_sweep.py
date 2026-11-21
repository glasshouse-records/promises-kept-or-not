"""Capital Group: New Economy Fund added by the sweep (CRMC is the investment adviser; its SAI says the adviser adopted
the Proxy Voting Procedures and Principles). American High Income Trust (823620) is left out: a bond fund whose N-PX
holds 154 vote lines, mostly bankruptcy-related, so it adds no equity voting record."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["capital_group"]
# cik -> (expected key, `from` date = earliest SAI read, evidence accession)
ADDED = {
    "719608": ("CRMC", "2022-02-01", "0000051931-22-000109"),   # The New Economy Fund
}
LEFT_OUT = {"823620"}


def _entry(cik):
    return next(e for e in N["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, day, series=""):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_added_registrants_resolve_from_their_sai_date():
    for cik, (key, frm, _acc) in ADDED.items():
        assert _key(cik, "2026-06-30") == key, cik
        assert _key(cik, frm) == key, cik
        assert _key(cik, "2021-01-01") is None, cik   # before any SAI read: unlabelled
        day_before = (date.fromisoformat(frm) - timedelta(days=1)).isoformat()
        assert _key(cik, day_before) is None, cik


def test_added_registrants_carry_provenance_and_valid_rules():
    for cik, (_, _frm, acc) in ADDED.items():
        e = _entry(cik)
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), cik
        assert acc.replace("-", "") in e["adviser_source"], cik
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"], cik
        engine.validate_rules(engine.normalize_rules(e), cik)


def test_left_out_registrants_are_absent():
    ciks = {str(e["cik"]) for e in N["npx_ciks"]}
    assert not ciks & LEFT_OUT
    assert set(ADDED) <= ciks
