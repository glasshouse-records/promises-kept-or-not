"""Nuveen / TIAA trusts: votes follow the Nuveen Proxy Voting Policies.

Evidence (accessions in config/institutions.yaml): each trust's SAI says the Funds'
proxies are voted under the "Nuveen Proxy Voting Policies" attached as an appendix, by
Nuveen Asset Management (Nuveen Investment Trust, II, III; via Nuveen Fund Advisors) or
by Teachers Advisors / TIAA-CREF Investment Management (TIAA-CREF Funds, Life Funds,
CREF). The policy itself says it applies to NAM and TCIM, so one key (NUVEEN) names the
policy; the voting entity per trust is recorded in the config notes. Rules are DATED
(from the earliest SAI read), never an open default. The one exception is a series whose
own SAI says its sub-adviser votes under its own policy (Winslow Capital).
"""
from datetime import date, timedelta
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
NV = CFG["institutions"]["nuveen"]
TRUSTS = {"1013881": "2023-10-31", "1041673": "2023-10-31", "1071336": "2023-12-29",
          "1084380": "2023-03-01", "1068204": "2023-05-01", "777535": "2023-05-01"}


def _entry(cik):
    return next(e for e in NV["npx_ciks"] if str(e["cik"]) == cik)


def test_exactly_the_six_trusts_are_registered_and_none_has_an_open_default():
    assert {str(e["cik"]) for e in NV["npx_ciks"]} == set(TRUSTS)
    for e in NV["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")


def test_nuveen_is_keyed_only_from_the_earliest_sai_read():
    for cik, first in TRUSTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "NUVEEN"
        before = (date.fromisoformat(first) - timedelta(days=1)).isoformat()
        assert engine.resolve_key(rules, "S000000001", before) is None


def test_winslow_series_is_not_paired_with_the_nuveen_policy():
    e = _entry("1041673")
    (sid, rules), = e["series_adviser"].items()
    assert sid.startswith("S") and rules[0]["key"] == "EXTERNAL"
    r = engine.normalize_rules(e)
    assert engine.resolve_key(r, sid, "2025-11-15") == "EXTERNAL"
    assert engine.resolve_key(r, "S000099999", "2025-11-15") == "NUVEEN"


def test_policy_is_one_sai_printed_label_keyed_nuveen():
    docs = NV["commitments"]
    assert len(docs) == 1 and docs[0]["label"].endswith("-as-printed-in-sai")
    assert docs[0]["adviser_key"] == "NUVEEN"
    cfg = docs[0]["sai_appendix"]
    assert cfg["cik"] == "0001013881" and cfg["start"] and cfg["end"] and cfg["strip_patterns"]


def test_scope_notes_say_what_is_not_covered():
    notes = " ".join(NV["voting_scope_notes"])
    for word in ("Winslow", "municipal", "blocked"):
        assert word in notes
