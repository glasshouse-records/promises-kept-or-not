"""A version's date must say WHAT it is a date of.

Audited 2026-08-27: every archived version is dated by its Wayback capture
timestamp, presented to the reader as a bare date. But a capture date is not a
publication date — it is the date the Internet Archive happened to look. Across
the 42 Wayback captures whose document states its own date, the capture runs a
MEDIAN of 98 days late, and in 12 cases more than six months (max 342: JPMorgan's
April-2025 policy captured 2026-03-09).

That gap is the cheapest possible rebuttal to a retreat claim — "your timeline
says August 2019, our policy is dated January 2019" — and the fix costs nothing:
say which date it is. The capture date keeps its real evidentiary job, which is
a floor: this text was demonstrably public by then.
"""

from __future__ import annotations

import pytest

from glasshouse import ledger, timeline


@pytest.fixture()
def conn(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock')")
    c.commit()
    return c


def test_version_dates_are_labelled_as_capture_dates(conn, tmp_path):
    """The reader must never see a bare date that looks like a publication date."""
    doc = tmp_path / "p.pdf"
    doc.write_bytes(b"%PDF-1.4")
    for wb in ("20190806220724", "20200324010046"):
        conn.execute(
            "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
            " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
            " text_sha256) VALUES ('blk','principles','https://x/p.pdf','2026-01-01',"
            "?,?,'application/pdf',8,?,?)", (wb[:10], str(doc), wb, "t" + wb[:6]))
    conn.commit()
    versions = timeline.policy_versions(conn, "blk")
    assert versions, "fixture should produce versions"
    for v in versions:
        assert "captured" in v, (
            "each version must carry the capture date under a name that says so; "
            f"got keys {sorted(v)}")


def test_timeline_markdown_names_the_kind_of_date(conn, tmp_path):
    """The published markdown is what a journalist quotes. It must not present a
    capture timestamp as the date the institution published the policy."""
    md = timeline.timeline_markdown(timeline.institution_timeline(conn, "blk"))
    lowered = md.lower()
    assert "capture" in lowered or "archived" in lowered, (
        "the artifact must state that its dates are archive capture dates")
