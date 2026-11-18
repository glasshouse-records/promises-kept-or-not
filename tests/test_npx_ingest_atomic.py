"""A filing is ingested whole or not at all.

Found 2026-11-16: an SEC 503 while listing a filing's exhibits killed the run
for the whole manager, and a failure between two vote-table exhibits would have
left a filing recorded with part of its votes — then skipped as "already
ingested" on every later run. A silently short filing is a false data point.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from glasshouse import http, ledger
from glasshouse.ingest import npx
from glasshouse.ingest.edgar import Filing

FIX = Path(__file__).parent / "fixtures"


def _filing(n: int) -> Filing:
    return Filing(cik="0000000001", company_name="T", form_type="N-PX",
                  filing_date="2026-08-28", period_of_report="2026-06-30",
                  accession_number=f"0000000001-26-00000{n}")


@pytest.fixture()
def world(tmp_path, monkeypatch):
    conn = ledger.connect(tmp_path / "l.db")
    cover = (FIX / "npx_cover_notice.xml").read_bytes().replace(
        b"FUND NOTICE REPORT", b"FUND VOTING REPORT")
    state = {"fail": True}

    class R:
        content = cover

    monkeypatch.setattr(http, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(npx, "list_filings", lambda *a, **k: [_filing(1), _filing(2)])
    monkeypatch.setattr(http, "get", lambda url, **k: R())
    monkeypatch.setattr(npx, "find_vote_table_exhibits",
                        lambda f: [f"{f.directory_url}/a.xml", f"{f.directory_url}/b.xml"])

    def download(url, dest, **k):
        if state["fail"] and url.endswith("26000001/b.xml"):
            raise ConnectionError("503")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / "npx_sample.xml", dest)
        return dest

    monkeypatch.setattr(http, "download", download)
    return conn, state


def _counts(conn):
    return dict(conn.execute("SELECT accession, COUNT(*) FROM votes GROUP BY accession"))


def test_a_filing_that_fails_midway_leaves_nothing_and_the_run_goes_on(world):
    conn, state = world
    stats = npx.ingest_npx(conn, "1")
    bad, good = _filing(1).accession_number, _filing(2).accession_number
    assert conn.execute("SELECT COUNT(*) FROM filings WHERE accession=?",
                        (bad,)).fetchone()[0] == 0
    assert bad not in _counts(conn)
    assert _counts(conn)[good] > 0 and stats["filings"] == 1

    state["fail"] = False                     # next run: SEC is back
    npx.ingest_npx(conn, "1")
    assert _counts(conn)[bad] == _counts(conn)[good]


def test_ingest_marks_duplicates_before_returning(world):
    """Found 2026-11-18: ingest left repeated exhibit rows unflagged and ~107k
    duplicates shipped as distinct votes. Both fixture exhibits are the same
    table, so every row of the second copy must be flagged on return."""
    conn, state = world
    state["fail"] = False
    npx.ingest_npx(conn, "1")
    total, dups = conn.execute("SELECT COUNT(*), SUM(is_duplicate) FROM votes").fetchone()
    unique = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT issuer_name, cusip, meeting_date, "
        "vote_description, vote_series, how_voted, shares_voted FROM votes)").fetchone()[0]
    assert dups > 0 and total - dups == unique
    assert ledger.duplicate_flags_stale(conn) == ""
