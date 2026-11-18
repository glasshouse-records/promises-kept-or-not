"""Release and doctor refuse when votes are newer than the last dedupe run."""

from glasshouse import doctor, ledger


def _vote(c):
    c.execute("INSERT OR IGNORE INTO filings (accession, cik, form_type, source_url, "
              "retrieval_date) VALUES ('A','1','N-PX','https://e','2026-06-11')")
    c.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted) "
              "VALUES ('A','X','FOR',1)")
    c.commit()


def test_stale_then_current(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    assert ledger.duplicate_flags_stale(c) == ""          # no votes, nothing to be stale
    _vote(c)
    assert "stale" in ledger.duplicate_flags_stale(c)
    errs = [x for x in doctor.diagnose(c)["checks"]
            if x["name"] == "votes:duplicate-flags"]
    assert errs[0]["severity"] == "error" and not errs[0]["ok"]
    ledger.dedupe_votes(c)
    assert ledger.duplicate_flags_stale(c) == ""
    _vote(c)
    assert "stale" in ledger.duplicate_flags_stale(c)


def test_release_refuses_when_stale(tmp_path):
    import pytest

    from glasshouse import release
    c = ledger.connect(tmp_path / "l.db")
    _vote(c)
    with pytest.raises(release.StaleEngineError, match="duplicate flags"):
        release.build_release(c, root=tmp_path, version="x", with_parquet=False,
                              no_derived=True)
    assert not (tmp_path / "vx").exists()


def _two_filers(c):
    for acc, cik in (("A", "1"), ("B", "2")):
        c.execute("INSERT INTO filings (accession, cik, form_type, source_url, "
                  "retrieval_date) VALUES (?,?,'N-PX','https://e','2026-06-11')", (acc, cik))
        for _ in range(2):
            c.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted) "
                      "VALUES (?,'X','FOR',1)", (acc,))
    c.commit()


def test_scoped_dedupe_touches_only_its_filer_and_keeps_the_guard_honest(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _two_filers(c)
    assert ledger.dedupe_votes(c, ciks=["1"]) == 1
    flags = dict(c.execute("SELECT accession, SUM(is_duplicate) FROM votes GROUP BY accession"))
    assert flags == {"A": 1, "B": 0}
    assert "stale" in ledger.duplicate_flags_stale(c)   # filer 2 is still unchecked
    assert ledger.dedupe_votes(c, ciks=["2"]) == 1
    assert "stale" in ledger.duplicate_flags_stale(c)   # a scoped run can't vouch for the rest
    assert ledger.dedupe_votes(c) == 2                  # only a full run closes the gap
    assert ledger.duplicate_flags_stale(c) == ""
