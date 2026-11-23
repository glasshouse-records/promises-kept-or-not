"""Legacy 'Issue No.' N-PX exported as HTML tables (Putnam, Neuberger Berman): detection,
the day-first guard on tag-stripped text, its own quarantined legacy_format and report types,
end to end through the shared 'Issue No.' mapping, and npx dispatch under --legacy-issueno."""

from __future__ import annotations

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_issueno, legacy_issueno_html, legacy_pe
from glasshouse.ingest.edgar import Filing

FUND = "Putnam Dynamic Asset Allocation Balanced Fund"
SID = "S000000009"
HDR = f"<SERIES-ID>{SID}\n<SERIES-NAME>{FUND}\n"
ACC = "0000928816-23-001234"


def _tr(*cells):
    return "<TR vAlign=top>" + "".join(f"<TD>{c}</TD>" for c in cells) + "</TR>\n"


def make_html(rows, date="06/13/2023", status="Voted", fund=FUND):
    """Putnam-style table; rows = [(issue, text, proponent, rec, vote, for_against)]."""
    out = ["<HTML><BODY><TABLE>",
           _tr("", "<B>Fund Name :</B>", f" {fund}"),
           '<TR height=50><TD></TD><TD colspan=8><HR noShade size=2></TD> <TR>',
           _tr("", "<B>2seventy bio, Inc.</B>", "", "", "", ""),
           _tr("", "", "<B>Ticker</B>", "<B>Security ID:</B>", "", "<B>Meeting Date</B>", "",
               "<B>Meeting Status</B>", ""),
           _tr("", "", "TSVT", "CUSIP 901384107", "", date, "", status, ""),
           _tr("", "", "<B>Meeting Type</B>", "<B>Country of Trade</B>", "", ""),
           _tr("", "", "Annual", "United States", "", ""),
           _tr("", "", "<B>Issue No.</B>", "<B>Description</B>", "", "<B>Proponent</B>",
               "<B>Mgmt Rec</B>", "<B>Vote Cast</B>", "<B>For/Agnst Mgmt</B>")]
    for i, t, p, rec, v, fa in rows:
        out.append(_tr("", "", i, t, "", p, rec, v, fa))
    out.append('<TR height=50><TD></TD><TD colspan=8><HR noShade size=2></TD> <TR>')
    out.append("</TABLE></BODY></HTML>")
    return "\n".join(out)


ROWS = [("1.1", "Elect Daniel S. Lynch", "Mgmt", "For", "For", "For"),
        ("2", "Ratification of Auditor", "Mgmt", "For", "Against", "Against"),
        ("3", "Report on Climate", "ShrHoldr", "Against", "Against", "For")]
DOC = make_html(ROWS)

NEUBERGER = (
    '<table><tr><td style="width: 20%">&#160;</td><td style="width: 9%"><div style="'
    'font-weight: bold;">Issue No.</div></td><td><div style="font-weight: bold;">Description'
    '</div></td><td>&#160;</td><td><div style="font-weight: bold;">Proponent</div></td><td>'
    '<div style="font-weight: bold;">Mgmt Rec</div></td><td><div>Vote Cast</div></td><td>'
    '<div>For/Agnst Mgmt</div></td></tr></table>')


# -- detection ----------------------------------------------------------------

def test_detects_putnam_and_neuberger_tables():
    assert legacy_iss.doc_format(DOC) == "issueno_html"
    assert legacy_iss.doc_format(NEUBERGER) == "issueno_html"


def test_text_layout_is_still_issueno_and_a_mix_is_refused():
    text = ("Issue No.  Description              Proponent  Mgmt Rec   Vote Cast  For/Against\n")
    assert legacy_iss.doc_format(text) == "issueno"
    assert legacy_iss.detect_format({"a": text, "b": DOC}) is None


def test_labels_outside_table_cells_are_not_the_html_layout():
    assert not legacy_iss.is_issueno_html(
        "<p>Issue No. Description Proponent Mgmt Rec Vote Cast</p>")


