"""Tests for the completion batch: review gate, own-record findings,
holdings diff, concern index, outreach ladder."""

from datetime import date

import pytest

from glasshouse import diff, ledger, outreach, review, scoring
from glasshouse.contradictions import ContradictionCandidate
from glasshouse.findings import own_record
from glasshouse.ledger import EnforcementAction


def _candidate():
    return ContradictionCandidate(
        theme="climate", institution_id="blackrock",
        doc_label="stewardship", doc_version="2026-06-11", doc_sha256="abc123" * 10,
        doc_url="https://x/p.pdf",
        commitment_quote="Our approach to climate risk informs our voting.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025",
        vote_description="SHAREHOLDER PROPOSAL REQUESTING ALTERNATIVE EMISSIONS REPORTING",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=114_697_391.0)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    return ledger.connect(tmp_path / "test.db")


def test_review_gate_requires_note_and_is_durable(conn, monkeypatch):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions",
                        lambda c, **kw: [_candidate()])
    assert review.sync(conn)["added"] == 1
    assert review.sync(conn)["added"] == 0  # idempotent
    fid = review.queue(conn)[0]["id"]
    with pytest.raises(ValueError):
        review.decide(conn, fid, "approved", "   ")  # empty note refused
    review.decide(conn, fid, "approved", "read policy p.4; verified proposal on EDGAR")
    assert review.stats(conn) == {"approved": 1}
    # A re-sync never overwrites a human decision.
    review.sync(conn)
    assert review.queue(conn)[0]["status"] == "approved"


def test_own_record_finds_institutions_in_enforcement(conn):
    conn.execute("INSERT INTO institutions (id, display_name) "
                 "VALUES ('goldman_sachs', 'Goldman Sachs Group Inc.')")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="DOJ/SEC (FCPA)", company_name="The Goldman Sachs Group, Inc.",
        action_date="2020-10-22", resolution_type="dpa", penalty_usd=2_900_000_000,
        primary_ref="DOJ 20-1110", source_url="https://j.gov/x")])
    rows = own_record(conn)
    assert len(rows) == 1
    assert rows[0].institution_id == "goldman_sachs"
    assert rows[0].quarantined  # subsidiary-vs-parent must be human-confirmed


def test_flagged_votes_excludes_ofac_sdn_collisions(conn):
    """Votes at a portfolio issuer must not be flagged because the issuer's
    name collides with an OFAC SDN designation (the Aldar case) — but a real
    enforcement match still surfaces."""
    from glasshouse.findings import flagged_votes
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('F','1','blackrock','N-PX','u','d')")
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, is_duplicate) "
                 "VALUES ('F','ALDAR PROPERTIES PJSC','FOR',1,0)")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="OFAC (SDN)", company_name="ALDAR PROPERTIES", action_date="2019-01-01",
        resolution_type="sanction_designation", primary_ref="O-1", source_url="https://o")])
    assert flagged_votes(conn) == []   # SDN name-collision suppressed
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="SEC", company_name="ALDAR PROPERTIES PJSC", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="S-1", source_url="https://s")])
    assert any(r.issuer_name == "ALDAR PROPERTIES PJSC" for r in flagged_votes(conn))


def test_own_record_excludes_ofac_sdn_name_collisions(conn):
    """A tracked manager appearing on the OFAC SDN list by normalized-name
    collision (e.g. Vanguard Group == a sanctioned 'VANGUARD') is NOT its own
    record — sanction designations must be excluded (the Aldar lesson)."""
    conn.execute("INSERT INTO institutions (id, display_name) "
                 "VALUES ('vanguard', 'The Vanguard Group, Inc.')")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="OFAC (SDN)", company_name="VANGUARD", action_date="2019-01-01",
        resolution_type="sanction_designation", primary_ref="OFAC-1",
        source_url="https://ofac.gov/x")])
    assert own_record(conn) == []   # the collision is suppressed, not surfaced


def test_holdings_diff_opened_closed_changed(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    for acc, period in (("H1", "2025-09-30"), ("H2", "2025-12-31")):
        conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, "
                     "period_of_report, source_url, retrieval_date) "
                     "VALUES (?, '1364742', 'blackrock', '13F-HR', ?, 'u', 'd')",
                     (acc, period))
    rows = [
        ("H1", "OLD POSITION", "AAA000000", 50_000_000, 1000.0),
        ("H1", "SHRINKING CO", "BBB000000", 40_000_000, 1000.0),
        ("H2", "SHRINKING CO", "BBB000000", 30_000_000, 500.0),
        ("H2", "NEW POSITION", "CCC000000", 60_000_000, 2000.0),
    ]
    conn.executemany("INSERT INTO holdings (accession, issuer_name, cusip, value_usd, "
                     "shares) VALUES (?,?,?,?,?)", rows)
    d = diff.holdings_changes(conn, "blackrock")
    assert [p["issuer_name"] for p in d["opened"]] == ["NEW POSITION"]
    assert [p["issuer_name"] for p in d["closed"]] == ["OLD POSITION"]
    assert d["changed"][0]["issuer_name"] == "SHRINKING CO"
    assert d["changed"][0]["pct"] == -50.0


def test_concern_index_math_and_zero_for_quarantined():
    today = date(2026, 6, 11)
    s = scoring.concern_index([
        {"resolution_type": "guilty_plea", "action_date": "2021-06-11"},  # 5y → ×0.5
        {"resolution_type": "allegation", "action_date": "2026-01-01"},   # zero
        {"resolution_type": "unverified", "action_date": "2026-01-01"},   # zero
    ], today=today)
    assert s["n_scored_actions"] == 1
    assert s["recidivism_multiplier"] == 1.0
    assert abs(s["raw"] - 5.0) < 0.05  # 10 × 0.5
    s2 = scoring.concern_index([
        {"resolution_type": "guilty_plea", "action_date": "2026-06-11"}] * 8, today=today)
    assert s2["recidivism_multiplier"] == 2.0  # capped


def test_all_outreach_kinds_draft_and_ladder_tracks(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    c = _candidate()
    for kind in outreach.KINDS:
        oid = outreach.draft_from_candidate(conn, c, kind=kind)
        assert oid > 0
    lad = outreach.ladder(conn)
    assert len(lad) == 1
    assert set(lad[0]["steps"]) == set(outreach.KINDS)
    # Pitch draft uses placeholder until contacts.yaml is filled.
    body = open(conn.execute("SELECT body_path FROM outreach WHERE kind='pitch'")
                .fetchone()[0]).read()
    assert "CONTACT" in body or "@" not in body.split("\n")[0]
