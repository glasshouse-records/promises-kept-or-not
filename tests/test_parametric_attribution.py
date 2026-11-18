"""Parametric-voted Eaton Vance series are attributed per series, never per trust.

Evidence: each keyed series' own SAI names Parametric Portfolio Associates as its
sub-adviser and says the Board delegated proxy voting to the investment
sub-adviser (accessions are cited in the comments in config/institutions.yaml).
The contract is pinned here so a registrant-level default can never silently label
an Eaton Vance- or MSIM-voted series PARAMETRIC, and so the Morgan Stanley ETF
Trust (whose SAI says the Adviser, not Parametric, votes) never gets keyed.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
PA = CFG["institutions"]["parametric"]
TRUSTS = {"745463", "74663"}


def _entry(cik):
    return next(e for e in PA["npx_ciks"] if str(e["cik"]) == cik)


def test_trusts_have_series_rules_and_no_registrant_default():
    assert {str(e["cik"]) for e in PA["npx_ciks"]} == TRUSTS
    for cik in TRUSTS:
        e = _entry(cik)
        assert not e.get("adviser_key"), "a registrant default would mislabel Eaton Vance-voted series"
        assert any(r[0]["key"] == "PARAMETRIC" for r in e["series_adviser"].values())


def test_every_rule_is_dated():
    n = 0
    for cik in TRUSTS:
        for sid, rules in _entry(cik)["series_adviser"].items():
            assert sid.startswith("S") and rules[0]["key"] == "PARAMETRIC" and rules[0]["from"]
            assert all(r["key"] in ("PARAMETRIC", "PARAMETRIC_MSIM") for r in rules)
            n += 1
    assert n == 6


def test_msim_policy_period_is_not_paired_with_parametric_policy():
    """From the effective date of a 2026 SAI that prints the MSIM Equity policy, the
    voter is still Parametric but the key has no policy document, so no pairing."""
    rules = engine.normalize_rules(_entry("745463"))
    for sid, last_own, first_msim in [("S000032773", "2026-04-30", "2026-05-01"),
                                      ("S000012701", "2026-05-31", "2026-06-01"),
                                      ("S000028355", "2026-05-31", "2026-06-01"),
                                      ("S000056237", "2026-05-31", "2026-06-01")]:
        assert engine.resolve_key(rules, sid, last_own) == "PARAMETRIC"
        assert engine.resolve_key(rules, sid, first_msim) == "PARAMETRIC_MSIM"
    # no 2026 SAI was found for Dividend Income and the Nov 2025 SAI of Tax-Managed EM still prints Parametric's policy
    assert engine.resolve_key(rules, "S000044370", "2026-06-30") == "PARAMETRIC"
    ts2 = engine.normalize_rules(_entry("74663"))
    assert engine.resolve_key(ts2, "S000002405", "2026-06-30") == "PARAMETRIC"


def test_msim_key_has_no_policy_document():
    assert all(d["adviser_key"] == "PARAMETRIC" for d in PA["commitments"])


def test_series_resolve_only_from_evidence_window():
    rules = engine.normalize_rules(_entry("745463"))
    assert engine.resolve_key(rules, "S000012701", "2026-03-01") == "PARAMETRIC"   # Parametric Emerging Markets
    assert engine.resolve_key(rules, "S000012701", "2025-03-01") is None            # before the SAI that says so
    assert engine.resolve_key(rules, "S000044370", "2025-06-30") is None            # Dividend Income: SAI dated 2025-07-01
    ts2 = engine.normalize_rules(_entry("74663"))
    assert engine.resolve_key(ts2, "S000002405", "2025-01-01") == "PARAMETRIC"


def test_eaton_vance_series_are_not_attributed():
    evmft = engine.normalize_rules(_entry("745463"))
    assert engine.resolve_key(evmft, "S000005278", "2026-03-01") is None   # Eaton Vance Stock Fund
    assert engine.resolve_key(evmft, "S000026932", "2026-03-01") is None   # Eaton Vance Total Return Bond
    assert engine.resolve_key(evmft, "S000005279", "2025-03-01") is None   # Parametric Tax-Managed Intl Equity: no SAI located
    ts2 = engine.normalize_rules(_entry("74663"))
    assert engine.resolve_key(ts2, "S000004984", "2026-03-01") is None     # Eaton Vance Income Fund of Boston


def test_policy_document_is_keyed_and_sai_sourced():
    docs = {d["label"]: d for d in PA["commitments"]}
    assert docs, "Parametric policy document must be configured"
    for label, d in docs.items():
        assert d["adviser_key"] == "PARAMETRIC"
        assert label.endswith("-as-printed-in-sai")   # the website blocks honest clients: SAI route only
        assert d["sai_appendix"]["start"] and d["sai_appendix"]["end"]
