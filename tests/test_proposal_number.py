"""votes.proposal_number: the printed item number of a 2022-23 legacy line (found 2026-11-27).

A fund can print two different agenda items with identical text at one meeting (Principal
Funds 04/26/2023: 56 sub-fund copies of one item; 'Instructions if Meeting is Held on Second
Call' as items 4 and 33). Without the number, dedupe and the engine merged them."""

import test_legacy_iss as ti
import test_legacy_issueno as tn
import test_legacy_pe as tp

from glasshouse import ledger
from glasshouse.ingest import legacy_issueno, legacy_pe


def _filing(c, acc, form="N-PX", date="2023-08-24", cik="1"):
    c.execute("INSERT INTO filings (accession, cik, form_type, filing_date, period_of_report, "
              "source_url, retrieval_date) VALUES (?,?,?,?,'06/30/2023','https://e','2026-11-27')",
              (acc, cik, form, date))


def _vote(c, acc, pn, how="FOR", legacy=True):
    c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
              "vote_series, how_voted, shares_voted, legacy_format, proposal_number) "
              "VALUES (?,'X','C','04/26/2023','Second call','S1',?,NULL,?,?)",
              (acc, how, "issueno" if legacy else None, pn))


def _live(c):
    return c.execute("SELECT COUNT(*) FROM votes WHERE is_duplicate = 0").fetchone()[0]


def test_column_exists_and_migrates(tmp_path):
    p = tmp_path / "old.db"
    c = ledger.connect(p)
    c.execute("ALTER TABLE votes DROP COLUMN proposal_number")
    c.commit()
    c.close()
    c = ledger.connect(p)
    assert "proposal_number" in {r[1] for r in c.execute("PRAGMA table_info(votes)")}


def test_dedupe_keeps_distinct_numbers_and_collapses_the_same_number(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "A")
    _vote(c, "A", "4")
    _vote(c, "A", "33")
    _vote(c, "A", "33")
    c.commit()
    ledger.dedupe_votes(c)
    assert _live(c) == 2


def test_dedupe_xml_null_numbers_unchanged(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "A")
    for _ in range(3):
        _vote(c, "A", None, legacy=False)
    c.commit()
    ledger.dedupe_votes(c)
    assert _live(c) == 1


def test_amendment_supersedes_per_item_number(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    _filing(c, "O")
    _filing(c, "AM", "N-PX/A", "2023-09-01")
    _vote(c, "O", "4")
    _vote(c, "O", "33")
    _vote(c, "AM", "4", how="AGAINST")   # the amendment restates item 4 only
    c.commit()
    ledger.dedupe_votes(c)
    live = {tuple(r) for r in c.execute(
        "SELECT accession, proposal_number FROM votes WHERE is_duplicate = 0")}
    assert live == {("O", "33"), ("AM", "4")}


def test_issueno_and_issueno_family_carry_the_number():
    rows, _ = tn._rows([("Mgmt", "For", "For", "For"), ("Mgmt", "For", "For", "For")])
    assert [r["proposal_number"] for r in rows] == ["1", "2"]


def test_issueno_blank_number_is_none():
    (r,), _ = legacy_issueno.to_vote_rows([{**tn._agreed_row(), "proposal_id": "  "}], tn.SMAP)
    assert r["proposal_number"] is None


def test_iss_rows_carry_the_number():
    rows, _ = ti._rows(ti.FUND, [ti.MGMT])
    assert rows and all(r["proposal_number"] for r in rows)


def test_proxyedge_rows_carry_the_number():
    (v,), _ = legacy_pe.to_vote_rows([tp._row(proposal_id=" 33 ")], tp.SMAP)
    assert v["proposal_number"] == "33"
    (v,), _ = legacy_pe.to_vote_rows([tp._row(proposal_id="")], tp.SMAP)
    assert v["proposal_number"] is None
