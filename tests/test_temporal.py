"""Temporal alignment — the engine must quote the policy version in force ON
OR BEFORE the vote, never accuse an institution of breaking a commitment it
hadn't yet made. Surfaced 2026-06-15 by a simulated reviewer panel: 40% of
candidates quoted a 2026 policy against 2024-2025 votes."""

import pytest

from glasshouse import ledger
from glasshouse.contradictions import _yyyymmdd, find_commitment_vote_contradictions


def test_yyyymmdd_parses_all_formats():
    assert _yyyymmdd("05/21/2025") == "20250521"   # N-PX meeting date
    assert _yyyymmdd("2026-06-11") == "20260611"   # ISO retrieval date
    assert _yyyymmdd("20220117225925") == "20220117"  # Wayback timestamp
    assert _yyyymmdd("") == "" and _yyyymmdd("n/a") == ""


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vanguard','Vanguard')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('A1','1','vanguard','N-PX','u','d')")
    c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
              "how_voted, shares_voted) VALUES ('A1','AMAZON','C1','05/21/2024',"
              "'Shareholder proposal requesting a report on climate risk','AGAINST',1000)")
    return c


def _add_version(c, content_path, version, text):
    from pathlib import Path
    p = Path(content_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256, "
              "content_path, content_type, size_bytes, wayback_timestamp) VALUES "
              "('vanguard','stewardship','https://x/p.txt',?,?,?,'text/plain',1,?)",
              (version if "-" in version else "", version[:10] if "-" in version else version,
               content_path, "" if "-" in version else version))
    c.commit()


def test_vote_not_paired_with_a_later_policy(conn, tmp_path):
    # Only policy version is dated AFTER the 2024 vote → no fair contradiction.
    _add_version(conn, str(tmp_path / "v2026.txt"), "20260611000000",
                 "We are committed to robust climate risk oversight in our voting.")
    cands = find_commitment_vote_contradictions(conn)
    assert cands == []  # cannot quote a 2026 promise against a 2024 vote


def test_vote_paired_with_the_in_force_earlier_policy(conn, tmp_path):
    # A 2022 policy (in force at the 2024 vote) AND a 2026 one. The engine must
    # quote the 2022 version, not the anachronistic 2026 one.
    _add_version(conn, str(tmp_path / "v2022.txt"), "20220301000000",
                 "We expect companies to disclose climate risk; we will hold boards accountable.")
    _add_version(conn, str(tmp_path / "v2026.txt"), "20260611000000",
                 "We are committed to a brand new 2026 climate stance never seen before.")
    cands = find_commitment_vote_contradictions(conn)
    assert len(cands) == 1
    assert cands[0].doc_version == "20220301000000"   # the in-force version
    assert "2026" not in cands[0].commitment_quote     # not the anachronistic one
