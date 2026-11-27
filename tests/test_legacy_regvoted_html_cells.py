from glasshouse.ingest import legacy_regvoted_html_cells as c
from glasshouse.ingest.legacy_issueno import KEYS

HDR = ("<tr><td colspan=2><b>Proposal</b></td><td></td><td><b>Proposed by</b></td>"
       "<td><b>Mgt. Position</b></td><td><b>Registrant Voted</b></td></tr>")


def tr(*cells):
    return "<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"


def doc(*rows, heading="Democracy International Fund"):
    return ("<html><body><table>" + tr(f"<b>{heading}</b>") + HDR + "".join(rows)
            + "</table></body></html>")


ABB = [tr("<b>ABB LTD.</b>"), tr("<i>Security ID: H0010V101</i>", "<i>Ticker: ABBN</i>"),
       tr("Meeting Date: 07-Sep-22", "Meeting Type: Extraordinary Shareholders")]


def prop(n, text, pr="Management", rec="For", vote="Voted - For"):
    return tr(n, text, pr, rec, vote)


def test_numbered_example_and_keys():
    rows = c.parse(doc(*ABB, prop("1", "Approve Spin-Off of Accelleron Industries AG")))
    assert rows == [{
        "fund_heading": "Democracy International Fund", "issuer_name": "ABB LTD.",
        "ticker": "ABBN", "security_id": "H0010V101", "meeting_date": "09/07/2022",
        "meeting_status": "", "meeting_type": "Extraordinary Shareholders", "country": "",
        "proposal_id": "1", "proposal_text": "Approve Spin-Off of Accelleron Industries AG",
        "proponent": "Management", "rec": "For", "vote": "For", "for_against": ""}]
    assert tuple(rows[0]) == KEYS


def test_unnumbered_and_vote_forms():
    rows = c.parse(doc(*ABB,
        tr("Accept Financial Statements", "Management", "For", "Voted - For"),
        tr("Frequency", "Management", "One Year", "Voted - One Year")))
    assert [r["proposal_id"] for r in rows] == ["", ""]
    assert rows[0]["vote"] == "For" and rows[1]["vote"] == "One Year"


def test_wrapped_proposal_with_empty_cells():
    rows = c.parse(doc(*ABB, tr("2", "Approve the allocation of"), tr("", "income", ""),
        "<tr><td></td><td>Profits/Dividends</td><td></td><td>Management</td><td>For</td>"
        "<td>Voted - Against</td></tr>"))
    assert len(rows) == 1
    assert rows[0]["proposal_text"] == "Approve the allocation of income Profits/Dividends"
    assert rows[0]["vote"] == "Against" and rows[0]["proposal_id"] == "2"


def test_meeting_for_adr_is_continuation_not_meeting():
    rows = c.parse(doc(*ABB, tr("Meeting for ADR Holders"),
                       prop("1", "Approve X")))
    assert [r["proposal_text"] for r in rows] == ["Approve X"]
    assert c.parse_stats(doc(*ABB, tr("Meeting for ADR Holders"),
                             prop("1", "Approve X")))["proposal_unclosed"] == 1


def test_security_ticker_same_cell_and_meeting_type_second_cell():
    d = doc(tr("Foo"), tr("Security ID: B44DPG3 BD5CMH2 Ticker: FOO"),
            tr("Meeting Date: 01-Jan-23", "Meeting Type: Annual"), prop("1", "A"))
    r = c.parse(d)[0]
    assert (r["security_id"], r["ticker"], r["meeting_type"]) == (
        "B44DPG3 BD5CMH2", "FOO", "Annual")
    r = c.parse(doc(tr("Foo"), tr("Security ID: X1"), tr("Meeting Date: 01-Jan-23"),
                    prop("1", "A")))[0]
    assert r["ticker"] == "" and r["meeting_type"] == ""


def test_repeated_header_continues_meeting_and_bare_date_after_it():
    d = doc(*ABB, prop("1", "A"), tr("<b>Democracy International Fund</b>"), HDR,
            prop("2", "B"), tr("<b>Democracy International Fund</b>"),
            HDR, tr("Meeting Date: 08-Sep-22"), prop("1", "C"))
    rows = c.parse(d)
    assert [r["proposal_text"] for r in rows] == ["A", "B", "C"]
    assert rows[2]["issuer_name"] == "ABB LTD." and rows[2]["meeting_date"] == "09/08/2022"


def test_different_heading_starts_new_fund_no_identity():
    d = doc(*ABB, prop("1", "A"), tr("Other Fund"), HDR, tr("Meeting Date: 08-Sep-22"),
            prop("1", "B"))
    assert [r["proposal_text"] for r in c.parse(d)] == ["A"]


def test_bare_date_after_closed_proposal_inherits():
    rows = c.parse(doc(*ABB, prop("1", "A"), tr("Meeting Date: 20-Oct-22"), prop("1", "B")))
    assert [(r["proposal_text"], r["meeting_date"], r["issuer_name"]) for r in rows] == [
        ("A", "09/07/2022", "ABB LTD."), ("B", "10/20/2022", "ABB LTD.")]


def test_bare_date_without_identity_dropped_and_later_one_too():
    d = doc(tr("Foo"), tr("Security ID: X1"), tr("Something else"),
            tr("Meeting Date: 01-Jan-23"), prop("1", "A"),
            tr("Meeting Date: 02-Jan-23"), prop("1", "B"))
    assert c.parse(d) == []
    s = c.parse_stats(d)
    assert s["meeting_dropped_no_date_row"] == 1
    assert s["meeting_dropped_bare_date"] == 2


