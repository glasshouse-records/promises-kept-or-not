"""AQR: AQR Funds is voted by AQR Capital Management, LLC under its own proxy voting policy (key AQR), dated from the earliest SAI read.

Evidence (accessions in config/institutions.yaml): the SAI 'Proxy Voting Policies and Procedures' says 'The Trust has delegated
proxy voting responsibilities with respect to each Fund to the Adviser' and prints the Adviser's policy as Appendix A; a third-party
proxy adviser executes votes and supplies research under AQR's policy. Every series is advised by AQR alone.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["aqr"]
CIK = "0001167557"
FIRST = {"1444822": "2021-01-28"}
LEFT_OUT = {"1167557", "2123596"}
KEYS = {"AQR"}


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
    for left in LEFT_OUT:
        assert left in D["notes"], f"left-out registrant {left} must be listed with a reason in the notes"


def test_exactly_the_researched_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in D["npx_ciks"]}
    assert ciks == set(FIRST)
    assert not ciks & LEFT_OUT
    for e in D["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        assert "<date>" not in str(e)
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
        assert not e.get("series_adviser"), "AQR advises every series; no exception"


def test_keyed_only_from_the_earliest_filing_read():
    for cik, first in FIRST.items():
        for series in ("S000024170", "S000093174"):
            assert _key(cik, series, first) == "AQR"
            assert _key(cik, series, "2026-06-30") == "AQR"
            assert _key(cik, series, _day_before(first)) is None


def test_commitments_are_keyed_and_extractable():
    assert D["commitments"]
    for c in D["commitments"]:
        assert c["label"] and c["adviser"] and c["adviser_key"] in KEYS
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"
            assert sa["forms"] == ["485BPOS"] and sa["since"] >= "2021-01-01"
    assert any(c.get("url", "").endswith("AQR-Proxy-Voting-Policy.pdf") for c in D["commitments"])
    assert any("sai_appendix" in c for c in D["commitments"])
