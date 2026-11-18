"""Columbia trusts: Columbia Management Investment Advisers (CMIA) votes every series.

Evidence (accessions in config/institutions.yaml): each trust's SAI says "The Funds have
delegated to the Investment Manager the responsibility to vote proxies ..., including Funds
managed by subadvisers", the Investment Manager being CMIA. So each trust carries a
registrant-level, DATED rule (from the earliest SAI read), never an open default. One series,
Columbia Pyrford International Stock Fund, is carved out until the first SAI that no longer
says the Corporate Governance Guidelines "do not apply to Pyrford".
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
COL = CFG["institutions"]["columbia"]
TRUSTS = {"773757": "2023-03-01", "1352280": "2023-03-01", "1097519": "2023-06-01",
          "2110": "2023-05-01", "1551950": "2023-03-01", "1450501": "2023-08-01"}
PYRFORD = "S000074123"


def _entry(cik):
    return next(e for e in COL["npx_ciks"] if str(e["cik"]) == cik)


def test_exactly_the_six_trusts_are_registered_and_none_has_an_open_default():
    assert {str(e["cik"]) for e in COL["npx_ciks"]} == set(TRUSTS)
    for e in COL["npx_ciks"]:
        assert not e.get("adviser_key"), "an undated default would label meetings before the SAI evidence"
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")


def test_cmia_is_keyed_only_from_the_earliest_sai_read():
    for cik, first in TRUSTS.items():
        rules = engine.normalize_rules(_entry(cik))
        assert engine.resolve_key(rules, "S000000001", first) == "CMIA"
        assert engine.resolve_key(rules, "S000000001", "2024-11-15") == "CMIA"
        before = (__import__("datetime").date.fromisoformat(first)
                  - __import__("datetime").timedelta(days=1)).isoformat()
        assert engine.resolve_key(rules, "S000000001", before) is None


def test_pyrford_series_is_carved_out_until_the_exception_is_dropped():
    rules = engine.normalize_rules(_entry("1352280"))
    assert engine.resolve_key(rules, PYRFORD, "2025-11-15") == "EXTERNAL"
    assert engine.resolve_key(rules, PYRFORD, "2026-04-30") == "EXTERNAL"
    assert engine.resolve_key(rules, PYRFORD, "2026-05-01") == "CMIA"
    assert engine.resolve_key(rules, "S000099999", "2025-11-15") == "CMIA"   # other series unaffected
    for cik in set(TRUSTS) - {"1352280"}:
        assert PYRFORD not in engine.normalize_rules(_entry(cik))["series"]


def test_policy_documents_are_keyed_cmia_and_the_sai_copy_is_its_own_label():
    docs = {d["label"]: d for d in COL["commitments"]}
    assert len(docs) == 2
    assert all(d["adviser_key"] == "CMIA" for d in docs.values())
    sai = [d for lab, d in docs.items() if lab.endswith("-as-printed-in-sai")]
    assert len(sai) == 1 and sai[0]["sai_appendix"]["start"] and sai[0]["sai_appendix"]["end"]
    assert sai[0]["sai_appendix"]["strip_patterns"], "page footers carry the SAI date"
    web = [d for lab, d in docs.items() if not lab.endswith("-as-printed-in-sai")]
    assert web[0]["url"].startswith("https://docs.columbiathreadneedle.com/")


def test_scope_notes_say_what_is_not_keyed():
    notes = " ".join(COL["voting_scope_notes"])
    for word in ("Pyrford", "Variable", "Guidelines"):
        assert word in notes