def test_bare_date_not_after_closed_proposal_dropped():
    d = doc(*ABB, prop("1", "A"), tr("dangling text"), tr("Meeting Date: 02-Jan-23"),
            prop("1", "B"))
    assert [r["proposal_text"] for r in c.parse(d)] == ["A"]
    assert c.parse_stats(d)["meeting_dropped_bare_date"] == 1


def test_contest_cases_drop_whole_meeting():
    for rows in (
        [prop("1", "Elect Dissident Nominee X")],
        [prop("1", "Elect Management Nominee Y")],
        [prop("1", "A"), prop("1", "B")],
        [tr("Elect A", "Management", "For", "Voted - For"),
         tr("Elect A", "Management", "For", "Voted - For")],
    ):
        assert c.parse(doc(*ABB, *rows)) == []
    d = doc(tr("Foo"), tr("Security ID: X1"),
            tr("Meeting Date: 01-Jan-23", "Meeting Type: Proxy Contest"), prop("1", "A"))
    assert c.parse(d) == []


def test_unclosed_proposal_dropped():
    d = doc(*ABB, tr("1", "Approve something"), prop("2", "B"), tr("3", "never closed"))
    assert [r["proposal_id"] for r in c.parse(d)] == ["2"]
    assert c.parse_stats(d)["proposal_unclosed"] == 2


def test_en_dash_is_not_column_row():
    d = doc(*ABB, tr("1", "A", "Management", "For", "Voted – For"))
    assert c.parse(d) == []


def test_orphan_column_row_drops_meeting():
    d = doc(*ABB, tr("Management", "For", "Voted - For"))
    assert c.parse(d) == []
    assert c.parse_stats(d)["meeting_dropped_orphan_column_row"] == 1


def test_heading_must_be_single_value():
    d = ("<table>" + tr("a", "b") + HDR + "</table>")
    assert c.parse(d) == [] and c.parse_stats(d)["doc_rejected_heading"] == 1


def test_entities_and_nbsp():
    rows = c.parse(doc(*ABB, prop("1", "Smith&nbsp;&amp;&#160;Sons")))
    assert rows[0]["proposal_text"] == "Smith & Sons"


def test_bad_date_drops_meeting():
    d = doc(tr("Foo"), tr("Security ID: X1"), tr("Meeting Date: 31-Feb-23"), prop("1", "A"))
    assert c.parse(d) == []


# ---- amendments HR1-HR5 ----

def div(x):
    return f"<div>{x}</div>"


def test_hr1_div_rows_between_tables():
    d = ("<body><p><b>Fund Z</b></p><table>" + HDR + "</table>" + div("<b>ABB LTD.</b>")
         + div("<i>Security ID: 000375204</i>") + div("Ticker: ABBN")
         + div("Meeting Date: 07-Sep-22") + div("Meeting Type: Extraordinary")
         + "<table>" + prop("1", "A") + "</table></body>")
    r = c.parse(d)
    assert len(r) == 1
    assert (r[0]["fund_heading"], r[0]["issuer_name"], r[0]["security_id"], r[0]["ticker"],
            r[0]["meeting_type"], r[0]["meeting_date"]) == (
        "Fund Z", "ABB LTD.", "000375204", "ABBN", "Extraordinary", "09/07/2022")


def test_hr1_wrapper_div_and_div_in_table_are_not_rows():
    d = ("<p>Fund Z</p><table>" + HDR + "</table><div>" + div("Foo") + div("Security ID: X1")
         + div("Meeting Date: 01-Jan-23") + "</div><table>"
         + tr("<div>1</div>", "<div>Approve A</div>", "Management", "For", "Voted - For")
         + "</table>")
    r = c.parse(d)
    assert [(x["issuer_name"], x["proposal_text"]) for x in r] == [("Foo", "Approve A")]


def test_hr1_unclosed_p():
    d = "<p>Fund Z</p><table>" + HDR + "".join(ABB) + prop("1", "A") + "</table>"
    assert len(c.parse(d)) == 1


def test_hr2_tables_are_not_breaks():
    d = ("<table>" + tr("<b>F</b>") + HDR + "".join(ABB) + tr("1", "Approve")
         + "</table><table>" + tr("of things", "Management", "For", "Voted - For") + "</table>")
    r = c.parse(d)
    assert [x["proposal_text"] for x in r] == ["Approve of things"]


def test_hr3_ticker_and_type_rows():
    d = doc(tr("Foo"), tr("Security ID: X1"), tr("Ticker: FOO"), tr("Meeting Date: 01-Jan-23"),
            tr("Meeting Type: Annual"), prop("1", "A"), tr("Meeting Date: 02-Jan-23"),
            tr("Meeting Type: Special"), prop("1", "B"))
    r = c.parse(d)
    assert [(x["ticker"], x["meeting_type"]) for x in r] == [("FOO", "Annual"),
                                                              ("FOO", "Special")]


def test_hr4_page_furniture_ignored():
    d = doc(*ABB, tr("1", "Approve"), tr("Page | 3"), tr("Page 4"), tr("5"),
            tr("of things", "Management", "For", "Voted - For"))
    r = c.parse(d)
    assert r[0]["proposal_text"] == "Approve of things"
    assert c.parse_stats(d)["page_furniture"] == 3


def test_hr5_empty_security_id_kept():
    r = c.parse(doc(tr("Foo"), tr("Security ID:"), tr("Meeting Date: 01-Jan-23"),
                    prop("1", "A")))
    assert len(r) == 1 and r[0]["security_id"] == ""
