"""The self-improvement loop: a measurable balanced index with trend memory,
a strategist that ranks tool-level moves, and a SAFE auto-apply tier that
never touches data decisions or publication."""

from datetime import date

import pytest

from glasshouse import improve, ledger, metrics, outreach, review
from glasshouse.ledger import EnforcementAction


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(improve, "DATA_DIR", tmp_path)
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    from glasshouse.ingest import commitments
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "commitments")
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    ledger.insert_enforcement(c, [EnforcementAction(
        agency="SEC", company_name="Oracle", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="LR-1",
        source_url="https://s", retrieval_date=date.today().isoformat())])
    c.commit()
    return c


def test_balanced_index_is_in_range_with_documented_components(conn):
    m = metrics.compute(conn)
    assert 0.0 <= m["balanced_index"] <= 100.0
    assert set(m["components"]) == {"coverage", "completeness", "provenance", "freshness"}
    # provenance is ~1.0 (the invariant); thin coverage drags the index down.
    assert m["components"]["provenance"] == 1.0


def test_snapshot_records_trend_and_delta(conn):
    metrics.snapshot(conn, today=date(2026, 1, 1))
    assert metrics.delta(conn) is None           # only one snapshot
    metrics.snapshot(conn, today=date(2026, 1, 1))
    assert metrics.delta(conn) == 0.0            # no change between identical snapshots
    assert len(metrics.trend(conn)) == 2


def test_assess_ranks_coverage_first_when_thin(conn):
    a = improve.assess(conn)
    assert a["agenda"][0]["area"] in ("coverage", "sources")  # binding constraint first
    # The hygiene item is the only auto_safe one; coverage is not auto.
    cov = next(x for x in a["agenda"] if x["area"] == "coverage")
    assert cov["auto_safe"] is False and cov["executor"] == "coverage-run"


def test_apply_safe_is_idempotent_and_never_approves_findings(conn, monkeypatch):
    import glasshouse.contradictions as ct
    from glasshouse.contradictions import ContradictionCandidate
    cand = ContradictionCandidate(
        theme="climate", institution_id="blackrock", doc_label="d", doc_version="2024-01-01",
        doc_sha256="a" * 64, doc_url="u", commitment_quote="We are committed to climate.",
        accession="ACC", issuer_name="X", cusip="C", meeting_date="05/01/2024",
        vote_description="climate report", how_voted="AGAINST",
        management_recommendation="FOR", shares_voted=1.0)
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **k: [cand])

    res = improve.apply_safe(conn)
    assert "dedupe" in res["ran"] and "reconcile-review" in res["ran"]
    # SAFE tier must never approve a finding — pending stays pending.
    assert review.stats(conn).get("approved", 0) == 0
    # Idempotent: a second run changes nothing material and doesn't crash.
    res2 = improve.apply_safe(conn)
    assert review.stats(conn).get("approved", 0) == 0
    assert isinstance(res2["delta"], float)


def test_write_brief_emits_agenda(conn):
    path = improve.write_brief(conn)
    body = open(path).read()
    assert "Balanced index" in body
    assert "data decisions and publication stay human-gated" in body
