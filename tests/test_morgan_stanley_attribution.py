"""Morgan Stanley Investment Management (MSIM) fund registrants: MSIM votes under its Equity Proxy Voting Policy.

Evidence (accessions in config/institutions.yaml): each registrant's SAI (or, for the two closed-end
funds, the N-CSR Item 7 / Item 12) says the Board delegated proxy voting to MSIM / the Adviser
(Morgan Stanley Investment Management Inc.) and prints MSIM's policy; sub-advisers named are MSIM
affiliates covered by that policy. Rules are DATED from the earliest SAI/N-CSR read, never an open
default. The Morgan Stanley ETF Trust mixes MSIM-voted series with six Calvert index/bond ETFs that
follow Calvert's own policy (named in the SAI), so it is keyed per series and Calvert stays unlabelled.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
MS = CFG["institutions"]["morgan_stanley"]
PA = CFG["institutions"]["parametric"]
# CIK -> first date MSIM is keyed (effective date of the earliest SAI / filing date of the earliest N-CSR read).
REGISTRANTS = {"741375": "2023-01-27", "836487": "2023-04-28", "1011378": "2023-04-28",
               "860720": "2023-02-28", "1002427": "2023-04-28",
               "1368493": "2023-03-10", "916618": "2023-03-10"}
ETF = "1676326"
# Calvert fund registrants added 2026-11-21 (keyed CALVERT, see tests/test_morgan_stanley_sweep.py)
CALVERT_REGISTRANTS = {"356682", "708950", "1121624", "319676", "884110", "1105446", "743773"}
CALVERT_ETFS = {"S000077958", "S000077959", "S000077960", "S000077961", "S000077962", "S000077963"}
# Series of the Morgan Stanley ETF Trust keyed MSIM, each from the effective date of its own earliest SAI read.
ETF_SERIES = {"S000082246": "2023-10-07", "S000082247": "2023-10-07", "S000082248": "2023-10-07",
              "S000082250": "2023-10-07", "S000082252": "2023-10-07",
              "S000083413": "2023-12-16", "S000083416": "2023-12-16", "S000083827": "2024-01-13",
              "S000084183": "2024-03-02", "S000088098": "2024-09-30", "S000088107": "2024-09-30",
              "S000088108": "2024-09-30", "S000101437": "2026-02-18"}


def _entry(cik):
    return next(e for e in MS["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_exactly_the_eight_msim_registrants_plus_calvert_and_no_open_default():
    assert {str(e["cik"]) for e in MS["npx_ciks"]} == set(REGISTRANTS) | {ETF} | CALVERT_REGISTRANTS
    for e in MS["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"]


def test_msim_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "MSIM"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "MSIM"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None


def test_etf_trust_is_keyed_per_series_and_calvert_etfs_stay_unlabelled():
    e = _entry(ETF)
    assert not e.get("adviser_key_history"), "a registrant-level rule would label the Calvert ETFs MSIM"
    rules = engine.normalize_rules(e)
    for sid, first in ETF_SERIES.items():
        assert engine.resolve_key(rules, sid, first) == "MSIM", sid
        assert engine.resolve_key(rules, sid, _day_before(first)) is None, sid
        assert engine.resolve_key(rules, sid, "2026-06-30") == ("MSIM" if first <= "2026-06-30" else None), sid
    for sid in CALVERT_ETFS:
        assert sid not in rules["series"]
        assert engine.resolve_key(rules, sid, "2025-11-15") is None, sid   # follows Calvert's own policy
    assert engine.resolve_key(rules, "S000099999", "2025-11-15") is None   # an unknown series is never keyed


def test_no_eaton_vance_trust_is_registered_here():
    ours = {str(e["cik"]) for e in MS["npx_ciks"]}
    parametric_ciks = {str(e["cik"]) for e in PA["npx_ciks"]}
    assert not ours & parametric_ciks, "a CIK must never be ingested under two institutions"
    for cik in ("745463", "74663", "102818", "779991", "1121746", "1552324"):
        assert cik not in ours


def test_policy_is_one_sai_printed_label_keyed_msim():
    docs = {d["label"]: d for d in MS["commitments"] if d["adviser_key"] == "MSIM"}
    assert len(docs) == 1
    (label, d), = docs.items()
    assert label.endswith("-as-printed-in-sai") and d["adviser_key"] == "MSIM"
    cfg = d["sai_appendix"]
    assert cfg["cik"] == "0000836487" and cfg["start"] and cfg["end"] and cfg["strip_patterns"]
    assert all(s.startswith("APPENDIX A") for s in cfg["start"]), "the section must start at the appendix heading"
    assert cfg["end"] == ["APPENDIX B — DESCRIPTION OF RATINGS"], "never run into the next appendix"


def test_parametric_msim_policy_is_its_own_label_taken_from_the_parametric_sais():
    docs = {d["label"]: d for d in PA["commitments"]}
    msim = [d for d in docs.values() if d["adviser_key"] == "PARAMETRIC_MSIM"]
    assert len(msim) == 1
    d, = msim
    assert d["label"].endswith("-as-printed-in-sai")
    assert d["label"] not in {x["label"] for x in MS["commitments"]}, "never reuse the MSIM-keyed label"
    assert str(d["sai_appendix"]["cik"]).lstrip("0") in {"745463", "74663"}   # a Parametric series' own trust
    assert d["sai_appendix"]["allow_identical_copies"] is True
    assert d["sai_appendix"]["since"] >= "2026-01-01"       # only 2026 SAIs print the MSIM policy there
    # Parametric's own text stays keyed PARAMETRIC
    assert any(x["adviser_key"] == "PARAMETRIC" for x in docs.values())


def _sai(heading, footer, tail="APPENDIX B — DESCRIPTION OF RATINGS Standard & Poor's"):
    """A miniature SAI: table-of-contents mention, the appendix with running page footers, then the ratings appendix."""
    return ("Appendix A -- Morgan Stanley Investment Management Proxy Voting Policy and Procedures A-1 "
            "108 Back to Table of Contents " + heading + " I. POLICY STATEMENT We vote in clients' best interests. "
            + footer.format(n=8) + " II. GUIDELINES Boards. " + footer.format(n=9) + " AIP may follow Section II. "
            + footer.format(n=10) + " " + tail)


def test_policy_extraction_ignores_footers_and_heading_variants():
    from glasshouse.ingest import sai_appendix as sa
    cfg = MS["commitments"][0]["sai_appendix"]
    args = (cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    a = sa.extract_section(_sai("APPENDIX A — MORGAN STANLEY INVESTMENT MANAGEMENT PROXY VOTING POLICY AND PROCEDURES",
                                "A-{n} Back To Table of Contents"), *args)
    b = sa.extract_section(_sai("APPENDIX A MORGAN STANLEY INVESTMENT MANAGEMENT EQUITY PROXY VOTING POLICY AND PROCEDURES",
                                "A-{n} Back to Table of Contents"), *args)
    assert a and b
    assert "Back to" not in a and "A-8" not in a and "Back To" not in a
    assert "Standard & Poor" not in a, "the section stops at the ratings appendix"
    assert "II. GUIDELINES Boards. AIP may follow Section II." in a
    # the policy text itself is the same; only the heading differs, so the two editions differ exactly there
    assert a.split(" I. POLICY STATEMENT ", 1)[1] == b.split(" I. POLICY STATEMENT ", 1)[1]


def test_policy_extraction_refuses_an_ambiguous_filing():
    from glasshouse.ingest import sai_appendix as sa
    cfg = MS["commitments"][0]["sai_appendix"]
    h = "APPENDIX A — MORGAN STANLEY INVESTMENT MANAGEMENT EQUITY PROXY VOTING POLICY AND PROCEDURES"
    two = _sai(h, "A-{n}") + " " + _sai(h, "A-{n}")
    assert sa.extract_section(two, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"]) is None


def test_parametric_msim_extraction_takes_identical_copies_and_ends_at_the_footer():
    from glasshouse.ingest import sai_appendix as sa
    cfg = next(d for d in PA["commitments"] if d["adviser_key"] == "PARAMETRIC_MSIM")["sai_appendix"]
    pol = ("Morgan Stanley Investment Management (“MSIM”) Equity Proxy Voting Policy and Procedures January 2026 "
           "Introduction We vote proxies. G-2 Back to Table of Contents Guidelines. G-9 ")
    two = ("APPENDIX G — ADVISER " + pol + "PARAMETRIC VOLATILITY RISK PREMIUM FUND SAI cover text "
           "APPENDIX C — ADVISER " + pol.replace("G-", "E-") + "PART C - OTHER INFORMATION")
    got = sa.extract_section(two, cfg["start"], cfg["end"], True, False, cfg["strip_patterns"])
    assert got == "Morgan Stanley Investment Management (“MSIM”) Equity Proxy Voting Policy and Procedures January 2026 Introduction We vote proxies. Guidelines."
    assert sa.extract_section(two, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"]) is None
