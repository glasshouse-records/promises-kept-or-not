"""Fidelity registrant sweep (docs/research/sweep.md).

Evidence: the SAIs (485BPOS) of each added trust print one proxy-voting policy. Twelve trusts print only the Fidelity
Proxy Voting Guidelines (FMR and its affiliates FMR UK / H.K. / Japan; "Geode" appears only in the board boilerplate), so
they are listed WITHOUT an adviser key (Fidelity has no key; unlabelled = not on record, never guessed), exactly like the
existing FMR-only registrants. Fidelity Commonwealth Trust's only series, the Fidelity Nasdaq Composite Index ETF
(S000006011), prints Geode's voting policy alone in every SAI from 2022-01-25 on, so it is keyed GEODE from that date.
Left out: Covington Trust (mixed Geode index ETFs / FMR active ETFs, needs a per-series pass), Central Investment
Portfolios LLC (no SAI to read), Oxford Street Trust (Geode-advised, N-PX is a notice report with no votes).
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
F = CFG["institutions"]["fidelity"]
UNKEYED = {"24238", "754510", "744822", "707823", "320351", "35348", "61397", "35341", "275309", "356494",
           "315700", "720318"}
GEODE_SERIES = {"205323": "S000006011"}
LEFT_OUT = {"945908", "1303459", "28540"}


def _entry(cik):
    return next(e for e in F["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_added_registrants_present_with_evidence_and_left_out_absent():
    ciks = {str(e["cik"]) for e in F["npx_ciks"]}
    assert (UNKEYED | set(GEODE_SERIES)) <= ciks
    assert not ciks & LEFT_OUT
    for c in UNKEYED | set(GEODE_SERIES):
        e = _entry(c)
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), c
        assert e["name"] and e["adviser_verified"] and e["validated"] and e["adviser"], c
        engine.validate_rules(engine.normalize_rules(e), c)


def test_fmr_only_trusts_are_unlabelled_before_and_after():
    for c in UNKEYED:
        assert not _entry(c).get("adviser_key"), c
        assert not _entry(c).get("series_adviser"), c
        for day in ("2021-06-30", "2025-07-01", "2026-06-30"):
            assert _key(c, "S000000001", day) is None, (c, day)


def test_commonwealth_nasdaq_etf_is_geode_from_the_first_sai_read():
    sid = GEODE_SERIES["205323"]
    assert _key("205323", sid, "2022-06-30") == "GEODE"
    assert _key("205323", sid, "2026-06-30") == "GEODE"
    assert _key("205323", sid, "2022-01-24") is None      # before the evidence
    assert _key("205323", "S000000001", "2026-06-30") is None   # any other series: not on record
    assert not _entry("205323").get("adviser_key")


def test_left_out_registrants_are_documented():
    text = " ".join(str(n) for n in F["voting_scope_notes"])
    for c in LEFT_OUT:
        assert c in text, c
