"""Tests for vote divergence (Phase 3 class b), the commitments ledger
(Phase 2), and the diff engine."""

import pytest

from glasshouse import diff, ledger
from glasshouse.findings import vote_divergence
from glasshouse.ingest import commitments
from glasshouse.ledger import EnforcementAction


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "commitments")
    return ledger.connect(tmp_path / "test.db")


def _vote(conn, issuer, how, shares, desc="Report on human rights due diligence",
          cusip="68389X105", acc="ACC-1"):
    conn.execute(
        "INSERT OR IGNORE INTO filings (accession, cik, form_type, source_url, retrieval_date) "
        "VALUES (?, '1100663', 'N-PX', 'https://sec.gov/x', '2026-06-11')", (acc,))
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
        "how_voted, shares_voted, management_recommendation) "
        "VALUES (?, ?, ?, '2024-11-15', ?, ?, ?, 'AGAINST')",
        (acc, issuer, cusip, desc, how, shares))


def test_vote_divergence_detects_split_votes(conn):
    _vote(conn, "ORACLE CORP", "AGAINST", 1_250_000)
    _vote(conn, "ORACLE CORP", "FOR", 34_000)
    # A unanimous proposal must not appear.
    _vote(conn, "MICROSOFT CORP", "FOR", 100, desc="Election of director", cusip="594918104")

    rows = vote_divergence(conn)
    assert len(rows) == 1
    r = rows[0]
    assert r.issuer_name == "ORACLE CORP"
    assert r.ways == {"AGAINST": 1_250_000, "FOR": 34_000}

    only_sp = vote_divergence(conn, shareholder_proposals_only=True)
    assert len(only_sp) == 1  # "human rights" matches the proposal heuristic


def test_commitment_versioning_is_content_addressed(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    v1 = commitments.record_snapshot(conn, "blackrock", "stewardship", "https://x/p.pdf",
                                     b"we are committed to anti-corruption", "application/pdf")
    again = commitments.record_snapshot(conn, "blackrock", "stewardship", "https://x/p.pdf",
                                        b"we are committed to anti-corruption", "application/pdf")
    v2 = commitments.record_snapshot(conn, "blackrock", "stewardship", "https://x/p.pdf",
                                     b"we are committed to engagement", "application/pdf")
    assert v1 is True and again is False and v2 is True

    edits = commitments.policy_edits(conn)
    assert len(edits) == 1
    assert edits[0]["n_versions"] == 2
    # Both versions' bytes must be on disk for diffing/quoting.
    from pathlib import Path
    for v in edits[0]["versions"]:
        assert Path(v["content_path"]).exists()


def test_wayback_versions_kept_distinct_from_live(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    same = b"identical bytes"
    live = commitments.record_snapshot(conn, "blackrock", "stewardship", "https://x/p.pdf", same)
    wb = commitments.record_snapshot(conn, "blackrock", "stewardship", "https://x/p.pdf", same,
                                     wayback_timestamp="20240101000000")
    assert live is True and wb is True  # same content, different provenance — both kept


def test_diff_engine_reports_deltas_and_records_runs(conn):
    diff.record_run(conn)
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="SEC", company_name="Oracle Corporation", action_date="2012-08-16",
        resolution_type="civil_settlement", primary_ref="SEC Rel. 34-67574",
        source_url="https://www.sec.gov/x")])
    _vote(conn, "ORACLE CORP", "AGAINST", 100)

    d = diff.compute(conn)
    assert d.since is not None
    assert d.new_enforcement == 1
    assert d.new_votes == 1
    assert d.enforcement_samples[0]["primary_ref"] == "SEC Rel. 34-67574"

    diff.record_run(conn)
    assert diff.compute(conn).is_empty
