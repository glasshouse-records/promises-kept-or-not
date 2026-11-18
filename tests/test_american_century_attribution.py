"""American Century Investments (American Century Investment Management, Inc., ACIM) fund registrants:
ACIM votes every series.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "The advisor is responsible for
exercising the voting rights associated with the securities purchased and/or held by the funds" (the two
trusts that print a board statement of principles say the funds "have delegated to the advisor the
responsibility for exercising such rights"), and prints ACIM's proxy voting policies as an appendix. The
two sub-advised series (Nomura Corporate Research and Asset Management Inc. for the High Income Fund and the
Select High Yield ETF) are named as investment sub-advisers only, the delegation to ACIM carries no
carve-out; the Avantis ETFs and funds are ACIM products (Avantis Investors is an ACIM business unit) under the
same policy. Rules are DATED from the EDGAR filing date of the earliest SAI read, never an open default.
The policy is archived twice, under separate labels: the americancentury.com page and the text printed in
the Mutual Funds SAI appendix.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
AC = CFG["institutions"]["american_century"]
# CIK -> first date AMERICAN_CENTURY is keyed (EDGAR filing date of the earliest 485BPOS/SAI read; the ETF
# Trust is keyed from the full American Century ETFs SAI, the earlier Avantis-only SAI is 2022-03-07).
REGISTRANTS = {
    "100334": "2022-02-28", "908186": "2022-02-28", "1710607": "2022-12-29", "1353176": "2022-11-28",
    "827060": "2022-05-04", "924211": "2022-11-28", "814680": "2022-04-14", "872825": "2022-03-30",
    "908406": "2022-05-18",
}
# Left out on purpose: trusts whose N-PX hold only investment-company ballots (the fund-of-funds Asset
# Allocation Portfolios, the Government Income, Municipal, California Tax-Free, International Bond and
# Target Maturities trusts) or no vote table (Variable Portfolios II); plus the institutional-manager
# filers (American Century Companies 748054 files a separate-account voting report, 52388 a notice).
LEFT_OUT = {"1293210", "773674", "880268", "746458", "717316", "757928", "1124155", "748054", "52388"}


def _entry(cik):
    return next(e for e in AC["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    from datetime import date, timedelta
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert AC.get(k), k
    assert AC["cik"] == "0000748054"          # American Century Companies Inc, the 13-F filer
    assert "aum_usd_tr" in AC


def test_exactly_the_registrants_and_no_open_default():
    assert {str(e["cik"]) for e in AC["npx_ciks"]} == set(REGISTRANTS)
    assert not {str(e["cik"]) for e in AC["npx_ciks"]} & LEFT_OUT
    for e in AC["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        assert not e.get("series_adviser"), "no series is voted by an outside adviser"


def test_american_century_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "AMERICAN_CENTURY"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "AMERICAN_CENTURY"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in AC["npx_ciks"]} | {str(AC["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "american_century":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_copy_and_one_sai_printed_label_both_keyed_american_century():
    docs = {d["label"]: d for d in AC["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://www.americancentury.com/")
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "AMERICAN_CENTURY"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000100334" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-02-28"
    assert all("Proxy Voting Policies American Century Investment Management, Inc." in s for s in cfg["start"])
    assert cfg["end"], "never run into the SAI back cover"
    assert cfg["strip_patterns"]


def _sai(who="Advisor", notes="Notes ", page="E-6"):
    """A miniature Mutual Funds SAI: the table of contents line, the appendix, the back cover, Part C."""
    return ("Appendix D – Explanation of Fixed-Income Securities Ratings D-1 Appendix E – Proxy Voting Policies E-1 "
            "The Funds’ History American Century Mutual Funds, Inc. is a registered company. "
            f"D-4 Appendix E – Proxy Voting Policies American Century Investment Management, Inc. (the “{who}”) is the "
            f"investment manager. E-1 The {who} will vote proxies. E-2 Electronic records will be kept of all votes made. "
            f"{page} {notes}American Century Investments americancentury.com Retail Investors P.O. Box 419200 "
            "Investment Company Act File No. 811-00816 CL-SAI-91794 2203 AMERICAN CENTURY MUTUAL FUNDS, INC. "
            "PART C OTHER INFORMATION Item 28 Exhibits")


def _cfg():
    return next(d for d in AC["commitments"] if "sai_appendix" in d)["sai_appendix"]


def test_extraction_takes_the_appendix_and_not_the_contents_line_or_back_cover():
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    got = sa.extract_section(_sai(), cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    assert got == ("Appendix E – Proxy Voting Policies American Century Investment Management, Inc. (the “Advisor”) "
                   "is the investment manager. The Advisor will vote proxies. Electronic records will be kept of all votes made.")
    assert "E-1" not in got and "Notes" not in got and "P.O. Box" not in got and "PART C" not in got


def test_extraction_handles_both_spellings_and_back_cover_variants():
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    new = sa.extract_section(_sai("Adviser", "", "E-7"), cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    assert new and "(the “Adviser”)" in new and new.endswith("votes made.")


def test_extraction_is_identical_whatever_the_page_numbers():
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    a = sa.extract_section(_sai(page="E-6"), cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    b = sa.extract_section(_sai(page="E-7"), cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])
    assert a == b


def test_extraction_refuses_an_ambiguous_filing():
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    s = _sai()
    assert sa.extract_section(s + " " + s, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"]) is None
