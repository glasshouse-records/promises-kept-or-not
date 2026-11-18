"""Federated Hermes (Federated Hermes, Inc.; the Federated advisory companies: Federated Equity
Management Company of Pennsylvania, Federated Global Investment Management Corp., Federated Investment
Management Company, Federated MDTA LLC) fund registrants.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "The Board has delegated to the
Adviser authority to vote proxies on the securities held in the Fund's portfolio" and prints the Federated
proxy voting policy under "Voting Proxies On Fund Portfolio Securities". Exception, read from the SAIs
fund by fund: for the series sub-advised by Hermes Investment Management Limited (HIML) the SAI says the
Adviser "has in turn delegated to the Sub-Adviser, the authority to vote proxies" under HIML's own
Corporate Governance and Responsible Investment Guidelines, and the US summary says HIML "maintains its own
voting policy". Those series get a separate key (HERMES_HIML) that is never paired with the Federated policy.
Rules are DATED from the EDGAR filing date of the earliest SAI read, never an open default. The Federated
policy is archived twice under separate labels: the PDF Federated serves (Wayback gives the older edition)
and the text printed in the Federated Hermes Global Allocation Fund SAI.
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
FH = CFG["institutions"]["federated_hermes"]
# CIK -> first date FEDERATED_HERMES is keyed (EDGAR filing date of the earliest SAI read that prints the
# Federated policy for the trust). The Adviser Series (1707560) is keyed per series instead.
REGISTRANTS = {
    "912577": "2022-04-25", "1849998": "2022-06-24", "745968": "2022-01-26", "879569": "2022-01-31",
    "13386": "2022-01-27", "745967": "2022-04-26", "789281": "2022-01-26", "861469": "2022-12-27",
    "1363526": "2022-09-27", "1340579": "2022-01-28", "799704": "2022-01-26", "918199": "2022-01-27",
    "925723": "2022-07-26",
}
ADVISER_SERIES = "1707560"
# Series of the Adviser Series voted by the Federated adviser: series -> first SAI filing date read.
ADVISER_SERIES_FED = {"S000072284": "2022-02-28", "S000066201": "2022-07-27", "S000066202": "2022-07-27",
                      "S000066203": "2022-07-27", "S000070657": "2022-10-25", "S000058355": "2022-12-27"}
# Series voted by Hermes Investment Management Limited (own policy): series -> first SAI filing date read.
ADVISER_SERIES_HIML = {"S000065055": "2022-01-26", "S000068640": "2022-08-25", "S000063461": "2022-12-27"}
# Sustainable High Yield Bond Fund: Federated adviser until the SAI of 2023-05-26, HIML after.
SUSTAINABLE_HY = "225318"
# Left out on purpose: money-market and municipal trusts (N-PX hold only Nuveen / BlackRock fund ballots), notice
# reports with no vote table, the Core Trust (no SAI to read), and the manager-level filers.
LEFT_OUT = {"856517", "866700", "1199004", "353101", "1034106", "771524", "1411674", "357052", "770116",
            "742286", "889388", "201801", "1677615", "357159", "739594", "946868", "912763", "355691",
            "1279012", "1279010", "1086431", "1056508", "1013143", "1056288"}


def _entry(cik):
    return next(e for e in FH["npx_ciks"] if str(e["cik"]) == cik)


def _day_before(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert FH.get(k), k
    assert FH["cik"] == "0001056288"          # Federated Hermes, Inc., the 13-F filer
    assert "aum_usd_tr" in FH


def test_exactly_the_registrants_and_no_open_default():
    ciks = {str(e["cik"]) for e in FH["npx_ciks"]}
    assert ciks == set(REGISTRANTS) | {ADVISER_SERIES, SUSTAINABLE_HY}
    assert not ciks & LEFT_OUT
    for e in FH["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_every_trust_is_keyed_only_from_the_earliest_sai_read():
    for cik, first in REGISTRANTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "FEDERATED_HERMES"
        assert engine.resolve_key(rules, "S000000001", "2026-06-30") == "FEDERATED_HERMES"
        assert engine.resolve_key(rules, "S000000001", _day_before(first)) is None
        assert first < "2023-07-01", "the SAI evidence must predate the first dated N-PX meeting"


def test_adviser_series_is_keyed_per_series_and_hermes_voted_series_never_get_the_federated_key():
    e = _entry(ADVISER_SERIES)
    assert not e.get("adviser_key_history"), "a registrant-wide key would label the HIML-voted series"
    rules = engine.normalize_rules(e)
    for sid, first in ADVISER_SERIES_FED.items():
        assert engine.resolve_key(rules, sid, first) == "FEDERATED_HERMES"
        assert engine.resolve_key(rules, sid, "2026-06-30") == "FEDERATED_HERMES"
        assert engine.resolve_key(rules, sid, _day_before(first)) is None
    for sid, first in ADVISER_SERIES_HIML.items():
        assert engine.resolve_key(rules, sid, first) == "HERMES_HIML"
        assert engine.resolve_key(rules, sid, "2026-06-30") == "HERMES_HIML"
        assert engine.resolve_key(rules, sid, _day_before(first)) is None
    assert engine.resolve_key(rules, "S000099999", "2025-01-01") is None, "an unread series stays unlabelled"


def test_sustainable_high_yield_changes_hands_to_hermes_when_its_sai_says_so():
    rules = engine.normalize_rules(_entry(SUSTAINABLE_HY))
    assert engine.resolve_key(rules, "S000009068", "2022-05-24") == "FEDERATED_HERMES"
    assert engine.resolve_key(rules, "S000009068", "2023-05-25") == "FEDERATED_HERMES"
    assert engine.resolve_key(rules, "S000009068", "2023-05-26") == "HERMES_HIML"
    assert engine.resolve_key(rules, "S000009068", "2026-06-30") == "HERMES_HIML"
    assert engine.resolve_key(rules, "S000009068", "2022-05-23") is None


def test_no_cik_is_registered_under_two_institutions():
    ours = {str(e["cik"]).lstrip("0") for e in FH["npx_ciks"]} | {str(FH["cik"]).lstrip("0")}
    for iid, inst in CFG["institutions"].items():
        if iid == "federated_hermes":
            continue
        theirs = {str(e["cik"]).lstrip("0") for e in inst.get("npx_ciks") or []} | {str(inst.get("cik", "")).lstrip("0")}
        assert not ours & theirs, iid


def test_policy_has_a_website_pdf_and_one_sai_printed_label_both_keyed_federated_hermes():
    docs = {d["label"]: d for d in FH["commitments"]}
    assert len(docs) == 2
    sai = [d for d in docs.values() if d["label"].endswith("-as-printed-in-sai")]
    web = [d for d in docs.values() if not d["label"].endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and len(web) == 1
    assert web[0]["url"].startswith("https://services.federatedinvestors.com/teamsite-file-server/content/")
    assert "body" not in web[0], "the website policy is a PDF, not an HTML page that needs a body bound"
    assert web[0]["adviser_key"] == sai[0]["adviser_key"] == "FEDERATED_HERMES"
    cfg = sai[0]["sai_appendix"]
    assert cfg["cik"] == "0000013386" and cfg["forms"] == ["485BPOS"] and cfg["since"] <= "2022-01-27"
    assert cfg["start"] == ["Proxy Voting Policies As an investment adviser with a fiduciary duty to the Fund and its shareholders"]
    assert cfg["end"] == ["Proxy Voting Report A report on"], "stop before the N-PX availability paragraph, after the policy's last sentence"
    assert cfg["strip_patterns"], "page numbers print inside the policy"
    assert not any(d.get("adviser_key") == "HERMES_HIML" for d in docs.values()), \
        "HIML's own policy is not archived, so nothing may pair with HERMES_HIML"


def _sai(page_a=38, page_b=39, ratio="15%", tail="shall be voted."):
    """A miniature Federated Global Allocation SAI: heading, policy with page numbers, then the report paragraph."""
    return ("Voting Proxies On Fund Portfolio Securities The Board has delegated to the Adviser authority to vote "
            "proxies on the securities held in the Fund’s portfolio. Proxy Voting Policies As an investment adviser "
            "with a fiduciary duty to the Fund and its shareholders, the Adviser’s general policy is to vote in favor "
            f"of management. The Adviser votes (1) against a nominee who sat on 3 boards; (2) for proposals when owners "
            f"of at least {ratio} agree, under Rule 206(4)-6. {page_a} On matters of capital structure the Adviser votes "
            f"case by case. {page_b} The PVOT may seek direction from the Committee on how the proposal {tail} "
            "Proxy Voting Report A report on “Form N-PX” is available at sec.gov . 41 Portfolio Holdings Information")


def _cfg():
    return next(d for d in FH["commitments"] if "sai_appendix" in d)["sai_appendix"]


def _extract(text):
    from glasshouse.ingest import sai_appendix as sa
    cfg = _cfg()
    return sa.extract_section(text, cfg["start"], cfg["end"], False, False, cfg["strip_patterns"])


def test_extraction_takes_the_policy_without_page_numbers_or_the_report_paragraph():
    got = _extract(_sai())
    assert got.startswith("Proxy Voting Policies As an investment adviser with a fiduciary duty")
    assert got.endswith("on how the proposal shall be voted."), "the final sentence is not cut"
    assert "Proxy Voting Report" not in got and "Portfolio Holdings" not in got and "Voting Proxies On" not in got
    assert " 38 " not in got and " 39 " not in got


def test_page_number_removal_keeps_real_numbers():
    got = _extract(_sai())
    for keep in ("(1)", "(2)", "15%", "206(4)-6", "3 boards"):
        assert keep in got, keep


def test_extraction_is_identical_whatever_the_page_numbers():
    assert _extract(_sai(38, 39)) == _extract(_sai(33, 34)) == _extract(_sai(41, 42))


def test_extraction_keeps_a_real_wording_change_and_refuses_an_ambiguous_filing():
    assert _extract(_sai()) != _extract(_sai(ratio="10%"))
    s = _sai()
    assert _extract(s + " " + s) is None, "two copies of the heading in one filing give nothing"
    assert _extract(_sai().replace("Proxy Voting Report A report on", "Report")) is None, \
        "no end marker means no section, never the rest of the SAI"
