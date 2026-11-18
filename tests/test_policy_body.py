"""`body: {start, end}` bounds an HTML policy page to its policy text, so a change in
navigation, menus or trademark spacing is not a new policy version."""

from __future__ import annotations

from glasshouse import engine, ledger
from glasshouse.contradictions import bound_body

BODY = {"start": r"Acme Advisers, Inc\. \(the .Advis", "end": r"Votes will be recorded\."}
POLICY = ("Acme Advisers, Inc. (the “Advisor”) votes proxies in the interest of clients. "
          + "We will vote against proposals that dilute holders. " * 6 + "Votes will be recorded.")


def _page(nav: str, body: str = POLICY, foot: str = "Copyright") -> str:
    return f"<html><body><nav>{nav}</nav><p>{body}</p><footer>{foot}</footer></body></html>"


def _build(tmp_path, pages, body=BODY):
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme')")
    for n, (wb, html) in enumerate(pages):
        f = tmp_path / f"p{n}.html"
        f.write_text(html)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                  " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
                  " text_sha256) VALUES ('acme','page','https://acme.example/p','2026-01-01',"
                  "?,?,'text/html',1,?,?)", (f"sha{n}", str(f), wb, f"t{n}"))
    c.commit()
    c.close()
    inst = {"acme": {"commitments": [{"label": "page", **({"body": body} if body else {})}]}}
    out = tmp_path / "engine.db"
    engine.build(led, out, institutions=inst)
    return engine.Engine(out, led)


def test_bound_body_cuts_start_to_first_end():
    t = "menu Investments ® " + POLICY + " Votes will be recorded. more footer"
    assert bound_body(t, BODY) == POLICY
    assert bound_body(t, None) == t
    assert bound_body("no markers here", BODY) is None
    assert bound_body(POLICY[:-len("Votes will be recorded.")], BODY) is None


def test_navigation_only_changes_are_one_version(tmp_path):
    e = _build(tmp_path, [("20240101000000", _page("Investments® Home")),
                          ("20250101000000", _page("Investments ® Home About Us", foot="2025"))])
    vs = e.policy_versions("acme")["result"]
    assert len(vs) == 1 and vs[0]["captured"] == "2024-01-01" and vs[0]["readable"]


def test_a_body_change_is_a_new_version(tmp_path):
    e = _build(tmp_path, [("20240101000000", _page("a")),
                          ("20250101000000", _page("a", POLICY.replace("dilute", "harm")))])
    assert len(e.policy_versions("acme")["result"]) == 2


def test_missing_end_marker_is_unreadable_not_a_version(tmp_path):
    cut = POLICY.replace("Votes will be recorded.", "")
    e = _build(tmp_path, [("20240101000000", _page("a")), ("20250101000000", _page("b", cut))])
    vs = {v["captured"]: v for v in e.policy_versions("acme")["result"]}
    assert vs["2024-01-01"]["readable"] and not vs["2025-01-01"]["readable"]
    assert e.db.execute("SELECT COUNT(*) FROM policy_sentences WHERE commitment_id=?",
                        (vs["2025-01-01"]["commitment_id"],)).fetchone()[0] == 0


def test_without_body_the_whole_page_is_the_identity(tmp_path):
    e = _build(tmp_path, [("20240101000000", _page("a")), ("20250101000000", _page("b"))], body=None)
    # fixture text_sha256 values differ ("t0", "t1"): two versions, as before
    assert len(e.policy_versions("acme")["result"]) == 2


# ---- trademark spacing and the shared identity helper ----------------------

def test_identity_text_ignores_spacing_before_trademark_signs():
    from glasshouse.contradictions import identity_text
    base = identity_text("American Century Investments® family")
    for variant in ("American Century Investments ® family",
                    "American Century Investments  \n® family",
                    "American Century Investments {sup}®{/sup} family",
                    "American Century Investments<sup> ®</sup> family"):
        assert identity_text(variant) == base, variant
    assert identity_text("Acme ™ and Beta ©") == identity_text("Acme™ and Beta©")
    assert identity_text("a b") != identity_text("ab")      # ordinary spacing still counts


def test_trademark_spacing_alone_is_not_a_version_on_any_label(tmp_path):
    pad = " Filler policy sentence goes here. " * 10
    e = _build(tmp_path, [("20240101000000", "<p>Investments® family." + pad + "</p>"),
                          ("20250101000000", "<p>Investments ® family." + pad + "</p>")],
               body=None)
    assert len(e.policy_versions("acme")["result"]) == 1


