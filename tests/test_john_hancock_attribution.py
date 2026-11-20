"""John Hancock (John Hancock Investment Management LLC and its subadvisers) fund registrants.

Evidence (accessions in config/institutions.yaml): every open-end series is sub-advised, and each trust's SAI delegates voting
to the series' subadviser under its own policy, so a registrant has NO single voter: each series is keyed from the trust's Form
N-CEN (Item C.3). Manulife Investment Management affiliates share one policy (MANULIFE_IM); any unaffiliated subadviser makes
the series EXTERNAL; two different voters or a subadviser change inside the window make it UNRESOLVED; the 30 fund-of-funds
series stay unlabelled. Closed-end funds carry a dated registrant-level key. Rules are DATED from the first N-CEN read.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
J = CFG["institutions"]["john_hancock"]
KEYS = {"MANULIFE_IM", "EXTERNAL", "UNRESOLVED"}


def _entry(cik):
    return next(e for e in J["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_registry_entry_has_the_standard_fields():
    for k in ("display_name", "short_name", "cik", "country", "type", "notes"):
        assert J.get(k), k
    assert J["cik"] == "0001230788"
    assert "aum_usd_tr" in J
    assert len(J["npx_ciks"]) == 14


def test_no_registrant_default_on_open_end_trusts():
    for cik in ("1331971", "756913", "1329954", "743861", "45291", "1478482"):
        e = _entry(cik)
        assert not e.get("adviser_key") and not e.get("adviser_key_history"), cik
    for e in J["npx_ciks"]:
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser_verified"] and e["voting_note"]


def test_every_series_rule_uses_a_known_key_and_a_date():
    n = 0
    for e in J["npx_ciks"]:
        for sid, rules in (e.get("series_adviser") or {}).items():
            assert sid.startswith("S0"), sid
            for r in rules:
                n += 1
                assert r["key"] in KEYS, (sid, r)
                assert r.get("from") or r.get("until"), (sid, r)
    assert n > 50


def test_manulife_series_is_keyed_manulife_im():
    assert _key("756913", "S000008219", "2024-10-01") == "MANULIFE_IM"    # 500 Index Trust: Manulife IM (North America)


def test_unaffiliated_subadviser_is_external():
    assert _key("756913", "S000008217", "2024-10-01") == "EXTERNAL"       # Blue Chip Growth Trust: T. Rowe Price


def test_an_unresolved_series_resolves_as_unresolved():
    unresolved = [(e["cik"], sid, r) for e in J["npx_ciks"] for sid, rules in (e.get("series_adviser") or {}).items()
                  for r in rules if r["key"] == "UNRESOLVED"]
    assert unresolved
    cik, sid, r = unresolved[0]
    day = r.get("from") or "2025-01-01"
    assert _key(str(cik), sid, day) == "UNRESOLVED"


def test_meetings_before_the_evidence_stay_unlabelled_and_unknown_series_too():
    assert _key("756913", "S000008219", "2020-06-01") is None
    assert _key("756913", "S000000000", "2024-10-01") is None


def test_closed_end_funds_are_keyed_from_their_first_ncsr():
    assert _key("925683", "", "2024-06-30") == "MANULIFE_IM"
    assert _key("925683", "", "2020-06-30") is None
    assert _key("1496749", "", "2024-06-30") == "EXTERNAL"


def test_manulife_policy_label_is_wayback_only_and_no_unverified_sai_label():
    labels = {d["label"]: d for d in J["commitments"]}
    assert set(labels) == {"manulife-im-global-proxy-voting-policy-and-procedures"}
    d = labels["manulife-im-global-proxy-voting-policy-and-procedures"]
    assert d["adviser_key"] == "MANULIFE_IM" and d["access"]["status"] == "blocked"
