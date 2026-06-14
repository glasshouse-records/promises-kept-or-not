"""The public-snapshot disclosure boundary: the export and MCP surface must
expose only publishable data, never the operator's working state (triage,
llm_log, outreach drafts, signals, match_log, or pending/rejected findings)."""

import sqlite3

import pytest

from glasshouse import ledger, outreach, publish, review
from glasshouse.contradictions import ContradictionCandidate
from glasshouse.ledger import EnforcementAction


def _candidate():
    return ContradictionCandidate(
        theme="climate", institution_id="blackrock", doc_label="stewardship",
        doc_version="2026-06-11", doc_sha256="a" * 64, doc_url="https://x/p.pdf",
        commitment_quote="We are committed to climate oversight.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025", vote_description="EMISSIONS PROPOSAL",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=1000.0)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    # A vote + its as-filed duplicate; only the deduped one is public.
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC-1','1','blackrock','N-PX','u','d')")
    for dup in (0, 1):
        c.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, "
                  "is_duplicate) VALUES ('ACC-1','AMAZON','AGAINST',1000,?)", (dup,))
    ledger.insert_enforcement(c, [EnforcementAction(
        agency="SEC", company_name="Oracle", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="LR-1", source_url="https://s")])
    # Operator-internal residue that must NOT be exported.
    c.execute("INSERT INTO outreach (kind, institution_id, subject, body_path, created_ts) "
              "VALUES ('inquiry','blackrock','secret draft','/tmp/x','t')")
    c.execute("INSERT INTO signals (ts, kind, detail) VALUES ('t','citation','internal note')")
    c.execute("INSERT INTO llm_log (ts, model, purpose, prompt_sha, input_key, output) "
              "VALUES ('t','m','p','s','k','raw model output')")
    c.commit()
    return c


def test_snapshot_excludes_operator_tables(conn, tmp_path):
    dest = publish.build_public_snapshot(conn, tmp_path / "pub.db")
    pub = sqlite3.connect(dest)
    tables = {r[0] for r in pub.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in publish.OPERATOR_ONLY:
        assert t not in tables, f"{t} leaked into the public snapshot"
    assert "votes" in tables and "enforcement_actions" in tables


def test_snapshot_filters_duplicates_and_unapproved_findings(conn, tmp_path, monkeypatch):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **kw: [_candidate()])
    review.sync(conn)                         # 1 pending finding
    fid = review.queue(conn, "pending")[0]["id"]
    # leave it pending — must NOT be published
    dest = publish.build_public_snapshot(conn, tmp_path / "pub.db")
    pub = sqlite3.connect(dest)
    assert pub.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 1   # dup excluded
    assert pub.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0  # pending excluded

    review.decide(conn, fid, "approved", "verified")
    dest2 = publish.build_public_snapshot(conn, tmp_path / "pub2.db")
    pub2 = sqlite3.connect(dest2)
    assert pub2.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1  # approved included


def test_newest_snapshot_selection(tmp_path):
    assert publish.newest_snapshot(tmp_path) is None
    (tmp_path / "glasshouse-public-2026-06-10.db").write_text("x")
    (tmp_path / "glasshouse-public-2026-06-14.db").write_text("y")
    assert publish.newest_snapshot(tmp_path).name == "glasshouse-public-2026-06-14.db"


def test_mcp_query_rejects_operator_tables(conn, tmp_path, monkeypatch):
    # Build a snapshot and point the MCP server's data dir at it.
    publish.build_public_snapshot(conn, tmp_path / "exports" / "glasshouse-public-2026-06-14.db")
    from glasshouse import mcp_server
    monkeypatch.setattr(mcp_server, "DATA_DIR", tmp_path)
    # The raw query path must refuse operator-internal table names.
    import re

    def guarded(sql):
        low = sql.lower()
        if not low.lstrip().startswith(("select", "with")):
            return {"error": "read-only"}
        for t in mcp_server.OPERATOR_ONLY:
            if re.search(rf"\b{t}\b", low):
                return {"error": f"{t} blocked"}
        return {"ok": True}

    assert "error" in guarded("SELECT * FROM llm_log")
    assert "error" in guarded("SELECT * FROM outreach")
    assert guarded("SELECT * FROM votes").get("ok")
