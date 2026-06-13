"""Tests for the agent layer: doctor sensing, LLM triage invariants, the
eval gate, and dossier assembly. All LLM calls are mocked — the suite runs
offline and asserts the ADVISORY-ONLY architecture, not model quality."""

import json

import pytest

from glasshouse import doctor, evals, ledger, llm, review, triage
from glasshouse.contradictions import ContradictionCandidate


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "DOCTOR_DIR", tmp_path / "doctor")
    return ledger.connect(tmp_path / "test.db")


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


def test_doctor_emits_report_and_repair_task(conn):
    report_path, task_path = doctor.emit(conn)
    report = json.loads(open(report_path).read())
    # Fresh ledger: live sources never ingested → errors → unhealthy + task.
    assert report["healthy"] is False
    assert task_path is not None
    task = open(task_path).read()
    assert "never impersonate a browser" in task
    assert "Failing checks" in task
    # Known-blocked sources are pre-explained so the agent doesn't rediscover them.
    assert any(c["name"].startswith("blocked:") for c in report["checks"])


def test_llm_refuses_without_configuration(conn, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.NotConfigured):
        llm.call(conn, purpose="x", input_key="k", system="s", user="u")


def test_adjudication_is_logged_cached_and_advisory(conn, monkeypatch):
    calls = []

    def fake_call(c, *, purpose, input_key, system, user, **kw):
        calls.append(purpose)
        c.execute("INSERT INTO llm_log (ts, model, purpose, prompt_sha, input_key, output) "
                  "VALUES ('t','m',?,'p',?,?)", (purpose, input_key, "out"))
        return '{"verdict": "no_match", "confidence": "high", "rationale": "different countries"}'

    monkeypatch.setattr(llm, "call", fake_call)
    a = {"name": "ALDAR PROPERTIES PJSC", "country": "AE"}
    b = {"name": "ALDAR PROPERTIES", "context": "OFAC SDGT, Sudan"}
    d1 = triage.adjudicate_pair(conn, a, b)
    assert d1["verdict"] == "no_match"
    # Cached: second call must not hit the model.
    d2 = triage.adjudicate_pair(conn, a, b)
    assert d2["verdict"] == "no_match" and len(calls) == 1
    # Advisory invariant: triage rows exist, ledger facts untouched.
    assert conn.execute("SELECT COUNT(*) FROM triage").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM enforcement_actions").fetchone()[0] == 0
    # Every call is logged with the raw output.
    assert conn.execute("SELECT advisory FROM llm_log").fetchone()[0] == 1


def test_eval_gate_passes_perfect_and_fails_sloppy(conn, monkeypatch):
    def perfect(c, ra, rb, model=None):
        # Oracle: country conflict or subsidiary language → no_match, else match.
        txt = json.dumps([ra, rb])
        if ra.get("country") and rb.get("country") and ra["country"] != rb["country"] or "Sudan" in txt or "SDGT" in txt or "Hospitality" in txt \
                or "spun-off" in txt or "Egyptian" in txt or "different registry" in txt:
            v = "no_match"
        else:
            v = "match"
        return {"verdict": v, "confidence": "high", "rationale": "oracle"}

    monkeypatch.setattr(triage, "adjudicate_pair", perfect)
    r = evals.run_matcher_eval(conn)
    assert r["passes_bar"] is True and r["precision_on_match"] == 1.0

    monkeypatch.setattr(triage, "adjudicate_pair",
                        lambda c, a, b, model=None: {"verdict": "match",
                                                     "confidence": "high",
                                                     "rationale": "sloppy"})
    r2 = evals.run_matcher_eval(conn)
    assert r2["passes_bar"] is False  # matches everything incl. Aldar → fails


def test_dossier_contains_checklist_and_degrades_without_llm(conn, monkeypatch, tmp_path):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions",
                        lambda c, **kw: [_candidate()])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from glasshouse import http
    monkeypatch.setattr(http, "DATA_DIR", tmp_path)
    review.sync(conn)
    fid = review.queue(conn)[0]["id"]
    path = review.dossier(conn, fid)
    body = open(path).read()
    assert "Reviewer checklist" in body
    assert "managementRecommendation field is known-unreliable" in body
    assert "DEF+14A" in body
    assert "deterministic" in body  # LLM-not-configured note
    assert "glasshouse review approve/reject" in body
