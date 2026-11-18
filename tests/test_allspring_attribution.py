"""Allspring Global Investments (Allspring Funds Management, LLC, "Allspring Funds Management"; formerly Wells Fargo
Asset Management, sold by Wells Fargo in 2021) fund registrants. NOT the `wells_fargo` institution: Wells Fargo & Company
exited asset management and keeps only its 13-F and enforcement record.

Evidence (accessions in config/institutions.yaml): the Allspring SAIs say "The Board of the Trusts has delegated the
responsibility for voting proxies relating to the Funds' portfolio securities to Allspring Funds Management", which
"utilizes the Allspring Global Investments Proxy Voting Policies and Procedures, included below", and the policy's scope
paragraph names Allspring Funds Trust, Master Trust, Variable Trust and the four closed-end funds. Sub-advisers (Allspring
Global Investments LLC and UK, Galliard, and for the C&B funds Cooke & Bieler) may give input but do not decide: the policy
says the Proxy Governance Committee makes "the final voting decision". Rules are DATED from the EDGAR filing date of the
earliest filing read, never an open default. The policy is archived twice under separate labels: the allspringglobal.com
page (HTML, bounded by a `body` spec) and the text printed in the Allspring Variable Trust SAI.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine
from glasshouse.contradictions import bound_body, identity_text

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
AS = CFG["institutions"]["allspring"]
# CIK -> first date ALLSPRING is keyed (EDGAR filing date of the earliest filing read that says so).
REGISTRANTS = {
    "1081400": "2022-01-25",    # Allspring Funds Trust, 485BPOS 0001081400-22-000037 (U.S. Equity Funds SAI)
    "1087961": "2022-01-25",    # Allspring Master Trust, named in the same SAI's scope paragraph
    "1081402": "2022-04-25",    # Allspring Variable Trust, own SAI 485BPOS 0001081400-22-000339
    "1611331": "2024-12-02",    # Allspring Exchange-Traded Funds Trust, 497 (SAI) 0001081400-24-000733
    "1386067": "2022-01-25",    # Global Dividend Opportunity Fund (named in the SAI scope paragraph)
    "1210123": "2022-01-25",    # Income Opportunities Fund
    "1227073": "2022-01-25",    # Multi-Sector Income Fund
    "1279014": "2022-01-25",    # Utilities and High Income Fund
}
# Left out on purpose: the management company and distributor, the 13-F filers and the non-registrant holding companies.
LEFT_OUT = {"1327354", "1307977", "1075869", "1890906", "1893197"}


def _entry(cik):
    return next(e for e in AS["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert AS.get(k), k
    assert AS["cik"] == "0001890906"          # Allspring Global Investments Holdings, LLC, the 13-F filer
    assert "aum_usd_tr" in AS


def test_wells_fargo_note_points_at_allspring_and_is_not_attached_to_it():
    wf = CFG["institutions"]["wells_fargo"]
    assert not wf.get("npx_ciks") and not wf.get("commitments"), "Wells Fargo & Company exited asset management"
    assert "`allspring`" in wf["notes"]
    text = (Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text()
    assert "`allspring`" in text.split("wells_fargo:")[1].split("fidelity:")[0], "the config comment names the institution id too"


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in AS["npx_ciks"]}
    assert ciks == set(REGISTRANTS)
    assert not ciks & LEFT_OUT
    for e in AS["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_allspring_is_keyed_only_from_the_earliest_filing_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000099999", first) == "ALLSPRING"
        assert engine.resolve_key(rules, "S000099999", "2026-06-30") == "ALLSPRING"
        assert engine.resolve_key(rules, "S000099999", _day_before(first)) is None
    for cik, first in REGISTRANTS.items():
        if cik != "1611331":
            assert first < "2023-07-01", "the evidence must predate the first dated N-PX meeting"


def test_no_series_is_external_because_the_proxy_governance_committee_decides():
    for e in AS["npx_ciks"]:
        assert not e.get("series_adviser"), "no SAI or policy text gives any series' vote to an outside sub-adviser"


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in AS["npx_ciks"]} | {str(AS["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "allspring":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_page_and_one_sai_printed_label_both_keyed_allspring():
    docs = {d["label"]: d for d in AS["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"] == "https://allspringglobal.com/corporate/proxy-voting-policies-and-procedures"
    assert web[0]["former_urls"] == [
        "https://www.allspringglobal.com/legal/proxy-voting-policies-and-procedures/",
        "https://www.allspringglobal.com/legal/proxy-voting-policies-and-procedures.html"]
    assert set(web[0]["body"]) == {"start", "end"}, "an HTML page needs a body bound or navigation mints versions"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "ALLSPRING"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0001081402" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-04-25"
    assert len(cfg["start"]) == 3, "one heading per printed wording (2022-23, 2024, 2025-26)"
    assert cfg["end"] and cfg["strip_patterns"], "page marks 'N Back To Table of Contents' print inside the policy"


# ---- SAI extraction -------------------------------------------------------------------------------------------

def _sai(edition="2022", pages=(81, 83, 85), tail="the final sentence ends here.", toc_line=True):
    """A miniature Variable Trust SAI: contents line, the Fund preface, the policy with page furniture, the next heading."""
    heading = {"2022": "Allspring Global Investments, LLC Proxy Voting Policies and Procedures Allspring Global Investments, LLC (“Allspring”) Stewardship As fiduciaries, we",
               "2024": "Allspring Global Investments Proxy Voting Policies and Procedures Allspring Global Investments (Allspring) Stewardship As fiduciaries, we",
               "2025": "Allspring Global Investments Proxy Voting Policies and Procedures Introduction Allspring Stewardship As a fiduciary, Allspring is committed"}[edition]
    a, b, c = pages
    furn = ((lambda n: f"{n} Back To Table of Contents") if edition == "2022" else
            (lambda n: f"Variable Trust Funds {n} Back to Table of Contents"))
    return (("Proxy Voting Policies and Procedures . . . . 80 Policies and Procedures for Disclosure of Fund Portfolio Holdings . . . 90 " if toc_line else "")
            + "Proxy Voting Policies and Procedures The Trusts have adopted policies. The Board of the Trusts has delegated the "
              "responsibility for voting proxies to Allspring Funds Management. Allspring Funds Management utilizes the "
              f"Allspring Global Investments, LLC Proxy Voting Policies and Procedures, included below, to ensure that. {a - 1} Variable Trust Funds Back To Table of Contents "
            + f"{heading} manage on behalf of our clients. {furn(a)} Voting Procedures The PGC votes. {furn(b)} "
              f"Conflicts are managed. {furn(c)} Allspring will not disclose how {tail} "
              "Policies and Procedures for Disclosure of Fund Portfolio Holdings I. Scope of Policies and Procedures. The following policies govern.")


def _cfg():
    return next(d for d in AS["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


def test_extraction_takes_the_policy_for_each_printed_wording_without_furniture_and_keeps_the_last_sentence():
    for ed in ("2022", "2024", "2025"):
        got = _extract(_sai(ed))
        assert got is not None, ed
        assert got.endswith("how the final sentence ends here."), "the final sentence is not cut by the end marker"
        assert "Back To" not in got and "Back to" not in got and "Table of Contents" not in got
        assert "Variable Trust Funds" not in got and "Disclosure of Fund Portfolio Holdings" not in got
        assert "delegated the responsibility" not in got, "the Fund preface sentence is not the policy heading"


def test_extraction_is_identical_whatever_the_page_numbers():
    for ed in ("2022", "2024", "2025"):
        assert _extract(_sai(ed, pages=(81, 83, 85))) == _extract(_sai(ed, pages=(7, 9, 11))) \
            == _extract(_sai(ed, pages=(112, 114, 116))), ed


def test_extraction_keeps_a_real_wording_change_and_refuses_an_ambiguous_or_unbounded_filing():
    assert _extract(_sai("2022")) != _extract(_sai("2024")) != _extract(_sai("2025"))
    assert _extract(_sai("2025", tail="a different last sentence ends here.")) != _extract(_sai("2025"))
    s = _sai("2025")
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
    assert _extract(_sai().replace("Policies and Procedures for Disclosure of Fund Portfolio Holdings I. Scope",
                                   "Something else entirely")) is None, "no end marker means no section, never the rest of the SAI"
    assert _extract(_sai(toc_line=True)) is not None, "the contents line 'Proxy Voting Policies and Procedures ... 80' is not a heading"


# ---- Website body bound ---------------------------------------------------------------------------------------

def _body():
    return next(d for d in AS["commitments"] if d.get("body"))["body"]


PREFACE = ("Allspring Funds Proxy Voting Policies and Procedures Scope of Policies and Procedures These Policies and "
           "Procedures are used to determine how to vote proxies. (Effective as of December 5, 2024) Allspring Global "
           "Investments Proxy Voting Policies and Procedures Introduction Allspring Stewardship . As a fiduciary, ")
POLICY_TAIL = ("Approved by PGC: 10 February 2026 Effective date: 1 April 2026 1 Where provisions of the 1940 Act apply, Allspring "
               "shall vote accordingly. 4 The term high importance is defined as proxy level 6 or 5, and other reorganizations.")


def _page(nav="Main Menu About Us Insights Careers", footer="Quick links Careers Press Room Contact Us", policy=PREFACE + POLICY_TAIL,
          extra_title=True):
    top = "Proxy Voting Policies and Procedures | Allspring Global Investments Contact Us "
    mid = "Proxy Voting Policies and Procedures " if extra_title else ""
    return f"{top}{nav} skip to main content Select your location {mid}{policy} {footer}"


def test_body_bound_is_the_policy_only_whatever_the_navigation_and_footer():
    spec = _body()
    base = bound_body(_page(), spec)
    assert base is not None and base.startswith("Allspring Funds Proxy Voting Policies and Procedures Scope of Policies")
    assert base.endswith("and other reorganizations."), "the last footnote is kept; the footer marker is not swallowed"
    assert "Quick links" not in base and "Main Menu" not in base
    for footer in ("Quick links Careers", "LinkedIn Instagram YouTube Quick links", "CFA® and Chartered Financial Analyst® are trademarks",
                   "Quick Links Legal Terms of Use"):
        assert identity_text(bound_body(_page(footer=footer), spec)) == identity_text(base), footer
    assert identity_text(bound_body(_page(nav="A completely different menu", extra_title=False), spec)) == identity_text(base)


def test_body_bound_follows_a_real_edit_and_is_unreadable_when_the_markers_miss():
    spec = _body()
    edited = _page(policy=(PREFACE + POLICY_TAIL).replace("6 or 5", "6, 5 or 4"))
    assert identity_text(bound_body(edited, spec)) != identity_text(bound_body(_page(), spec))
    assert bound_body("Some other page about something else.", spec) is None
    # a capture that ends at the policy's own last sentence (no footer at all, as in the 2022 capture) still reads
    assert bound_body(PREFACE + POLICY_TAIL, spec).endswith("and other reorganizations.")
