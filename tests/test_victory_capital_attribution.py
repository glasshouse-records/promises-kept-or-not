"""Victory Capital (Victory Capital Management Inc.) fund registrants, including the Pioneer funds acquired from Amundi US.

Evidence (accessions in config/institutions.yaml): every Victory SAI says "The Proxy Voting Policy delegates to the Adviser
the obligation to vote the Funds' proxies" (the Adviser is Victory Capital Management Inc.); the USAA trust (Victory Portfolios
III) and the SAIs that name Park Avenue / SailingStone say the sub-adviser votes its own sleeve, so those series are EXTERNAL.
The Pioneer funds were advised by Amundi Asset Management US, Inc. until 2025-03-31 under its OWN policy: that era is keyed
AMUNDI_US, never VICTORY; the weeks after the 2025-04-01 combination, when no document says whose policy voted, are UNRESOLVED.
Rules are DATED from the EDGAR filing date of the earliest document read.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
V = CFG["institutions"]["victory_capital"]
KEYS = {"VICTORY", "AMUNDI_US", "EXTERNAL", "UNRESOLVED"}
# Victory's own trusts: CIK -> first date VICTORY is keyed (EDGAR filing date of the earliest SAI read).
NATIVE = {
    "802716": "2021-02-25",    # Victory Portfolios, 485BPOS 0001683863-21-001022
    "1547580": "2021-09-28",   # Victory Portfolios II (VictoryShares ETFs), 0001683863-21-005579
    "908695": "2021-02-05",    # Victory Portfolios III (formerly USAA Mutual Funds Trust), 0001683863-21-000546
    "1068663": "2021-04-19",   # Victory Variable Insurance Funds, 0001683863-21-001958
}
# The Pioneer funds' new homes: AMUNDI_US before 2025-04-01, UNRESOLVED until their own first Victory document, then VICTORY.
PIONEER_NEW = {"2042316": "2025-07-25", "2042317": "2026-04-29"}
# Pioneer open-end trusts that kept their own CIK (N-PX 2024, some 2025): AMUNDI_US until 2025-03-31.
PIONEER_TRUSTS = {
    "78713", "1288255", "276776", "869356", "1094521", "863334", "1265389", "1140157", "893660", "1174520", "78758",
    "1051010", "1077452", "1286364", "930709", "908996", "1306349", "1331854", "1341256", "1380192",
}
# Pioneer closed-end funds (one fund per registrant), with the date VICTORY starts (None = never keyed VICTORY).
CLOSED_END = {"1388126": "2025-07-09", "1166258": "2026-06-04", "1305767": None}
# Left out on purpose: the municipal / money-market / interval-fund Pioneer registrants and the institutional-manager N-PX
# of Victory Capital Management and Amundi US (they overlap the fund tables or hold no equity votes).
LEFT_OUT = {"1040188", "1102598", "812195", "1258943", "1223026", "1864290", "1823387", "1616037", "1679751"}


def _entry(cik):
    return next(e for e in V["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert V.get(k), k
    assert V["cik"] == "0001040188"           # Victory Capital Management Inc., the 13-F filer
    assert "aum_usd_tr" in V


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in V["npx_ciks"]}
    assert ciks == set(NATIVE) | set(PIONEER_NEW) | PIONEER_TRUSTS | set(CLOSED_END)
    assert not ciks & LEFT_OUT
    for e in V["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        rules = engine.normalize_rules(e)
        engine.validate_rules(rules, e["cik"])
        for key, _lo, _hi in rules["history"]:
            assert key in KEYS


def test_victory_keyed_only_from_the_earliest_sai_read():
    for cik, first in NATIVE.items():
        assert _key(cik, "S000099999", first) == "VICTORY", cik
        assert _key(cik, "S000099999", "2026-06-30") == "VICTORY", cik
        assert _key(cik, "S000099999", _day_before(first)) is None, cik
        assert first < "2022-07-01", "the evidence must predate the first dated N-PX meeting"


def test_unaffiliated_sub_advised_series_are_external():
    external = {"908695": ["S000012903", "S000012911", "S000012927", "S000012895", "S000012914"],
                "802716": ["S000053568"]}
    for cik, series in external.items():
        for s in series:
            assert _key(cik, s, "2023-09-30") == "EXTERNAL", s
            assert _key(cik, s, "2026-06-30") == "EXTERNAL", s
    assert _key("908695", "S000012897", "2022-12-31") == "EXTERNAL"      # Northern Trust to FY2023
    assert _key("908695", "S000012897", "2024-06-30") == "VICTORY"
    assert _key("908695", "S000012920", "2024-06-30") == "VICTORY"       # Victory Value Fund: no sub-adviser
    assert _key("908695", "S000012920", "2021-02-04") is None


def test_park_avenue_series_are_external_then_unresolved_then_victory():
    for cik, series, last_named, first_clear in (("802716", "S000053572", "2023-12-31", "2025-04-25"),
                                                 ("802716", "S000053576", "2023-12-31", "2025-04-25"),
                                                 ("802716", "S000053575", "2023-12-31", "2025-04-25"),
                                                 ("1068663", "S000053590", "2023-12-31", "2025-04-14")):
        assert _key(cik, series, "2023-06-30") == "EXTERNAL", series
        assert _key(cik, series, last_named) == "EXTERNAL", series
        assert _key(cik, series, "2024-06-30") == "UNRESOLVED", series   # SAI and N-CEN disagree: nothing claimed
        assert _key(cik, series, first_clear) == "VICTORY", series
        assert _key(cik, series, "2026-06-30") == "VICTORY", series


def test_pre_acquisition_pioneer_periods_are_never_victory():
    for cik, first_victory in PIONEER_NEW.items():
        assert _key(cik, "S000089764", "2024-09-30") == "AMUNDI_US", cik
        assert _key(cik, "S000089764", "2025-03-31") == "AMUNDI_US", cik
        # 2025-04-01 Amundi US was combined with Victory Capital; whose policy voted is not documented
        assert _key(cik, "S000089764", "2025-04-01") == "UNRESOLVED", cik
        assert _key(cik, "S000089764", _day_before(first_victory)) == "UNRESOLVED", cik
        assert _key(cik, "S000089764", first_victory) == "VICTORY", cik
    for cik in PIONEER_TRUSTS:
        assert _key(cik, "S000000001", "2024-03-31") == "AMUNDI_US", cik
        assert _key(cik, "S000000001", "2025-03-31") == "AMUNDI_US", cik
        later = _key(cik, "S000000001", "2025-05-15")
        assert later in (None, "UNRESOLVED"), cik
        assert later != "VICTORY", cik


def test_pioneer_closed_end_funds_follow_the_fund_own_filings():
    for cik, victory_from in CLOSED_END.items():
        assert _key(cik, "", "2024-03-31") == "AMUNDI_US", cik
        assert _key(cik, "", "2025-03-31") == "AMUNDI_US", cik
        assert _key(cik, "", "2025-04-01") == "UNRESOLVED", cik
        if victory_from:
            assert _key(cik, "", _day_before(victory_from)) == "UNRESOLVED", cik
            assert _key(cik, "", victory_from) == "VICTORY", cik
        else:
            assert _key(cik, "", "2026-06-30") == "UNRESOLVED", cik


def test_amundi_us_is_a_pre_acquisition_key_everywhere():
    for e in V["npx_ciks"]:
        for k, _lo, hi in engine.normalize_rules(e)["history"]:
            if k == "AMUNDI_US":
                assert hi and hi <= "2025-03-31", e["cik"]
        for rules in engine.normalize_rules(e)["series"].values():
            for k, _lo, _hi in rules:
                assert k != "AMUNDI_US", "series rules carry only sub-adviser exceptions"


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in V["npx_ciks"]} | {str(V["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "victory_capital":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_ended_registrants_declare_their_last_season():
    for e in V["npx_ciks"]:
        if str(e["cik"]) in PIONEER_TRUSTS:
            assert e["npx_ended"]["last_period"] in ("2024-06-30", "2025-06-30"), e["cik"]
            assert e["npx_ended"]["source"].startswith("https://www.sec.gov/"), e["cik"]


def test_policy_labels_are_keyed_and_sai_labels_are_separate_from_the_website_memo():
    docs = {d["label"]: d for d in V["commitments"]}
    sai = [d for d in docs.values() if "sai_appendix" in d]
    web = [d for d in docs.values() if "sai_appendix" not in d]
    assert len(web) == 1 and web[0]["adviser_key"] == "VICTORY"
    assert web[0]["url"].startswith("https://vcm.com/assets/policies/") and web[0]["url"].endswith(".pdf")
    assert "body" not in web[0], "a PDF needs no body bound"
    assert {d["adviser_key"] for d in sai} == {"VICTORY", "AMUNDI_US"}
    for d in sai:
        cfg = d["sai_appendix"]
        assert cfg["cik"].isdigit() and cfg["forms"] and cfg["since"] <= "2025-07-09"
        assert d["label"].endswith("-as-printed-in-sai") or d["label"].endswith("-as-printed-in-n-csr")
        assert cfg["start"] and cfg["end"]
    labels = [d["label"] for d in docs.values()]
    assert len(labels) == len(set(labels))


# ---- SAI / N-CSR extraction -----------------------------------------------------------------------------------

def _cfg(label):
    return next(d for d in V["commitments"] if d["label"] == label)["sai_appendix"]


def _extract(label, text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg(label)
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg.get("strip_patterns"),
                              bool(cfg.get("page_sequence")))


POLICY = "The Adviser votes proxies in the best interests of the Funds and their shareholders. " * 4


def test_victory_sai_section_runs_from_the_1940_act_paragraph_to_the_next_heading_and_skips_the_contents_list():
    label = "victory-proxy-voting-policy-as-printed-in-sai"
    doc = ("CODE OF ETHICS 54 PROXY VOTING POLICIES AND PROCEDURES 56 PORTFOLIO TRANSACTIONS AND BROKERAGE 58 body "
           "PROXY VOTING POLICIES AND PROCEDURES In accordance with the 1940 Act, the Trust has adopted policies and "
           f"procedures for voting proxies related to equity securities held by the Funds. {POLICY} "
           "Page 49 is a page number: 49 The Adviser. Calling 800-539-FUND (800-539-3863), 800-235-8396 for Member Class, or "
           "available at www.sec.gov. PORTFOLIO TRANSACTIONS AND BROKERAGE Decisions to buy.")
    got = _extract(label, doc)
    assert got is not None and got.startswith("PROXY VOTING POLICIES AND PROCEDURES In accordance")
    assert got.endswith("available at www.sec.gov.") and "Decisions to buy" not in got and "CODE OF ETHICS" not in got
    # a multi-trust SAI prints the heading several times: nothing is taken, never a guess
    assert _extract(label, doc + " " + doc) is None
    # page numbers (44-64) and the Member Class phone clause are furniture, June 30 is not
    assert " 49 The Adviser" not in got and "Member Class" not in got
    assert "(800-539-3863) or available" in got
    # a single-fund SAI ("held by the Fund") prints an older summary: not read (2026-11-19)
    assert _extract(label, doc.replace("held by the Funds", "held by the Fund")) is None


def test_h12_section_in_the_n_csr_stops_before_the_portfolio_manager_item():
    label = "victory-h-12-proxy-voting-policy-as-printed-in-n-csr"
    doc = (f"ITEM 7. Disclosure ... H-12 PROXY VOTING BACKGROUND AND RISKS Voting rights ... {POLICY}H-12 Proxy Voting Policy "
           "Applicability: Victory Capital Management Inc. ITEM 13. PORTFOLIO MANAGERS OF CLOSED-END MANAGEMENT INVESTMENT COMPANIES. (a) names.")
    got = _extract(label, doc)
    assert got is not None and got.startswith("H-12 PROXY VOTING BACKGROUND AND RISKS")
    assert got.endswith("Victory Capital Management Inc.") and "ITEM 13" not in got
    assert _extract(label, doc.replace("ITEM 13. PORTFOLIO MANAGERS OF CLOSED-END", "ITEM 99. OTHER")) is None


def test_amundi_policy_drops_page_furniture_and_the_sai_document_code_but_keeps_the_last_sentence():
    label = "amundi-us-proxy-voting-policy-as-printed-in-sai"
    head = "20. Appendix B — Proxy voting policies and procedures Policy Each of the Pioneer Funds and certain other clients"
    end = "Revision Dates: September 2009, December 2015, August 2017, February 2019, and January 2021"
    body = " ".join(f"Amundi US votes rule {n}. {POLICY}" for n in range(10))

    def printing(first_page, code, toc):
        pages = []
        for n, chunk in enumerate(body.split("rule ")[1:]):
            pages.append(f"rule {chunk.strip()} {first_page + n}{' Table of Contents' if toc else ''}")
        return f"intro {head} of Amundi US have delegated. {' '.join(pages)} {end} {code} PART C - OTHER INFORMATION Item 28."
    a = printing(75, "22123-14-0521 86", True)
    b = printing(86, "32363-01-1221 87", False)
    got_a, got_b = _extract(label, a), _extract(label, b)
    assert got_a is not None and got_a.endswith("January 2021")
    assert got_a == got_b, "page numbers, contents links and the SAI's document code must not split one edition into two versions"
    assert "PART C" not in got_a and "Table of Contents" not in got_a
