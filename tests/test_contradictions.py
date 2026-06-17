import pytest

from glasshouse import ledger
from glasshouse.contradictions import commitment_sentences, find_commitment_vote_contradictions


@pytest.fixture
def conn(tmp_path):
    return ledger.connect(tmp_path / "test.db")


def test_commitment_sentences_quote_verbatim_policy_language():
    text = ("We expect companies to maintain robust anti-corruption policies. "
            "Unrelated sentence about index funds. "
            "Our approach to climate risk reflects the goals of the Paris Agreement.")
    hits = commitment_sentences(text, [r"anti-?corruption"])
    assert hits == ["We expect companies to maintain robust anti-corruption policies."]
    assert commitment_sentences(text, [r"climate"])[0].startswith("Our approach to climate")


def _setup(conn, tmp_path, *, vote_desc, how="AGAINST", mgmt="AGAINST"):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    policy = tmp_path / "policy.txt"
    policy.write_text("We are committed to strong anti-corruption practices at investee companies.")
    conn.execute(
        # Policy in force BEFORE the 2024-11-15 vote (temporal alignment).
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256, "
        "content_path, content_type, size_bytes) VALUES "
        "('blackrock', 'stewardship', 'https://x/p.pdf', '2024-01-01', 'abc123', ?, 'text/plain', 1)",
        (str(policy),))
    conn.execute(
        "INSERT INTO filings (accession, cik, institution_id, form_type, source_url, retrieval_date) "
        "VALUES ('ACC-1', '1100663', 'blackrock', 'N-PX', 'https://sec.gov/x', '2026-06-11')")
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
        "how_voted, shares_voted, management_recommendation) "
        "VALUES ('ACC-1', 'ORACLE CORP', '68389X105', '2024-11-15', ?, ?, 1250000, ?)",
        (vote_desc, how, mgmt))


def test_say_do_join_produces_quarantined_candidate_with_citation_chain(conn, tmp_path):
    _setup(conn, tmp_path,
           vote_desc="Shareholder proposal: report on anti-corruption accountability")
    rows = find_commitment_vote_contradictions(conn)
    assert len(rows) == 1
    r = rows[0]
    assert r.theme == "anti-corruption"
    assert r.quarantined is True
    # Full citation chain present on both sides.
    assert "anti-corruption" in r.commitment_quote
    assert r.doc_version == "2024-01-01" and r.doc_sha256 == "abc123"
    assert r.accession == "ACC-1" and r.issuer_name == "ORACLE CORP"
    assert r.how_voted == "AGAINST" and r.shares_voted == 1_250_000


def test_for_votes_do_not_qualify(conn, tmp_path):
    # FOR votes on theme proposals are consistent with the commitment, not
    # contradictions; they must not appear regardless of management's rec.
    _setup(conn, tmp_path,
           vote_desc="Shareholder proposal: report on anti-corruption accountability",
           how="FOR", mgmt="AGAINST")
    assert find_commitment_vote_contradictions(conn) == []


def test_against_votes_qualify_whatever_management_recommended(conn, tmp_path):
    # Say-on-climate shape: management sponsored the climate plan (mgmt FOR),
    # the fund voted AGAINST — still a reviewable say-do candidate.
    _setup(conn, tmp_path,
           vote_desc="Approve the company's climate transition action plan",
           how="AGAINST", mgmt="FOR")
    policy = conn.execute("SELECT content_path FROM commitments").fetchone()[0]
    from pathlib import Path
    Path(policy).write_text("Our approach to climate risk informs our voting.")
    Path(policy + ".txt").unlink(missing_ok=True)
    rows = find_commitment_vote_contradictions(conn)
    assert len(rows) == 1
    assert rows[0].theme == "climate"
    assert rows[0].management_recommendation == "FOR"


def test_promise_language_outranks_definitional_filler():
    from glasshouse.contradictions import score_commitment_sentence
    weak = "Examples of environmental issues include, but are not limited to, water use and climate risk."
    strong = "We expect companies to disclose how climate risk is overseen by the board."
    binding = "We are committed to engaging on climate risk."
    assert score_commitment_sentence(strong) > score_commitment_sentence(weak)
    assert score_commitment_sentence(binding) > score_commitment_sentence(weak)
    # And the ordering shows up in commitment_sentences output.
    hits = commitment_sentences(f"{weak} {strong}", [r"climate"])
    assert hits[0] == strong


def test_off_theme_votes_do_not_match(conn, tmp_path):
    _setup(conn, tmp_path, vote_desc="Election of director Jane Doe")
    assert find_commitment_vote_contradictions(conn) == []
