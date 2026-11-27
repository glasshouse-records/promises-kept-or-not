"""legacy_parse stores the guard stats and parser_version; integrity checks for legacy rows."""
import pytest
from test_legacy_pe import BASIC, HDR, _filing

from glasshouse import ledger
from glasshouse.ingest import legacy_pe

NEW_COLS = {"rows_dropped_disputed", "meetings_dropped_disputed", "order_resets",
            "order_repeats", "rows_dropped_order", "parser_version"}


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('jpm','JPM')")
    return c


def test_parser_version_constant():
    assert legacy_pe.PARSER_VERSION == "2026-11-27"


def test_migration_adds_guard_columns_idempotently(tmp_path):
    p = tmp_path / "old.db"
    c = ledger.connect(p)
    for col in NEW_COLS:
        c.execute(f"ALTER TABLE legacy_parse DROP COLUMN {col}")
    c.commit()
    c.close()
    for _ in range(2):
        c = ledger.connect(p)
    assert {r[1] for r in c.execute("PRAGMA table_info(legacy_parse)")} >= NEW_COLS


def test_record_filing_stores_guard_stats_and_version(conn):
    legacy_pe.ingest_filing(conn, _filing(), "jpm", "2026-11-22", {"doc.txt": BASIC}, HDR)
    s = conn.execute("SELECT * FROM legacy_parse").fetchone()
    assert s["parser_version"] == legacy_pe.PARSER_VERSION
    for k in NEW_COLS - {"parser_version"}:
        assert isinstance(s[k], int)


def _vote(conn, acc, rec, fmt="proxyedge"):
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, cusip, isin, meeting_date, vote_description,"
        " category_type, vote_source, vote_series, how_voted, management_recommendation,"
        " legacy_format) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (acc, "X", "", "", "01/01/2023", "p", "", "ISSUER", "S1", "FOR", rec, fmt))


def test_integrity_flags_bad_legacy_management_recommendation(conn):
    legacy_pe.ingest_filing(conn, _filing(), "jpm", "2026-11-22", {"doc.txt": BASIC}, HDR)
    acc = _filing().accession_number
    for rec in ("FOR", "AGAINST", ""):
        _vote(conn, acc, rec)
    conn.commit()
    assert ledger.integrity_check(conn)["legacy_bad_management_recommendation"] == []
    _vote(conn, acc, "ABSTAIN")
    _vote(conn, acc, None)
    conn.commit()
    bad = ledger.integrity_check(conn)["legacy_bad_management_recommendation"]
    assert sorted(str(b[2]) for b in bad) == ["ABSTAIN", "None"]


def test_xml_rows_are_not_checked(conn):
    legacy_pe.ingest_filing(conn, _filing(), "jpm", "2026-11-22", {"doc.txt": BASIC}, HDR)
    _vote(conn, _filing().accession_number, "ABSTAIN", fmt=None)
    conn.commit()
    assert ledger.integrity_check(conn)["legacy_bad_management_recommendation"] == []


def test_stale_parser_version_listing(conn):
    legacy_pe.ingest_filing(conn, _filing(), "jpm", "2026-11-22", {"doc.txt": BASIC}, HDR)
    assert ledger.legacy_stale_parser_filings(conn) == []
    conn.execute("UPDATE legacy_parse SET parser_version = '2026-11-21'")
    conn.commit()
    assert [r[0] for r in ledger.legacy_stale_parser_filings(conn)] == [_filing().accession_number]
    conn.execute("UPDATE legacy_parse SET parser_version = NULL")
    conn.commit()
    assert len(ledger.legacy_stale_parser_filings(conn)) == 1
    conn.execute("UPDATE filings SET report_type = 'LEGACY_PROXYEDGE_REJECTED'")
    conn.commit()
    assert ledger.legacy_stale_parser_filings(conn) == []    # only ACCEPTED filings
