"""Global X Funds (CIK 1432353): votes follow the Adviser's own Proxy Voting Policies (key GLOBAL_X), but the SAIs
name funds under a Catholic or ESG voting-policy ADDENDUM that the archive does not hold. Those series carry their
own key (never GLOBAL_X, so their votes are not paired with the general text) for the window the SAIs support, and
UNRESOLVED where a start or end is not established."""
from pathlib import Path

import yaml

from glasshouse import engine

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "institutions.yaml").read_text())
G = CFG["institutions"]["global_x"]
E = G["npx_ciks"][0]


def _key(series, day):
    return engine.resolve_key(engine.normalize_rules(E), series, day)


def test_general_series_resolve_to_global_x():
    assert _key("S000023259", "2025-06-30") == "GLOBAL_X"   # a fund named in no addendum list
    assert _key("S000023259", "2021-01-04") == "GLOBAL_X"


def test_catholic_funds_resolve_to_the_catholic_key_inside_their_window():
    assert _key("S000050646", "2025-06-30") == "GLOBAL_X_CATHOLIC"      # S&P 500 Catholic Values, named from 2021-02-23
    assert _key("S000068649", "2025-06-30") == "GLOBAL_X_CATHOLIC"      # Developed ex-U.S., named from 2024-02-28
    assert _key("S000068649", "2023-09-01") == "UNRESOLVED"             # existed, not yet named in any SAI


def test_esg_funds_resolve_to_the_esg_key_inside_their_window():
    assert _key("S000049685", "2025-06-30") == "GLOBAL_X_ESG"           # Renewable Energy Producers
    assert _key("S000072699", "2024-06-30") == "GLOBAL_X_ESG"           # Solar, named 2022-03-24 to 2025-03-26
    assert _key("S000072699", "2026-05-01") == "UNRESOLVED"             # dropped from the 2026-03-27 list
    assert _key("S000054690", "2024-06-30") == "UNRESOLVED"             # Education: named to 2023-03-29, then absent
    assert _key("S000075802", "2023-09-01") == "GLOBAL_X_ESG"           # Green Building, named only 2023-03-29
    assert _key("S000079695", "2025-06-30") == "UNRESOLVED"             # Nasdaq 100 ESG CC: named only 2024-02-28


def test_no_addendum_series_is_ever_plain_global_x_inside_its_named_window():
    rules = engine.normalize_rules(E)["series"]
    assert len(rules) == 16
    for sid, lst in rules.items():
        assert not any(k == "GLOBAL_X" for k, _, _ in lst), sid
        assert any(k in ("GLOBAL_X_CATHOLIC", "GLOBAL_X_ESG") for k, _, _ in lst), sid
