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
