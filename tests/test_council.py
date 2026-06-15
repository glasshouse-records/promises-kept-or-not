"""The advisory review council: multi-perspective evaluation that recommends
but never decides. Tests assert it's advisory by construction — it writes
recommendations to triage, never promotes a finding, and the human gate is
untouched."""

import json

import pytest

from glasshouse import council, ledger, llm, review
from glasshouse.contradictions import ContradictionCandidate


def _candidate(theme="climate"):
    return ContradictionCandidate(
        theme=theme, institution_id="blackrock", doc_label="stewardship",
        doc_version="2026-06-11", doc_sha256="a" * 64, doc_url="https://x/p.pdf",
        commitment_quote="We are committed to climate risk oversight in our voting.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025", vote_description="EMISSIONS REPORTING PROPOSAL",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=1000.0)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions",
                        lambda c, **kw: [_candidate()])
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    review.sync(c)
    return c


def _fake_llm(monkeypatch, synth_verdict="finding"):
    calls = []

    def fake_call(conn, *, purpose, input_key, system, user, model=llm.DEFAULT_MODEL, max_tokens=500):
        calls.append(purpose)
        conn.execute("INSERT INTO llm_log (ts, model, purpose, prompt_sha, input_key, output) "
                     "VALUES ('t',?,?,'s',?,?)", (model, purpose, input_key, "x"))
        if purpose == "council_synth":
            return json.dumps({"verdict": synth_verdict, "confidence": "high",
                               "rationale": "test synthesis"})
        return f"{purpose} note. VERDICT: holds"

    monkeypatch.setattr(llm, "call", fake_call)
    return calls


def test_council_runs_four_passes_plus_synth_and_is_advisory(conn, monkeypatch):
    calls = _fake_llm(monkeypatch, synth_verdict="finding")
    f = review.queue(conn, "pending")[0]
    rec = council.evaluate(conn, f["payload"], key=f["fingerprint"])

    assert rec["verdict"] == "finding" and rec["confidence"] == "high"
    assert {"skeptic", "advocate", "libel", "theme"} <= set(rec["notes"])
    assert {"council_skeptic", "council_advocate", "council_libel",
            "council_theme", "council_synth"} <= set(calls)
    # ADVISORY: the finding is still pending — the council never promotes it.
    assert review.queue(conn, "pending") and review.stats(conn).get("approved", 0) == 0
    # Recorded for the workbench, and every call logged.
    assert conn.execute("SELECT COUNT(*) FROM triage WHERE kind='council'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM llm_log").fetchone()[0] == 5


def test_council_is_cached(conn, monkeypatch):
    calls = _fake_llm(monkeypatch)
    f = review.queue(conn, "pending")[0]
    council.evaluate(conn, f["payload"], key=f["fingerprint"])
    n = len(calls)
    again = council.evaluate(conn, f["payload"], key=f["fingerprint"])
    assert again["cached"] is True and len(calls) == n  # no new model calls


def test_recommendations_surface_for_workbench(conn, monkeypatch):
    _fake_llm(monkeypatch, synth_verdict="reject")
    f = review.queue(conn, "pending")[0]
    council.evaluate(conn, f["payload"], key=f["fingerprint"])
    recs = council.recommendations(conn)
    assert recs[f["fingerprint"]]["verdict"] == "reject"
    assert "notes" in recs[f["fingerprint"]]


def test_council_refuses_without_api_key(conn, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    f = review.queue(conn, "pending")[0]
    with pytest.raises(llm.NotConfigured):
        council.evaluate(conn, f["payload"], key=f["fingerprint"])
