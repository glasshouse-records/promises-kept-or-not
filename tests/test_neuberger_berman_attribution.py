"""Neuberger Berman (Neuberger Berman Group LLC; the voting adviser is Neuberger Berman Investment
Advisers LLC, "NBIA") fund registrants.

Evidence (accessions in config/institutions.yaml): every SAI says "The Board has delegated to NBIA the
responsibility to vote proxies related to the securities held in the Funds' portfolios" and prints the NB
Proxy Voting Policies and Procedures as Appendix B; the closed-end funds say the same in Item 7 of their
N-CSR. Exceptions, read series by series: the Absolute Return Multi-Manager Fund (Alternative Funds), whose
SAI says NBIA "has delegated to each Subadviser by contract the responsibility to vote proxies", and the
Greater China Equity Fund (Equity Funds), sub-advised by Green Court, whose own proxy voting policy the SAI
prints (Appendix C). Those series are EXTERNAL. Rules are DATED from the EDGAR filing date of the earliest
SAI (N-CSR for the closed-end funds) read, never an open default. The policy is archived twice, under
separate labels: the nb.com PDF (reached through Wayback, the site answers honest clients with a bot
challenge) and the text printed in the Advisers Management Trust SAI.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
NB = CFG["institutions"]["neuberger_berman"]
# CIK -> first date NEUBERGER_BERMAN is keyed (EDGAR filing date of the earliest SAI, or for the closed-end
# funds the N-CSR with Item 7, read).
REGISTRANTS = {
    "44402": "2022-12-15",      # Equity Funds, 485BPOS 0001206774-22-002878
    "736913": "2022-04-20",     # Advisers Management Trust, 485BPOS 0000898432-22-000287
    "1317474": "2022-02-25",    # Alternative Funds, 485BPOS 0000898432-22-000127
    "1506001": "2022-12-14",    # ETF Trust, 485BPOS 0001206774-22-002804
    "1843181": "2022-01-05",    # Next Generation Connectivity Fund, N-CSR 0000898432-22-000026
    "1562051": "2022-02-04",    # Energy Infrastructure & Income Fund, N-CSR 0000898432-22-000077
    "1487610": "2022-01-05",    # High Yield Strategies Fund, N-CSR 0000898432-22-000023
    "1261166": "2022-01-05",    # Real Estate Securities Income Fund, N-CSR 0000898432-22-000027
    "1818105": "2022-06-06",    # Private Markets Access Fund, N-CSR 0001104659-22-068492
}
# Series voted by an outside sub-adviser: (registrant, series) -> first date read.
EXTERNAL_SERIES = {("1317474", "S000036681"): "2022-02-25",   # Absolute Return Multi-Manager Fund (Subadvisers vote)
                   ("44402", "S000041658"): "2022-12-15"}     # Greater China Equity Fund (Green Court)
# Left out on purpose: notice-report registrants (municipal funds, NB Crossroads / Private Markets funds,
# the NB trust companies and non-US advisers), registrants that stopped filing N-PX before the window, and the
# manager-level filers (NBIA 1230440 files a notice report; Group LLC 1465109 is the 13-F filer).
LEFT_OUT = {"1178839", "1178840", "1178841", "1230440", "1465109", "1669380", "1669384", "1669382", "1715736",
            "1702537", "1716942", "1714708", "1702885", "1742837", "1742838", "1743402", "1887499", "1851515",
            "1851265", "1501376", "1501378", "1501377", "1572914", "1572915", "1572916", "1497372", "1497476",
            "1640762", "1531987", "1944468", "2041175", "1228361", "1276893", "1227699", "1221327", "1187520",
            "1303620"}


def _entry(cik):
    return next(e for e in NB["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert NB.get(k), k
    assert NB["cik"] == "0001465109"          # Neuberger Berman Group LLC, the 13-F filer
    assert "aum_usd_tr" in NB


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in NB["npx_ciks"]}
    assert ciks == set(REGISTRANTS)
    assert not ciks & LEFT_OUT
    for e in NB["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_neuberger_berman_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000099999", first) == "NEUBERGER_BERMAN"
        assert engine.resolve_key(rules, "S000099999", "2026-06-30") == "NEUBERGER_BERMAN"
        assert engine.resolve_key(rules, "S000099999", _day_before(first)) is None
        assert first < "2023-07-01", "the evidence must predate the first dated N-PX meeting"


def test_subadviser_voted_series_are_external_and_never_get_the_nb_key():
    for (cik, sid), first in EXTERNAL_SERIES.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, sid, first) == "EXTERNAL"
        assert engine.resolve_key(rules, sid, "2026-06-30") == "EXTERNAL"
        assert engine.resolve_key(rules, sid, _day_before(first)) is None
        assert engine.resolve_key(rules, "S000099999", "2026-06-30") == "NEUBERGER_BERMAN", \
            "the carve-out is for the named series only"
    # the Long Short Fund is voted by NBIA (its SAI says "the Funds' portfolios", no Subadviser)
    rules = engine.normalize_rules(_entry("1317474"))
    assert engine.resolve_key(rules, "S000035446", "2025-01-01") == "NEUBERGER_BERMAN"


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in NB["npx_ciks"]} | {str(NB["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "neuberger_berman":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_neuberger_berman():
    docs = {d["label"]: d for d in NB["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"] == "https://www.nb.com/handlers/documents.ashx?id=e6b2f962-93ae-48b5-854e-627c89b3ea7f"
    assert len(web[0]["former_urls"]) == 1 and web[0]["former_urls"][0].startswith(web[0]["url"] + "&name="), \
        "the nameless address is walked first so each text keeps its earliest Wayback capture"
    assert "body" not in web[0], "the website policy is a PDF, not an HTML page that needs a body bound"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "NEUBERGER_BERMAN"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000736913" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-04-20"
    assert len(cfg["start"]) == 3, "one heading per printed edition (April 2019, March 2024, February 2025)"
    assert cfg["end"] == ["PART C OTHER INFORMATION"], "never run into Part C of the registration statement"
    assert cfg["strip_patterns"], "page marks B- n print inside the policy"


def _sai(edition="apr2019", pages=(1, 2, 3), tail="break a tie vote.", header_after=0):
    """A miniature AMT SAI: contents line, Appendix A ratings, Appendix B (page furniture), Part C."""
    heading = {"apr2019": "APPENDIX B APRIL 2019 PROXY VOTING POLICIES AND PROCEDURES I. INTRODUCTION AND GENERAL PRINCIPLES",
               "mar2024": "Appendix B March 2024 Proxy Voting Policies and Procedures I. Introduction and General Principles",
               "feb2025": "Appendix B Proxy Voting Policies and Procedures February 2025 I. Introduction and General Principles"}[edition]
    a, b, c = pages
    # the running page header (upper case in 2019, title case later) lands wherever the SAI breaks its pages
    hdr = "PROXY VOTING POLICIES AND PROCEDURES" if edition == "apr2019" else "Proxy Voting Policies and Procedures"
    h = [hdr if header_after == i else "" for i in (1, 2, 3)]
    return ("APPENDIX B - PROXY VOTING POLICY FOR NEUBERGER BERMAN INVESTMENT ADVISERS LLC B-1 INVESTMENT INFORMATION "
            "The Funds vote through NBIA. A- 7 "
            f"{heading} A. Certain subsidiaries of Neuberger Berman Group LLC (“NB”) have been delegated the authority "
            f"to vote proxies. {h[0]} B- {a} II. Responsibility and Oversight NB has designated a Proxy Committee. {h[1]} "
            f"B- {b} The members will be appointed by the Proxy Committee, which may vote by a quorum or {tail} {h[2]} "
            f"B- {c} PART C OTHER INFORMATION Item 28 . Exhibits (a) (1) Restated Certificate of Trust")


def _cfg():
    return next(d for d in NB["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


def test_extraction_takes_the_policy_for_each_printed_edition_without_furniture_or_part_c():
    for ed in ("apr2019", "mar2024", "feb2025"):
        got = _extract(_sai(ed))
        assert got is not None, ed
        assert "Certain subsidiaries of Neuberger Berman Group LLC" in got
        assert got.endswith("or break a tie vote."), "the final sentence is not cut"
        assert "B-" not in got and "PART C" not in got and "Exhibits" not in got
        assert "INVESTMENT INFORMATION" not in got and "A- 7" not in got
    assert _extract(_sai("mar2024")).startswith("Appendix B March 2024 Proxy Voting Policies and Procedures")


def test_extraction_is_identical_whatever_the_page_numbers():
    assert _extract(_sai(pages=(1, 2, 3))) == _extract(_sai(pages=(3, 4, 5))) == _extract(_sai(pages=(12, 13, 14)))


def test_running_page_headers_are_stripped_wherever_the_page_breaks_but_the_heading_is_kept():
    """Observed live: the SAI's page header 'Proxy Voting Policies and Procedures' sits at a different spot in each
    filing, which minted a phantom version for the very same policy text."""
    for ed in ("apr2019", "mar2024", "feb2025"):
        base = _extract(_sai(ed))
        assert base == _extract(_sai(ed, header_after=1)) == _extract(_sai(ed, header_after=2)) == _extract(_sai(ed, header_after=3)), ed
        assert base.count("PROXY VOTING POLICIES AND PROCEDURES") + base.count("Proxy Voting Policies and Procedures") == 1, \
            "only the edition heading keeps the title"


def test_extraction_keeps_a_real_edition_change_and_refuses_an_ambiguous_filing():
    assert _extract(_sai("apr2019")) != _extract(_sai("mar2024")) != _extract(_sai("feb2025"))
    s = _sai("feb2025")
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
    assert _extract(_sai().replace("PART C OTHER INFORMATION", "Exhibits")) is None, \
        "no end marker means no section, never the rest of the SAI"
