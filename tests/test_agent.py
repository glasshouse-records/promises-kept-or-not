"""The findings agent: it investigates and DRAFTS cited story leads, and it
must respect the charter's gate — drafts only, never findings, never sent.
"""

import pytest

from glasshouse import agent, ledger


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "BRIEFS_DIR", tmp_path / "agent" / "briefs")
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    pol = tmp_path / "pol.txt"
    pol.write_text("We are committed to climate risk oversight and support emissions "
                   "reduction at the companies our funds hold.")
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256, "
              "content_path, content_type, size_bytes) VALUES "
              "('blackrock','stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
              ("a" * 64, str(pol)))
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://e','2025-01-01')")

    def vote(issuer, desc, how):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
                  "how_voted, shares_voted, is_duplicate) VALUES ('ACC',?,?, '05/21/2024', ?, ?, 100, 0)",
                  (issuer, "C" + issuer[:5], desc, how))
    for i in range(8):
        vote(f"CO{i}", "Shareholder proposal on greenhouse gas emissions reduction", "AGAINST")
    vote("COX", "Report on climate transition plan", "FOR")
    c.commit()
    return c


def test_agent_drafts_a_cited_lead(conn):
    briefs = agent.investigate_and_draft(conn, min_rate=0.5, min_votes=3, top_n=5)
    assert briefs, "expected at least one drafted lead"
    b = briefs[0]
    assert b["institution_id"] == "blackrock" and b["theme"] == "climate"
    assert "BlackRock" in b["headline"] and "climate" in b["headline"]
    # the body is a cited draft, framed as a lead, quoting SAY and citing DO
    assert "committed to climate" in b["body"].lower()
    assert "DRAFT" in b["body"] and "lead" in b["body"].lower()
    assert "N-PX" in b["body"]                       # DO is cited


def test_agent_writes_drafts_to_disk_not_ledger(conn):
    before = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    agent.investigate_and_draft(conn, min_rate=0.5, min_votes=3, top_n=5)
    after = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert after == before, "agent must NOT write to the findings table"
    # drafts landed on disk for human review
    runs = list((agent.BRIEFS_DIR).glob("*/index.json"))
    assert runs, "expected an index.json of drafted briefs"
    md = list((agent.BRIEFS_DIR).glob("*/blackrock--climate.md"))
    assert md and "DRAFT" in md[0].read_text()


def test_llm_polish_falls_back_when_unconfigured(conn, monkeypatch):
    """llm=True must not break without an API key — it falls back to the
    deterministic draft, and never silently drops the lead."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    briefs = agent.investigate_and_draft(conn, min_rate=0.5, min_votes=3, top_n=5, llm=True)
    assert briefs and "commits to climate" in briefs[0]["headline"].lower()
    assert "N-PX" in briefs[0]["body"]              # cited evidence still deterministic


def test_thresholds_gate_weak_leads(conn):
    # require more votes than exist ⇒ nothing drafted (no over-claiming)
    assert agent.investigate_and_draft(conn, min_rate=0.5, min_votes=999, top_n=5) == []
    # require a higher rate than reality ⇒ nothing
    assert agent.investigate_and_draft(conn, min_rate=0.99, min_votes=1, top_n=5) == []
