"""Vanguard sweep: registrants added beyond the brand-named index trusts.

Evidence (accessions in config/institutions.yaml): each Vanguard SAI says Vanguard-advised funds retain the authority to
vote proxies (one unified Vanguard policy until 2026-01-11; VCM or VPM from 2026-01-12, the team named on Vanguard's two
funds lists), while "the Board of each Vanguard fund advised by a manager not affiliated with Vanguard has delegated the
authority to vote proxies ... to its respective advisor(s)". So every kept registrant is keyed PER SERIES from the SAI's
list of who advises which fund; the earliest SAI read (2022 or later) is the `from` date. Series wholly advised by outside
firms are EXTERNAL; series split between Vanguard and an outside firm, or whose arrangement the SAIs do not settle, are
left without a rule (or UNRESOLVED). Registrants that vote nothing, or vote only through outside advisers, are left out.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
V = CFG["institutions"]["vanguard"]

# cik -> (from date, {series: key from 2026-01-12 / EXTERNAL / UNRESOLVED}); a "V:" key means Vanguard-voted:
# VANGUARD from `from` to 2026-01-11, then the named team.
SWEEP = {
    "736054": ("2022-02-25", {"S000002932": "V:VCM"}),
    "923202": ("2022-04-29", {"S000004386": "V:VCM", "S000004383": "V:VCM", "S000004384": "V:VPM",
                              "S000004387": "V:VPM"}),
    "734383": ("2022-05-27", {"S000011322": "V:VPM", "S000002924": "V:VPM", "S000002920": "EXTERNAL",
                              "S000002921": "EXTERNAL", "S000002922": "EXTERNAL", "S000002923": "EXTERNAL",
                              "S000065529": "EXTERNAL"}),
    "105563": ("2022-03-30", {"S000004406": "EXTERNAL", "S000061301": "V:VPM", "S000061302": "V:VPM",
                              "S000061303": "V:VPM", "S000061304": "V:VPM", "S000061305": "V:VPM",
                              "S000061310": "V:VPM"}),
    "1004655": ("2022-02-25", {"S000014011": "V:VPM", "S000043242": "V:VPM", "S000051871": "V:VCM",
                               "S000051872": "V:VCM", "S000004407": "EXTERNAL", "S000004408": "EXTERNAL",
                               "S000004409": "EXTERNAL"}),
    "106444": ("2022-05-31", {"S000059086": "V:VPM"}),
    "932471": ("2022-01-31", {"S000002593": "V:VPM", "S000012432": "V:VPM", "S000066700": "EXTERNAL",
                              "S000002595": "EXTERNAL", "S000002594": "EXTERNAL"}),
    "857490": ("2022-05-02", {"S000004400": "V:VCM", "S000004404": "V:VPM", "S000004392": "V:VPM",
                              "S000004401": "EXTERNAL", "S000004390": "EXTERNAL", "S000004403": "EXTERNAL",
                              "S000004398": "EXTERNAL", "S000004397": "EXTERNAL", "S000004399": "UNRESOLVED",
                              "S000004394": "UNRESOLVED", "S000004402": "UNRESOLVED"}),
    "52848": ("2022-12-21", {
        **dict.fromkeys(("S000004440", "S000004443", "S000004446", "S000004447", "S000004448", "S000004449", "S000004450", "S000004451", "S000004452", "S000004441", "S000004445", "S000063075", "S000019698", "S000019699"), "V:VPM"),
        "S000063074": "V:VCM", "S000004453": "EXTERNAL", "S000059219": "EXTERNAL", "S000059218": "EXTERNAL"}),
}
# series whose own earliest SAI is later than the registrant's
LATER = {("52848", "S000094513"): ("2025-12-19", "V:VCM")}
# series deliberately without a rule: split between Vanguard and an outside firm, or not settled by the SAIs
NO_RULE = {("52848", "S000004444"), ("1004655", "S000074280"), ("1004655", "S000074281"),
           ("1004655", "S000074282"), ("1004655", "S000082943"), ("52848", "S000019700"),
           ("106444", "S000002584")}
LEFT_OUT = {"889519", "107606", "752177", "794105", "34066", "313850", "826473"}
KEYS = {"VANGUARD", "VCM", "VPM", "EXTERNAL", "UNRESOLVED"}


def _entry(cik):
    return next(e for e in V["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _expected_pairs():
    for cik, (frm, series) in SWEEP.items():
        for sid, k in series.items():
            yield cik, sid, frm, k
    for (cik, sid), (frm, k) in LATER.items():
        yield cik, sid, frm, k


def test_registrants_added_and_left_out_are_exact():
    ciks = {str(e["cik"]) for e in V["npx_ciks"]}
    assert set(SWEEP) <= ciks
    assert not ciks & LEFT_OUT


def test_every_added_registrant_has_the_standard_fields():
    for cik in SWEEP:
        e = _entry(cik)
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), cik
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"] and e["adviser"], cik
        assert "<date>" not in str(e)
        engine.validate_rules(engine.normalize_rules(e), cik)


def test_series_keys_after_from_and_none_before():
    for cik, sid, frm, k in _expected_pairs():
        before = "2021-12-31"
        after = "2026-03-01"
        assert _key(cik, sid, before) is None, (cik, sid)
        assert _key(cik, sid, "2022-01-01") is None, (cik, sid)
        if k.startswith("V:"):
            assert _key(cik, sid, after) == k[2:], (cik, sid)
            assert _key(cik, sid, "2026-01-11") == "VANGUARD", (cik, sid)
            assert _key(cik, sid, "2026-01-12") == k[2:], (cik, sid)
            assert _key(cik, sid, frm) == "VANGUARD", (cik, sid)
        else:
            assert _key(cik, sid, after) == k, (cik, sid)
            assert _key(cik, sid, frm) == k, (cik, sid)
        # the day before the SAI that first states the voter is not labelled
        d = frm[:8] + f"{int(frm[8:]) - 1:02d}"
        assert _key(cik, sid, d) is None, (cik, sid, d)


def test_series_with_no_settled_voter_are_unlabelled():
    for cik, sid in NO_RULE:
        assert _key(cik, sid, "2026-03-01") in (None, "UNRESOLVED"), (cik, sid)


def test_unknown_series_and_registrant_default():
    # no registrant is keyed wholesale: an unnamed series must stay unlabelled
    for cik in SWEEP:
        assert not _entry(cik).get("adviser_key"), cik
        assert _key(cik, "S999999999", "2026-03-01") is None, cik


def test_every_rule_uses_a_known_key():
    for cik in SWEEP:
        rules = engine.normalize_rules(_entry(cik))
        assert engine.rule_keys(rules) <= KEYS, cik


def test_left_out_registrants_stay_out_and_are_documented():
    text = "\n".join(V["voting_scope_notes"])
    ciks = {str(e["cik"]) for e in V["npx_ciks"]}
    for c in LEFT_OUT:
        assert c not in ciks
        assert c in text, f"left-out CIK {c} must be named in voting_scope_notes"
