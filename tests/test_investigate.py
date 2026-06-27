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
    # A 13-F holding so company-scan can join holdings × votes:
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC13F','1','blackrock','13F-HR','https://e13','2025-02-01')")
    c.execute("INSERT INTO holdings (accession, issuer_name, cusip, value_usd, shares) "
              "VALUES ('ACC13F','EXXON MOBIL CORP','CEXXON',5000000000,1000)")
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


def test_company_record_joins_holdings_and_votes(conn):
    r = investigate.company_record(conn, "EXXON")
    assert "EXXON" in r["company"].upper()
    blk = next(h for h in r["holders"] if h["institution_id"] == "blackrock")
    assert blk["held_usd"] == 5000000000           # from the 13-F holding
    assert blk["votes_against"] >= 1               # voted AGAINST at Exxon
    ex = blk["examples"][0]
    assert "climate" in ex["themes"]               # the AGAINST vote is theme-tagged
    assert ex["accession"] == "ACC" and ex["source_url"] == "https://e"


def test_theme_trend_by_year(conn):
    tr = investigate.theme_trend(conn, "climate")
    blk = tr.get("blackrock")
    assert blk and "2024" in blk["years"]          # fixture votes are dated 2024
    assert blk["years"]["2024"]["against"] == 2 and blk["years"]["2024"]["for"] == 1
    assert round(blk["years"]["2024"]["rate"], 2) == 0.67
    # acme has no climate commitment ⇒ excluded from the say-vs-do trend
    assert "acme" not in tr


def test_custom_keyword_hypothesis(conn):
    """A journalist can test their own hypothesis via keywords, not just the
    5 built-in themes. 'greenhouse,emission' should rediscover the climate-ish
    votes (the policy text also mentions emissions, so BlackRock is committed)."""
    recs = investigate.theme_records(conn, "my-test", keywords=["greenhouse", "emission"])
    blk = next(r for r in recs if r.institution_id == "blackrock")
    assert blk.theme == "my-test"
    assert blk.committed is True            # policy mentions emissions reduction
    assert blk.votes_against >= 1
    assert {"EXXON", "CHEVRON"} & {e["issuer_name"] for e in blk.examples}


def test_evidence_pack_is_cited_markdown(conn):
    blk = next(r for r in investigate.theme_records(conn, "climate") if r.institution_id == "blackrock")
    pack = investigate.evidence_pack(blk, hypothesis="test hypothesis")
    assert "# BlackRock Inc. — climate" in pack
    assert "test hypothesis" in pack
    assert "What it says" in pack and "What it does" in pack
    assert blk.commitment_quote[:20] in pack          # SAY cited
    assert "EXXON" in pack and "N-PX" in pack          # DO cited
    assert "verify" in pack.lower()                    # framed as a lead


def test_examples_carry_source_url(conn):
    blk = next(r for r in investigate.theme_records(conn, "climate") if r.institution_id == "blackrock")
    assert all("source_url" in e for e in blk.examples)
    assert blk.examples[0]["source_url"] == "https://e"


def test_cache_matrix_roundtrip(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(investigate, "MATRIX_CACHE", tmp_path / "investigate" / "matrix.json")
    assert investigate.load_matrix() is None
    investigate.cache_matrix(conn)
    loaded = investigate.load_matrix()
    assert loaded and loaded["themes"] and loaded["institutions"]
