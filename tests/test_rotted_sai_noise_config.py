"""The configured strip_patterns and declared reprints of the Lazard, Artisan and
Calamos SAI labels remove page furniture only (diffed against the real filings
2026-11-20/21); a real wording change must still change the extracted section."""
import re

from glasshouse import registry
from glasshouse.ingest import sai_appendix as sai


def _cfg(inst, label):
    for d in registry.load()[inst]["commitments"]:
        if d["label"] == label:
            return d["sai_appendix"]
    raise KeyError(label)


def _sec(cfg, body):
    return sai.extract_section(f"x {cfg['start'][0]} {body} {cfg['end'][0]} y",
                               cfg["start"], cfg["end"], True,
                               cfg.get("strip_page_numbers", False),
                               cfg.get("strip_patterns"), False)


def test_lazard_page_marks_mid_sentence_do_not_make_a_version():
    cfg = _cfg("lazard", "lazard-global-proxy-voting-policy-as-printed-in-sai-funds")
    a = _sec(cfg, "Lazard will vote against the proposal if the board B- 6 is not independent.")
    b = _sec(cfg, "Lazard will vote against the proposal if the board B-6 is not independent.")
    c = _sec(cfg, "Lazard will vote against the proposal if the board is not independent.")
    assert a == b == c


def test_lazard_real_edit_still_differs():
    cfg = _cfg("lazard", "lazard-global-proxy-voting-policy-as-printed-in-sai-etf")
    assert _sec(cfg, "Revised: April 2024 B- 3") != _sec(cfg, "Revised As Of November 15, 2023 B- 3")


def test_artisan_footer_in_either_order_and_bullet_glyph_removed():
    cfg = _cfg("artisan_partners", "artisan-partners-proxy-voting-as-printed-in-sai")
    a = _sec(cfg, "to vote the proxy. Statement of Additional Information —Artisan Partners Funds | 55 The Fund holds ■ items")
    b = _sec(cfg, "to vote the proxy. | Statement of Additional Information —Artisan Partners Funds 61 The Fund holds ◾ items")
    c = _sec(cfg, "to vote the proxy. The Fund holds items")
    assert re.sub(r"\s+", " ", a) == re.sub(r"\s+", " ", b) == c


def test_calamos_stray_page_numbers_removed_only_in_their_sentence():
    cfg = _cfg("calamos", "calamos-proxy-voting-policy-as-printed-in-sai")
    a = _sec(cfg, "related to the Portfolio's portfolio 32 securities for which the Portfolio has voted 32 times")
    assert "portfolio securities for which" in a and "voted 32 times" in a
    cfg = _cfg("calamos", "calamos-sustainable-proxy-voting-policy-as-printed-in-sai")
    assert " 24 " not in _sec(cfg, "in an effort to mitigate 24 negative environmental impact")


def test_declared_reprints_are_documented():
    for inst, label in [("lazard", "lazard-global-proxy-voting-policy-as-printed-in-sai-etf"),
                        ("lazard", "lazard-global-proxy-voting-policy-as-printed-in-sai-funds"),
                        ("artisan_partners", "artisan-partners-proxy-voting-as-printed-in-sai")]:
        for rp in _cfg(inst, label)["reprints"]:
            assert re.fullmatch(r"\d{10}-\d{2}-\d{6}", rp["accession"])
            assert rp["same_as_previous"] is True and rp["reason"] and rp["checked"]
