"""Lord, Abbett & Co. LLC ("Lord Abbett") fund registrants.

Evidence (accessions in config/institutions.yaml): every Lord Abbett SAI says "The Funds have delegated proxy voting
responsibilities to the Funds' investment adviser, Lord Abbett, subject to the [Proxy / ESG and Proxy / Sustainability and
Proxy / Board's] general oversight. Lord Abbett has adopted its own proxy voting policies and procedures for this purpose",
attached as Appendix C. No SAI names an outside sub-adviser that votes its own proxies, so no series is EXTERNAL. Rules are
DATED from the EDGAR filing date of the earliest SAI read, never an open default. The policy is archived twice under separate
labels: the PDF on lordabbett.com (no HTML page is a label: the policy page is a landing page that only links to the PDF) and
the text printed in Appendix C of the Lord Abbett Affiliated Fund SAI.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
LA = CFG["institutions"]["lord_abbett"]
# CIK -> first date LORD_ABBETT is keyed (EDGAR filing date of the earliest SAI read that says so).
REGISTRANTS = {
    "2691": "2021-02-23",      # Lord Abbett Affiliated Fund, 485BPOS 0000930413-21-000386
    "60365": "2021-04-26",     # Bond-Debenture Fund, 0000930413-21-000876
    "276914": "2021-11-22",    # Developing Growth Fund, 0000930413-21-001898
    "716788": "2021-04-26",    # Mid Cap Stock Fund, 0000930413-21-000875
    "829901": "2021-04-26",    # Global Fund, 0000930413-21-000877
    "887194": "2021-03-25",    # Research Fund, 0000930413-21-000637
    "1139819": "2021-06-21",   # Trust I, 0000930413-21-001202
    "855396": "2021-04-08",    # Series Fund, 0000930413-21-000740
    "898031": "2021-02-23",    # Securities Trust, 0000930413-21-000387
    "911507": "2021-03-26",    # Investment Trust, 0000930413-21-000648
}
# Left out on purpose: the manager's own institutional-manager N-PX (say-on-pay of accounts, overlaps the fund tables on
# cusip and meeting), money-market / municipal / interval and closed-end funds that file notice reports only.
LEFT_OUT = {"728100", "311635", "1753712", "1802293", "1855299", "2005563", "2029852", "737800"}


def _entry(cik):
    return next(e for e in LA["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert LA.get(k), k
    assert LA["cik"] == "0000728100"          # Lord, Abbett & Co. LLC, the 13-F filer
    assert "aum_usd_tr" in LA


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in LA["npx_ciks"]}
    assert ciks == set(REGISTRANTS)
    assert not ciks & LEFT_OUT
    for e in LA["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_lord_abbett_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000099999", first) == "LORD_ABBETT"
        assert engine.resolve_key(rules, "S000099999", "2026-06-30") == "LORD_ABBETT"
        assert engine.resolve_key(rules, "S000099999", _day_before(first)) is None
        assert first < "2023-07-01", "the evidence must predate the first dated N-PX meeting"


def test_no_series_is_external_because_no_sai_gives_a_vote_to_an_outside_sub_adviser():
    for e in LA["npx_ciks"]:
        assert not e.get("series_adviser"), "no SAI names a sub-adviser that votes its own proxies"


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in LA["npx_ciks"]} | {str(LA["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "lord_abbett":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_lord_abbett():
    docs = {d["label"]: d for d in LA["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].endswith("/Governance-and-Sustainability/Proxy-Voting-Policy-and-Procedures.pdf")
    assert web[0]["url"].startswith("https://www.lordabbett.com/")
    assert "body" not in web[0], "a PDF needs no body bound; the HTML policy page is a landing page and is not a label"
    assert "https://www.lordabbett.com/content/dam/lordabbett/en/resources/proxyVoting/Proxy_Voting_Policy_and_Procedures.pdf" \
        in web[0]["former_urls"]
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "LORD_ABBETT"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000002691" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2021-02-23"
    assert len(cfg["start"]) == 6, "one heading per printed edition (2020, 2021, 2022, 2024, 2025, 2026)"
    assert cfg["end"] and cfg["strip_patterns"], "running page marks 'Part II C- n' print inside the policy"


# ---- SAI extraction -------------------------------------------------------------------------------------------

def _sai(edition="2021", pages=(4, 5, 6), tail="the final sentence ends here.", toc_line=True):
    """A miniature Affiliated Fund SAI: contents line, the Fund paragraph, Appendix C with page furniture, Appendix D."""
    heading = {"2020": "APPENDIX C PROXY VOTING POLICIES AND PROCEDURES THE LORD ABBETT FAMILY OF FUNDS LORD, ABBETT & CO. LLC 1. Introduction",
               "2021": "APPENDIX C Proxy Voting Policy and Procedures March 2021 Using Our Voice Lord Abbett is guided",
               "2022": "APPENDIX C Sustainable Investing & Proxy Voting Policy November 2022 The information contained herein is",
               "2024": "APPENDIX C Proxy Voting Policy February 2024 The information contained herein is",
               "2025": "APPENDIX C PROXY VOTING POLICY February 2025 APPLIES TO: Lord, Abbett & Co. LLC",
               "2026": "PROXY VOTING POLICY March 2026 APPENDIX C APPLIES TO: Lord, Abbett & Co. LLC"}[edition]
    a, b, c = pages
    return (("APPENDIX B – Fund Portfolio Information Recipients B-1 APPENDIX C – Proxy Voting Policies and Procedures C-1 "
             "APPENDIX D – Description of Corporate Bond Ratings D-1 " if toc_line else "")
            + "Proxy Voting The Funds have delegated proxy voting responsibilities to the Funds’ investment adviser, Lord Abbett. "
              "Lord Abbett has adopted its own proxy voting policies and procedures for this purpose. Part II B- 1 "
            + f"{heading} we vote proxies. {a} Part II C- {a} Conflicts are managed. {b} Part II C- {b} "
              f"The Boards delegated 12 of 13 matters. {c} Part II C-{c} Lord Abbett will not disclose how {tail} "
              f"{c + 1} Part II C- {c + 1} APPENDIX D DESCRIPTION OF CORPORATE BOND RATINGS Moody’s Global Long-Term Rating Scale")


def _cfg():
    return next(d for d in LA["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


def test_extraction_takes_each_printed_edition_without_page_marks_and_keeps_the_last_sentence():
    for ed in ("2020", "2021", "2022", "2024", "2025", "2026"):
        got = _extract(_sai(ed))
        assert got is not None, ed
        assert got.endswith("how the final sentence ends here."), "the final sentence is not cut by the end marker"
        assert "Part II" not in got and "APPENDIX D" not in got
        assert "The Boards delegated 12 of 13 matters." in got, "a real number is not mistaken for a page number"
        assert "have delegated proxy voting responsibilities" not in got, "the Fund paragraph is not the policy heading"


def test_extraction_is_identical_whatever_the_page_numbers():
    for ed in ("2020", "2021", "2022", "2024", "2025", "2026"):
        assert _extract(_sai(ed, pages=(4, 5, 6))) == _extract(_sai(ed, pages=(7, 9, 11))) \
            == _extract(_sai(ed, pages=(12, 14, 16))), ed


def test_extraction_keeps_a_real_wording_change_and_refuses_an_ambiguous_or_unbounded_filing():
    eds = [_extract(_sai(e)) for e in ("2020", "2021", "2022", "2024", "2025", "2026")]
    assert len(set(eds)) == 6
    assert _extract(_sai("2025", tail="a different last sentence ends here.")) != _extract(_sai("2025"))
    s = _sai("2025")
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
    assert _extract(_sai().replace("APPENDIX D DESCRIPTION OF CORPORATE BOND RATINGS", "Something else entirely")) is None, \
        "no end marker means no section, never the rest of the SAI"
    assert _extract(_sai(toc_line=True)) is not None, "the contents line 'APPENDIX C - Proxy Voting ... C-1' is not a heading"
