"""The health check must notice a missing voting season.

Found 2026-11-16: the 2026 N-PX season had been on EDGAR since late August and
the ledger held none of it. `doctor` watched enforcement sources and policy
URLs but never the votes — the half of the record every rate is computed from.
"""

from __future__ import annotations

from datetime import date

from glasshouse import doctor, ledger


def _ledger(tmp_path, seasons):
    conn = ledger.connect(tmp_path / "l.db")
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('alpha','Alpha AM')")
    for n, (cik, period) in enumerate(seasons):
        conn.execute(
            "INSERT INTO filings (accession, cik, institution_id, form_type, period_of_report,"
            " report_type, source_url, retrieval_date) VALUES (?,?,'alpha','N-PX',?,"
            "'FUND VOTING REPORT','https://sec.example','2026-01-01')", (f"A{n}", cik, period))
    conn.commit()
    return conn


def test_a_season_past_its_filing_deadline_is_reported_missing(tmp_path):
    conn = _ledger(tmp_path, [("1", "06/30/2024"), ("1", "06/30/2025")])
    gaps = doctor.missing_vote_seasons(conn, today=date(2026, 11, 16))
    assert gaps == [{"institution": "alpha", "cik": "1", "latest_on_file": 2025,
                     "expected": 2026}]


def test_no_alarm_before_the_deadline_or_when_current(tmp_path):
    conn = _ledger(tmp_path, [("1", "06/30/2025"), ("2", "2026-06-30"), ("2", "06/30/2025")])
    assert doctor.missing_vote_seasons(conn, today=date(2026, 8, 20)) == []
    late = doctor.missing_vote_seasons(conn, today=date(2026, 11, 16))
    assert [g["cik"] for g in late] == ["1"]


def test_the_doctor_reports_it_as_an_error(tmp_path, monkeypatch):
    conn = _ledger(tmp_path, [("1", "06/30/2024")])
    monkeypatch.setattr(doctor, "_today", lambda: date(2026, 11, 16))
    names = {c["name"]: c for c in doctor.diagnose(conn)["checks"]}
    assert names["votes:alpha/1"]["ok"] is False
    assert names["votes:alpha/1"]["severity"] == "error"
