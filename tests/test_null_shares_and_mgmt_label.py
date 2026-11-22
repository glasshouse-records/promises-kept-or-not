"""NULL shares_voted (legacy N-PX) must never crash or print 0; the
management_recommendation column means 'vote WITH/AGAINST management'."""
import json

import pytest

from glasshouse import cli, council, fmt, ledger, outreach, review
from glasshouse.contradictions import ContradictionCandidate


def _cand(shares=None, mgmt="FOR"):
    return ContradictionCandidate(
        theme="climate", institution_id="blackrock", doc_label="stewardship",
        doc_version="2026-06-11", doc_sha256="a" * 64, doc_url="https://x/p.pdf",
        commitment_quote="We are committed to climate risk oversight in our voting.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025", vote_description="EMISSIONS REPORTING PROPOSAL",
        how_voted="AGAINST", management_recommendation=mgmt, shares_voted=shares)


def test_fmt_helpers():
    assert fmt.shares_phrase(None) == "shares not filed"
    assert fmt.shares_phrase(1234.0) == "1,234 shares"
    assert fmt.shares_phrase(0) == "0 shares"          # a filed zero stays a zero
    assert fmt.vote_vs_mgmt("FOR") == "with management"
    assert fmt.vote_vs_mgmt("against") == "against management"
    assert fmt.vote_vs_mgmt("MIXED") == "MIXED"
    assert fmt.vote_vs_mgmt(None) == "—"


def test_council_brief_null_shares():
    p = json.loads(json.dumps(_cand().__dict__, default=str))
    out = council._candidate_brief(p)
    assert "shares not filed" in out and " 0 shares" not in out
    assert "management recommendation" not in out
    assert "with management" in out


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    return ledger.connect(tmp_path / "test.db")


@pytest.mark.parametrize("kind", ["inquiry", "social_post", "pitch", "fiduciary", "data_offer"])
def test_outreach_null_shares_and_label(conn, kind):
    oid = outreach.draft_from_candidate(conn, _cand(None, "FOR"), kind=kind)
    body = open(conn.execute("SELECT body_path FROM outreach WHERE id=?",
                             (oid,)).fetchone()["body_path"]).read()
    assert "shares not filed" in body
    assert "0 shares" not in body and "0 sh)" not in body
    assert "management recommendation" not in body.lower()


def test_outreach_label_maps_for_and_against(conn):
    for mgmt, want in (("FOR", "with management"), ("AGAINST", "against management")):
        oid = outreach.draft_from_candidate(conn, _cand(500.0, mgmt), kind="inquiry")
        body = open(conn.execute("SELECT body_path FROM outreach WHERE id=?",
                                 (oid,)).fetchone()["body_path"]).read()
        assert f"vote vs management: {want}" in body
        assert "500 shares" in body


def test_review_dossier_null_shares(conn, monkeypatch, tmp_path):
    import glasshouse.http as gh_http
    monkeypatch.setattr(gh_http, "DATA_DIR", tmp_path)
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **kw: [_cand()])
    review.sync(conn)
    fid = review.queue(conn)[0]["id"]
    d = open(review.dossier(conn, fid)).read()
    assert "shares not filed" in d
    assert "mgmt rec" not in d and "vote vs management: with management" in d


def _cli_conn(monkeypatch, tmp_path, cands):
    import argparse

    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **kw: cands)
    c = ledger.connect(tmp_path / "cli.db")
    monkeypatch.setattr(cli, "_conn", lambda: c)
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    return argparse, c


def test_cli_report_contradictions_null_shares(tmp_path, monkeypatch, capsys):
    argparse, _ = _cli_conn(monkeypatch, tmp_path, [_cand(None, "AGAINST")])
    cli.cmd_report_contradictions(argparse.Namespace(limit_per_theme=5, theme=None))
    out = capsys.readouterr().out
    assert "shares not filed" in out and "0 sh" not in out
    assert "mgmt rec" not in out and "vote vs management: against management" in out


def test_cli_outreach_draft_with_null_shares(tmp_path, monkeypatch, capsys):
    argparse, _ = _cli_conn(monkeypatch, tmp_path, [_cand(None), _cand(5.0)])
    cli.cmd_outreach_draft(argparse.Namespace(institution=None, theme=None, kind="inquiry"))


def test_cli_awards_null_shares(tmp_path, monkeypatch, capsys):
    argparse, _ = _cli_conn(monkeypatch, tmp_path, [_cand(None)])
    cli.cmd_report_awards(argparse.Namespace())
    out = capsys.readouterr().out
    assert "shares not filed" in out
    assert " 0 shares voted" not in out


# ── other renderers: a NULL count is "shares not filed", never 0, never a crash ──

_EX = {"issuer_name": "ACME", "meeting_date": "05/01/2025", "vote_description": "climate report",
       "how_voted": "AGAINST", "shares_voted": None, "accession": "A-1", "source_url": ""}


def _rec():
    from glasshouse.investigate import ThemeRecord
    return ThemeRecord(
        theme="climate", institution_id="x", institution_name="X Mgmt", committed=True,
        commitment_quote="We commit to climate.", doc_label="d", doc_version="2025-01-01",
        doc_url="u", votes_for=1, votes_against=1, votes_abstain=0, n_theme=2,
        against_rate=0.5, examples=[dict(_EX)])


def test_investigate_evidence_pack_null_shares():
    from glasshouse import investigate
    md = investigate.evidence_pack(_rec())
    assert "shares not filed" in md


def test_agent_draft_null_shares():
    from glasshouse import agent
    out = agent._draft(_rec(), 1.0)
    assert "shares not filed" in out["standfirst"] and "with 0 shares" not in out["standfirst"]


def test_firststone_body_null_shares():
    from glasshouse import firststone
    s = {"theme": "climate", "headline": "h", "trail": [], "institution_name": "X", "standfirst": "s", "quote": "q", "doc_label": "d",
         "doc_version": "v", "doc_url": "u", "votes_against": 1, "votes_for": 1,
         "n_votes": 2, "against_rate": 0.5, "examples": [dict(_EX)]}
    body = firststone._compose_body(s)
    assert "shares not filed" in body and "with 0 shares" not in body


def test_site_finding_card_null_shares():
    from glasshouse import site
    p = json.loads(json.dumps(_cand().__dict__, default=str))
    p["_reviewed"] = "2026-01-01"
    html = site._finding_card(p, featured=True)
    assert "shares not filed" in html and "0 shares" not in html
    assert site._featured_finding([p, {**p, "shares_voted": 9.0}])["shares_voted"] == 9.0
    assert site._featured_finding([p])["shares_voted"] is None
    assert site._featured_finding([]) is None


def test_newsroom_story_null_shares(conn):
    from glasshouse import newsroom
    p = json.loads(json.dumps(_cand().__dict__, default=str))
    conn.execute("INSERT INTO findings (fingerprint, theme, institution_id, payload, status, "
                 "reviewer_note, reviewed_date) VALUES ('fp1','climate','blackrock',?,"
                 "'approved','n','2026-01-01')", (json.dumps(p),))
    conn.commit()
    q = newsroom.story_queue(conn)
    f = next(s for s in q if s["kind"] == "finding")
    assert "shares not filed" in " | ".join(f["why"])
    assert not any("0 shares" in w for w in f["why"])


def test_workbench_js_guards_null_shares():
    from glasshouse import workbench
    src = open(workbench.__file__).read()
    assert "Number(x.shares_voted)" not in src and "Number(p.shares_voted)" not in src
