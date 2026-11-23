"""Legacy 'Issue No.' N-PX ingestion: detection, two-parser agreement, series mapping,
contest drop, vote/proposer vocabulary, security ids, for/against, quarantine, end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_issueno, legacy_pe
from glasshouse.ingest.edgar import Filing

FIX = Path(__file__).parent / "fixtures" / "legacy_issueno_blocks"
SCHWAB = (FIX / "schwab_excerpt.txt").read_text()
CONTEST = (FIX / "schwab_contest.txt").read_text()
ECHO = (FIX / "schwab_echo.txt").read_text()
RUSSELL = (FIX / "russell_excerpt.txt").read_text()
FUND = "Schwab 1000 Index Fund"
SID = "S000000001"
HDR = f"<SERIES-ID>{SID}\n<SERIES-NAME>Schwab 1000 Index Fund\n"
SMAP = {legacy_pe._norm(FUND): SID}
ACC = "0001104659-23-095999"

COLS = "Issue No.  Description              Proponent  Mgmt Rec   Vote Cast  For/Against"


def make_doc(rows, fund=FUND, secid="CUSIP 88579Y101", mtype="Annual", status="Voted"):
    """rows = [(proponent, rec, vote, for_against)]; one meeting, one line per proposal."""
    out = [f"Fund Name : {fund}", "_" * 80, "3M Company",
           "Ticker     Security ID:             Meeting Date          Meeting Status",
           f"MMM        {secid:<24} 05/09/2023            {status}",
           "Meeting Type                        Country of Trade",
           f"{mtype:<35} United States", COLS, " " * 69 + "Mgmt", ""]
    for i, (p, rec, vote, fa) in enumerate(rows, 1):
        out.append(f"{i:<10} {'Proposal number ' + str(i):<24} {p:<10} {rec:<10} {vote:<10} {fa}")
    out.append("_" * 80)
    return "\n".join(out) + "\n"


def _rows(rows, smap=None, **kw):
    text = make_doc(rows, **kw)
    agreed, st = legacy_issueno.agreed(text)
    assert st["disagreement_rate"] == 0 and len(agreed) == len(rows), st
    return legacy_issueno.to_vote_rows(agreed, SMAP if smap is None else smap)


# -- detection ----------------------------------------------------------------

def test_detection_plain_upper_and_nbsp():
    assert legacy_issueno.is_issueno(SCHWAB)
    assert legacy_issueno.is_issueno(RUSSELL)               # upper case
    assert legacy_issueno.is_issueno(
        "Issue&nbsp;No.&nbsp;&nbsp;Description  Proponent&nbsp;Mgmt Rec  Vote Cast")
    assert not legacy_issueno.is_issueno("Issue No. Description Proponent Vote Cast")
    assert not legacy_issueno.is_issueno("Agenda Number: 1")


def test_doc_format_and_detect_format():
    assert legacy_iss.doc_format(SCHWAB) == "issueno"
    assert legacy_iss.detect_format({"a": SCHWAB, "b": RUSSELL}) == "issueno"
    assert legacy_iss.doc_format("Agenda Number: 1") == "proxyedge"
    assert legacy_iss.detect_format({"a": SCHWAB, "b": "Agenda Number: 1"}) is None
    assert "issueno" not in legacy_iss.PARSERS    # not wired through the ISS dispatch


# -- agreement ----------------------------------------------------------------

def test_agreed_on_fixture_has_all_stats():
    rows, st = legacy_issueno.agreed(SCHWAB)
    assert len(rows) == 13 and st["disagreement_rate"] == 0
    assert {"rows_a", "rows_b", "agreed", "a_only", "b_only", "rows_dropped_disputed",
            "meetings_dropped_disputed"} <= set(st)


def test_agreed_keeps_only_common_rows(monkeypatch):
    a = [dict.fromkeys(legacy_issueno.KEYS, "x") | {"issuer_name": n, "proposal_id": "1"}
         for n in "ABC"]
    b = a[:2]     # meeting C is disputed: parser B does not produce it

    class A:
        parse = staticmethod(lambda t: a)

    class B:
        parse = staticmethod(lambda t: b)
    rows, st = legacy_issueno.agreed("", (A, B))
    assert [r["issuer_name"] for r in rows] == ["A", "B"] and st["a_only"] == 1 and st["b_only"] == 0
    assert st["disagreement_rate"] == pytest.approx(1 / 3)
    assert len(legacy_issueno.KEYS) == 14


# -- mapping ------------------------------------------------------------------

def test_basic_row_mapping():
    votes, info = _rows([("Mgmt", "For", "For", "For")])
    v = votes[0]
    assert v["legacy_format"] == "issueno" and v["shares_voted"] is None
    assert v["category_type"] == "" and v["vote_series"] == SID
    assert v["how_voted"] == "FOR" and v["vote_source"] == "ISSUER"
    assert v["management_recommendation"] == "FOR" and v["for_against_management"] == "For"
    assert v["meeting_date"] == "05/09/2023" and v["cusip"] == "88579Y101" and v["isin"] == ""
    assert v["issuer_name"] == "3M Company" and v["vote_description"] == "Proposal number 1"


@pytest.mark.parametrize("raw,want", [
    ("For", "FOR"), ("FOR", "FOR"), ("Against", "AGAINST"), ("Abstain", "ABSTAIN"),
    ("Withhold", "WITHHOLD"), ("1 Year", "1 YEAR"), ("2 Years", "2 YEARS"),
    ("3 Years", "3 YEARS"), ("TNA", "TNA")])
def test_how_voted_vocabulary(raw, want):
    votes, _ = legacy_issueno.to_vote_rows([{**_agreed_row(), "vote": raw}], SMAP)
    assert votes[0]["how_voted"] == want


def test_na_and_echo_vote_dropped_and_counted():
    rows, st = legacy_issueno.agreed(ECHO)
    assert rows
    votes, info = legacy_issueno.to_vote_rows(rows, {legacy_pe._norm("Schwab Test Fund"): SID})
    assert votes == [] and info["dropped_vote"] + info["dropped_status"] == len(rows)
    votes, info = _rows([("Mgmt", "For", "N/A", "N/A"), ("Mgmt", "For", "For", "For")])
    assert len(votes) == 1 and info["dropped_vote"] == 1


def test_proponent_mapping_and_drop():
    votes, info = _rows([("Mgmt", "For", "For", "For"), ("ShrHoldr", "Against", "Against", "For"),
                         ("N/A", "For", "For", "For"), ("MGMT", "For", "For", "For")])
    assert [v["vote_source"] for v in votes] == ["ISSUER", "SECURITY HOLDER", "ISSUER"]
    assert info["dropped_sponsor"] == 1


def test_management_recommendation_is_xml_meaning():
    votes, _ = _rows([("Mgmt", "For", "Against", "Against"), ("ShrHoldr", "Against", "For", "Against"),
                      ("Mgmt", "N/A", "For", "For"), ("Mgmt", "For", "TNA", "N/A")])
    votes += legacy_issueno.to_vote_rows(
        [{**_agreed_row(), "rec": "1 Year", "vote": "3 Years"}], SMAP)[0]
    assert [v["management_recommendation"] for v in votes] == [
        "AGAINST", "AGAINST", "", "", "AGAINST"]


def test_for_against_is_filers_column():
    votes, _ = _rows([("Mgmt", "For", "For", "For"), ("Mgmt", "For", "Against", "Against"),
                      ("Mgmt", "For", "TNA", "N/A")])
    assert [v["for_against_management"] for v in votes] == ["For", "Against", None]


def test_contest_meeting_dropped_entirely():
    rows, _ = legacy_issueno.agreed(CONTEST)
    votes, info = legacy_issueno.to_vote_rows(
        rows, {legacy_pe._norm("Schwab Test Fund"): SID})
    assert votes == [] and info["contest_rows_dropped"] == len(rows) > 0
    votes, info = _rows([("Mgmt", "For", "For", "For")], mtype="Special Proxy CONTEST")
    assert votes == [] and info["contest_rows_dropped"] == 1


def test_security_ids():
    ok = {"CUSIP 88579Y101": ("88579Y101", ""), "CINS G1151C150": ("G1151C150", ""),
          "ISIN US88579Y1010": ("88579Y101", "US88579Y1010"),
          "SEDOL 2118050": ("", ""), "CUSIP 88579Y102": ("", ""),    # bad check digit
          "ISIN US88579Y1011": ("", ""), "CINS G1151C151": ("", "")}
    for printed, (cusip, isin) in ok.items():
        votes, _ = legacy_issueno.to_vote_rows(
            [{**_agreed_row(), "security_id": printed}], SMAP)
        assert (votes[0]["cusip"], votes[0]["isin"]) == (cusip, isin), printed
    cins_only = [{**_agreed_row(), "security_id": "ISIN GB00B4BNMY34"}]
    v, _ = legacy_issueno.to_vote_rows(cins_only, SMAP)
    assert v[0]["cusip"] == "" and v[0]["isin"] == "GB00B4BNMY34"


def _agreed_row():
    return legacy_issueno.agreed(make_doc([("Mgmt", "For", "For", "For")]))[0][0]


def test_unmapped_and_policy_section_dropped():
    votes, info = _rows([("Mgmt", "For", "For", "For")], smap={})
    assert votes == [] and info["unmapped"] == {FUND: 1}
    votes, info = _rows([("Mgmt", "For", "For", "For")], fund=FUND + " - GLASS LEWIS POLICY")
    assert votes == [] and info["policy_section_dropped"] == 1


# -- quarantine ---------------------------------------------------------------

def test_promoted_after_review(tmp_path):
    # Promoted 2026-11-23 after the reviewer pass (fixes e06dc99) and a 14-row hand sample.
    assert "issueno" in ledger.PROMOTED_LEGACY_FORMATS
    conn = _conn(tmp_path)
    _ingest(conn)
    n = conn.execute("SELECT COUNT(*) FROM votes WHERE legacy_format='issueno'").fetchone()[0]
    assert n > 0
    assert conn.execute(f"SELECT COUNT(*) FROM votes WHERE {ledger.NON_LEGACY_VOTE_SQL} "
                        "AND legacy_format='issueno'").fetchone()[0] == n
    assert conn.execute(f"SELECT COUNT(*) FROM votes v WHERE {ledger.non_legacy_vote_sql('v')} "
                        "AND v.legacy_format='issueno'").fetchone()[0] == n


# -- end to end ---------------------------------------------------------------

def _conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('sc','Schwab')")
    return c


def _filing():
    return Filing(cik="0000100002", company_name="Schwab", form_type="N-PX",
                  filing_date="2023-08-30", period_of_report="2023-06-30",
                  accession_number=ACC)


def _ingest(conn, text=SCHWAB, hdr=HDR):
    return legacy_issueno.ingest_filing(conn, _filing(), "sc", "2026-11-23",
                                        {"doc.txt": text}, hdr)


def test_end_to_end_ingest_and_idempotent(tmp_path):
    conn = _conn(tmp_path)
    assert _ingest(conn) == 13
    rt = conn.execute("SELECT report_type, source_url FROM filings WHERE accession=?",
                      (ACC,)).fetchone()
    assert rt[0] == "LEGACY_ISSUENO" and rt[1]
    row = conn.execute("SELECT parser_version, agreed, rows_inserted FROM legacy_parse "
                       "WHERE accession=?", (ACC,)).fetchone()
    assert tuple(row) == (legacy_pe.PARSER_VERSION, 13, 13)
    assert _ingest(conn) == 13
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE accession=?", (ACC,)).fetchone()[0] == 13
    assert conn.execute("SELECT COUNT(DISTINCT legacy_format) FROM votes").fetchone()[0] == 1


def test_rejected_when_parsers_disagree(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(legacy_issueno, "agreed", lambda t: ([], {
        "rows_a": 5, "rows_b": 0, "agreed": 0, "a_only": 5, "b_only": 0,
        "disagreement_rate": 1.0}))
    assert _ingest(conn) == 0
    assert conn.execute("SELECT report_type FROM filings WHERE accession=?",
                        (ACC,)).fetchone()[0] == "LEGACY_ISSUENO_REJECTED"
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0


def test_other_format_documents_skipped(tmp_path):
    conn = _conn(tmp_path)
    n = legacy_issueno.ingest_filing(conn, _filing(), "sc", "2026-11-23",
                                     {"doc.txt": "Agenda Number: 1\n"}, HDR)
    assert n == 0


# -- ingest_npx dispatch ------------------------------------------------------

def _npx_run(conn, monkeypatch, docs, **kw):
    import requests

    from glasshouse.ingest import npx

    def no_cover(url, *a, **k):
        r = requests.Response()
        r.status_code = 404
        raise requests.HTTPError(response=r)

    monkeypatch.setattr(npx, "list_filings", lambda *a, **k: [_filing()])
    monkeypatch.setattr(npx.http, "get", no_cover)
    monkeypatch.setattr(legacy_pe, "load_filing_texts", lambda f, cache_dir=None: (docs, HDR))
    return npx.ingest_npx(conn, "0000100002", institution_id="sc", **kw)


def test_npx_flag_is_opt_in(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    for flags in ({}, {"legacy_iss_text": True, "legacy_proxyedge": True}):
        st = _npx_run(conn, monkeypatch, {"a": SCHWAB}, **flags)
        assert st["votes"] == 0 and st["filings"] == 0
    assert [r[0] for r in conn.execute("SELECT report_type FROM filings")] == ["LEGACY_NO_COVER"]
    st = _npx_run(conn, monkeypatch, {"a": SCHWAB}, legacy_issueno_text=True)
    assert st["votes"] == 13 and st["filings"] == 1
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISSUENO"


def test_npx_reingest_handles_issueno(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _npx_run(conn, monkeypatch, {"a": SCHWAB}, legacy_issueno_text=True)
    conn.execute("DELETE FROM votes WHERE accession=?", (ACC,))
    conn.commit()
    st = _npx_run(conn, monkeypatch, {"a": SCHWAB}, legacy_issueno_text=True,
                  reingest={ACC}, reingest_reason="test")
    assert st["votes"] == 13
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE accession=?", (ACC,)).fetchone()[0] == 13



@pytest.mark.parametrize("status", ["Unvoted", "Take No Action", "Not Voted"])
def test_only_voted_meetings_become_votes(status):
    # Review 2026-11-23: VanEck Oil Services ETF / Liberty Energy 04/18/2023 is printed
    # 'Unvoted' with Withhold/For in the vote column: those instructions were never cast.
    votes, info = _rows([("Mgmt", "For", "Withhold", "Against"), ("Mgmt", "For", "For", "For")],
                        status=status)
    assert votes == [] and info["dropped_status"] == 2


def test_voted_status_any_case_is_kept():
    votes, info = _rows([("Mgmt", "For", "For", "For")], status="VOTED")
    assert len(votes) == 1 and info["dropped_status"] == 0
