"""Precision guards on the legacy two-parser agreement: meeting-level drop of disputed
meetings, and the fund-boundary alphabetical-order guard."""
import pytest

from glasshouse.ingest import legacy_iss, legacy_pe


def _pe(fund, issuer, date="2023-01-01", n="1", vote="For"):
    return dict.fromkeys(legacy_pe.KEYS, "") | {
        "fund_name": fund, "issuer_name": issuer, "meeting_date": date,
        "security_id": "S" + issuer, "proposal_id": n, "vote": vote}


def _iss(fund, issuer, date="2023-01-01", n="1", vote="For"):
    return dict.fromkeys(legacy_iss.KEYS, "") | {
        "fund_heading": fund, "issuer_name": issuer, "meeting_date": date,
        "security_id": "S" + issuer, "proposal_id": n, "vote": vote}


def _run(kind, monkeypatch, rows_a, rows_b):
    if kind == "pe":
        monkeypatch.setattr(legacy_pe.legacy_pe_blocks, "parse", lambda t: rows_a)
        monkeypatch.setattr(legacy_pe.legacy_pe_lines, "parse", lambda t: rows_b)
        return legacy_pe.agreed("x")

    class A:
        parse = staticmethod(lambda t: rows_a)

    class B:
        parse = staticmethod(lambda t: rows_b)

    return legacy_iss.agreed("x", (A, B))


KINDS = [("pe", _pe), ("iss", _iss)]


@pytest.mark.parametrize("kind,mk", KINDS)
def test_disputed_meeting_loses_agreed_siblings(kind, mk, monkeypatch):
    a = [mk("F", "Acme", n="1"), mk("F", "Acme", n="2"), mk("F", "Beta", n="1")]
    b = [mk("F", "Acme", n="1"), mk("F", "Acme", n="2", vote="Against"), mk("F", "Beta", n="1")]
    out, st = _run(kind, monkeypatch, a, b)
    assert [r["issuer_name"] for r in out] == ["Beta"]
    assert st["meetings_dropped_disputed"] == 1 and st["rows_dropped_disputed"] == 1
    assert st["a_only"] == 1 and st["b_only"] == 1 and st["agreed"] == 2  # raw gate stats


@pytest.mark.parametrize("kind,mk", KINDS)
def test_same_issuer_other_fund_or_date_kept(kind, mk, monkeypatch):
    a = [mk("F", "Acme"), mk("G", "Acme"), mk("G", "Acme", date="2023-02-02")]
    b = [mk("F", "Acme", vote="Against"), mk("G", "Acme"), mk("G", "Acme", date="2023-02-02")]
    out, st = _run(kind, monkeypatch, a, b)
    assert len(out) == 2 and st["meetings_dropped_disputed"] == 0   # was 1: F had no agreed rows
    assert st["rows_dropped_disputed"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_order_reset_drops_tail_of_section(kind, mk, monkeypatch):
    rows = [mk("F", "Alpha"), mk("F", "Delta"), mk("F", "Beta"), mk("F", "Gamma"),
            mk("G", "Zed")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert [r["issuer_name"] for r in out] == ["Beta", "Gamma", "Zed"]
    assert st["order_resets"] == 1 and st["rows_dropped_order"] == 2
    assert st["order_repeats"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_as_filed_repeat_is_kept(kind, mk, monkeypatch):
    rows = [mk("F", "Alpha"), mk("F", "Beta"), mk("F", "Alpha"), mk("F", "Beta")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert len(out) == 4
    assert st["order_resets"] == 1 and st["order_repeats"] == 1 and st["rows_dropped_order"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_sorted_and_multirow_meetings_no_reset(kind, mk, monkeypatch):
    rows = [mk("F", "alpha", n="1"), mk("F", "alpha", n="2"), mk("F", "Beta"),
            mk("G", "Alpha")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert len(out) == 4 and st["order_resets"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_iss_collation_punctuation_is_not_a_reset(kind, mk, monkeypatch):
    # real ISS HTML order (0001710607-23-000209): E-GUARDIAN, E.ON SE, E-J HOLDINGS
    rows = [mk("F", n) for n in ("E-GUARDIAN, INC.", "E.ON SE", "E-J HOLDINGS INC.",
                                 "EAGERS AUTOMOTIVE", "THE ZED CO")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert len(out) == 5 and st["order_resets"] == 0


# -- review fixes 2026-11-22 --------------------------------------------------

def _names(out):
    return [r["issuer_name"] for r in out]


@pytest.mark.parametrize("kind,mk", KINDS)
def test_digit_and_symbol_initials_never_make_a_reset(kind, mk, monkeypatch):
    # real ISS order: punctuation, then digits, then letters
    rows = [mk("F", n) for n in ("&DO HOLDINGS CO., LTD.", "1&1 AG", "A2A SPA", "ZED")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert len(out) == 4 and st["order_resets"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_letter_to_digit_is_not_a_reset(kind, mk, monkeypatch):
    rows = [mk("F", n) for n in ("ZED", "3I GROUP")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert len(out) == 2 and st["order_resets"] == 0


@pytest.mark.parametrize("kind,mk", KINDS)
def test_out_of_order_head_meetings_dropped_sorted_tail_kept(kind, mk, monkeypatch):
    # real: ProxyEdge lists JOHN HANCOCK COLLATERAL TRUST / JACKSON FINANCIAL first
    rows = [mk("F", "JOHN HANCOCK COLLATERAL TRUST", n="1"), mk("F", "JOHN HANCOCK COLLATERAL TRUST", n="2"),
            mk("F", "JACKSON FINANCIAL INC."), mk("F", "ABBOTT"), mk("F", "BETA"), mk("F", "ZED"),
            mk("G", "ALPHA")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert _names(out) == ["ABBOTT", "BETA", "ZED", "ALPHA"]
    assert st["order_resets"] == 1 and st["rows_dropped_order"] == 3


@pytest.mark.parametrize("kind,mk", KINDS)
def test_head_of_three_meetings_cuts_to_end(kind, mk, monkeypatch):
    rows = [mk("F", n) for n in ("MMM", "NNN", "OOO", "ABBOTT", "BETA")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert _names(out) == ["MMM", "NNN", "OOO"] and st["rows_dropped_order"] == 2


@pytest.mark.parametrize("kind,mk", KINDS)
def test_second_reset_in_tail_cuts_to_end(kind, mk, monkeypatch):
    rows = [mk("F", n) for n in ("MMM", "ABBOTT", "DELTA", "BETA")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert _names(out) == ["MMM"] and st["rows_dropped_order"] == 3


@pytest.mark.parametrize("kind,mk", KINDS)
def test_repeat_that_differs_only_in_vote_is_cut(kind, mk, monkeypatch):
    rows = [mk("F", "AAA"), mk("F", "BBB"), mk("F", "CCC"),
            mk("F", "AAA", vote="Against"), mk("F", "BBB", vote="Against")]
    out, st = _run(kind, monkeypatch, rows, list(rows))
    assert _names(out) == ["AAA", "BBB", "CCC"]
    assert st["order_repeats"] == 0 and st["rows_dropped_order"] == 2


@pytest.mark.parametrize("kind,mk", KINDS)
def test_disputed_count_is_meetings_actually_removed(kind, mk, monkeypatch):
    a = [mk("F", "Acme"), mk("F", "Beta")]
    b = [mk("F", "Acme"), mk("F", "Beta"), mk("F", "Ghost")]   # Ghost: b only, no agreed rows
    out, st = _run(kind, monkeypatch, a, b)
    assert len(out) == 2 and st["meetings_dropped_disputed"] == 0
