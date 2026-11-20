"""An N-PX/A that restates a vote supersedes the earlier line (found 2026-11-19).

First Trust's 2026 N-PX/A for four trusts restated share counts, so the
original lines (different shares_voted) were not exact duplicates and 56,840
of them stayed is_duplicate = 0: summing shares counted those votes twice.
Morgan Stanley had 290 such lines in a 2025 filing. Supersession is per ballot
item (issuer, cusip, meeting, proposal, series), so an amendment that only
adds missing records leaves the original's other lines alone."""

from glasshouse import ledger


def _filing(c, acc, form, date, cik="1", period="06/30/2026"):
    c.execute("INSERT INTO filings (accession, cik, form_type, filing_date, period_of_report, "
              "source_url, retrieval_date) VALUES (?,?,?,?,?,'https://e','2026-11-19')",
              (acc, cik, form, date, period))


def _vote(c, acc, issuer, how, shares, series="S1"):
    c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
              "vote_series, how_voted, shares_voted) VALUES (?,?,'C','05/01/2026','Elect A',?,?,?)",
              (acc, issuer, series, how, shares))


def _live(c):
    return sorted(tuple(r) for r in c.execute("SELECT accession, issuer_name, how_voted, shares_voted FROM votes "
                                              "WHERE is_duplicate = 0"))


def test_restated_amendment_supersedes_the_original_item(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O", "N-PX", "2026-08-24")
    _filing(c, "A", "N-PX/A", "2026-08-25")
    _vote(c, "O", "X", "FOR", 100)        # restated in the amendment (split vote)
    _vote(c, "O", "X", "AGAINST", 50)
    _vote(c, "O", "Y", "FOR", 10)         # not in the amendment: stays
    _vote(c, "A", "X", "FOR", 120)
    _vote(c, "A", "X", "AGAINST", 30)
    _vote(c, "A", "Z", "FOR", 5)          # new record added by the amendment
    c.commit()
    ledger.dedupe_votes(c)
    assert _live(c) == [("A", "X", "AGAINST", 30), ("A", "X", "FOR", 120),
                        ("A", "Z", "FOR", 5), ("O", "Y", "FOR", 10)]
    assert ledger.duplicate_flags_stale(c) == ""


def test_latest_amendment_wins_and_other_filers_and_periods_are_untouched(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O", "N-PX", "2026-08-24")
    _filing(c, "A1", "N-PX/A", "2026-08-25")
    _filing(c, "A2", "N-PX/A", "2026-09-01")
    _filing(c, "P", "N-PX", "2025-08-20", period="06/30/2025")   # other period
    _filing(c, "Q", "N-PX", "2026-08-24", cik="2")               # other filer
    for acc, n in (("O", 1), ("A1", 2), ("A2", 3), ("P", 4), ("Q", 5)):
        _vote(c, acc, "X", "FOR", n)
    c.commit()
    ledger.dedupe_votes(c)
    assert _live(c) == [("A2", "X", "FOR", 3), ("P", "X", "FOR", 4), ("Q", "X", "FOR", 5)]


def test_scoped_run_applies_supersession_too(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O", "N-PX", "2026-08-24")
    _filing(c, "A", "N-PX/A", "2026-08-25")
    _vote(c, "O", "X", "FOR", 1)
    _vote(c, "A", "X", "FOR", 2)
    c.commit()
    ledger.dedupe_votes(c, ciks=["1"])
    assert _live(c) == [("A", "X", "FOR", 2)]


def test_two_originals_without_an_amendment_are_not_superseded(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O1", "N-PX", "2026-08-24")
    _filing(c, "O2", "N-PX", "2026-08-30")
    _vote(c, "O1", "X", "FOR", 1)
    _vote(c, "O2", "X", "FOR", 2)
    c.commit()
    ledger.dedupe_votes(c)
    assert len(_live(c)) == 2
