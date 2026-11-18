"""Janus Henderson Investors (Janus Henderson Investors US LLC, the Adviser) fund registrants:
the Adviser votes every series.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "The Trustees of the Trust have
delegated to the Adviser the authority to vote all proxies relating to such Fund's portfolio securities in
accordance with the Adviser's own policies and procedures". Until April 2022 (Janus Investment Fund: the
Intech Managed Volatility funds, Intech's sub-advisory agreements were terminated 2022-04-05) and until 2023
(Janus Aspen Series: Janus Henderson U.S. Low Volatility Portfolio) an outside-but-affiliated sub-adviser,
Intech, voted under its own policy; the rules are therefore DATED from the first SAI after that, never an open
default. Kapstream and the other Janus Henderson affiliates work under personnel-sharing arrangements and do
not vote. The policy is archived twice, under separate labels: the janushenderson.com PDF and the text printed
as Appendix B of the Janus Investment Fund SAI.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
JH = CFG["institutions"]["janus_henderson"]
# CIK -> first date JANUS_HENDERSON is keyed (EDGAR filing date of the first SAI read in which the Adviser
# alone votes every series of the trust).
REGISTRANTS = {"277751": "2022-10-28", "906185": "2023-04-28", "1500604": "2022-02-28"}
# Left out on purpose: Clayton Street Trust (Protective Life Dynamic Allocation Series) is a fund of funds whose
# N-PX hold only Vanguard / Franklin ETF ballots; the Janus Henderson Investors US LLC (812295) and Group
# (1274173) filings are institutional-manager reports, and the foreign affiliates file the same.
LEFT_OUT = {"1660765", "812295", "1274173", "2146052", "1280110", "1794678", "1874815", "1810753"}


def _entry(cik):
    return next(e for e in JH["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert JH.get(k), k
    assert JH["cik"] == "0001274173"          # Janus Henderson Group, the 13-F filer (the US LLC files 13F-NT)
    assert "aum_usd_tr" in JH


def test_exactly_the_registrants_and_no_open_default():
    assert {str(e["cik"]) for e in JH["npx_ciks"]} == set(REGISTRANTS)
    assert not {str(e["cik"]) for e in JH["npx_ciks"]} & LEFT_OUT
    for e in JH["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        assert not e.get("series_adviser"), "no series is voted by an outside adviser in the dated window"


def test_janus_henderson_is_keyed_only_from_the_first_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "JANUS_HENDERSON"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "JANUS_HENDERSON"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in JH["npx_ciks"]} | {str(JH["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "janus_henderson":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_janus_henderson():
    docs = {d["label"]: d for d in JH["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://www.janushenderson.com/")
    assert "body" not in web[0], "the website policy is a PDF, not an HTML page that needs a body bound"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "JANUS_HENDERSON"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000277751" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2023-10-27"
    assert cfg["start"] == ["Proxy Voting Policy and Procedures Last Review Date:"]
    assert cfg["end"], "never run into the SAI back cover"
    assert cfg["strip_patterns"]
    assert cfg.get("allow_identical_copies"), "the October filing prints the policy once per SAI"


def _sai(date_="March 2023", pages=(96, 97, 98), note=2, back="This page intentionally left blank. janushenderson.com 151 Detroit Street"):
    """A miniature Janus Investment Fund SAI: contents line, Appendix B (contents list, body, footnote, page numbers)."""
    a, b, c = pages
    return (
        f"Appendix A – explanation of rating categories 95 Appendix B – proxy voting policy and procedures {a - 1} "
        "Classification, investment policies and restrictions. The Trustees of the Trust have delegated to the Adviser "
        "the authority to vote all proxies. Appendix B – proxy voting policy and procedures "
        f"Proxy Voting Policy and Procedures Last Review Date: {date_} {a} Contents 1 Overview {a + 2} 1.1 Policy Statement "
        f"{a + 2} 2 Additional Definitions {a + 3} Proxy Voting Guidelines {a + 7} Proposals Outside the Guidelines {a + 12} "
        f"{a + 1} 1 Overview 1.1 Policy Statement Where Janus Henderson Investors has been provided voting discretion, it will vote. "
        "1.2 Key Principles • Janus Henderson Investors will vote proxies in the best interest of each client. "
        f"2 Additional Definitions Proxy Voting Service refers to ISS. {note} Janus Henderson Investors US LLC has been designated by the Boards of "
        f"Trustees of Janus Investment Fund to vote proxies for the Proprietary U.S. Funds, as applicable. {b} "
        f"3 Proxy Voting Procedures Votes follow the Guidelines Article 21 FCA COLL {b} CSSF Regulation. "
        f"Proposals Outside the Guidelines Janus Henderson Investors will rely on the Proxy Voting Service. {c} {back} "
        "125-22-02200 10-23 ▼ October 27, 2023 Janus Investment Fund Statement of Additional Information")


def _cfg():
    return next(d for d in JH["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], True, False, cfg["strip_patterns"])


def test_extraction_takes_the_appendix_without_contents_list_footnote_or_page_numbers():
    got = _extract(_sai())
    assert got.startswith("Proxy Voting Policy and Procedures Last Review Date: March 2023 1 Overview 1.1 Policy Statement Where")
    assert got.endswith("will rely on the Proxy Voting Service.")
    assert "Contents" not in got and "designated by the Boards" not in got and "•" not in got
    assert "Article 21 FCA COLL CSSF Regulation" in got, "a real number stays, a page number between is dropped"
    assert "janushenderson.com" not in got and "125-22" not in got and "Detroit" not in got


def test_extraction_is_identical_whatever_the_page_numbers_and_footnote_number():
    a = _extract(_sai(pages=(96, 97, 98), note=2))
    b = _extract(_sai(pages=(133, 134, 135), note=1))
    c = _extract(_sai(pages=(85, 86, 87), note=3, back="janushenderson.com 151 Detroit Street"))
    assert a == b == c


def test_extraction_keeps_the_edition_date_and_refuses_an_ambiguous_filing():
    assert "Last Review Date: February 2025" in _extract(_sai("February 2025"))
    s = _sai()
    assert _extract(s + " " + s) is not None   # identical copies are allowed
    other = _sai(date_="February 2024")
    assert _extract(s + " " + other) is None, "copies that disagree give nothing"
