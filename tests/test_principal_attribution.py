"""Principal (Principal Global Investors, LLC / Principal Asset Management) fund registrants.

Evidence (accessions in config/institutions.yaml): every Principal SAI says "The Board has delegated responsibility for
decisions regarding proxy voting for securities held by each Fund to PGI or to that Fund's Sub-Advisor, as appropriate",
with each policy printed in Appendix C. The registrant default is PRINCIPAL (PGI); a series with an unaffiliated sub-adviser
is EXTERNAL; Spectrum and Origin (affiliates that vote under their OWN printed policy) get their own keys; Principal Real
Estate Investors is covered by the PGI policy. Rules are DATED from the EDGAR filing date of the earliest SAI read.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
P = CFG["institutions"]["principal"]
# CIK -> first date PRINCIPAL is keyed (EDGAR filing date of the earliest SAI read that says so).
KEYED = {
    "898745": "2021-02-24",    # Principal Funds, Inc., 485BPOS 0000898745-21-000179
    "12601": "2021-04-28",     # Principal Variable Contracts Funds, 0000012601-21-000065
    "1572661": "2021-04-26",   # Principal Exchange-Traded Funds, 0001572661-21-000034
}
UNKEYED = {"1756404"}          # Principal Real Asset Fund: ingested, sub-advisers not named
# Left out on purpose: the institutional-manager N-PX of PGI and Principal Real Estate Investors (overlap the fund tables),
# the ALPS-advised Principal Real Estate Income Fund, and private / interval funds with no vote table.
LEFT_OUT = {"769734", "1218333", "1557523", "1046029"}


def _entry(cik):
    return next(e for e in P["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert P.get(k), k
    assert P["cik"] == "0000769734"           # Principal Global Investors, the 13-F filer
    assert "aum_usd_tr" in P


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in P["npx_ciks"]}
    assert ciks == set(KEYED) | UNKEYED
    assert not ciks & LEFT_OUT
    for e in P["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_principal_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in KEYED.items():
        assert _key(cik, "S000099999", first) == "PRINCIPAL"
        assert _key(cik, "S000099999", "2026-06-30") == "PRINCIPAL"
        assert _key(cik, "S000099999", _day_before(first)) is None
        assert first < "2023-07-01", "the evidence must predate the first dated N-PX meeting"
    assert not _entry("1756404").get("adviser_key_history"), "sub-advisers not named: stays unkeyed"
    assert _key("1756404", "S000000000", "2025-06-30") is None


def test_unaffiliated_sub_advised_series_are_external_for_the_whole_window():
    external = {"898745": ["S000007175", "S000007122", "S000023512", "S000007077", "S000007173", "S000007169",
                           "S000007125", "S000006996", "S000006997", "S000024296", "S000028139", "S000033960"],
                "12601": ["S000007682"]}
    for cik, series in external.items():
        for s in series:
            assert _key(cik, s, "2024-06-30") == "EXTERNAL", s
            assert _key(cik, s, "2026-06-30") == "EXTERNAL", s
    # an unlisted series of the same trust keeps the registrant key
    assert _key("898745", "S000007016", "2024-06-30") == "PRINCIPAL"      # LargeCap S&P 500 Index Fund


def test_affiliates_with_their_own_policy_never_carry_the_pgi_key():
    for cik, series in (("898745", "S000041598"), ("898745", "S000007170")):
        assert _key(cik, series, "2024-06-30") == "SPECTRUM"
        assert _key(cik, series, "2023-12-26") == "UNRESOLVED", "before the SAI that names Spectrum nothing is claimed"
    for series in ("S000054767", "S000068805"):
        assert _key("1572661", series, "2024-06-30") == "SPECTRUM"
        assert _key("1572661", series, "2023-10-25") == "UNRESOLVED"
    # Origin: own key while the SAIs name it, then nothing is claimed
    assert _key("898745", "S000047839", "2023-09-01") == "ORIGIN"
    assert _key("898745", "S000047839", "2024-12-26") == "ORIGIN"
    assert _key("898745", "S000047839", "2025-06-30") == "UNRESOLVED"
    assert _key("12601", "S000042784", "2025-06-30") == "UNRESOLVED"       # Spectrum sleeve in a PGI account


def test_real_estate_series_follow_the_pgi_policy_from_the_sai_that_names_the_sub_adviser():
    for cik, s in (("898745", "S000007212"), ("898745", "S000019119"), ("898745", "S000077513"), ("12601", "S000007673")):
        assert _key(cik, s, "2024-06-30") == "PRINCIPAL", s
        assert _key(cik, s, "2021-10-26") == "UNRESOLVED", s
        assert _key(cik, s, "2021-10-27") == "PRINCIPAL", s


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in P["npx_ciks"]} | {str(P["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "principal":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_principal():
    docs = {d["label"]: d for d in P["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://brandassets.principal.com/")
    assert web[0]["url"].endswith("/Policy-on-Proxy-Voting-for-Investment-Advisory-Clients.pdf")
    assert "body" not in web[0], "a PDF needs no body bound"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "PRINCIPAL"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0001572661" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2021-04-26"
    assert len(cfg["start"]) == 6 and len(cfg["end"]) == 3 and cfg["strip_patterns"]


# ---- SAI extraction -------------------------------------------------------------------------------------------

_HEAD = {
    "2021": "PRINCIPAL GLOBAL INVESTORS, LLC Proxy Voting and Class Action Monitoring Rule 206(4)-6 Background The Advisers",
    "2021b": "PRINCIPAL GLOBAL INVESTORS, LLC Principal Real Estate Investors, LLC Proxy Voting and Class Action Monitoring Rule 206(4)-6",
    "2022": "PRINCIPAL GLOBAL INVESTORS, LLC Principal Real Estate Investors, LLC Proxy Voting Policies and Procedures Introduction Principal",
    "2023": "PRINCIPAL GLOBAL INVESTORS, LLC Proxy Voting Policies and Procedures Introduction Principal Global Investors 1",
    "2025": "Principal Global Investors, LLC Proxy Voting Policy Introduction Principal Global Investors, LLC 1 (doing business as Principal Asset Management)",
    "2026": "Principal Asset Management SM Proxy Voting Policies and Procedures February 2026 Introduction Principal Global Investors, LLC",
}
_END = {
    "old": "Principal Global Investors PGI Global Compliance Manual POLICY ON PROXY VOTING SPECTRUM ASSET MANAGEMENT, INC. FOR INVESTMENT ADVISORY CLIENTS",
    "mid": "Principal Global Investors, LLC SPECTRUM ASSET MANAGEMENT, INC. Policy on Proxy Voting For Investment Advisory Clients 2024 GENERAL POLICY",
    "new": "SPECTRUM ASSET MANAGEMENT, INC. Policy on Proxy Voting For Investment Advisory Clients 2024 GENERAL POLICY",
}


def _sai(head, end, footer=True, tail="the final sentence ends here."):
    """A miniature ETF SAI: the delegation paragraph, the PGI policy with page furniture, then the Spectrum policy."""
    foot = " Principal Global Investors PGI Global Compliance Manual " if footer else " "
    return ("Proxy Voting Policies and Procedures The Board has delegated responsibility for decisions regarding proxy voting "
            "to PGI or the Fund's Sub-Advisor. 8. Whether the vote was cast for or against management of the issuer. "
            f"{_HEAD[head]} we vote proxies.{foot}Conflicts are managed.{foot}Committees meet 4 times a year.{foot}"
            f"Records are kept so {tail} {_END[end]} Spectrum receives few proxies.")


def _cfg():
    return next(d for d in P["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


_EDITIONS = (("2021", "old"), ("2021b", "old"), ("2022", "old"), ("2023", "old"), ("2025", "mid"), ("2026", "new"))


def test_extraction_takes_each_printed_edition_without_the_footer_and_stops_before_spectrum():
    for head, end in _EDITIONS:
        got = _extract(_sai(head, end))
        assert got is not None, head
        assert got.endswith("Records are kept so the final sentence ends here."), head
        assert "SPECTRUM" not in got and "PGI Global Compliance Manual" not in got, head
        assert "Committees meet 4 times a year." in got
        assert "has delegated responsibility" not in got, "the Fund paragraph is not the policy heading"


def test_extraction_is_identical_with_or_without_running_footers_and_sees_wording_changes():
    for head, end in _EDITIONS:
        assert _extract(_sai(head, end, footer=True)) == _extract(_sai(head, end, footer=False)), head
    assert len({_extract(_sai(h, e)) for h, e in _EDITIONS}) == 6
    assert _extract(_sai("2025", "mid", tail="a different last sentence ends here.")) != _extract(_sai("2025", "mid"))


def test_extraction_refuses_an_ambiguous_or_unbounded_filing():
    s = _sai("2025", "mid")
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
    assert _extract(_sai("2025", "mid").replace("SPECTRUM ASSET MANAGEMENT, INC.", "Something else")) is None, \
        "no end marker (the 2026-04-20 SAI prints no Spectrum policy) means no section, never the rest of the SAI"
