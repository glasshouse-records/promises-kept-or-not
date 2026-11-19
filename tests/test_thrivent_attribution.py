"""Thrivent (Thrivent Asset Management, LLC; Thrivent Financial for Lutherans) fund registrants.

Evidence (accessions in config/institutions.yaml): every Thrivent SAI says "The Board has delegated to [Thrivent] ... the
responsibility for voting any proxies"; the 2021-2022 Thrivent Series Fund SAIs and the Thrivent Mutual Funds SAIs to
2023-02-28 add that the Adviser may delegate to a subadviser, which then votes under its OWN policy (Goldman Sachs Asset
Management, Aberdeen, BlackRock print theirs in Appendix A): those series are EXTERNAL while the SAI and the Form N-CEN
name the subadviser. Rules are DATED from the EDGAR filing date of the earliest SAI read.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
T = CFG["institutions"]["thrivent"]
KEYS = {"THRIVENT", "EXTERNAL", "UNRESOLVED"}
# CIK -> first date THRIVENT is keyed (EDGAR filing date of the earliest SAI read).
FIRST = {
    "790166": "2021-04-30",     # Thrivent Series Fund, 485BPOS 0001193125-21-141000
    "811869": "2021-02-26",     # Thrivent Mutual Funds, 485BPOS 0001193125-21-057328
    "1669626": "2021-02-26",    # Thrivent Core Funds, 485BPOS 0001193125-21-057514
    "1896670": "2022-10-03",    # Thrivent ETF Trust, 497 0001193125-22-256574 (the first prospectus + SAI after effectiveness)
}
# Left out on purpose: no operating-company vote table (notice-only or no votable positions) or an overlapping filer.
LEFT_OUT = {"314984", "1300087", "1721413"}


def _entry(cik):
    return next(e for e in T["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert T.get(k), k
    assert T["cik"] == "0000314984"       # Thrivent Financial for Lutherans, the 13-F filer
    assert "aum_usd_tr" in T


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in T["npx_ciks"]}
    assert ciks == set(FIRST)
    assert not ciks & LEFT_OUT
    for e in T["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]
        rules = engine.normalize_rules(e)
        engine.validate_rules(rules, e["cik"])
        for key, _lo, _hi in rules["history"]:
            assert key in KEYS
        for lst in rules["series"].values():
            for key, _lo, _hi in lst:
                assert key in KEYS


def test_thrivent_keyed_only_from_the_earliest_sai_read():
    for cik, first in FIRST.items():
        assert _key(cik, "S000099999", first) == "THRIVENT", cik
        assert _key(cik, "S000099999", "2026-06-30") == "THRIVENT", cik
        assert _key(cik, "S000099999", _day_before(first)) is None, cik


def test_subadvised_series_are_external_only_while_the_sai_and_n_cen_name_the_subadviser():
    # Thrivent Series Fund: International Allocation (Goldman Sachs), Partner Emerging Markets Equity (Aberdeen),
    # Partner Healthcare (BlackRock): named by the SAI of 2022-04-29 and the N-CEN of FY2022, not by the SAI of 2023-04-28.
    for s in ("S000021859", "S000021862", "S000021867"):
        assert _key("790166", s, "2021-04-30") == "EXTERNAL", s
        assert _key("790166", s, "2022-12-31") == "EXTERNAL", s
        assert _key("790166", s, "2023-01-01") == "UNRESOLVED", s      # N-CEN is silent, the SAI still names it
        assert _key("790166", s, "2023-04-27") == "UNRESOLVED", s
        assert _key("790166", s, "2023-04-28") == "THRIVENT", s
        assert _key("790166", s, "2026-06-30") == "THRIVENT", s
        assert _key("790166", s, "2021-04-29") is None, s
    # Thrivent Mutual Funds: International Allocation Fund, GSAM 'until April 30, 2023' (SAI of 2023-02-28)
    assert _key("811869", "S000020867", "2021-02-26") == "EXTERNAL"
    assert _key("811869", "S000020867", "2023-04-30") == "EXTERNAL"
    assert _key("811869", "S000020867", "2023-05-01") == "THRIVENT"
    assert _key("811869", "S000020867", "2021-02-25") is None
    # every other series is the registrant key
    assert _key("790166", "S000001416", "2022-06-30") == "THRIVENT"
    assert _key("811869", "S000000700", "2022-06-30") == "THRIVENT"


def test_no_subadviser_series_in_the_core_funds_and_the_etf_trust():
    for cik in ("1669626", "1896670"):
        assert not engine.normalize_rules(_entry(cik))["series"], cik


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in T["npx_ciks"]} | {str(T["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "thrivent":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_label_is_keyed_and_reads_the_mutual_funds_sai_family_only():
    docs = T["commitments"]
    assert len(docs) == 1
    d = docs[0]
    assert d["adviser_key"] == "THRIVENT" and d["label"].endswith("-as-printed-in-sai")
    cfg = d["sai_appendix"]
    assert cfg["cik"] == "0000811869" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2021-02-26"
    assert cfg["start"] and cfg["end"]


# ---- SAI extraction -----------------------------------------------------------------------------------------------

LABEL = "thrivent-proxy-voting-policy-as-printed-in-sai"
BODY = "Thrivent votes proxies solely in the interests of the client, including Thrivent Funds. " * 3


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = T["commitments"][0]["sai_appendix"]
    return sa.extract_section(text, cfg["start"], cfg["end"], False, bool(cfg.get("strip_page_numbers")),
                              cfg.get("strip_patterns"), bool(cfg.get("page_sequence")))


def test_every_edition_heading_opens_the_section_and_the_next_document_closes_it():
    heads = [
        "Thrivent Financial for Lutherans and Thrivent Asset Management, LLC Proxy Voting Policies and Procedures Summary Responsibility to Vote Proxies Overview .",
        "THRIVENT FINANCIAL FOR LUTHERANS and THRIVENT ASSET MANAGEMENT, LLC PROXY VOTING POLICIES AND PROCEDURES SUMMARY RESPONSIBILITY TO VOTE PROXIES Overview .",
        "Thrivent Financial for Lutherans and Thrivent Asset Management, LLC Proxy Voting Policies and Procedures and Voting Guidelines Summary Introduction Responsibility to Vote Proxies Overview .",
    ]
    for head in heads:
        # a subadviser's policy follows (to 2023) or Part C does (2024 on)
        for tail in ("Policy, Procedures and Guidelines for GSAM Global Proxy Voting 2021 Edition",
                     "12 THRIVENT MUTUAL FUNDS PART C: OTHER INFORMATION Item 28. Exhibits"):
            doc = f"Appendix A 100 {head} {BODY} Copies of Voting Records and Policies are available. {tail} more text."
            got = _extract(doc)
            assert got is not None and got.startswith(head.split(" Overview")[0][:40]), head
            assert got.endswith("available."), (head, tail, got[-40:])
            assert "Item 28" not in got and "GSAM" not in got and "PART C" not in got


def test_bullet_glyphs_are_typesetting_not_wording():
    head = "Thrivent Financial for Lutherans and Thrivent Asset Management, LLC Proxy Voting Policies and Procedures and Voting Guidelines Summary Introduction"
    a = _extract(f"{head} {BODY} ● independence issues ● attendance § one § two THRIVENT MUTUAL FUNDS PART C: OTHER INFORMATION")
    b = _extract(f"{head} {BODY} • independence issues • attendance ◾ one ◾ two THRIVENT MUTUAL FUNDS PART C: OTHER INFORMATION")
    assert a is not None and a == b
    assert "independence issues" in a and "§" not in a
