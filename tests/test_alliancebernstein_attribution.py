"""AllianceBernstein (AllianceBernstein L.P., "the Adviser" / "the Manager") fund registrants:
AllianceBernstein votes every series.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "The Funds have adopted the
Adviser's proxy voting policies and procedures" (the Bernstein Fund: "Each Fund has adopted the Manager's
proxy voting policies and procedures", Appendix B) and prints AllianceBernstein's Proxy Voting and
Governance Policy as an appendix; the closed-end Global High Income Fund prints it in Item 7 of its N-CSR.
No SAI names a sub-adviser that votes, so no series is EXTERNAL and the Bernstein Fund (the former Sanford C.
Bernstein Fund) shares the same policy and the same key. Rules are DATED from the EDGAR filing date of the
earliest SAI read, never an open default. The policy is archived twice, under separate labels: the
alliancebernstein.com PDF and the text printed in the AB Large Cap Growth Fund SAI (Appendix A).
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
AB = CFG["institutions"]["alliancebernstein"]
# CIK -> first date ALLIANCEBERNSTEIN is keyed (EDGAR filing date of the earliest SAI, or for the closed-end
# fund the N-CSR with Item 7, read).
REGISTRANTS = {
    "1496608": "2023-02-14", "3794": "2022-01-28", "81443": "2022-03-01", "1090504": "2022-03-01",
    "19614": "2022-10-28", "910036": "2022-03-01", "883676": "2022-01-28", "1018368": "2022-03-01",
    "69752": "2022-03-01", "915845": "2022-01-31", "1018592": "2022-01-28", "889508": "2022-10-28",
    "812015": "2022-10-28", "29292": "2022-03-01", "350181": "2022-10-28", "920701": "2022-10-28",
    "1129870": "2022-03-01", "825316": "2022-04-29", "906013": "2022-06-03", "1653463": "2022-01-28",
}
# Left out on purpose: registrants whose N-PX is a notice report with no vote table (Corporate Shares,
# Fixed Income Shares, Municipal Income Fund II, National Municipal Income Fund, Multi-Manager Alternative
# Fund, Bernstein Fund II), and registrants that stopped filing N-PX before the window.
LEFT_OUT = {"1274676", "862021", "899774", "1162027", "1543188", "1166729", "1002718", "917713", "1308576",
            "1172221", "1109448", "825313"}


def _entry(cik):
    return next(e for e in AB["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert AB.get(k), k
    assert AB["cik"] == "0001109448"          # AllianceBernstein L.P., the 13-F filer
    assert "aum_usd_tr" in AB


def test_exactly_the_registrants_and_no_open_default():
    assert {str(e["cik"]) for e in AB["npx_ciks"]} == set(REGISTRANTS)
    assert not {str(e["cik"]) for e in AB["npx_ciks"]} & LEFT_OUT
    for e in AB["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        assert not e.get("series_adviser"), "no series is voted by an outside adviser"


def test_alliancebernstein_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "ALLIANCEBERNSTEIN"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "ALLIANCEBERNSTEIN"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in AB["npx_ciks"]} | {str(AB["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "alliancebernstein":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_alliancebernstein():
    docs = {d["label"]: d for d in AB["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://www.alliancebernstein.com/") and web[0]["url"].endswith(".pdf")
    assert "body" not in web[0], "the website policy is a PDF, not an HTML page that needs a body bound"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "ALLIANCEBERNSTEIN"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000889508" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-10-28"
    assert cfg["start"] == ["Proxy Voting and Governance Policy Statement Introduction"]
    assert cfg["end"], "never run into Part C of the registration statement"
    assert cfg["strip_patterns"]


def _sai(who="Fund", mission="best financial", pages=(1, 2, 3), tail="electronically."):
    """A miniature AB Large Cap Growth SAI: contents line, Appendix A (page furniture), Part C."""
    a, b, c = pages
    return ("Appendix A: Statement of Policies and Procedures for Proxy Voting A-1 Financial statements 195 "
            f"The {who}s have adopted the Adviser's proxy voting policies. 211 Table of Contents Appendix A "
            "STATEMENT OF POLICIES AND PROCEDURES FOR PROXY VOTING Proxy Voting and Governance Policy Statement "
            f"Introduction AllianceBernstein L.P.’s mission is to work in our clients’ {mission} interests. "
            f"We vote proxies in the interest of clients. A- {a} Table of Contents Our Policy applies to all accounts. "
            f"A- {b} Table of Contents We keep records of every vote. We maintain the vast majority of these records {tail} "
            f"A- {c} PART C OTHER INFORMATION ITEM 28. Exhibits (a) Articles of Incorporation")


def _cfg():
    return next(d for d in AB["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


def test_extraction_takes_the_appendix_without_page_furniture_contents_line_or_part_c():
    got = _extract(_sai())
    assert got.startswith("Proxy Voting and Governance Policy Statement Introduction AllianceBernstein L.P.’s mission")
    assert got.endswith("these records electronically."), "the final sentence is not cut"
    assert "A-" not in got and "Table of Contents" not in got
    assert "PART C" not in got and "Exhibits" not in got and "211" not in got and "STATEMENT OF POLICIES" not in got


def test_extraction_is_identical_whatever_the_page_numbers():
    assert _extract(_sai(pages=(1, 2, 3))) == _extract(_sai(pages=(5, 6, 7))) == _extract(_sai(pages=(12, 13, 14)))


def test_extraction_keeps_a_real_wording_change_and_refuses_an_ambiguous_filing():
    assert _extract(_sai()) != _extract(_sai(mission="best"))
    s = _sai()
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
