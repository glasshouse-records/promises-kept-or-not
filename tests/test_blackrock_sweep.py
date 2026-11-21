"""BlackRock registrant sweep (2026-11-21): active and non-index trusts added to the existing `blackrock` block.

Evidence (accessions in config/institutions.yaml): every BlackRock SAI says the Board delegated proxy voting to the
Manager (BlackRock Advisors, LLC for the mutual funds, BlackRock Fund Advisors for the ETF Trust). Until 2024-12-31 one
Open-End Fund Proxy Voting Policy covered every fund (key BIS, the existing block's convention); from 2025-01-01 the
per-fund grid in each SAI marks either the Open-End Active and Fixed Income Index Fund policy (BAIS) or the Index Equity
Fund policy (BIS). `from` is the filing date of the earliest SAI (2022 or later) that was read for that series, so
meetings before it stay unlabelled. These registrants have no registrant-wide default: every series is keyed one by one.

Left out: Master Investment Portfolio (915092), BlackRock Funds III (893818), BlackRock Funds V (1738078).
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
B = CFG["institutions"]["blackrock"]

ACTIVE, INDEX = "A", "I"

# registrant CIK -> {series id: (from = earliest SAI read, policy class in the 2025-26 SAI grid)}
BLACKROCK_FUNDS = {
    "S000001505": ("2022-09-22", ACTIVE), "S000001507": ("2022-01-26", ACTIVE), "S000001509": ("2022-09-21", ACTIVE),
    "S000001510": ("2022-09-21", ACTIVE), "S000001869": ("2022-09-21", ACTIVE), "S000001870": ("2022-08-22", ACTIVE),
    "S000001871": ("2022-09-20", ACTIVE), "S000001877": ("2022-09-22", ACTIVE), "S000001878": ("2022-04-26", ACTIVE),
    "S000008399": ("2022-09-20", ACTIVE), "S000033601": ("2022-09-22", ACTIVE), "S000033603": ("2022-08-23", ACTIVE),
    "S000038448": ("2022-05-26", ACTIVE), "S000039460": ("2022-08-23", ACTIVE), "S000039982": ("2022-09-20", ACTIVE),
    "S000049319": ("2022-11-21", INDEX), "S000050371": ("2022-05-26", INDEX), "S000050372": ("2022-11-22", INDEX),
    "S000050373": ("2022-11-21", INDEX), "S000051092": ("2022-09-21", ACTIVE), "S000063942": ("2022-02-24", ACTIVE),
    "S000069107": ("2022-08-23", ACTIVE), "S000069108": ("2022-08-23", ACTIVE), "S000070274": ("2022-08-25", ACTIVE),
    "S000079513": ("2025-08-25", ACTIVE), "S000080437": ("2025-06-12", ACTIVE), "S000087852": ("2026-05-21", INDEX),
}
ETF_TRUST = {
    "S000064945": ("2022-11-22", ACTIVE), "S000069260": ("2022-11-22", ACTIVE), "S000071281": ("2022-11-22", ACTIVE),
    "S000071282": ("2022-11-22", ACTIVE), "S000074569": ("2022-11-22", ACTIVE), "S000076808": ("2022-08-09", ACTIVE),
    "S000081702": ("2023-09-21", ACTIVE), "S000082317": ("2023-10-19", ACTIVE), "S000083238": ("2024-05-22", ACTIVE),
    "S000084031": ("2024-03-21", ACTIVE), "S000085065": ("2024-06-06", ACTIVE), "S000085067": ("2024-05-28", ACTIVE),
    "S000086268": ("2024-10-16", ACTIVE), "S000086269": ("2024-10-16", ACTIVE), "S000088408": ("2024-11-27", ACTIVE),
    "S000090467": ("2025-02-20", ACTIVE), "S000090468": ("2025-02-20", ACTIVE), "S000092375": ("2025-05-13", ACTIVE),
    "S000093567": ("2025-07-09", ACTIVE), "S000093569": ("2025-07-09", ACTIVE), "S000096437": ("2025-10-29", ACTIVE),
    "S000096907": ("2025-11-10", ACTIVE), "S000101156": ("2026-02-20", ACTIVE), "S000101316": ("2026-02-06", ACTIVE),
}
VARIABLE_SERIES = {
    "S000002874": ("2022-04-21", ACTIVE), "S000002875": ("2022-04-21", INDEX), "S000002876": ("2022-04-21", ACTIVE),
    "S000002877": ("2022-04-21", ACTIVE), "S000002878": ("2022-04-21", ACTIVE), "S000002879": ("2022-04-21", ACTIVE),
    "S000002880": ("2022-04-21", ACTIVE), "S000002881": ("2022-04-21", ACTIVE), "S000002882": ("2022-04-21", ACTIVE),
    "S000002885": ("2022-04-21", ACTIVE), "S000002887": ("2022-04-21", ACTIVE), "S000059909": ("2022-04-21", INDEX),
    "S000059910": ("2022-04-21", INDEX),
}
LARGE_CAP_SERIES = {
    "S000001973": ("2022-01-27", ACTIVE), "S000001975": ("2022-09-23", ACTIVE), "S000018499": ("2022-09-23", ACTIVE),
}
FUNDS_IV = {"S000062369": ("2022-04-25", ACTIVE), "S000062370": ("2022-11-22", ACTIVE)}
SERIES_REGISTRANTS = {"844779": BLACKROCK_FUNDS, "1761055": ETF_TRUST, "355916": VARIABLE_SERIES,
                      "1097077": LARGE_CAP_SERIES, "1738074": FUNDS_IV}
# single-fund registrants: registrant-level history, (from, class)
SINGLE_FUND = {"814507": ("2022-08-22", ACTIVE), "834237": ("2022-08-25", ACTIVE)}
LEFT_OUT = {"915092", "893818", "1738078"}
PRE_EXISTING = {"1100663", "930667", "1524513", "1026144"}
KEYS = {"BIS", "BAIS"}


def _entry(cik):
    return next(e for e in B["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def _day_before(day):
    from datetime import date, timedelta
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _check(cik, series, frm, cls):
    first = "BIS" if (cls == INDEX or frm < "2025-01-01") else "BAIS"
    latest = "BIS" if cls == INDEX else "BAIS"
    assert _key(cik, series, _day_before(frm)) is None, (cik, series, "must stay unlabelled before the first SAI read")
    assert _key(cik, series, frm) == first, (cik, series, frm)
    assert _key(cik, series, "2026-11-01") == latest, (cik, series)
    if frm < "2025-01-01":
        assert _key(cik, series, "2024-12-31") == "BIS", (cik, series)    # single Open-End Fund policy until then
        assert _key(cik, series, "2025-01-01") == latest, (cik, series)    # policy split effective 2025-01-01


def test_exactly_the_old_and_new_registrants_and_no_left_out_trust():
    ciks = {str(e["cik"]) for e in B["npx_ciks"]}
    assert ciks == PRE_EXISTING | set(SERIES_REGISTRANTS) | set(SINGLE_FUND)
    assert not ciks & LEFT_OUT


def test_every_added_registrant_has_the_standard_fields_and_no_default_key():
    for cik in [*SERIES_REGISTRANTS, *SINGLE_FUND]:
        e = _entry(cik)
        assert not e.get("adviser_key"), (cik, "no registrant-wide default: unlisted series must stay unlabelled")
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/")
        assert e["name"] and e["adviser"] and e["adviser_verified"] and e["voting_note"] and e["validated"]
        engine.validate_rules(engine.normalize_rules(e), cik)
        assert "<date>" not in str(e)


def test_every_series_resolves_as_researched():
    for cik, series in SERIES_REGISTRANTS.items():
        rules = _entry(cik)["series_adviser"]
        assert set(rules) == set(series), (cik, set(rules) ^ set(series))
        for sid, (frm, cls) in series.items():
            _check(cik, sid, frm, cls)


def test_single_fund_registrants_use_registrant_level_history():
    for cik, (frm, cls) in SINGLE_FUND.items():
        e = _entry(cik)
        assert not e.get("series_adviser"), cik
        for sid in ("S000000000", ""):
            _check(cik, sid, frm, cls)


def test_every_rule_uses_a_known_key_and_a_date():
    for cik in [*SERIES_REGISTRANTS, *SINGLE_FUND]:
        e = _entry(cik)
        rules = list((e.get("series_adviser") or {}).values()) + [e.get("adviser_key_history") or []]
        for lst in rules:
            for r in lst:
                assert r["key"] in KEYS, (cik, r)
                assert r.get("from"), (cik, r, "an undated start would label meetings before the evidence")


def test_unknown_series_stays_unlabelled():
    for cik in SERIES_REGISTRANTS:
        assert _key(cik, "S000000000", "2026-06-30") is None


def test_the_pre_existing_registrants_are_untouched():
    assert _key("1100663", "S000004272", "2025-06-30") is not None
    assert _entry("1524513")["adviser_key"] == "BAIS"
    assert _entry("1026144")["adviser_key"] == "BIS"


def test_left_out_trusts_are_documented_in_the_block():
    notes = " ".join(B.get("voting_scope_notes", [])) + " " + str(B.get("sweep_left_out", ""))
    for cik in LEFT_OUT:
        assert cik in notes, cik
