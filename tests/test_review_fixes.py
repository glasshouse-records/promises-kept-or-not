"""TDD round from the superpowers-style code review (written RED, before
the fixes): CSRF origin guard, malformed-JSON handling, no-write reads,
and the votes(accession) index."""

import json
import urllib.error
import urllib.request

import pytest

from glasshouse import ledger, workbench


@pytest.fixture
def server(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(workbench, "DB_PATH", db)
    monkeypatch.setattr(workbench, "LABELS_PATH", tmp_path / "labels" / "l.jsonl")
    ledger.connect(db).close()
    srv = workbench.serve(port=0)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, body: bytes, headers: dict | None = None):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_cross_origin_posts_are_rejected(server):
    """A malicious page in the operator's browser must not be able to forge
    ledger decisions via fetch() to localhost (CSRF)."""
    code, body = _post(server + "/api/act/signal",
                       json.dumps({"kind": "other", "detail": "forged"}).encode(),
                       headers={"Origin": "https://evil.example"})
    assert code == 403
    assert b"origin" in body.lower()
    # Same-origin (the workbench page itself) still works.
    code, _ = _post(server + "/api/act/signal",
                    json.dumps({"kind": "other", "detail": "legit"}).encode(),
                    headers={"Origin": server})
    assert code == 200


def test_malformed_json_returns_400_not_dropped_connection(server):
    code, body = _post(server + "/api/act/signal", b"{not json")
    assert code == 400
    assert b"error" in body


def test_state_reads_do_not_write(server, tmp_path):
    """GET /api/state must not take the write lock (it ran a 20-row registry
    upsert per request before the fix)."""
    db = tmp_path / "test.db"
    before = db.stat().st_mtime_ns
    for _ in range(2):
        with urllib.request.urlopen(server + "/api/state", timeout=10) as r:
            assert r.status == 200
    assert db.stat().st_mtime_ns == before


def test_votes_accession_is_indexed(tmp_path):
    conn = ledger.connect(tmp_path / "t.db")
    names = {r[1] for r in conn.execute("PRAGMA index_list(votes)")}
    assert any("accession" in n for n in names)
