"""Goldman Sachs Trust II added by the sweep, UNRESOLVED: when a fund allocates to Underlying Managers they take every
proxy action for their sleeve, while GSAM votes anything it holds itself (SAI 'Proxy Voting by the Investment Adviser'),
so no series has a single voter we can name without a per-series reading."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["goldman_sachs"]
# cik -> (expected key, `from` date = earliest SAI read, evidence accession)
ADDED = {
    "1557156": ("UNRESOLVED", "2022-02-28", "0001193125-22-058202"),   # Goldman Sachs Trust II
}
LEFT_OUT = set()


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
