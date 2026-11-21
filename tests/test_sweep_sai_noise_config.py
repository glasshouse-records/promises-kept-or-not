"""Noise found by diffing consecutive SAI-printed editions after the 2026-11-21 sweep:
Brown Advisory's editions alternate bullet glyphs and underscore rules; one GQG edition
ends with the page header 'The Advisors’' (of 'The Advisors' Inner Circle Fund III').
Neither may make a version; a real wording change still must."""
from glasshouse import registry
from glasshouse.ingest import sai_appendix as sai


def _cfg(inst, label):
    for d in registry.load()[inst]["commitments"]:
        if d["label"] == label:
            return d["sai_appendix"]
    raise KeyError(label)


def _sec(cfg, body, end=None):
    return sai.extract_section(f"x {cfg['start'][0]} {body} {end or cfg['end'][0]} y",
                               cfg["start"], cfg["end"], True,
                               cfg.get("strip_page_numbers", False),
                               cfg.get("strip_patterns"), False)


BROWN = ("brown_advisory", "brown-advisory-proxy-voting-policy-as-printed-in-sai")
GQG = ("gqg", "gqg-proxy-voting-policy-as-printed-in-sai")


def test_brown_bullet_glyphs_and_rules_do_not_make_a_version():
    cfg = _cfg(*BROWN)
    a = _sec(cfg, "request to: • Attend a meeting • Vote in line ____________ 1. The firm")
    b = _sec(cfg, "request to: ◦ Attend a meeting ◦ Vote in line _______________ 1. The firm")
    c = _sec(cfg, "request to: ▪ Attend a meeting Vote in line 1. The firm")
    assert a == b == c


def test_brown_real_edit_still_differs():
    cfg = _cfg(*BROWN)
    assert _sec(cfg, "the firm will vote against") != _sec(cfg, "the firm will vote for")


def test_gqg_trailing_page_header_is_not_text():
    cfg = _cfg(*GQG)
    body = "the guidelines also should serve for voting on all accounts under management."
    assert _sec(cfg, body + " The Advisors’", "Inner Circle Fund III") == _sec(cfg, body)
    assert _sec(cfg, body + " The Advisors'", "Inner Circle Fund III") == _sec(cfg, body)


GUGGENHEIM = ("guggenheim", "guggenheim-advisor-proxy-voting-procedures-as-printed-in-sai")


def test_guggenheim_page_number_mid_sentence_is_not_text():
    cfg = _cfg(*GUGGENHEIM)
    a = _sec(cfg, "in the same proportion as the vote of all other 55 shareholders of the fund.")
    b = _sec(cfg, "in the same proportion as the vote of all other 74 shareholders of the fund.")
    c = _sec(cfg, "in the same proportion as the vote of all other shareholders of the fund.")
    assert a == b == c


def test_guggenheim_real_numbers_kept():
    cfg = _cfg(*GUGGENHEIM)
    assert "30 days" in _sec(cfg, "the Advisor votes within 30 days of the meeting.")


def test_gmo_2026_footnote_move_is_a_declared_reprint():
    for d in registry.load()["gmo"]["commitments"]:
        if d["label"] == "gmo-proxy-voting-policy-as-printed-in-sai":
            reps = {r["accession"]: r for r in d["sai_appendix"].get("reprints") or []}
    r = reps["0001193125-26-290521"]
    assert r["same_as_previous"] is True and r["reason"] and r["checked"]
