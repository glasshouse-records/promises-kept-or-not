"""Voya: all fourteen registrants are voted by Voya Investments, LLC under the Board's Voya Funds policy (key VOYA), dated from the earliest SAI (N-CSR for the closed-end funds) read."""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["voya"]
CIK = "0001077479"
FIRST = {"837276": "2021-04-26", "1039001": "2021-04-26", "1063946": "2021-09-24", "895430": "2021-02-25", "916403": "2021-04-27", "2664": "2021-04-27", "846799": "2021-04-27", "1066602": "2021-07-29", "1385632": "2021-05-06", "1332943": "2021-05-06", "1285890": "2021-05-06", "1417802": "2021-05-06", "1496292": "2021-05-06", "1124959": "2021-05-06"}
KEY = dict.fromkeys(FIRST, "VOYA")
KEYS = {"VOYA"}


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
