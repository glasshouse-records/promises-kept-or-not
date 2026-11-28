"""Proposal ids are a pure function of the item, not of build order (ROADMAP 3b-e):
drafts that cite a proposal_id must survive any later ingest."""

import pytest

from glasshouse import engine, ledger


def _ledger(tmp_path, name, extra=False, reverse=False):
    led = tmp_path / f"{name}.db"
    c = ledger.connect(led)
    for iid in ("alpha", "beta"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"A-{iid}", "1", iid, f"https://sec.example/{iid}"))

    def vote(iid, desc, issuer, cusip, date="05/20/2024", how="FOR"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, is_duplicate) VALUES (?,?,?,?,?,'SECURITY HOLDER',?,'FOR',10,0)",
                  (f"A-{iid}", issuer, cusip, date, desc, how))

    rows = [("alpha", "Report on Climate Transition Plan", "EXXON", "30231G102"),
            ("beta", "Report on Climate Transition Plan", "EXXON", "30231G102"),
            ("alpha", "Report on Lobbying Payments", "CHEVRON", "166764100")]
    if extra:                       # unrelated rows ingested later
        rows += [("alpha", "Report on Plastic Pollution", "PEPSI", "713448108"),
                 ("beta", "Report on Lobbying Payments", "CHEVRON", "166764100")]
    for r in (reversed(rows) if reverse else rows):
        vote(*r)
    c.commit()
    c.close()
    return led


def _ids(tmp_path, name, **kw):
    led = _ledger(tmp_path, name, **kw)
    out = tmp_path / f"{name}.engine.db"
    engine.build(led, out)
    e = engine.Engine(out, led)
    return {(r["institution_id"], r["issuer_name"], r["description"]): r["proposal_id"]
            for r in e.db.execute("SELECT * FROM proposals")}


def test_same_ledger_same_ids_whatever_the_row_order(tmp_path):
    a = _ids(tmp_path, "a")
    b = _ids(tmp_path, "b", reverse=True)
    assert a == b and len(set(a.values())) == len(a)


def test_unrelated_rows_do_not_renumber_existing_proposals(tmp_path):
    before = _ids(tmp_path, "before")
    after = _ids(tmp_path, "after", extra=True)
    assert len(after) == len(before) + 2
    for k, pid in before.items():
        assert after[k] == pid


def test_ids_fit_sqlite_and_are_positive(tmp_path):
    for pid in _ids(tmp_path, "x").values():
        assert 0 < pid < 2 ** 63


def test_an_id_collision_fails_the_build_loudly(monkeypatch):
    monkeypatch.setattr(engine, "_hash_id", lambda parts: 7)
    groups = {("a", None, "c", "d", "x", "xml"): {"era": "xml", "extra": False},
              ("b", None, "c", "d", "x", "xml"): {"era": "xml", "extra": False}}
    with pytest.raises(RuntimeError, match="collision"):
        engine._stable_ids(groups)
