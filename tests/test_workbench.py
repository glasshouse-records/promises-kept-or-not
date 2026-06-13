"""Integration tests for the operator workbench: real HTTP against a server
thread, asserting the decision loops and the guardrails."""

import json
import urllib.request

import pytest

from glasshouse import ledger, outreach, review, workbench
from glasshouse.contradictions import ContradictionCandidate
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
def server(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(workbench, "DB_PATH", db)
    monkeypatch.setattr(workbench, "LABELS_PATH", tmp_path / "labels" / "lead_labels.jsonl")
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions",
                        lambda c, **kw: [_candidate()])

    conn = ledger.connect(db)
    conn.execute("INSERT INTO institutions (id, display_name) "
                 "VALUES ('goldman_sachs', 'Goldman Sachs Group Inc.')")
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="DOJ/SEC (FCPA)", company_name="The Goldman Sachs Group, Inc.",
        action_date="2020-10-22", resolution_type="dpa", primary_ref="DOJ 20-1110",
        source_url="https://j.gov/x")])
    review.sync(conn)
    outreach.draft_from_candidate(conn, _candidate(), kind="inquiry")
    conn.close()

    srv = workbench.serve(port=0)
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_state_exposes_all_desks(server):
    s = _get(server + "/api/state")
    assert len(s["review"]) == 1
    assert s["leads"][0]["kind"] == "own-record"
    assert s["outreach"][0]["status"] == "draft"
    assert s["gold_labels"] == 0


def test_review_decision_requires_note_and_persists(server):
    s = _get(server + "/api/state")
    fid = s["review"][0]["id"]
    code, out = _post(server + "/api/act/review",
                      {"id": fid, "decision": "approved", "note": "  "})
    assert code == 400 and "note" in out["error"]
    code, out = _post(server + "/api/act/review",
                      {"id": fid, "decision": "approved",
                       "note": "verified quote in PDF p.15; proposal confirmed on EDGAR"})
    assert code == 200
    assert _get(server + "/api/state")["review"] == []  # queue drained


def test_lead_label_becomes_gold_case(server, tmp_path):
    s = _get(server + "/api/state")
    lead = s["leads"][0]
    code, _ = _post(server + "/api/act/lead",
                    {"lead_key": lead["lead_key"], "label": "match",
                     "note": "same entity, name variation only",
                     "a": lead["a"], "b": lead["b"]})
    assert code == 200
    s2 = _get(server + "/api/state")
    assert s2["gold_labels"] == 1
    assert s2["leads"] == []  # labeled lead leaves the queue
    # And it feeds the eval gold set.
    from glasshouse.evals import gold_cases
    cases = gold_cases()
    assert any(c["why"] == "same entity, name variation only" for c in cases)


def test_outreach_sent_guard_enforced_server_side(server):
    s = _get(server + "/api/state")
    oid = s["outreach"][0]["id"]
    code, out = _post(server + "/api/act/outreach_sent",
                      {"id": oid, "i_sent_this": False})
    assert code == 400 and "humans only" in out["error"]
    code, _ = _post(server + "/api/act/outreach_sent",
                    {"id": oid, "i_sent_this": True})
    assert code == 200
    code, _ = _post(server + "/api/act/outreach_response",
                    {"id": oid, "summary": "IR replied with a statement"})
    assert code == 200
    assert _get(server + "/api/state")["outreach"][0]["status"] == "sent"


def test_signal_recording(server):
    code, _ = _post(server + "/api/act/signal",
                    {"kind": "citation", "detail": "cited by example outlet",
                     "url": "https://example.org/story"})
    assert code == 200
    assert _get(server + "/api/state")["signals"][0]["detail"] == "cited by example outlet"


def test_page_serves_html(server):
    with urllib.request.urlopen(server + "/", timeout=10) as r:
        body = r.read().decode()
    assert "Workbench" in body and "GLASS" in body
