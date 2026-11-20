"""COVERAGE.json must not scan every vote line once per institution.

Found 2026-11-20: release 2026-11-20.2 sat in dataset.coverage for over two
hours: each per-institution query joined filings to a subquery over all
shipped votes, so SQLite scanned all 26M vote lines twice per institution
(~40 s each). The per-institution vote set must be reached through the
accession index."""

from glasshouse import dataset, ledger


def test_coverage_vote_queries_use_the_accession_index(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    for sql in dataset.coverage_vote_sql():
        plan = " | ".join(r[3] for r in c.execute("EXPLAIN QUERY PLAN " + sql, ("x",)))
        assert "SCAN votes" not in plan, plan


def test_coverage_counts_unchanged(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X'),('y','Y')")
    for acc, inst in (("A", "x"), ("B", "y")):
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                  "retrieval_date) VALUES (?,?,?,'N-PX','u','2026-01-01')", (acc, acc, inst))
    rows = [("A", "SECURITY HOLDER", "", "FOR", 0), ("A", "ISSUER", "DIRECTOR ELECTIONS", "FOR", 0),
            ("A", "ISSUER", "", "", 0), ("A", "ISSUER", "", "FOR", 1), ("B", "ISSUER", "", "AGAINST", 0)]
    for acc, src, cat, how, dup in rows:
        c.execute("INSERT INTO votes (accession, issuer_name, meeting_date, vote_source, category_type, "
                  "how_voted, is_duplicate) VALUES (?,'I','06/30/2025',?,?,?,?)", (acc, src, cat, how, dup))
    c.commit()
    cov = {r["institution"]: r for r in dataset.coverage(c)}
    assert cov["X"]["votes"] == 2 and cov["X"]["npx_filings"] == 1
    assert cov["X"]["votes_by_kind"] == {"shareholder_proposals": 1, "director_elections": 1}
    assert cov["X"]["vote_dates"] == "2025-06-30 → 2025-06-30"
    assert cov["Y"]["votes"] == 1
