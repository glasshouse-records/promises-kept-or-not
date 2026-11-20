"""Russell Investment Company, Russell Investment Funds and Russell Investments Exchange Traded Funds: voted by Russell Investment Management, LLC (key RUSSELL)."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["russell"]
CIK = "0001415227"
FIRST = {"351601": "2021-03-01", "824036": "2021-04-30", "2042513": "2025-04-01"}
KEY = dict.fromkeys(FIRST, "RUSSELL")
KEYS = {"RUSSELL"}


def _entry(cik):
    return next(e for e in D["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert D.get(k), k
    assert D["cik"] == CIK
    assert "aum_usd_tr" in D


def test_exactly_the_researched_registrants_and_no_open_default():
    assert {str(e["cik"]) for e in D["npx_ciks"]} == set(FIRST)
    for e in D["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        assert "<date>" not in (e["adviser_verified"], e["validated"])
        engine.validate_rules(engine.normalize_rules(e), e["cik"])


def test_keyed_only_from_the_earliest_filing_read():
    for cik, first in FIRST.items():
        assert _key(cik, "S000000001", first) == KEY[cik]
        assert _key(cik, "S000000001", "2026-06-30") == KEY[cik]
        assert _key(cik, "S000000001", _day_before(first)) is None


def test_commitment_labels_carry_the_institution_keys():
    assert D["commitments"]
    for c in D["commitments"]:
        assert c["label"] and c["adviser_key"] in KEYS
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"


def test_no_series_exception():
    for e in D["npx_ciks"]:
        assert not engine.normalize_rules(e)["series"]
