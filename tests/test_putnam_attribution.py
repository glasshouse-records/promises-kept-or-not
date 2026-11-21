"""Putnam Investments fund registrants, under Franklin Templeton (Franklin Resources acquired Putnam on 2024-01-01).

Evidence (accessions in config/institutions.yaml): from the Putnam Funds SAIs filed from 2023-03-27 (and the Putnam ETF
Trust's from 2021-05-20) "The Trustees of the Putnam Funds have delegated proxy voting authority for the securities
held in the funds' portfolios to Putnam Management and have approved Putnam Management's current proxy voting
guidelines and procedures", printed as Appendix A ("Putnam Investments Proxy Voting Procedures"). The same board's
earlier SAIs (to 2023-02-28) say the Trustees themselves established the guidelines and a Director of Proxy Voting in
the Office of the Trustees directed the votes: that is NOT Putnam Management voting, so those meetings stay unlabelled.
Rules are DATED from the EDGAR filing date of each registrant's earliest SAI that says so, never an open default.
The existing Franklin registrants are keyed FRANKLIN (their SAIs: voting delegated to Franklin Advisers, Inc.), so
nothing in the multi-adviser institution is silently unlabelled.
"""
import re
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
FT = CFG["institutions"]["franklin_templeton"]
# CIK -> first date PUTNAM is keyed (EDGAR filing date of the registrant's earliest SAI whose Part II says the Trustees
# delegated proxy voting to Putnam Management).
PUTNAM = {
    "1005942": "2023-03-27",   # Putnam Funds Trust, 485BPOS 0000928816-23-000404
    "787836": "2023-03-27",    # Putnam High Yield Fund, 0000928816-23-000400
    "822671": "2023-04-28",    # Putnam Variable Trust, 0000928816-23-000541
    "932101": "2023-06-27",    # Putnam Investment Funds, 0000928816-23-001000
    "868648": "2023-10-26",    # Putnam International Equity Fund, 0000928816-23-001494
    "81259": "2023-11-27",     # George Putnam Balanced Fund, 0000928816-23-001596
    "357295": "2023-12-28",    # Putnam Global Health Care Fund, 0000928816-23-001708
    "914209": "2023-12-29",    # Putnam Asset Allocation Funds, 0000928816-23-001727
    "836622": "2024-01-25",    # Putnam Diversified Income Trust, 0000928816-24-000235
    "81247": "2024-02-26",     # Putnam Convertible Securities Fund, 0000928816-24-000349
    "216934": "2024-02-26",    # Putnam Large Cap Value Fund, 0000928816-24-000353
    "81251": "2024-02-26",     # Putnam Focused International Equity Fund, 0000928816-24-000360
    "1845809": "2021-05-20",   # Putnam ETF Trust, 0000928816-21-000572
}
FRANKLIN = {
    "38721": "2021-01-26",     # Franklin Custodian Funds, 485BPOS 0001379491-21-000215
    "1551895": "2021-07-28",   # Franklin ETF Trust, 0001379491-21-003455
}
# Left out on purpose: Putnam's institutional-manager N-PX filers (they overlap the fund tables), the notice-only funds
# (money market, municipal, global income, income), and High Income Securities Fund (renamed from Putnam in 2018,
# no longer Putnam-managed).
LEFT_OUT = {"81273", "81238", "1140334", "794614", "81264", "711402", "81248", "810943"}
SEASON_END = "2026-06-30"


