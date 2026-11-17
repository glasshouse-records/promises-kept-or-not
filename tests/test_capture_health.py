"""The doctor must notice a policy page that stopped being captured.

Found 2026-11-17: BlackRock's principles URL began answering with an HTML
error page and UBS's with a 404. `ingest commitments` logged a warning and
moved on; `doctor` still said "[ok] 1 live snapshot(s) on record" for both,
because it only counted rows — and an unchanged page writes no row, so a
five-month-old row and a capture confirmed this morning looked identical.
A day a page goes uncaptured cannot be back-filled, so the ingester now
records every attempt and the doctor reads that record.
"""

from __future__ import annotations

from datetime import date

import pytest
import requests

from glasshouse import doctor, ledger, publish, registry
from glasshouse.ingest import commitments


def _page(body: str) -> bytes:
    return (f"<!doctype html><html><head><title>Proxy Voting Policy</title></head>"
            f"<body>{body} {'We expect boards to oversee material risk. ' * 12}</body></html>"
            ).encode()


_ERROR_HTML = (b"<!doctype html><html><head><title>Error Page | Alpha</title></head>"
               b"<body>Sorry.</body></html>")
_404_HTML = (b"<!doctype html><html><head><title>404 Error - Page not found</title>"
             b"</head><body>Sorry.</body></html>")

_INSTS = {"alpha": {"display_name": "Alpha AM", "commitments": [
    {"label": "policy", "url": "https://alpha.example/policy.html"}]}}
_PDF_INSTS = {"alpha": {"display_name": "Alpha AM", "commitments": [
    {"label": "policy", "url": "https://alpha.example/policy.pdf"}]}}


class _Resp:
    def __init__(self, content: bytes, ctype: str = "text/html"):
        self.content = content
        self.headers = {"Content-Type": ctype}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(commitments, "COMMITMENTS_DIR", tmp_path / "commitments")
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('alpha','Alpha AM')")
    c.commit()
    return c


def _serve(monkeypatch, result):
    def fake_get(url, **kw):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(commitments.http, "get", fake_get)


def _attempts(conn):
    return [(r["outcome"], r["url"]) for r in conn.execute(
        "SELECT outcome, url FROM capture_attempts ORDER BY id")]


def _check(conn, monkeypatch, today, insts=_INSTS):
    monkeypatch.setattr(registry, "load", lambda *a, **k: insts)
    monkeypatch.setattr(doctor, "_today", lambda: today)
    names = {c["name"]: c for c in doctor.diagnose(conn)["checks"]}
    return names["commitment-live:alpha/policy"]


# --- the ingester keeps a record of every attempt ---------------------------

def test_every_attempt_is_recorded_with_its_outcome(conn, monkeypatch):
    _serve(monkeypatch, _Resp(_page("v1")))
    commitments.fetch_live(conn, _INSTS)
    commitments.fetch_live(conn, _INSTS)
    _serve(monkeypatch, requests.HTTPError("404 Client Error"))
    assert commitments.fetch_live(conn, _INSTS) == {}       # contract: failures are absent
    assert [o for o, _ in _attempts(conn)] == ["new_version", "unchanged", "failed"]
    assert _attempts(conn)[0][1] == "https://alpha.example/policy.html"


def test_a_pdf_url_answering_with_html_is_a_failed_attempt(conn, monkeypatch):
    _serve(monkeypatch, _Resp(_ERROR_HTML, "text/html; charset=utf-8"))
    assert commitments.fetch_live(conn, _PDF_INSTS) == {}
    assert [o for o, _ in _attempts(conn)] == ["failed"]


def test_an_error_page_is_a_failed_attempt_not_an_unchanged_policy(conn, monkeypatch):
    # record_snapshot refuses an error page and returns False — which fetch_live
    # used to report as "unchanged", i.e. as a capture that succeeded.
    _serve(monkeypatch, _Resp(_404_HTML))
    assert commitments.fetch_live(conn, _INSTS) == {}
    assert [o for o, _ in _attempts(conn)] == ["failed"]
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


# --- the doctor reads it ----------------------------------------------------

def test_doctor_errors_when_the_most_recent_attempt_failed(conn, monkeypatch):
    _serve(monkeypatch, _Resp(_page("v1")))
    commitments.fetch_live(conn, _INSTS)
    _serve(monkeypatch, requests.HTTPError("404 Client Error"))
    commitments.fetch_live(conn, _INSTS)
    c = _check(conn, monkeypatch, date.today())
    assert c["ok"] is False and c["severity"] == "error"
    assert "404" in c["detail"]


def test_a_later_success_clears_the_alarm(conn, monkeypatch):
    _serve(monkeypatch, requests.HTTPError("404 Client Error"))
    commitments.fetch_live(conn, _INSTS)
    _serve(monkeypatch, _Resp(_page("v1")))
    commitments.fetch_live(conn, _INSTS)
    assert _check(conn, monkeypatch, date.today())["ok"] is True


