"""The archive's one irreplaceable asset gets the one check it never had.

integrity_check() verified enforcement provenance, resolution enums and orphaned
votes — but never that a stored commitment file still EXISTS, or still hashes to
the sha256 recorded for it. The policy snapshots are the only thing in this
project that cannot be re-fetched once the source URL rots (three already have),
and they were the only artefacts with no custody check at all.

Found 2026-08-27 alongside the CI hole that made it urgent: the scheduled
workflow cached only data/glasshouse.db, never data/commitments/, so every run
wrote the captured bytes to a runner that then discarded them — leaving rows
whose content_path pointed at files that would never exist again.
"""

from __future__ import annotations

import hashlib

import pytest

from glasshouse import ledger


@pytest.fixture()
def conn(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock')")
    c.commit()
    return c


def _add(conn, path, content, sha=None):
    path.write_bytes(content)
    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
        " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
        " text_sha256) VALUES ('blk','p','https://x/p.pdf','2026-01-01',?,?,"
        "'application/pdf',?,'','t')",
        (sha or hashlib.sha256(content).hexdigest(), str(path), len(content)))
    conn.commit()


def test_intact_archive_passes(conn, tmp_path):
    _add(conn, tmp_path / "a.pdf", b"policy bytes")
    assert integrity(conn)["commitments_custody"] == []


def test_missing_snapshot_file_is_a_hard_failure(conn, tmp_path):
    p = tmp_path / "gone.pdf"
    _add(conn, p, b"policy bytes")
    p.unlink()
    bad = integrity(conn)["commitments_custody"]
    assert len(bad) == 1, "a vanished snapshot must be reported, not silently tolerated"


def test_altered_snapshot_is_a_hard_failure(conn, tmp_path):
    p = tmp_path / "tampered.pdf"
    _add(conn, p, b"policy bytes")
    p.write_bytes(b"policy bytes, altered")
    bad = integrity(conn)["commitments_custody"]
    assert len(bad) == 1, "bytes that no longer match their recorded hash must fail"


def integrity(conn):
    return ledger.integrity_check(conn)