def _entry(cik):
    return next(e for e in FT["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_keeps_franklin_resources_as_the_institution():
    assert FT["cik"] == "0000038777"
    assert "Putnam" in FT["notes"]


def test_exactly_the_franklin_and_putnam_registrants():
    ciks = {str(e["cik"]) for e in FT["npx_ciks"]}
    # the 2026-11-21 sweep registrants are asserted in tests/test_franklin_templeton_sweep.py
    sweep = {"805650", "809707", "825063", "1655589", "872625", "837274", "805664", "225930"}
    assert ciks - sweep == set(PUTNAM) | set(FRANKLIN)
    assert not ciks & LEFT_OUT
    for e in FT["npx_ciks"]:
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_every_registrant_has_a_dated_rule_and_none_an_open_default():
    for e in FT["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e.get("adviser_key_history"), str(e["cik"])


def test_putnam_is_keyed_only_from_each_registrants_earliest_sai_and_never_ended():
    for cik, first in PUTNAM.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000099999", first) == "PUTNAM"
        assert engine.resolve_key(rules, "S000099999", SEASON_END) == "PUTNAM", "no later SAI hands voting to Franklin"
        assert engine.resolve_key(rules, "S000099999", _day_before(first)) is None, cik


def test_existing_franklin_registrants_are_keyed_franklin_from_their_own_sai():
    for cik, first in FRANKLIN.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000099999", first) == "FRANKLIN"
        assert engine.resolve_key(rules, "S000099999", SEASON_END) == "FRANKLIN"
        assert engine.resolve_key(rules, "S000099999", _day_before(first)) is None
        assert first < "2023-07-01", "the evidence must predate the first dated N-PX meeting"


def test_no_series_is_external_because_no_sai_gives_a_vote_to_an_outside_sub_adviser():
    for e in FT["npx_ciks"]:
        assert not e.get("series_adviser"), "no SAI names an outside sub-adviser that votes its own proxies"


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in FT["npx_ciks"]} | {str(FT["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "franklin_templeton":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_voting_notes_name_the_regime_change_and_the_unlabelled_gap():
    notes = " ".join(FT["voting_scope_notes"])
    for needle in ("2023-02-28", "Office of the Trustees", "unlabelled", "PanAgora", "Franklin Advisers"):
        assert needle in notes, needle


# ---- policy documents ---------------------------------------------------------------------------------------

def _docs():
    return {d["label"]: d for d in FT["commitments"]}


def test_policy_labels_are_keyed_and_the_website_pdf_has_no_body_bound():
    docs = _docs()
    franklin = docs["proxy-voting-policies-procedures"]
    assert franklin["adviser_key"] == "FRANKLIN"
    web = docs["putnam-investments-proxy-voting-procedures"]
    assert web["adviser_key"] == "PUTNAM"
    assert web["url"] == "https://www.franklintempleton.com/forms-literature/download/PI-PVG"
    assert "body" not in web, "a PDF needs no body bound"
    assert web["former_urls"] == [
        "https://www.putnam.com/static/pdf/proxy/proxy_voting_procedures_guidelines-f6887a00711c0c4e65cd1526b1ee7830.pdf",
        "https://www.putnam.com/static/pdf/proxy/proxy_voting_procedures_guidelines.pdf"], \
        "the Putnam Funds' own Trustee guidelines at proxy_voting_guidelines.pdf are another document and are not walked"
    sai = docs["putnam-investments-proxy-voting-procedures-as-printed-in-sai"]
    assert sai["adviser_key"] == "PUTNAM"
    assert len(docs) == 3
    for d in docs.values():
        assert d["adviser_key"] in {"FRANKLIN", "PUTNAM"}, "no unlabelled policy in a multi-adviser institution"


def _cfg():
    return _docs()["putnam-investments-proxy-voting-procedures-as-printed-in-sai"]["sai_appendix"]


def test_sai_config_reads_one_annual_registrant_with_page_furniture_stripped():
    cfg = _cfg()
    assert cfg["cik"] == "0000822671" and cfg["forms"] == ["485BPOS"] and cfg["since"] >= "2023-04-01"
    assert cfg["page_sequence"] is True and cfg["allow_identical_copies"] is True
    assert cfg["start"] == ["Putnam Investments Proxy Voting Procedures Introduction and Summary"]
    assert len(cfg["end"]) >= 2 and cfg["strip_patterns"]


def _page(n):
    return f"Page text number {n} says Putnam votes proxies. "


def _sai(offset=144, tail="was made solely on the investment merits and without regard to any other consideration. Name: Proxy Voting Team",
         marks="bare", after="Item 28. Exhibits (a) Agreement"):
    """A miniature Putnam Variable Trust SAI: the Part II paragraph, Appendix A with a page number at every page foot
    (a bare number from 2025, 'Month D, YYYY II- n' before), glyph bullets, signature blanks, then Part C."""
    body = ""
    for i in range(10):
        n = offset + i
        mark = f"{n}" if marks == "bare" else f"June 30, 2023 II- {n}"
        glyph = ["•", "Ø", "o", "◾"][i % 4]
        body += f"{glyph} {_page(i)}Items run to 200 percent, see Section 162(m). {mark} "
    return ("PROXY VOTING GUIDELINES AND PROCEDURES The Trustees of the Putnam Funds have delegated proxy voting authority "
            "for the securities held in the funds’ portfolios to Putnam Management. SECURITIES RATINGS Moody’s ... "
            "Appendix A Putnam Investments Proxy Voting Procedures Introduction and Summary Many of Putnam’s clients "
            f"have delegated. {body}CERTIFICATION The undersigned certifies that a recommendation {tail} ________ {after}")


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    c = _cfg()
    return sa.extract_section(text, c["start"], c["end"], c["allow_identical_copies"], False, c["strip_patterns"],
                              c["page_sequence"])


def test_extraction_keeps_the_last_sentence_and_drops_page_marks_glyphs_and_part_c():
    for marks in ("bare", "dated"):
        got = _extract(_sai(marks=marks))
        assert got is not None, marks
        assert got.startswith("Putnam Investments Proxy Voting Procedures Introduction and Summary")
        assert got.endswith("Name: Proxy Voting Team"), "the final sentence is not cut by the end marker"
        assert "Item 28" not in got and "II-" not in got and "___" not in got
        assert "Items run to 200 percent, see Section 162(m)." in got, "a real number is kept"
        assert "have delegated proxy voting authority" not in got, "the Part II paragraph is not the policy"
    for glyph in "•Ø◾":
        assert f" {glyph} " not in _extract(_sai())


def test_extraction_is_identical_whatever_the_page_numbers_and_the_part_c_heading():
    a = _extract(_sai(offset=144))
    assert a == _extract(_sai(offset=98)) == _extract(_sai(offset=311))
    assert a == _extract(_sai(after="PUTNAM VARIABLE TRUST FORM N-1A PART C OTHER INFORMATION Item 28"))
    assert a == _extract(_sai(marks="dated", offset=144)) == _extract(_sai(marks="dated", offset=98))


def test_extraction_sees_a_real_wording_change_and_refuses_an_unbounded_or_ambiguous_filing():
    assert _extract(_sai(tail="was made on other grounds. Name: Proxy Voting Team")) != _extract(_sai())
    s = _sai()
    assert _extract(s + " " + s.replace("Part", "Part")) is not None, "two identical copies are one section"
    assert _extract(_sai().replace("Item 28. Exhibits", "Something else")) is None, "no end marker, no section"
    assert _extract(_sai().replace("Introduction and Summary", "Introduction")) is None
    assert re.search(r"\bII-", _sai(marks="dated"))
