"""SAI-printed policy versions: section-extracted, dated by the EDGAR filing date.

A fund SAI reproduces the sub-adviser's proxy policy in an appendix; the filing
date proves the text was public by then. Precision rules: a marker that is not
found cleanly records NOTHING (a wrong section is a false data point)."""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.ingest import sai_appendix as sai

START = "APPENDIX A: PROXY VOTING POLICIES"
END = "APPENDIX B: CREDIT RATINGS"
BODY = "Wellington votes against directors who fail to act on majority votes. " * 6


def doc(body=BODY, start=START, end=END):
    return f"intro text {start} {body} {end} tail text"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(sai.cm, "COMMITMENTS_DIR", tmp_path / "commitments")
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('wel','Wellington')")
    c.commit()
    return c


def test_extracts_text_between_markers():
    out = sai.extract_section(doc(), START, END)
    assert out is not None and out.startswith(START) and BODY.strip() in out
    assert "tail text" not in out and "intro text" not in out and END not in out


def test_start_found_twice_gives_nothing():
    assert sai.extract_section(doc() + " " + doc(), START, END) is None


def test_missing_start_or_end_gives_nothing():
    assert sai.extract_section(f"x {START} {BODY} y", START, END) is None
    assert sai.extract_section(f"x {BODY} {END} y", START, END) is None


def test_end_before_start_gives_nothing():
    assert sai.extract_section(f"{END} {START} {BODY}", START, END) is None


def test_identical_copies_allowed_only_when_opted_in():
    twice = doc() + " " + doc()
    assert sai.extract_section(twice, START, END) is None
    assert sai.extract_section(twice, START, END, allow_identical_copies=True) is not None
    differing = doc() + " " + doc(BODY + " and one more sentence.")
    assert sai.extract_section(differing, START, END, allow_identical_copies=True) is None


def test_whitespace_only_difference_is_same_text():
    a = sai.extract_section(doc(), START, END)
    b = sai.extract_section(doc().replace(" ", "\n  \t"), START, END)
    assert a == b


def _filing(acc, date_, text):
    return {"accession": acc, "filing_date": date_, "url": f"https://sec/{acc}.htm", "text": text}


def test_same_text_in_two_filings_is_one_version_dated_by_earlier(conn):
    # presented newest first, as EDGAR lists them
    fs = [_filing("B", "2025-06-01", doc()), _filing("A", "2024-02-01", doc().replace(" ", "\n"))]
    n = sai.ingest_filings(conn, "wel", "wel-sai", fs, START, END)
    rows = conn.execute("SELECT public_by, url, via FROM commitments").fetchall()
    assert n == 1 and len(rows) == 1
    assert rows[0]["public_by"] == "2024-02-01" and rows[0]["url"].endswith("A.htm")
    assert rows[0]["via"] == "edgar-sai"


def test_earlier_filing_found_later_backdates_the_version(conn):
    sai.ingest_filings(conn, "wel", "wel-sai", [_filing("B", "2025-06-01", doc())], START, END)
    sai.ingest_filings(conn, "wel", "wel-sai", [_filing("A", "2024-02-01", doc())], START, END)
    rows = conn.execute("SELECT public_by, url FROM commitments").fetchall()
    assert len(rows) == 1 and rows[0]["public_by"] == "2024-02-01"


def test_different_text_is_two_versions(conn):
    fs = [_filing("A", "2024-02-01", doc()),
          _filing("B", "2025-06-01", doc(BODY + " A new amendment was adopted."))]
    assert sai.ingest_filings(conn, "wel", "wel-sai", fs, START, END) == 2
    got = conn.execute("SELECT public_by FROM commitments ORDER BY public_by").fetchall()
    assert [r[0] for r in got] == ["2024-02-01", "2025-06-01"]


def test_unextractable_filing_records_nothing(conn):
    fs = [_filing("A", "2024-02-01", "no policy here"), _filing("B", "2025-01-01", doc() + doc())]
    assert sai.ingest_filings(conn, "wel", "wel-sai", fs, START, END) == 0
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


def test_identity_ignores_all_whitespace_and_file_is_custodied(conn):
    import hashlib
    sai.ingest_filings(conn, "wel", "wel-sai", [_filing("A", "2024-02-01", doc())], START, END)
    r = conn.execute("SELECT * FROM commitments").fetchone()
    text = sai.extract_section(doc(), START, END)
    assert r["text_sha256"] == hashlib.sha256("".join(text.split()).encode()).hexdigest()
    assert ledger.integrity_check(conn)["commitments_custody"] == []


def test_html_spacing_before_punctuation_is_not_a_difference():
    a = sai.extract_section(doc("Vote AGAINST 1 . Attendance , and more ; fine ."), START, END)
    b = sai.extract_section(doc("Vote AGAINST 1. Attendance, and more; fine."), START, END)
    assert a == b


def test_page_numbers_stripped_only_when_opted_in():
    body = "Votes are cast in the client's interest. 94 Reconciliation of proxies follows. 97"
    plain = sai.extract_section(doc(body), START, END)
    assert "94 Reconciliation" in plain
    clean = sai.extract_section(doc(body), START, END, strip_page_numbers=True)
    assert "94" not in clean and "97" not in clean and "Reconciliation of proxies follows." in clean
    # a repagination must not look like a new version
    moved = sai.extract_section(doc(body.replace("94", "95").replace("97", "98")), START, END,
                                strip_page_numbers=True)
    assert moved == clean


def test_changed_extraction_rebuilds_instead_of_leaving_stale_rows(conn):
    sai.ingest_filings(conn, "wel", "wel-sai", [_filing("A", "2024-02-01", doc())], START, END)
    assert sai.purge_label(conn, "wel", "wel-sai") == 1
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0
    # other lineages are never touched
    conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256,"
                 " content_path) VALUES ('wel','site-pdf','u','2026-01-01','x','p')")
    conn.commit()
    assert sai.purge_label(conn, "wel", "wel-sai") == 0
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 1


def test_spacing_artifacts_from_html_inline_tags_are_not_a_new_version(conn):
    """Observed live on Geode: 'Issuer-specific' vs 'Issuer -specific' and
    '"excessive"' vs '" excessive "' are tag-boundary spacing, not edits."""
    a = doc("Vote AGAINST where Geode deems \"excessive\" for issuer-specific reasons.")
    b = doc("Vote AGAINST where Geode deems \" excessive \" for issuer -specific reasons.")
    fs = [_filing("A", "2025-01-01", a), _filing("B", "2025-06-01", b)]
    assert sai.ingest_filings(conn, "wel", "wel-sai", fs, START, END) == 1
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 1
