"""ProShares (ProShare Advisors LLC) and ProFunds (ProFund Advisors LLC): two trusts, one joint written policy.

Every SAI read (2021-2026) says the Board delegated voting to the trust's adviser and attaches ONE document,
'Proxy Voting Policies and Procedures FOR: ProShare Advisors LLC, ProFund Advisors LLC ... (collectively, the
"Advisor")', so both trusts share the key PROSHARES (a policy is one document, not one key per legal entity).
ISS maintains the Guidelines the policy follows, but the policy text is the advisers' own, so it is not an ISS key.
No SAI names a sub-adviser that votes or an addendum, so there are no series rules."""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
P = CFG["institutions"]["proshares"]
BY_CIK = {e["cik"]: e for e in P["npx_ciks"]}


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(BY_CIK[cik]), series, day)


def test_the_two_vote_filing_trusts_are_configured_and_nothing_else():
    assert set(BY_CIK) == {"1174610", "1039803"}   # ProShares Trust, ProFunds (Trust II/III and Access One file no ingestible votes)


def test_both_trusts_resolve_to_proshares_from_their_earliest_2021_sai():
    assert _key("1174610", "S000011111", "2021-01-15") == "PROSHARES"
    assert _key("1039803", "S000022222", "2021-04-21") == "PROSHARES"
    assert _key("1174610", "S000011111", "2025-06-30") == "PROSHARES"
    assert _key("1039803", "S000022222", "2025-06-30") == "PROSHARES"


def test_before_the_earliest_sai_read_stays_unlabelled():
    assert _key("1174610", "S000011111", "2020-12-31") is None
    assert _key("1039803", "S000022222", "2021-04-20") is None


def test_no_series_rule_and_no_iss_key_pretending_otherwise():
    for e in P["npx_ciks"]:
        assert not e.get("series_adviser")
        assert {h["key"] for h in e["adviser_key_history"]} == {"PROSHARES"}
