"""A policy document can have lived at earlier addresses (`former_urls`).

fetch_wayback only asked for each document's CURRENT address, so editions the
publisher posted at since-retired URLs (Vanguard 2023-2025 unified US policy)
were never looked up. Each former URL is now walked too, under the same
doc_label, and the version is recorded against the address it was captured at.
"""

from __future__ import annotations

from types import SimpleNamespace

from glasshouse.ingest import commitments


def test_former_urls_are_walked_and_recorded_at_their_own_address(monkeypatch):
    asked, recorded = [], []

    def fake_history(url, limit=50):
        asked.append(url)
        return [{"timestamp": "20230128105906", "mimetype": "application/pdf"}]

    monkeypatch.setattr(commitments, "wayback_history", fake_history)
    monkeypatch.setattr(commitments.http, "get",
                        lambda u, **k: SimpleNamespace(content=b"%PDF-1.4 x"))
    monkeypatch.setattr(
        commitments, "record_snapshot",
        lambda conn, inst, label, url, content, ctype, **k:
            recorded.append((label, url, k["wayback_timestamp"])) or True)

    insts = {"v": {"commitments": [{
        "label": "pol", "url": "https://x/now.pdf",
        "former_urls": ["https://x/2023.pdf", "https://x/2024.pdf"]}]}}
    assert commitments.fetch_wayback(None, insts) == 3
    assert asked == ["https://x/now.pdf", "https://x/2023.pdf", "https://x/2024.pdf"]
    assert ("pol", "https://x/2023.pdf", "20230128105906") in recorded


def test_no_former_urls_is_unchanged(monkeypatch):
    asked = []
    monkeypatch.setattr(commitments, "wayback_history",
                        lambda url, limit=50: asked.append(url) or [])
    commitments.fetch_wayback(None, {"v": {"commitments": [{"label": "p", "url": "https://x/a"}]}})
    assert asked == ["https://x/a"]
