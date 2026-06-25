"""N-PX fund-trust discovery: proposes candidate filer CIKs with submissions-
API evidence, sorted by N-PX volume, confirming the real entity name. Never
auto-attributes (a wrong trust = another fund's votes in this manager's
mouth) — that decision stays human."""

import pytest

from glasshouse.ingest import discover

_ATOM = """<?xml version="1.0"?><feed>
  <entry><content><company-info><cik>0000869365</cik></company-info></content></entry>
  <entry><content><company-info><cik>0001535839</cik></company-info></content></entry>
  <entry><content><company-info><cik>0000869365</cik></company-info></content></entry>
</feed>"""

_SUBS = {
    "0000869365": {"name": "SCHWAB INVESTMENTS", "filings": {"recent": {
        "form": ["N-PX", "N-PX", "485BPOS"], "filingDate": ["2025-08-29", "2024-08-30", "2025-01-01"]}}},
    "0001535839": {"name": "Donor Advised Charitable Giving, Inc.", "filings": {"recent": {
        "form": ["N-PX"], "filingDate": ["2025-08-21"]}}},
}


@pytest.fixture
def _net(monkeypatch):
    class Resp:
        text = _ATOM
    monkeypatch.setattr(discover.http, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(discover.http, "get_json",
                        lambda url, **k: _SUBS[url.split("CIK")[1].split(".")[0]])


def test_discovers_and_enriches_candidates(_net):
    out = discover.discover_npx_filers("Schwab")
    # Deduped CIKs, enriched with real name + N-PX count, sorted by volume.
    schwab = next(c for c in out if c["cik"] == "869365")
    assert schwab["name"] == "SCHWAB INVESTMENTS"
    assert schwab["npx_filings"] == 2 and schwab["latest"] == "2025-08-29"
    assert out[0]["npx_filings"] >= out[-1]["npx_filings"]   # sorted desc
    # The noise match still surfaces (a human filters it) but is NOT attributed.
    assert any("Donor Advised" in c["name"] for c in out)


def test_unpadded_cik_and_no_crash_on_network_failure(_net, monkeypatch):
    out = discover.discover_npx_filers("Schwab")
    assert all(not c["cik"].startswith("0") for c in out)  # registry-style unpadded
    # A search failure returns [] rather than raising.
    monkeypatch.setattr(discover.http, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert discover.discover_npx_filers("Schwab") == []
