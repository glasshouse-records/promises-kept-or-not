"""COVERAGE.json `policy_versions` must equal the policy_versions rows that ship.

Regression (release v2026-11-23): coverage counted distinct text per institution,
the shipped file keeps one row per (doc_label, text). Where two labels of one
institution carry identical text (subadviser labels), coverage under-counted
(Lazard 13 vs 14, New York Life 17 vs 21, Parnassus 7 vs 12)."""

from __future__ import annotations

from glasshouse import dataset, engine, ledger, release

PAD = "<p>" + "Filler policy sentence goes here. " * 10 + "</p>"


def test_coverage_policy_versions_equals_shipped_rows(tmp_path):
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme')")
    # (label, text variant): two labels share identical text; one label has a 2nd text.
    caps = [("main", "a"), ("sub_x", "a"), ("sub_y", "a"), ("main", "b")]
    for n, (label, v) in enumerate(caps):
        f = tmp_path / f"p{n}.html"
        f.write_text(f"<html><body>{PAD}<p>variant {v}</p></body></html>")
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                  " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
                  " text_sha256) VALUES ('acme',?,'https://acme.example/p','2026-01-01',"
                  "?,?,'text/html',1,?,?)",
                  (label, f"sha{n}", str(f), f"2024010{n + 1}000000", f"t{n}"))
    c.commit()
    c.close()
    out = tmp_path / "engine.db"
    inst = {"acme": {"commitments": [{"label": lb} for lb in ("main", "sub_x", "sub_y")]}}
    engine.build(led, out, institutions=inst)
    e = engine.Engine(out, led)
    shipped = [r for r in release.policy_versions_rows(e.ledger, e.db) if r[1] == "acme"]
    cov = next(r for r in dataset.coverage(e.ledger) if r["institution"] == "Acme")
    assert len(shipped) == 4
    assert cov["policy_versions"] == len(shipped)