def test_an_unchanged_capture_keeps_an_old_snapshot_fresh(conn, monkeypatch):
    # The row is five months old; the page was confirmed unchanged today.
    commitments.record_snapshot(conn, "alpha", "policy", "https://alpha.example/policy.html",
                                _page("v1"), "text/html", retrieval_date="2026-06-11")
    _serve(monkeypatch, _Resp(_page("v1")))
    commitments.fetch_live(conn, _INSTS)
    assert [o for o, _ in _attempts(conn)] == ["unchanged"]
    assert _check(conn, monkeypatch, date.today())["ok"] is True


def test_doctor_errors_when_the_last_confirmed_capture_is_over_budget(conn, monkeypatch):
    conn.execute(
        "INSERT INTO capture_attempts (institution_id, doc_label, url, attempted_at, outcome)"
        " VALUES ('alpha','policy','https://alpha.example/policy.html',"
        " '2026-11-01T06:00:00+00:00','unchanged')")
    conn.commit()
    commitments.record_snapshot(conn, "alpha", "policy", "https://alpha.example/policy.html",
                                _page("v1"), "text/html", retrieval_date="2026-06-11")
    within = _check(conn, monkeypatch, date(2026, 11, 15))
    assert within["ok"] is True
    over = _check(conn, monkeypatch, date(2026, 11, 16))
    assert over["ok"] is False and over["severity"] == "error"
    assert "2026-11-01" in over["detail"] and "15d" in over["detail"]


def test_a_ledger_with_no_attempt_log_falls_back_to_the_snapshot_date(conn, monkeypatch):
    # Ledgers from before the log existed: the newest live row is all we know.
    commitments.record_snapshot(conn, "alpha", "policy", "https://alpha.example/policy.html",
                                _page("v1"), "text/html", retrieval_date="2026-06-11")
    assert _check(conn, monkeypatch, date(2026, 6, 20))["ok"] is True
    stale = _check(conn, monkeypatch, date(2026, 11, 17))
    assert stale["ok"] is False and stale["severity"] == "error"


def test_wayback_copies_do_not_count_as_a_live_capture(conn, monkeypatch):
    commitments.record_snapshot(conn, "alpha", "policy", "https://alpha.example/policy.html",
                                _page("v1"), "text/html", wayback_timestamp="20240101000000",
                                retrieval_date=date.today().isoformat())
    assert _check(conn, monkeypatch, date.today())["ok"] is False


def test_the_doctor_only_reads(conn, monkeypatch):
    _serve(monkeypatch, requests.HTTPError("404 Client Error"))
    commitments.fetch_live(conn, _INSTS)
    before = conn.total_changes
    _check(conn, monkeypatch, date.today())
    assert conn.total_changes == before
    assert not conn.in_transaction


def test_the_attempt_log_is_operator_only():
    assert "capture_attempts" in publish.OPERATOR_ONLY
    assert "capture_attempts" not in publish.PUBLIC_TABLES


def test_attempt_and_snapshot_dates_share_one_clock(conn, monkeypatch):
    # Found on the first live run: attempts were stamped in UTC, snapshots in
    # local time, so a capture made just after local midnight read as yesterday's.
    _serve(monkeypatch, _Resp(_page("v1")))
    commitments.fetch_live(conn, _INSTS)
    stamp = conn.execute("SELECT attempted_at FROM capture_attempts").fetchone()[0]
    row = conn.execute("SELECT retrieval_date FROM commitments").fetchone()[0]
    assert stamp[:10] == row == date.today().isoformat()


# --- a truncated PDF is never a policy version (T. Rowe TRPA, 2026-11-17) ---
# pypdf: "Cannot find Root object in pdf" on a download that stopped short. The
# unreadable-text fallback is byte identity, so a partial file would have been
# filed as a brand-new version of the policy.

_GOOD_PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n" + b"x" * 3000 + b"\nstartxref\n116\n%%EOF\n"


class _PdfResp(_Resp):
    def __init__(self, content, declared=None):
        super().__init__(content, "application/pdf")
        if declared is not None:
            self.headers["Content-Length"] = str(declared)


def _serve_seq(monkeypatch, responses):
    it = iter(responses)
    monkeypatch.setattr(commitments.http, "get", lambda url, **kw: next(it))


def test_a_pdf_cut_short_is_a_failed_attempt_not_a_new_version(conn, monkeypatch):
    cut = _GOOD_PDF[:1500]                       # no %%EOF, shorter than declared
    _serve_seq(monkeypatch, [_PdfResp(cut, len(_GOOD_PDF))] * 2)
    assert commitments.fetch_live(conn, _PDF_INSTS) == {}
    assert [o for o, _ in _attempts(conn)] == ["failed"]
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


def test_a_pdf_without_end_marker_is_refused_even_without_content_length(conn, monkeypatch):
    _serve_seq(monkeypatch, [_PdfResp(_GOOD_PDF[:-12])] * 2)
    assert commitments.fetch_live(conn, _PDF_INSTS) == {}
    assert conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


def test_a_truncated_download_is_retried_once(conn, monkeypatch):
    _serve_seq(monkeypatch, [_PdfResp(_GOOD_PDF[:1500], len(_GOOD_PDF)),
                             _PdfResp(_GOOD_PDF, len(_GOOD_PDF))])
    assert commitments.fetch_live(conn, _PDF_INSTS) == {"alpha/policy": 1}
