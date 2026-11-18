"""Superseded commitment rows must be invisible to every reader, and ids must
never be handed out twice (INTEGER PRIMARY KEY without AUTOINCREMENT reuses the
id of a deleted top row, so a published commitment_id could point at other text)."""

from __future__ import annotations

import re
from pathlib import Path

import glasshouse
from glasshouse import ledger
from glasshouse.ingest import commitments

# Files that legitimately look at ALL rows: custody/dating integrity checks,
# "ids since last run", release lookups BY id, the ingesters themselves
# (dedupe lookups, backfill, the superseding code).
ALLOWED = {"ledger.py", "diff.py", "release.py", "ingest/sai_appendix.py",
           "ingest/commitments.py"}


def test_every_reader_of_commitments_excludes_superseded():
    root = Path(glasshouse.__file__).parent
    bad = []
    for f in root.rglob("*.py"):
        rel = f.relative_to(root).as_posix()
        if rel in ALLOWED:
            continue
        s = f.read_text()
        for m in re.finditer(r"FROM commitments\b", s):
            # the statement continues to the closing quote(s) of the query
            window = s[m.start(): m.start() + 450]
            if "superseded" not in window:
                bad.append(f"{rel}:{s[:m.start()].count(chr(10)) + 1}")
    assert not bad, f"readers that include superseded rows: {bad}"


def test_purge_error_pages_never_frees_an_id(tmp_path, monkeypatch):
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "c")
    conn = ledger.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    bad = tmp_path / "e.html"
    bad.write_bytes(b"<html><title>404 Not Found</title><body>Page not found</body></html>")
    conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                 " sha256, content_path, content_type) VALUES ('x','p','u','2026-01-01','a',?,"
                 "'text/html')", (str(bad),))
    conn.commit()
    handed = conn.execute("SELECT id FROM commitments").fetchone()[0]
    assert commitments.purge_error_pages(conn) == 1
    conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                 " sha256, content_path) VALUES ('x','p','u2','2026-01-02','b','q')")
    conn.commit()
    ids = [r[0] for r in conn.execute("SELECT id FROM commitments")]
    assert handed in ids and len(ids) == 2        # old row kept, new id is different
    assert conn.execute("SELECT superseded FROM commitments WHERE id=?",
                        (handed,)).fetchone()[0] == 1
    assert bad.exists()


def test_capture_attempts_accepts_needs_review_on_old_and_new_ledgers(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    c = ledger.connect(db)
    c.execute("DROP TABLE capture_attempts")
    c.execute("CREATE TABLE capture_attempts (id INTEGER PRIMARY KEY, institution_id TEXT NOT NULL,"
              " doc_label TEXT NOT NULL, url TEXT NOT NULL, attempted_at TEXT NOT NULL,"
              " outcome TEXT NOT NULL CHECK (outcome IN ('new_version','unchanged','failed')),"
              " detail TEXT NOT NULL DEFAULT '')")
    c.execute("INSERT INTO capture_attempts (institution_id, doc_label, url, attempted_at, outcome)"
              " VALUES ('a','b','u','t','failed')")
    c.commit()
    c.close()
    c = ledger.connect(db)   # migrates
    c.execute("INSERT INTO capture_attempts (institution_id, doc_label, url, attempted_at, outcome)"
              " VALUES ('a','b','u','t','needs_review')")
    assert c.execute("SELECT COUNT(*) FROM capture_attempts").fetchone()[0] == 2
    assert isinstance(c, sqlite3.Connection)


def test_purge_retires_truncated_pdf_captures(tmp_path, monkeypatch):
    """A PDF with no %%EOF in its tail is a failed capture, never a version
    (Wayback serves some large PDFs cut at 1 MiB). Captures recorded before the
    ingest guard existed are retired by the same purge, keeping row and file."""
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "c")
    conn = ledger.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    cut = tmp_path / "cut.pdf"
    cut.write_bytes(b"%PDF-1.7\n" + b"0" * 4000)              # no end marker
    whole = tmp_path / "whole.pdf"
    whole.write_bytes(b"%PDF-1.7\n" + b"0" * 4000 + b"\n%%EOF\n")
    for sha, p in (("a", cut), ("b", whole)):
        conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                     " sha256, content_path, content_type) VALUES ('x','p','u','2026-01-01',?,?,"
                     "'application/pdf')", (sha, str(p)))
    conn.commit()
    assert commitments.purge_error_pages(conn) == 1
    rows = dict(conn.execute("SELECT sha256, superseded FROM commitments"))
    assert rows == {"a": 1, "b": 0}
    assert cut.exists()
