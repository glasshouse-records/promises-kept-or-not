"""Source freshness means "last time the source was successfully fetched".

Found 2026-11-17: `ingest enforcement --source doj_fcpa` fetched 511 records,
0 new, and the doctor still said the last ingest was 159 days ago, because it
read the newest row's retrieval_date. A source that is checked and has nothing
new looked dead forever. Every run is now recorded in `ingest_runs`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from glasshouse import doctor, ledger, publish, registry


@pytest.fixture
def conn(tmp_path, monkeypatch):
    c = ledger.connect(tmp_path / "l.db")
    monkeypatch.setattr(registry, "load", lambda *a, **k: {})
    # one old DOJ row: the legacy signal says "159 days ago"
    old = (date.today() - timedelta(days=159)).isoformat()
    c.execute(
        "INSERT INTO enforcement_actions (agency, source_kind, retrieval_date, "
        "source_url, resolution_type, company_name, action_date) "
        "VALUES ('DOJ (FCPA)','live',?,'https://x.example','allegation','Acme','2020-01-01')",
        (old,))
    c.commit()
    return c


def _doj(conn):
    monkey_today = date.today()
    doctor._today = lambda: monkey_today  # restored by fixture below
    names = {c["name"]: c for c in doctor.diagnose(conn)["checks"]}
    return names["source:DOJ (FCPA)"]


@pytest.fixture(autouse=True)
def _restore_today():
    orig = doctor._today
    yield
    doctor._today = orig


def test_a_successful_zero_new_run_makes_the_source_fresh(conn):
    ledger.record_ingest_run(conn, "doj_fcpa", fetched=511, inserted=0)
    c = _doj(conn)
    assert c["ok"] is True
    assert "0d ago" in c["detail"]


def test_a_zero_fetched_run_is_not_a_success(conn):
    ledger.record_ingest_run(conn, "doj_fcpa", fetched=0, inserted=0)
    c = _doj(conn)
    assert c["ok"] is False
    assert conn.execute("SELECT ok FROM ingest_runs").fetchone()[0] == 0


def test_without_run_records_the_old_behaviour_holds(conn):
    c = _doj(conn)
    assert c["ok"] is False
    assert "159d ago" in c["detail"]


def test_a_failed_run_does_not_hide_an_older_success(conn):
    ledger.record_ingest_run(conn, "doj_fcpa", fetched=511, inserted=0)
    ledger.record_ingest_run(conn, "doj_fcpa", fetched=0, inserted=0, error="boom")
    assert _doj(conn)["ok"] is True


def test_the_doctor_only_reads(conn):
    ledger.record_ingest_run(conn, "doj_fcpa", fetched=511, inserted=0)
    before = conn.total_changes
    _doj(conn)
    assert conn.total_changes == before
    assert not conn.in_transaction


def test_ingest_runs_is_operator_only():
    assert "ingest_runs" in publish.OPERATOR_ONLY
    assert "ingest_runs" not in publish.PUBLIC_TABLES
