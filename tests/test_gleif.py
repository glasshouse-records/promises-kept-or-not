import pytest

from glasshouse import ledger
from glasshouse.ingest import gleif


@pytest.fixture
def conn(tmp_path):
    return ledger.connect(tmp_path / "test.db")


def _vote(conn, issuer, isin, cusip):
    conn.execute(
        "INSERT OR IGNORE INTO filings (accession, cik, form_type, source_url, retrieval_date) "
        "VALUES ('ACC-1', '1100663', 'N-PX', 'https://sec.gov/x', '2026-06-11')")
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, cusip, isin, meeting_date, how_voted) "
        "VALUES ('ACC-1', ?, ?, ?, '2025-05-01', 'FOR')", (issuer, cusip, isin))


def test_enrichment_links_cusip_and_is_resumable(conn, monkeypatch):
    _vote(conn, "ORACLE CORP", "US68389X1054", "68389X105")
    _vote(conn, "UNMAPPED LTD", "ZZ0000000000", "00000ZZ99")

    calls = []

    def fake_lookup(isin):
        calls.append(isin)
        if isin == "US68389X1054":
            return {"lei": "1Z4GXXU7ZHVWFCD8TV52", "name": "ORACLE CORPORATION", "country": "US"}
        return None

    monkeypatch.setattr(gleif, "lookup_isin", fake_lookup)
    monkeypatch.setattr(gleif, "_PAUSE", 0)

    stats = gleif.enrich_from_votes(conn)
    assert stats == {"resolved": 1, "unmapped": 1, "errors": 0}

    row = conn.execute(
        "SELECT e.canonical_name, e.lei, e.country FROM entities e "
        "JOIN entity_cusips c ON c.entity_id = e.id WHERE c.cusip = '68389X105'"
    ).fetchone()
    assert row["lei"] == "1Z4GXXU7ZHVWFCD8TV52"
    assert row["country"] == "US"

    # Resumable: the resolved CUSIP is not looked up again.
    calls.clear()
    gleif.enrich_from_votes(conn)
    assert "US68389X1054" not in calls
