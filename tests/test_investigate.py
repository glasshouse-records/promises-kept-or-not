"""The investigation engine: connect SAY (commitment) to DO (theme voting
record) as a quantified, cited, finding-shaped result — what a journalist
drives to find a story. Precision guards (polarity) must hold: an AGAINST vote
on an ANTI-theme proposal is not counted as voting against the theme.
"""

import pytest

from glasshouse import investigate, ledger


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme AM')")
    # BlackRock: a real, binding climate commitment (operator-side text file).
    pol = tmp_path / "blk_climate.txt"
    pol.write_text("Our approach to stewardship. We are committed to robust "
                   "climate risk oversight and support emissions reduction at "
                   "the companies our funds hold. We expect boards to manage "
                   "greenhouse gas risk.")
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
              "sha256, content_path, content_type, size_bytes) "
              "VALUES ('blackrock','stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
              ("a" * 64, str(pol)))
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://e','2025-01-01')")

    def vote(issuer, desc, how, shares):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, management_recommendation, shares_voted, is_duplicate) "
                  "VALUES ('ACC',?,?, '05/21/2024', ?, ?, 'AGAINST', ?, 0)",
                  (issuer, "C"+issuer[:6], desc, how, shares))

    # Pro-climate shareholder proposals (advance the theme):
    vote("EXXON", "Shareholder proposal on greenhouse gas emissions reduction targets", "AGAINST", 5000)
    vote("CHEVRON", "Report on climate transition plan and emissions", "AGAINST", 3000)
    vote("APPLE", "Proposal to report on climate risk", "FOR", 1000)
    # ANTI-theme proposal — voting AGAINST it DEFENDS climate; must be EXCLUDED:
    vote("META", "Shareholder proposal to cease climate-related disclosures", "AGAINST", 9000)
    # Off-theme — ignored entirely:
    vote("IBM", "Elect Director Jane Smith", "AGAINST", 200)
    c.commit()
    return c


def test_theme_record_connects_say_and_do(conn):
    recs = {r.institution_id: r for r in investigate.theme_records(conn, "climate")}
    blk = recs["blackrock"]
    assert blk.committed is True
    assert "committed to" in blk.commitment_quote.lower()
    # 2 pro-climate AGAINST + 1 FOR; the anti-theme AGAINST and off-theme are excluded
    assert blk.votes_for == 1
    assert blk.votes_against == 2
    assert blk.n_theme == 3
    assert round(blk.against_rate, 2) == 0.67    # 2 / (2+1)


def test_polarity_guard_excludes_anti_theme_vote(conn):
    blk = next(r for r in investigate.theme_records(conn, "climate") if r.institution_id == "blackrock")
    issuers = {e["issuer_name"] for e in blk.examples}
    assert "META" not in issuers        # anti-theme proposal not counted as against-climate
    assert "IBM" not in issuers         # off-theme
    assert {"EXXON", "CHEVRON"} <= issuers


def test_examples_are_cited(conn):
    blk = next(r for r in investigate.theme_records(conn, "climate") if r.institution_id == "blackrock")
    ex = blk.examples[0]
    for field in ("issuer_name", "meeting_date", "vote_description", "how_voted",
                  "shares_voted", "accession"):
        assert field in ex
    # ordered by shares (biggest stake first)
    assert blk.examples[0]["shares_voted"] >= blk.examples[-1]["shares_voted"]


def test_uncommitted_manager_has_no_say_side(conn):
    acme = next(r for r in investigate.theme_records(conn, "climate") if r.institution_id == "acme")
    assert acme.committed is False
    assert acme.commitment_quote is None
    assert acme.tension == 0.0          # no SAY ⇒ no say-vs-do tension


def test_committed_hypocrisy_ranks_above_uncommitted(conn):
    order = [r.institution_id for r in investigate.theme_records(conn, "climate")]
    assert order.index("blackrock") < order.index("acme")


def test_matrix_has_rates_per_theme(conn):
    m = investigate.theme_matrix(conn)
    assert "blackrock" in m
    assert "climate" in m["blackrock"]
    assert round(m["blackrock"]["climate"], 2) == 0.67


def test_build_matrix_cells_carry_say_and_do(conn):
    m = investigate.build_matrix(conn)
    assert "climate" in m["themes"]
    blk = next(i for i in m["institutions"] if i["id"] == "blackrock")
    cell = blk["cells"]["climate"]
    assert cell["committed"] is True and cell["quote"]
    assert cell["against"] == 2 and cell["for"] == 1
    assert round(cell["rate"], 2) == 0.67
    assert {e["issuer_name"] for e in cell["examples"]} == {"EXXON", "CHEVRON"}
    # acme has no climate commitment and no votes ⇒ no climate cell
    acme = next((i for i in m["institutions"] if i["id"] == "acme"), None)
    assert acme is None or "climate" not in acme["cells"]


def test_cache_matrix_roundtrip(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(investigate, "MATRIX_CACHE", tmp_path / "investigate" / "matrix.json")
    assert investigate.load_matrix() is None
    investigate.cache_matrix(conn)
    loaded = investigate.load_matrix()
    assert loaded and loaded["themes"] and loaded["institutions"]
