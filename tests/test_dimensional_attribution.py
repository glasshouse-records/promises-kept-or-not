"""Dimensional: master funds, and the Sustainability / Social guideline split by series.

Evidence (accessions in config/institutions.yaml): the SAIs of DFA Investment Dimensions Group
(0000355437-26-000120, 0001741773-25-001048, 0001741773-24-000695) and Dimensional ETF Trust
(0001816125-26-000046, 0001741773-24-000697) each print ONE summary of voting guidelines. Five
DFAIDG series print the Social summary, six the Sustainability summary, and four ETFs the
Sustainability summary; the 2023 SAIs print a single summary for all. The SAI proxy-voting section
of the feeder portfolios says the Board of the Trust (DFAITC) and of DEM delegated voting for the
Master Funds to the Advisor.

So a Social or Sustainability series must never be paired with the Standard text from the SAI
that introduced the split (2024-02-28); earlier meetings keep the registrant default.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
DIM = CFG["institutions"]["dimensional"]

SOCIAL = {"S000018154", "S000012960", "S000038669", "S000066958", "S000053205"}
SUSTAINABILITY = {"S000020422", "S000068937", "S000020423", "S000060925", "S000086505", "S000063222"}
ETF_SUSTAINABILITY = {"S000076639", "S000076640", "S000076641", "S000076642"}


def _entry(cik):
    return next(e for e in DIM["npx_ciks"] if str(e["cik"]) == cik)


def test_master_funds_are_registered_under_the_advisor_with_sai_evidence():
    assert {str(e["cik"]) for e in DIM["npx_ciks"]} == {"355437", "861929", "1816125", "896162", "896163"}
    for cik in ("896162", "896163"):
        e = _entry(cik)
        assert e["adviser_key"] == "DFA"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert "Master" in e["voting_note"]


def test_master_funds_are_no_longer_listed_as_not_covered():
    notes = " ".join(DIM["voting_scope_notes"])
    assert "are not covered" not in notes


def test_social_and_sustainability_series_have_their_own_keys_from_the_sai_that_split_them():
    rules = engine.normalize_rules(_entry("355437"))
    for sid in SOCIAL:
        assert engine.resolve_key(rules, sid, "2025-11-15") == "DFA_SOCIAL"
        assert engine.resolve_key(rules, sid, "2024-02-28") == "DFA_SOCIAL"
    for sid in SUSTAINABILITY - {"S000086505"}:
        assert engine.resolve_key(rules, sid, "2025-11-15") == "DFA_SUSTAINABILITY"
        assert engine.resolve_key(rules, sid, "2024-02-28") == "DFA_SUSTAINABILITY"
    # before the SAI that split the summaries the 2023 SAIs print one summary: registrant default
    assert engine.resolve_key(rules, "S000018154", "2024-02-27") == "DFA"
    # a series no SAI placed under either guideline is untouched
    assert engine.resolve_key(rules, "S000099999", "2025-11-15") == "DFA"
    # not yet operating at the 2025-02-28 SAI: keyed from that SAI only
    assert engine.resolve_key(rules, "S000086505", "2025-02-27") == "DFA"
    assert engine.resolve_key(rules, "S000086505", "2025-02-28") == "DFA_SUSTAINABILITY"


def test_etf_sustainability_series_keyed_and_other_etfs_not():
    rules = engine.normalize_rules(_entry("1816125"))
    for sid in ETF_SUSTAINABILITY:
        assert engine.resolve_key(rules, sid, "2025-11-15") == "DFA_SUSTAINABILITY"
        assert engine.resolve_key(rules, sid, "2024-02-27") == "DFA"
    assert engine.resolve_key(rules, "S000099999", "2025-11-15") == "DFA"


def test_no_series_sits_in_both_groups_and_other_trusts_have_no_series_rules():
    assert not (SOCIAL & SUSTAINABILITY)
    for cik in ("861929", "896162", "896163"):
        assert not engine.normalize_rules(_entry(cik))["series"]


def test_guideline_documents_are_keyed_to_their_own_groups_never_dfa():
    docs = {d["label"]: d for d in DIM["commitments"]}
    assert docs["summary-of-standard-proxy-voting-guidelines"]["adviser_key"] == "DFA"
    for lab, d in docs.items():
        if "social" in lab:
            assert d["adviser_key"] == "DFA_SOCIAL"
        if "sustainability" in lab:
            assert d["adviser_key"] == "DFA_SUSTAINABILITY"
    sai = [d for lab, d in docs.items() if lab.endswith("-as-printed-in-sai")]
    assert {d["adviser_key"] for d in sai} == {"DFA_SOCIAL", "DFA_SUSTAINABILITY"}
    for d in sai:
        assert d["sai_appendix"]["start"] and d["sai_appendix"]["end"]


def test_scope_notes_say_how_the_groups_were_decided():
    notes = " ".join(DIM["voting_scope_notes"])
    for word in ("DFA_SOCIAL", "DFA_SUSTAINABILITY", "2024-02-28"):
        assert word in notes
