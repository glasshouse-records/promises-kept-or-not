"""MFS (Massachusetts Financial Services Company) fund registrants: MFS votes every series.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "MFS votes proxies on
behalf of the Fund pursuant to the proxy voting policies and procedures set forth in APPENDIX E",
and no series names an outside sub-adviser (the two older mentions are a 2018 performance footnote
and a former sub-adviser). The two closed-end bond funds say the same in their N-CSR. Rules are
DATED from the earliest SAI / N-CSR read, never an open default. The policy is archived twice, under
separate labels: the mfs.com PDF and the text printed in the Trust I SAI (the restated Appendix E
supplement each December edition carries).
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
MFS = CFG["institutions"]["mfs"]
# CIK -> first date MFS is keyed (SAI cover date of the earliest SAI read; closed-end: N-CSR filing date).
REGISTRANTS = {
    "798244": "2022-12-29", "798250": "2022-03-30", "225604": "2022-05-31", "63068": "2022-12-29",
    "200489": "2022-01-28", "863032": "2022-02-28", "318874": "2022-11-28", "819673": "2022-02-28",
    "63075": "2022-02-28", "783740": "2022-02-28", "911637": "2022-01-28", "1330967": "2022-08-26",
    "356349": "2022-06-28", "764719": "2022-02-28", "63067": "2022-10-24", "867969": "2022-10-24",
    "918571": "2022-04-29", "719269": "2022-04-29", "1065698": "2022-04-29", "63091": "2022-04-29",
    "63090": "2022-03-30", "2018846": "2025-06-27", "851170": "2023-01-19", "833021": "2023-01-19",
}
# Left out on purpose: municipal trusts and the money-market trust hold no equities, their few votes are
# bond-issuer consents or MFS Series Trust XIV money-market shares.
LEFT_OUT = {"751656", "845606", "847411", "809844", "1392417"}


def _entry(cik):
    return next(e for e in MFS["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert MFS.get(k), k
    assert MFS["cik"] == "0000912938"        # Massachusetts Financial Services Co /MA/, the 13-F filer
    assert "aum_usd_tr" in MFS


def test_exactly_the_registrants_and_no_open_default():
    assert {str(e["cik"]) for e in MFS["npx_ciks"]} == set(REGISTRANTS)
    assert not {str(e["cik"]) for e in MFS["npx_ciks"]} & LEFT_OUT
    for e in MFS["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        assert not e.get("series_adviser"), "no series names an outside voter"


def test_mfs_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "MFS"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "MFS"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in MFS["npx_ciks"]}
    for iid, inst in CFG["institutions"].items():
        if iid == "mfs":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_copy_and_one_sai_printed_label_both_keyed_mfs():
    docs = {d["label"]: d for d in MFS["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://www.mfs.com/") and web[0]["url"].endswith(".pdf")
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "MFS"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000798244" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-12-28"
    assert all("MASSACHUSETTS FINANCIAL SERVICES COMPANY PROXY VOTING POLICIES AND PROCEDURES" in s for s in cfg["start"])
    assert cfg["end"] == ["Statement of Additional Information December"], "never run into the SAI cover"
    assert cfg["strip_patterns"]


def _sai(old, new, code="MULTI-SAI-SUP-I-122925"):
    """A miniature December 485BPOS: a supplement restating Appendix E for next January, the SAI cover, then
    the SAI's own appendix holding the edition in force (a different edition, so the filing has two copies)."""
    head = ("Effective January 1, 2026, the section entitled “APPENDIX E – PROXY VOTING POLICIES AND PROCEDURES” "
            "is restated in its entirety as follows: APPENDIX E - PROXY VOTING POLICIES AND PROCEDURES "
            "MASSACHUSETTS FINANCIAL SERVICES COMPANY PROXY VOTING POLICIES AND PROCEDURES {new} ")
    return (head.format(new=new) + "We vote proxies. " + code + " 8 Guidelines apply. 12 " + code + " 9 "
            "Engagements may consist of ongoing communications with a company. " + code + " 12 "
            "Statement of Additional Information December 29, 2025 Fund Ticker Symbol "
            "APPENDIX E - PROXY VOTING POLICIES AND PROCEDURES MASSACHUSETTS FINANCIAL SERVICES COMPANY "
            "PROXY VOTING POLICIES AND PROCEDURES " + old + " Old text. E - 9 More old text.")


def test_extraction_takes_the_restated_supplement_and_ignores_the_other_edition_and_footers():
    from glasshouse.ingest import sai_appendix as sa
    cfg = next(d for d in MFS["commitments"] if "sai_appendix" in d)["sai_appendix"]
    got = sa.extract_section(_sai("January 1, 2025", "January 1, 2026"), cfg["start"], cfg["end"], False, False,
                             cfg["strip_patterns"])
    assert got == ("MASSACHUSETTS FINANCIAL SERVICES COMPANY PROXY VOTING POLICIES AND PROCEDURES January 1, 2026 "
                   "We vote proxies. Guidelines apply. Engagements may consist of ongoing communications with a company.")
    assert "MULTI-SAI" not in got and "restated" not in got and "Old text" not in got and "E - 9" not in got


def test_extraction_is_identical_whatever_the_footer_code_and_page_numbers():
    from glasshouse.ingest import sai_appendix as sa
    cfg = next(d for d in MFS["commitments"] if "sai_appendix" in d)["sai_appendix"]
    a = sa.extract_section(_sai("January 1, 2025", "January 1, 2026", "MULTI-SAI-SUP-I-122925"),
                           cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    b = sa.extract_section(_sai("January 1, 2024", "January 1, 2026", "MULTI-SAI-SUP-I-122724"),
                           cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    assert a == b, "the footer carries the SAI's own date and must not invent an edition"


def test_extraction_refuses_an_ambiguous_filing():
    from glasshouse.ingest import sai_appendix as sa
    cfg = next(d for d in MFS["commitments"] if "sai_appendix" in d)["sai_appendix"]
    s = _sai("January 1, 2025", "January 1, 2026")
    assert sa.extract_section(s + " " + s, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"]) is None