# -- day-first guard on the table text ---------------------------------------

def test_day_first_date_in_a_value_row_is_counted():
    assert legacy_issueno_html.day_first_dates(make_html(ROWS, date="13/06/2023")) == 1
    assert legacy_issueno_html.day_first_dates(DOC) == 0


def test_day_first_document_is_rejected_whole():
    rows, st = legacy_issueno_html.agreed(make_html(ROWS, date="30/06/2023"))
    assert rows == [] and st["disagreement_rate"] == 1.0 and st["day_first_dates"] == 1


# -- quarantine and mapping ----------------------------------------------------

def test_html_layout_promoted_after_review():
    # Promoted 2026-11-23 after the review fixes (c637249), a 14-row field-by-field hand
    # sample and a 54-row fund-attribution check against the filings.
    assert legacy_issueno_html.LEGACY_FORMAT == "issueno_html"
    assert "issueno_html" in ledger.PROMOTED_LEGACY_FORMATS


def test_agreed_rows_map_like_the_text_layout_but_tagged_html():
    rows, st = legacy_issueno_html.agreed(DOC)
    assert st["disagreement_rate"] == 0 and len(rows) == 3, st
    votes, info = legacy_issueno_html.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})
    assert [v["how_voted"] for v in votes] == ["FOR", "AGAINST", "AGAINST"]
    assert {v["legacy_format"] for v in votes} == {"issueno_html"}
    assert votes[0]["meeting_date"] == "06/13/2023" and votes[0]["cusip"] == "901384107"
    assert votes[2]["vote_source"] == "SECURITY HOLDER"
    assert votes[1]["for_against_management"] == "Against"
    # the text module's own rows keep their tag
    assert legacy_issueno.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})[0][0][
        "legacy_format"] == "issueno"


@pytest.mark.parametrize("status", ["Unvoted", "Take No Action"])
def test_unvoted_meetings_give_no_votes(status):
    rows, _ = legacy_issueno_html.agreed(make_html(ROWS, status=status))
    votes, info = legacy_issueno_html.to_vote_rows(rows, {legacy_pe._norm(FUND): SID})
    assert votes == [] and info["dropped_status"] == 3


# -- end to end ---------------------------------------------------------------

def _conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('ft','Franklin')")
    return c


def _filing():
    return Filing(cik="0000928816", company_name="Putnam Asset Allocation Funds",
                  form_type="N-PX", filing_date="2023-08-30", period_of_report="2023-06-30",
                  accession_number=ACC)


def test_end_to_end_ingest_report_types_and_promotion(tmp_path):
    conn = _conn(tmp_path)
    n = legacy_issueno_html.ingest_filing(conn, _filing(), "ft", "2026-11-23",
                                          {"a_npx.htm": DOC}, HDR)
    assert n == 3
    assert conn.execute("SELECT report_type FROM filings WHERE accession=?",
                        (ACC,)).fetchone()[0] == "LEGACY_ISSUENO_HTML"
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE legacy_format='issueno_html'"
                        ).fetchone()[0] == 3
    assert conn.execute(f"SELECT COUNT(*) FROM votes WHERE {ledger.NON_LEGACY_VOTE_SQL}"
                        ).fetchone()[0] == 3        # promoted: visible to analysis
    # a text-layout document in the same call is not read by the HTML module
    assert legacy_issueno_html.ingest_filing(conn, _filing(), "ft", "2026-11-23",
                                             {"a": "Agenda Number: 1\n"}, HDR) == 0


