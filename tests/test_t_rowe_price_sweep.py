"""T. Rowe Price registrants added by the coverage sweep (2026-11-21).

Evidence: the Price SAI (485BPOS) says T. Rowe Price Associates (TRPA) is investment adviser to every Price Fund; sub-advisers
are listed per fund. Only T. Rowe Price Investment Management (TRPIM) is stated to hold the voting ("responsible for effecting
securities transactions and voting policies", SAI of 2022-04-28; the sub-advisory table is unchanged in the 2023-2026 SAIs) and
TRPIM votes under its own policy; Price International / Hong Kong / Japan / Singapore only "trade securities and make
discretionary investment decisions", so those funds vote under the TRPA policy. TRPIM funds among the added registrants: Mid-Cap
Growth, Small-Cap Stock, Small-Cap Value, Equity Funds' Institutional Mid-Cap Equity Growth and Institutional Small-Cap Stock,
Equity Series' Mid-Cap Growth Portfolio. Fund-of-funds series (Equity Series' Moderate Allocation Portfolio) are UNRESOLVED.
"""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
T = CFG["institutions"]["t_rowe_price"]

FROM = "2022-04-28"
# registrant-level keys: cik -> (key, from)
REGISTRANT_KEY = {
    "80257": ("TRPA", FROM),     # Growth Stock
    "927845": ("TRPA", FROM),    # Value
    "887147": ("TRPIM", FROM),   # Mid-Cap Growth (sub-adviser TRPIM)
    "894024": ("TRPA", FROM),    # Dividend Growth
    "1462712": ("TRPA", FROM),   # U.S. Large-Cap Core
    "80248": ("TRPA", FROM),     # New Horizons
    "1012678": ("TRPA", FROM),   # Mid-Cap Value
    "1002624": ("TRPA", FROM),   # Health Sciences
    "1486048": ("TRPA", FROM),   # Real Assets (Price International/HK/Japan/Singapore trade only; TRPA votes)
    "819930": ("TRPA", FROM),    # Science & Technology
    "834798": ("TRPIM", FROM),   # Small-Cap Value (sub-adviser TRPIM)
    "1038469": ("TRPA", FROM),   # Integrated Equity Funds
    "75170": ("TRPIM", FROM),    # Small-Cap Stock (sub-adviser TRPIM)
    "775688": ("TRPA", FROM),    # Equity Income
    "910671": ("TRPA", FROM),    # Communications & Technology
    "858581": ("TRPA", FROM),    # Index Trust
    "313212": ("TRPA", "2023-02-27"),   # International Funds (earliest SAI read)
}
SERIES_KEY = {
    "1012968": {"S000002092": "TRPIM", "S000002093": "TRPA", "S000002094": "TRPIM",
                "S000002095": "TRPA", "S000002096": "TRPA", "S000080479": "TRPA"},
    "918294": {"S000002077": "TRPA", "S000002078": "TRPA", "S000002079": "UNRESOLVED", "S000002080": "TRPIM",
               "S000002081": "TRPA", "S000002082": "TRPA", "S000002083": "TRPA"},
}
LEFT_OUT = {"923084", "808303", "1177017", "1169187", "912028", "1116626", "871839", "1267862", "216907", "918292"}
PREVIOUS = {"773485", "793347", "902259", "931151"}


def _entry(cik):
    return next(e for e in T["npx_ciks"] if str(e["cik"]) == cik)


def _key(cik, series, day):
    return engine.resolve_key(engine.normalize_rules(_entry(cik)), series, day)


def test_exactly_the_expected_registrants():
    ciks = {str(e["cik"]) for e in T["npx_ciks"]}
    assert ciks == PREVIOUS | set(REGISTRANT_KEY) | set(SERIES_KEY)
    assert not ciks & LEFT_OUT


def test_added_entries_have_standard_provenance_fields():
    for e in T["npx_ciks"]:
        if str(e["cik"]) in PREVIOUS:
            continue
        assert e["adviser_source"].startswith("https://www.sec.gov/Archives/"), e["cik"]
        assert e["name"] and e["adviser_verified"] and e["voting_note"] and e["validated"] and e["adviser"], e["cik"]
        engine.validate_rules(engine.normalize_rules(e), e["cik"])
        assert "<date>" not in str(e)


def test_registrant_level_keys_and_none_before_from():
    for cik, (key, frm) in REGISTRANT_KEY.items():
        assert _key(cik, "S000000001", "2025-06-30") == key, cik
        assert _key(cik, "S000000001", frm) == key, cik
        assert _key(cik, "S000000001", "2021-06-30") is None, cik
        assert _key(cik, "S000000001", "2022-04-27") is None, cik


def test_series_level_keys_and_none_before_from():
    for cik, series in SERIES_KEY.items():
        for sid, key in series.items():
            assert _key(cik, sid, "2025-06-30") == key, (cik, sid)
            assert _key(cik, sid, "2022-04-27") is None, (cik, sid)
        assert _key(cik, "S000000000", "2025-06-30") is None, cik   # unknown series stays unlabelled


def test_trpim_funds_are_the_sub_advised_ones_only():
    trpim = {c for c, (k, _f) in REGISTRANT_KEY.items() if k == "TRPIM"}
    assert trpim == {"887147", "834798", "75170"}


def test_existing_entries_untouched():
    assert _key("793347", "S000002084", "2025-06-30") == "TRPIM"
    assert _key("773485", "S000002073", "2025-06-30") == "TRPA"
    assert _key("902259", "S000002085", "2025-06-30") == "TRPA"
    assert _key("931151", "S000002086", "2025-06-30") == "TRPA"