def test_every_surface_counts_versions_through_the_one_helper(tmp_path):
    from glasshouse import dataset
    pad = " Filler policy sentence goes here. " * 10
    e = _build(tmp_path, [("20240101000000", "<p>Investments® family." + pad + "</p>"),
                          ("20250101000000", "<p>Investments ® family." + pad + "</p>")],
               body=None)
    row = [r for r in dataset.coverage(e.ledger) if r["institution"] == "Acme"]
    assert row and row[0]["policy_versions"] == 1
    from glasshouse.contradictions import distinct_versions
    assert len(distinct_versions(e.ledger, "institution_id=?", ("acme",))) == 1


def test_release_ships_the_identity_hash(tmp_path):
    import hashlib

    from glasshouse import release
    from glasshouse.contradictions import identity_text
    from glasshouse.ingest.commitments import html_to_text
    page = _page("nav one")
    e = _build(tmp_path, [("20240101000000", page)], body=None)
    rows = release.policy_versions_rows(e.ledger, e.db)
    want = hashlib.sha256(identity_text(html_to_text(page)).encode()).hexdigest()
    assert rows[0][10] == want            # identity_sha256 column
    assert rows[0][9] == "t0"             # text_sha256 stays the ledger's own hash


# ---- the persisted identity ---------------------------------------------------

PAD = " Filler policy sentence goes here. " * 10


def _row(c, n, path, identity="", wb="2024010100000"):
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256,"
              " content_path, content_type, size_bytes, wayback_timestamp, text_sha256,"
              " identity_sha256) VALUES ('acme','page','https://acme.example/p','2026-01-01',"
              "?,?,'text/html',1,?,'ledgerhash',?)",
              (f"sha{n}", path, f"2024010{n}000000", identity))


def test_identity_survives_a_ledger_with_no_files(tmp_path):
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme')")
    _row(c, 1, "", "i" * 64)
    _row(c, 2, "", "i" * 64)          # same identity: one version
    _row(c, 3, "", "j" * 64)          # another identity: a second
    _row(c, 4, "", "")                # neither identity nor file: unreadable
    c.commit()
    out = tmp_path / "e.db"
    engine.build(led, out, institutions={"acme": {"commitments": [{"label": "page"}]}})
    vs = engine.Engine(out, led).policy_versions("acme")["result"]
    assert len(vs) == 3
    from glasshouse.contradictions import distinct_versions
    assert len(distinct_versions(c)) == 3
    unreadable = [v for v in vs if v["captured"] == "2024-01-04"]
    assert len(unreadable) == 1


def test_record_snapshot_stores_the_identity_and_backfill_is_idempotent(tmp_path, monkeypatch):
    from glasshouse.contradictions import identity_text
    from glasshouse.ingest import commitments as cm
    monkeypatch.setattr(cm, "COMMITMENTS_DIR", tmp_path / "arch")
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme')")
    html = _page("nav", POLICY).encode()
    assert cm.record_snapshot(c, "acme", "page", "https://acme.example/p", html, "text/html")
    got = c.execute("SELECT identity_sha256 FROM commitments").fetchone()[0]
    import hashlib

    from glasshouse.ingest.commitments import html_to_text
    assert got == hashlib.sha256(identity_text(html_to_text(html.decode())).encode()).hexdigest()
    c.execute("UPDATE commitments SET identity_sha256=''")
    assert cm.backfill_identity_hashes(c) == 1
    assert c.execute("SELECT identity_sha256 FROM commitments").fetchone()[0] == got
    assert cm.backfill_identity_hashes(c) == 0


def test_restore_keeps_version_counts(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("pyarrow")
    from glasshouse import release, restore
    led = tmp_path / "src.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('acme','Acme')")
    for n, ident in ((1, "i" * 64), (2, "i" * 64), (3, "j" * 64)):
        f = tmp_path / f"f{n}.html"
        f.write_text("x")
        _row(c, n, str(f), ident)
    c.commit()
    reg = {"acme": {"commitments": [{"label": "page"}]}}
    eng = tmp_path / "e.db"
    engine.build(led, eng, institutions=reg)
    before = len(engine.Engine(eng, led).policy_versions("acme")["result"])
    release.build_release(c, root=tmp_path / "rel", version="T", no_derived=True,
                          engine_path=eng, institutions=reg)
    restore.restore(tmp_path / "rel" / "vT", tmp_path / "out" / "glasshouse.db")
    out = tmp_path / "out" / "glasshouse.db"
    eng2 = tmp_path / "e2.db"
    engine.build(out, eng2, institutions=reg)
    assert len(engine.Engine(eng2, out).policy_versions("acme")["result"]) == before == 2


def test_body_spec_raises_when_the_registry_cannot_load(monkeypatch):
    import pytest

    from glasshouse import contradictions, registry
    monkeypatch.setattr(contradictions, "_BODY_SPECS", None)
    def boom():
        raise OSError("no registry")
    monkeypatch.setattr(registry, "load", boom)
    with pytest.raises(OSError):
        contradictions.body_spec("acme", "page")
