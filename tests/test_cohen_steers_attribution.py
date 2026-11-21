"""Cohen & Steers: every fund registrant is voted by Cohen & Steers Capital Management, Inc. (the Advisor) under its own proxy voting policy (key COHEN_STEERS), dated from the earliest SAI / N-CSR read.

Evidence (accessions in config/institutions.yaml): the open-end SAIs say the Boards delegated voting 'to the Advisor and, as
applicable, the Subadvisors' and print ONE policy 'for the Advisor, CNS Asia and CNS UK' (the two subadvisers are the Advisor's
own Asian and UK affiliates); the closed-end funds' N-CSR Item 7 says 'The registrant has delegated voting of proxies ... to
Cohen & Steers Capital Management, Inc.'. No unaffiliated voter exists, so there is no series exception.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
D = CFG["institutions"]["cohen_steers"]
CIK = "0000845563"
FIRST = {
    # open-end trusts (SAI)
    "1041917": "2021-03-02", "1276070": "2021-03-02", "1484750": "2021-03-02", "1533503": "2021-03-02",
    "1580956": "2021-03-02", "1652200": "2021-04-05", "1760077": "2021-02-26", "1307144": "2021-02-26",
    "1590402": "2024-08-02",
    # closed-end funds (N-CSR Item 7; RLTY: first prospectus/SAI)
    "1498612": "2021-03-08", "1548717": "2021-03-08", "1157842": "2021-03-08", "1224450": "2021-03-08",
    "891290": "2021-03-08", "1275617": "2021-03-08", "1793882": "2021-12-29", "1866874": "2022-02-24",
}
LEFT_OUT = {"845563", "1284812", "1375340", "1564216", "1395057"}
KEYS = {"COHEN_STEERS"}


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


def test_keyed_only_from_the_earliest_filing_read():
    for cik, first in FIRST.items():
        assert _key(cik, "S000000001", first) == "COHEN_STEERS", cik
        assert _key(cik, "", "2026-06-30") == "COHEN_STEERS", cik
        assert _key(cik, "S000000001", _day_before(first)) is None, cik


def test_no_series_exception_because_no_unaffiliated_voter():
    for e in D["npx_ciks"]:
        assert not e.get("series_adviser"), e["cik"]


def test_commitments_are_keyed_and_extractable():
    assert D["commitments"]
    labels = set()
    for c in D["commitments"]:
        assert c["label"] and c["adviser"] and c["adviser_key"] in KEYS
        assert c["label"] not in labels
        labels.add(c["label"])
        assert c.get("url") or c.get("sai_appendix")
        if "sai_appendix" in c:
            sa = c["sai_appendix"]
            assert sa["start"] and sa["end"], "an empty end marker extracts nothing"
            assert sa["forms"] and sa["since"] >= "2021-01-01"
    assert any(c.get("url", "").endswith(".pdf") for c in D["commitments"])
    assert sum("sai_appendix" in c for c in D["commitments"]) == 2
