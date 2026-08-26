"""Version identity must be the POLICY TEXT, not the raw bytes.

Found live (2026-08-26) while auditing the archive: BNY's proxy-voting page
is served behind Akamai, which injects an mPulse/boomerang beacon carrying a
per-REQUEST token. Two captures of the same unchanged policy therefore had
different SHA-256s, and `record_snapshot` — which deduped on raw bytes — filed
each one as a new "version". Eight of BNY's ten archived versions were the
same two documents. With the daily capture cron now live, an HTML source
behind a CDN would have manufactured a fresh phantom version EVERY DAY.

The archive of what these firms promised is the project's one scarce asset;
a version count nobody can trust destroys it. So: raw sha256 keeps doing its
real job (byte-integrity of what we stored), and a separate text hash decides
what counts as a version.
"""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.contradictions import extract_text
from glasshouse.ingest import commitments as cm

_BODY = ("We will vote against directors who fail to act. " * 12).strip()


def _page(beacon: str, body: str = _BODY) -> bytes:
    """A CDN-served policy page: identical policy, per-request beacon token.

    The body is realistically long on purpose — policy_text() distrusts any
    extraction under _MIN_TEXT chars and falls back to byte identity, which is
    the behaviour test_unreadable_document_falls_back_to_bytes pins down."""
    return (
        "<!DOCTYPE HTML><html><head><title>Proxy Voting Policy</title>"
        f'<script>!function(e){{window.BOOMR_API_key="{beacon}";}}(window);</script>'
        f"</head><body><h1>Proxy Voting Policy</h1><p>{body}</p></body></html>"
    ).encode()


@pytest.fixture()
def conn(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('bny','BNY')")
    c.commit()
    return c


def test_beacon_only_change_is_not_a_new_version(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "COMMITMENTS_DIR", tmp_path / "snap")
    first = cm.record_snapshot(conn, "bny", "proxy", "https://x/p.html",
                               _page("TOKEN-AAA"), "text/html")
    second = cm.record_snapshot(conn, "bny", "proxy", "https://x/p.html",
                                _page("TOKEN-BBB"), "text/html")
    assert first is True, "the first capture is a genuine new version"
    assert second is False, "same policy, different CDN token — NOT a new version"
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 1


def test_real_policy_change_is_still_a_new_version(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "COMMITMENTS_DIR", tmp_path / "snap")
    cm.record_snapshot(conn, "bny", "proxy", "https://x/p.html",
                       _page("TOKEN-AAA", _BODY), "text/html")
    changed = cm.record_snapshot(
        conn, "bny", "proxy", "https://x/p.html",
        _page("TOKEN-AAA", _BODY.replace("We will vote", "We may consider voting")),
        "text/html")
    assert changed is True, "softened wording is exactly what we exist to catch"
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 2


def test_extract_text_returns_prose_not_markup(tmp_path):
    """The commitment scorer runs over extract_text(). For HTML it was handed
    raw markup — 25,479 chars of BNY page source for 2,851 chars of policy —
    so nav markup and beacon JavaScript were scored as promise language."""
    p = tmp_path / "policy.html"
    p.write_bytes(_page("TOKEN-AAA"))
    text = extract_text(p)
    assert "We will vote against directors" in text
    assert "<" not in text and "BOOMR_API_key" not in text, \
        "script bodies and tags must not reach the commitment scorer"


def test_unreadable_document_falls_back_to_bytes(conn, tmp_path, monkeypatch):
    """A scanned PDF or a failed extraction yields no text. Merging every such
    document into one "version" would silently erase real policy changes, so
    identity must fall back to raw bytes — over-counting is recoverable,
    swallowing a genuine version is not."""
    monkeypatch.setattr(cm, "COMMITMENTS_DIR", tmp_path / "snap")
    a = cm.record_snapshot(conn, "bny", "scan", "https://x/s.pdf", b"%PDF-1.4 aaa", "application/pdf")
    b = cm.record_snapshot(conn, "bny", "scan", "https://x/s.pdf", b"%PDF-1.4 bbb", "application/pdf")
    assert (a, b) == (True, True), "unreadable docs must not collapse into one version"


def test_beacon_page_yields_no_text_hash_collision_with_other_doc(conn, tmp_path, monkeypatch):
    """Text identity is scoped per document — two institutions publishing the
    same boilerplate must not shadow each other."""
    monkeypatch.setattr(cm, "COMMITMENTS_DIR", tmp_path / "snap")
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('ssga','SSgA')")
    conn.commit()
    assert cm.record_snapshot(conn, "bny", "proxy", "https://x/p.html", _page("A"), "text/html")
    assert cm.record_snapshot(conn, "ssga", "proxy", "https://y/p.html", _page("A"), "text/html")


def test_version_lineage_collapses_beacon_duplicates(conn, tmp_path, monkeypatch):
    """The diff layer must see one version, not ten.

    timeline.py deduped only CONSECUTIVE identical sha256 and contradictions.py
    did not dedupe at all, so BNY's ten byte-distinct captures of one unchanged
    policy entered the lineage as ten versions. Anything comparing version N to
    N+1 — commitment-decay, softening, the policy-edits report — was then diffing
    a document against itself, which is precisely the false data point that this
    project treats as fatal."""
    from glasshouse import timeline
    # Inserted DIRECTLY, bypassing record_snapshot: these rows are already in
    # the live archive from before the capture-side fix, so the read path has
    # to collapse them on its own. (On the real ledger this is BNY: 10 rows.)
    snap = tmp_path / "snap"
    snap.mkdir()
    rows = [("A", _BODY), ("B", _BODY), ("C", _BODY),
            ("D", _BODY.replace("We will", "We may"))]
    for i, (beacon, body) in enumerate(rows):
        content = _page(beacon, body)
        f = snap / f"proxy-{beacon}.html"
        f.write_bytes(content)
        raw_sha, text_sha = cm.version_identity(content, "text/html", "https://x/p.html")
        conn.execute(
            "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
            " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
            " text_sha256) VALUES ('bny','proxy','https://x/p.html','2026-01-01',"
            "?,?,'text/html',?,?,?)",
            (raw_sha, str(f), len(content), f"2025010{i + 1}000000", text_sha))
    conn.commit()
    versions = timeline.policy_versions(conn, "bny")
    assert len(versions) == 2, (
        f"one unchanged policy plus one real edit = 2 versions, got {len(versions)}")


def test_unreadable_pdf_failure_is_cached(tmp_path, caplog):
    """A corrupt PDF must be parsed once, not once per call.

    T. Rowe Price's 2023 Wayback capture is a truncated PDF ("Cannot find Root
    object"). extract_text() returned early on the exception WITHOUT writing
    its cache, so every detector pass re-parsed it — a full detector run went
    from ~26s to over ten minutes. Caching the failure is what makes the
    unreadable-document fallback affordable."""
    import logging

    from glasshouse.contradictions import extract_text
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4 this is not a parseable pdf")
    with caplog.at_level(logging.WARNING):
        assert extract_text(p) == ""
        first = len([r for r in caplog.records if "extraction failed" in r.message])
        assert extract_text(p) == ""
        second = len([r for r in caplog.records if "extraction failed" in r.message])
    assert first == 1 and second == 1, "the failure must be parsed once and remembered"
