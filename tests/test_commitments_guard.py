"""Error-page guard for the commitments ledger — found 2026-06 when 6 of 7
archived Vanguard 'policy versions' were the site's 404 page (rotted URL,
captured repeatedly by Wayback), masquerading as policy drift and silently
killing the contradiction engine for Vanguard."""

import pytest

from glasshouse import ledger
from glasshouse.ingest import commitments

_REAL_PDF = b"%PDF-1.7\nWe are committed to climate risk oversight in our voting.\n%%EOF\n"
_404_HTML = (b"<!DOCTYPE HTML><html lang=en><head><title>404 Error - Page not "
             b"found | Vanguard</title></head><body>Sorry.</body></html>")
_REAL_HTML = (b"<!doctype html><html><head><title>Proxy Voting Policy</title></head>"
              b"<body>We expect boards to disclose climate-related risks.</body></html>")


def test_detects_error_pages_not_real_docs():
    assert commitments.looks_like_error_page(_404_HTML, "text/html") is True
    assert commitments.looks_like_error_page(_REAL_HTML, "text/html") is False
    # A real PDF's bytes must never trip the HTML-only check.
    assert commitments.looks_like_error_page(_REAL_PDF, "application/pdf") is False


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "commitments")
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vanguard','Vanguard')")
    return c


def test_record_snapshot_rejects_error_pages(conn):
    assert commitments.record_snapshot(conn, "vanguard", "policy", "https://x/p.pdf",
                                       _REAL_PDF, "application/pdf") is True
    # A 404 captured for the same rotted URL must NOT become a version.
    assert commitments.record_snapshot(conn, "vanguard", "policy", "https://x/p.pdf",
                                       _404_HTML, "text/html",
                                       wayback_timestamp="20260520205008") is False
    n = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
    assert n == 1  # only the real doc is on record


def test_purge_removes_previously_ingested_error_pages(conn, monkeypatch, tmp_path):
    # Simulate the pre-guard state: write a 404 row directly (bypassing the guard).
    monkeypatch.setattr(commitments, "looks_like_error_page", lambda *a, **k: False)
    commitments.record_snapshot(conn, "vanguard", "policy", "https://x/p.pdf",
                                _REAL_PDF, "application/pdf")
    commitments.record_snapshot(conn, "vanguard", "policy", "https://x/p.pdf",
                                _404_HTML, "text/html", wayback_timestamp="20260520205008")
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 2

    # Now purge with the real detector restored.
    monkeypatch.undo()
    purged = commitments.purge_error_pages(conn)
    assert purged == 1
    # excluded, not deleted: ids are never reused
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 2
    rows = conn.execute("SELECT content_path FROM commitments WHERE superseded=0").fetchall()
    assert len(rows) == 1
    from pathlib import Path
    assert Path(rows[0]["content_path"]).read_bytes() == _REAL_PDF  # the real one survives
