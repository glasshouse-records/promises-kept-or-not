"""Franklin Templeton: the eight Franklin / Templeton / Mutual Series registrants added by the sweep.
Franklin Advisers votes under the FRANKLIN policy; Franklin Mutual Advisers, the Templeton Global Equity Group and
Franklin Templeton Investment Solutions print their OWN policies and have no key here, and the multi-series trusts
(ETF Trust, Strategic Series, Variable Insurance Products Trust) name several policies and sub-advisers, so those are
UNRESOLVED (quarantined), never guessed."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
N = CFG["institutions"]["franklin_templeton"]
# cik -> (expected key, `from` date = earliest SAI read, evidence accession)
ADDED = {
    "805650": ("FRANKLIN", "2022-01-26", "0001741773-22-000111"),      # Franklin Managed Trust (Rising Dividends)
    "809707": ("FRANKLIN", "2022-02-25", "0001741773-22-000406"),      # Franklin Investors Securities Trust
    "825063": ("UNRESOLVED", "2022-04-27", "0001741773-22-001277"),    # Mutual Series: Franklin Mutual Advisers' own policy
    "1655589": ("UNRESOLVED", "2024-05-30", "0001741773-24-002496"),   # ETF Trust: Equity Group + Investment Solutions
    "872625": ("UNRESOLVED", "2022-08-25", "0001741773-22-002835"),    # Strategic Series
    "837274": ("UNRESOLVED", "2022-03-15", "0001741773-22-000997"),    # VIP Trust: sub-advisers, six policies
    "805664": ("UNRESOLVED", "2022-12-27", "0001741773-22-004375"),    # Templeton Growth: Templeton Global Equity Group
    "225930": ("UNRESOLVED", "2022-12-27", "0001741773-22-004367"),    # Templeton Funds
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
