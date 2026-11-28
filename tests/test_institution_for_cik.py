"""Orphan filings: a CIK resolves to exactly one registered institution or to none."""

import argparse

from glasshouse import cli, ledger, registry

INSTS = {
    "a": {"display_name": "A", "cik": "0000000100",
          "npx_ciks": [{"cik": "0000000111", "name": "A Trust"}]},
    "b": {"display_name": "B", "cik": "200"},                       # falls back to manager CIK
    "c": {"display_name": "C", "cik": "300",
          "npx_ciks": [{"cik": "999", "name": "Shared"}]},
    "d": {"display_name": "D", "cik": "400",
          "npx_ciks": [{"cik": "0999", "name": "Shared"}]},
}


def test_unique_unregistered_ambiguous_padding():
    f = registry.institution_for_cik
    assert f("111", INSTS) == "a"
    assert f("0000000111", INSTS) == "a"
    assert f("200", INSTS) == "b"
    assert f("12345", INSTS) is None
    assert f("999", INSTS) is None                                  # two institutions
    assert f("not-a-cik", INSTS) is None


def _filing(c, acc, cik, inst, votes=True):
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES (?,?,?,'N-PX','https://e','2026-01-01')", (acc, cik, inst))
    if votes:
        c.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted) "
                  "VALUES (?,'X','FOR',1)", (acc,))
    c.commit()


def test_backfill_sets_only_null(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    registry.sync_to_ledger(c, INSTS)
    _filing(c, "N1", "111", None)
    _filing(c, "N2", "200", None)
    _filing(c, "N3", "999", None)             # ambiguous: untouched
    _filing(c, "N4", "111", "b")              # non-NULL, even if "wrong": untouched
    got = ledger.backfill_filing_institutions(c, INSTS)
    assert sorted(got) == [("N1", "111", "a"), ("N2", "200", "b")]
    rows = dict(c.execute("SELECT accession, institution_id FROM filings"))
    assert rows == {"N1": "a", "N2": "b", "N3": None, "N4": "b"}
    assert ledger.backfill_filing_institutions(c, INSTS) == []      # idempotent


def test_integrity_flags_orphan_with_votes_only(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O1", "111", None, votes=False)
    assert ledger.integrity_check(c)["filings_with_votes_no_institution"] == []
    _filing(c, "O2", "111", None, votes=True)
    assert [r[0] for r in ledger.integrity_check(c)["filings_with_votes_no_institution"]] == ["O2"]


def _args(**kw):
    d = {"cik": None, "institution": None, "reingest": None, "reason": None,
         "max_filings": None, "max_tables": None}
    d.update(kw)
    return argparse.Namespace(**d)


def test_cli_refuses_unregistered_and_mismatch(tmp_path, monkeypatch, capsys):
    c = ledger.connect(tmp_path / "l.db")
    monkeypatch.setattr(cli, "_conn", lambda: c)
    monkeypatch.setattr(registry, "load", lambda *a, **k: INSTS)
    called = []
    from glasshouse.ingest import npx
    monkeypatch.setattr(npx, "ingest_npx", lambda *a, **k: called.append(k) or {})
    assert cli.cmd_ingest_npx(_args(cik="12345")) == 2
    assert "--institution" in capsys.readouterr().err
    assert cli.cmd_ingest_npx(_args(cik="111", institution="b")) == 2
    assert not called
    assert cli.cmd_ingest_npx(_args(cik="111")) == 0
    assert called[-1]["institution_id"] == "a"


def test_cli_reingest_null_institution(tmp_path, monkeypatch):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "R1", "111", None, votes=False)
    monkeypatch.setattr(cli, "_conn", lambda: c)
    monkeypatch.setattr(registry, "load", lambda *a, **k: INSTS)
    called = []
    from glasshouse.ingest import npx
    monkeypatch.setattr(npx, "ingest_npx", lambda *a, **k: called.append(k) or {})
    assert cli.cmd_ingest_npx(_args(reingest="R1", reason="t")) == 0
    assert called[0]["institution_id"] == "a"
    _filing(c, "R2", "12345", None, votes=False)
    assert cli.cmd_ingest_npx(_args(reingest="R2", reason="t")) == 2
