import pytest

from glasshouse import ledger
from glasshouse.findings import flagged_votes
from glasshouse.ledger import EnforcementAction


@pytest.fixture
def conn(tmp_path):
    return ledger.connect(tmp_path / "test.db")


def test_resolution_type_is_enforced_in_code_not_just_prompt(conn):
    with pytest.raises(ValueError):
        EnforcementAction(agency="SEC", company_name="X", resolution_type="conviction",
                          source_url="https://example.org")


def test_source_url_required(conn):
    with pytest.raises(ValueError):
        EnforcementAction(agency="SEC", company_name="X",
                          resolution_type="civil_settlement", source_url="")


def test_allegations_are_flagged(conn):
    a = EnforcementAction(agency="CourtListener", company_name="X",
                          resolution_type="allegation", source_url="https://example.org")
    assert a.is_allegation


def test_insert_is_idempotent(conn):
    a = EnforcementAction(agency="SEC", company_name="Oracle Corporation",
                          action_date="2012-08-16", resolution_type="civil_settlement",
                          primary_ref="SEC Rel. 34-67574", source_url="https://www.sec.gov/x")
    assert ledger.insert_enforcement(conn, [a]) == 1
    assert ledger.insert_enforcement(conn, [a]) == 0


def test_integrity_check_flags_orphan_votes_and_quarantine(conn):
    conn.execute("PRAGMA foreign_keys = OFF")  # simulate corruption
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted) VALUES ('NOPE', 'X', 'FOR')")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="DOJ", company_name="Y", resolution_type="unverified",
        source_url="https://example.org")])
    problems = ledger.integrity_check(conn)
    assert len(problems["votes_orphaned"]) == 1
    assert len(problems["quarantined"]) == 1
    assert problems["enforcement_missing_provenance"] == []


def _add_vote(conn, issuer, how="AGAINST", desc="Shareholder proposal regarding report on anti-corruption"):
    conn.execute(
        "INSERT INTO filings (accession, cik, form_type, source_url, retrieval_date) "
        "VALUES ('ACC-1', '1100663', 'N-PX', 'https://sec.gov/x', '2026-06-11') "
        "ON CONFLICT DO NOTHING")
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
        "how_voted, management_recommendation) VALUES ('ACC-1', ?, '68389X105', "
        "'2024-11-15', ?, ?, 'AGAINST')", (issuer, desc, how))


def test_flagged_votes_joins_on_normalized_name_and_quarantines_all(conn):
    _add_vote(conn, "ORACLE CORP")
    ledger.insert_enforcement(conn, [
        EnforcementAction(agency="SEC", company_name="Oracle Corporation",
                          action_date="2012-08-16", resolution_type="civil_settlement",
                          primary_ref="SEC Rel. 34-67574", source_url="https://www.sec.gov/x"),
        EnforcementAction(agency="DOJ (FCPA)", company_name="Oracle Corp",
                          resolution_type="unverified", source_url="https://justice.gov/x"),
    ])
    rows = flagged_votes(conn)
    assert len(rows) == 2
    # Name-only joins are NEVER finding-grade: same normalized name can be a
    # different company (the OFAC "Aldar Properties" case, 2026-06-11).
    assert all(r.quarantined for r in rows)
    assert all(r.join_method == "name_exact" for r in rows)
    assert {r.primary_ref for r in rows} == {"SEC Rel. 34-67574", ""}


def test_flagged_votes_does_not_match_unrelated_issuers(conn):
    _add_vote(conn, "Apple Hospitality REIT Inc")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="SEC", company_name="Apple Inc", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="SEC LR-0000",
        source_url="https://www.sec.gov/x")])
    assert flagged_votes(conn) == []
