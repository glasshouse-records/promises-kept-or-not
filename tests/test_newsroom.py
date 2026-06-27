"""Tests for the newsroom — story selection, ranking, draftability, and the
pipeline-status surface. Asserts the visibility the operator asked for and
the no-send guardrail (drafting routes through the gated outreach queue)."""

import json
import urllib.request

import pytest

from glasshouse import ledger, newsroom, outreach, review, workbench
from glasshouse.contradictions import ContradictionCandidate


def _candidate(theme="climate", issuer="AMAZON.COM, INC.", shares=114_697_391.0):
    return ContradictionCandidate(
        theme=theme, institution_id="blackrock", doc_label="stewardship",
        doc_version="2026-06-11", doc_sha256="abc123" * 10, doc_url="https://x/p.pdf",
        commitment_quote="Our approach to climate risk informs our voting.",
        accession="ACC-1", issuer_name=issuer, cusip="023135106",
        meeting_date="05/21/2025", vote_description="EMISSIONS REPORTING PROPOSAL",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=shares)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr(newsroom, "DATA_DIR", tmp_path)
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    return c


def _seed_candidates(monkeypatch, cands):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **kw: cands)


def test_story_queue_ranks_findings_above_candidates(conn, monkeypatch):
    _seed_candidates(monkeypatch, [_candidate(shares=1000), _candidate(theme="lobbying-disclosure")])
    review.sync(conn)
    # Approve one → it should float to the top as a verified, publishable story.
    fid = review.queue(conn, "pending")[0]["id"]
    review.decide(conn, fid, "approved", "verified against EDGAR")

    q = newsroom.story_queue(conn)
    assert q, "expected stories"
    assert q[0]["kind"] == "finding"
    assert q[0]["draftable"] is True
    assert "human-verified finding" in q[0]["why"][0]
    # A candidate is present but not draftable (needs review first).
    cand = [s for s in q if s["kind"] == "candidate"]
    assert cand and cand[0]["draftable"] is False and cand[0]["next_step"] == "review"


def test_higher_share_vote_outranks_lower_within_kind(conn, monkeypatch):
    _seed_candidates(monkeypatch, [_candidate(theme="climate", shares=5_000),
                                   _candidate(theme="human-rights", shares=90_000_000)])
    review.sync(conn)   # candidates are read from the materialized review queue
    q = [s for s in newsroom.story_queue(conn) if s["kind"] == "candidate"]
    assert q[0]["shares"] > q[1]["shares"]  # ranked by newsworthiness weight


def test_event_alerts_surface_as_news_pegged_stories(conn, monkeypatch, tmp_path):
    _seed_candidates(monkeypatch, [])
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "2026-06-11_1_oracle.md").write_text("# Event alert: Oracle Corporation\n\nbody")
    (alerts / "2026-06-11_news_triggers.md").write_text("# News triggers\nnot a story")
    q = newsroom.story_queue(conn)
    events = [s for s in q if s["kind"] == "event"]
    assert len(events) == 1  # the news_triggers file is excluded
    assert "Oracle" in events[0]["headline"] and events[0]["draftable"] is False


def test_draft_story_routes_through_gated_queue(conn, monkeypatch):
    _seed_candidates(monkeypatch, [_candidate()])
    review.sync(conn)
    fid = review.queue(conn, "pending")[0]["id"]
    review.decide(conn, fid, "approved", "ok")
    story = next(s for s in newsroom.story_queue(conn) if s["kind"] == "finding")

    oid = newsroom.draft_story(conn, story["payload"], "social_post")
    row = conn.execute("SELECT kind, status, finding_fingerprint FROM outreach WHERE id=?", (oid,)).fetchone()
    assert row["kind"] == "social_post"
    assert row["status"] == "draft"            # drafted, never sent
    assert row["finding_fingerprint"] == story["key"]
    # And the story now reflects the drafted step + suggests the next ladder rung.
    s2 = next(s for s in newsroom.story_queue(conn) if s["key"] == story["key"])
    assert "social_post" in s2["drafted"] and s2["next_step"] == "pitch"


def test_pipeline_status_reports_every_stage(conn):
    rows = newsroom.pipeline_status(conn)
    stages = " ".join(r["stage"] for r in rows)
    for expected in ("INGEST", "ANALYZE", "REVIEW", "TRIGGER", "DISTRIBUTE", "SIGNAL"):
        assert expected in stages
    review_row = next(r for r in rows if r["stage"].startswith("REVIEW"))
    assert "no findings published yet" in review_row["note"]  # honest empty-state


# ── workbench integration: the Newsroom tab is actually served and wired ─────

@pytest.fixture
def server(tmp_path, monkeypatch):
    db = tmp_path / "wb.db"
    monkeypatch.setattr(workbench, "DB_PATH", db)
    monkeypatch.setattr(workbench, "LABELS_PATH", tmp_path / "labels" / "l.jsonl")
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr(newsroom, "DATA_DIR", tmp_path)
    _seed_candidates(monkeypatch, [_candidate()])
    c = ledger.connect(db)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    review.sync(c)
    fid = review.queue(c, "pending")[0]["id"]
    review.decide(c, fid, "approved", "verified")
    c.close()
    srv = workbench.serve(port=0)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_state_includes_newsroom_and_pipeline(server):
    with urllib.request.urlopen(server + "/api/state", timeout=10) as r:
        s = json.loads(r.read())
    assert s["newsroom"] and s["newsroom"][0]["kind"] == "finding"
    assert s["pipeline"] and any("INGEST" in p["stage"] for p in s["pipeline"])


def test_draft_story_action_over_http_does_not_send(server):
    with urllib.request.urlopen(server + "/api/state", timeout=10) as r:
        story = json.loads(r.read())["newsroom"][0]
    req = urllib.request.Request(server + "/api/act/draft_story",
                                 data=json.dumps({"payload": story["payload"],
                                                  "kind": "social_post"}).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.loads(r.read())
    assert out["ok"] and "N-PX" in out["body"]  # the drafted post carries the citation
    with urllib.request.urlopen(server + "/api/state", timeout=10) as r:
        assert json.loads(r.read())["outreach"][0]["status"] == "draft"