def test_rejected_report_type(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(legacy_issueno_html, "agreed", lambda t: ([], {
        "rows_a": 5, "rows_b": 0, "agreed": 0, "a_only": 5, "b_only": 0,
        "disagreement_rate": 1.0}))
    assert legacy_issueno_html.ingest_filing(conn, _filing(), "ft", "2026-11-23",
                                             {"a.htm": DOC}, HDR) == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == \
        "LEGACY_ISSUENO_HTML_REJECTED"


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
    return npx.ingest_npx(conn, "0000928816", institution_id="ft", **kw)


def test_npx_dispatch_under_the_issueno_flag_and_reingest(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    st = _npx_run(conn, monkeypatch, {"a.htm": DOC}, legacy_iss_text=True)
    assert st["votes"] == 0
    st = _npx_run(conn, monkeypatch, {"a.htm": DOC}, legacy_issueno_text=True)
    assert st["votes"] == 3 and st["filings"] == 1
    conn.execute("DELETE FROM votes WHERE accession=?", (ACC,))
    conn.commit()
    st = _npx_run(conn, monkeypatch, {"a.htm": DOC}, legacy_issueno_text=True,
                  reingest={ACC}, reingest_reason="test")
    assert st["votes"] == 3


# -- review 2026-11-23 (#4, #5) -------------------------------------------------

def test_detection_is_fast_on_many_empty_cells():
    import time
    bad = "Issue No." + "<td></td>" * 32000 + "Description"
    t = time.perf_counter()
    assert not legacy_iss.is_issueno_html(bad)
    assert time.perf_counter() - t < 1.0


def test_day_first_guard_does_not_depend_on_column_order():
    # date cell BEFORE the security id: the text-layout regex would miss it
    doc = DOC.replace("<TD>CUSIP 901384107</TD><TD></TD><TD>06/13/2023</TD>",
                      "<TD>24/05/2023</TD><TD></TD><TD>CUSIP 901384107</TD>")
    assert doc != DOC
    assert legacy_issueno_html.day_first_dates(doc) == 1


def test_day_first_guard_ignores_dates_in_proposal_text():
    doc = make_html([("1", "Approve Merger dated 30/06/2023", "Mgmt", "For", "For", "For")])
    assert legacy_issueno_html.day_first_dates(doc) == 0


# -- review 2026-11-23 (#1-#3), end to end through the agreement --------------

def _after_registrant_change():
    second = make_html([("1", "Elect Zed", "Mgmt", "For", "For", "For")])
    second = second.split(_tr("", "<B>Fund Name :</B>", f" {FUND}"), 1)[1]
    return (DOC.replace("</TABLE></BODY></HTML>", "")
            + _tr("", "<B>Registrant :</B>", " Other Trust") + second)


def test_registrant_change_never_carries_the_fund():
    rows, _ = legacy_issueno_html.agreed(_after_registrant_change())
    assert [r["proposal_text"] for r in rows] == [r[1] for r in ROWS]   # Zed dropped
    assert {r["fund_heading"] for r in rows} == {FUND}


def test_line_break_inside_a_cell_is_a_space():
    doc = make_html([("1", "Elect John<BR>Smith", "Mgmt", "For", "For", "For")])
    assert [r["proposal_text"] for r in legacy_issueno_html.agreed(doc)[0]] == ["Elect John Smith"]


def test_description_wrapped_onto_its_own_row_drops_the_meeting():
    doc = DOC.replace(
        _tr("", "", "2", "Ratification of Auditor", "", "Mgmt", "For", "Against", "Against"),
        _tr("", "", "2", "Shareholder Proposal Regarding", "", "Mgmt", "For", "Against", "Against")
        + _tr("", "", "", "Climate Lobbying", "", "", "", "", ""))
    assert doc != DOC
    assert legacy_issueno_html.agreed(doc)[0] == []


# -- ISS HTML detection: Franklin's td header (Amendment 4) --------------------

def test_franklin_td_header_is_iss_html():
    franklin = ('<table><tr><td style="x"><p style="y">Proposal No</p></td><td><p>Proposal</p></td>'
                '<td><p>Proposed By</p></td><td><p>Management Recommendation</p></td>'
                '<td><p>Vote Cast</p></td></tr></table>')
    assert legacy_iss.is_iss_html(franklin)
    assert legacy_iss.doc_format(franklin) == "iss_html"
    assert legacy_iss.is_iss_html("<table><tr><th>Proposal No</th></tr></table>")
    assert not legacy_iss.is_iss_html("<p>Proposal No</p>")          # not a cell
