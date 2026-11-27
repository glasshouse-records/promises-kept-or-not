"""Regex row parser for the 'Registrant Voted' HTML layout (contract H1-H9)."""
from glasshouse.ingest import legacy_regvoted_html_rows as P
from glasshouse.ingest.legacy_issueno import KEYS

HEAD = ("<tr><td colspan=3><b>Democracy International Fund</b></td></tr>"
        "<tr><td colspan=2><b>Proposal</b></td><td></td><td><b>Proposed by</b></td>"
        "<td><b>Mgt. Position</b></td><td><b>Registrant Voted</b></td></tr>")


def tr(*cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def doc(*rows, head=HEAD):
    return "<html><body><table>" + head + "".join(rows) + "</table></body></html>"


def issuer(name="ABB LTD.", sid="H0010V101", tick="ABBN", dt="07-Sep-22",
           mtype="Extraordinary Shareholders"):
    return (tr(f"<b>{name}</b>", "", "") + tr(f"<i>Security ID: {sid}</i>", f"<i>Ticker: {tick}</i>")
            + tr(f"Meeting Date: {dt}", f"Meeting Type: {mtype}"))


def prop(pid, text, pos="Management", rec="For", vote="Voted - For"):
    return tr(pid, text, pos, rec, vote)


def test_basic_row_and_keys():
    rows = P.parse(doc(issuer(), prop("1", "Approve Spin-Off")))
    assert len(rows) == 1
    r = rows[0]
    assert tuple(r) == KEYS
    assert r == {
        "fund_heading": "Democracy International Fund", "issuer_name": "ABB LTD.",
        "ticker": "ABBN", "security_id": "H0010V101", "meeting_date": "09/07/2022",
        "meeting_status": "", "meeting_type": "Extraordinary Shareholders", "country": "",
        "proposal_id": "1", "proposal_text": "Approve Spin-Off", "proponent": "Management",
        "rec": "For", "vote": "For", "for_against": ""}


def test_cell_positions_and_entities_ignored():
    html = doc(issuer(), tr("1", "", "Approve &amp; Ratify&nbsp;it", "", "Management", "For", "Voted - Against"))
    r = P.parse(html)[0]
    assert r["proposal_text"] == "Approve & Ratify it" and r["vote"] == "Against"


def test_unnumbered_and_wrapped():
    html = doc(issuer(), tr("Elect Directors", "", ""), tr("and ratify", "Management", "For", "Voted - For"),
               prop("2", "Second"))
    rows = P.parse(html)
    assert [r["proposal_id"] for r in rows] == ["", "2"]
    assert rows[0]["proposal_text"] == "Elect Directors and ratify"


def test_numbered_wrapped_over_rows():
    html = doc(issuer(), tr("1.a", "Elect Jane"), tr("Doe as director"),
               tr("Management", "For", "Voted - For"))
    r = P.parse(html)[0]
    assert r["proposal_id"] == "1.a" and r["proposal_text"] == "Elect Jane Doe as director"


def test_id_trailing_dot_removed():
    assert P.parse(doc(issuer(), prop("3.", "x")))[0]["proposal_id"] == "3"


def test_security_id_ticker_same_value_and_missing():
    html = doc(tr("<b>FOO</b>"), tr("Security ID: B44DPG3 BD5CMH2 Ticker: FOO"),
               tr("Meeting Date: 01-Jan-23 Meeting Type: Annual"), prop("1", "x"),
               tr("<b>BAR</b>"), tr("Security ID: 123"), tr("Meeting Date: 02-Feb-23"), prop("1", "y"))
    a, b = P.parse(html)
    assert (a["security_id"], a["ticker"], a["meeting_type"]) == ("B44DPG3 BD5CMH2", "FOO", "Annual")
    assert (b["security_id"], b["ticker"], b["meeting_type"], b["meeting_date"]) == ("123", "", "", "02/02/2023")


def test_security_id_case_exact():
    html = doc(tr("<b>FOO</b>"), tr("Security Id: 1"), tr("Meeting Date: 01-Jan-23"), prop("1", "x"))
    assert P.parse(html) == []


def test_repeated_header_continues_meeting():
    html = doc(issuer(), prop("1", "a"), "</table><table>" + HEAD, prop("2", "b"))
    rows = P.parse(html)
    assert [r["proposal_id"] for r in rows] == ["1", "2"]
    assert rows[1]["issuer_name"] == "ABB LTD."


def test_repeated_header_then_bare_meeting_date():
    html = doc(issuer(), prop("1", "a"), "</table><table>" + HEAD,
               tr("Meeting Date: 08-Sep-22", "Meeting Type: Annual"), prop("1", "b"))
    rows = P.parse(html)
    assert [r["meeting_date"] for r in rows] == ["09/07/2022", "09/08/2022"]
    assert rows[1]["security_id"] == "H0010V101"


def test_different_heading_starts_new_fund_and_drops_bare_date():
    head2 = HEAD.replace("Democracy International Fund", "Other Fund")
    html = doc(issuer(), prop("1", "a"), "</table><table>" + head2,
               tr("Meeting Date: 08-Sep-22"), prop("1", "b"))
    rows = P.parse(html)
    assert len(rows) == 1
    assert P.parse_stats(html)["drop_meeting_bare_date"] == 1


def test_bare_date_after_close_continues():
    html = doc(issuer(), prop("1", "a"), tr("Meeting Date: 08-Sep-22"), prop("1", "b"))
    rows = P.parse(html)
    assert [r["meeting_date"] for r in rows] == ["09/07/2022", "09/08/2022"]


def test_bare_date_not_after_close_drops_and_leaves_no_identity():
    html = doc(issuer(), prop("1", "a"), tr("some text"), tr("Meeting Date: 08-Sep-22"),
               prop("1", "b"), tr("Meeting Date: 09-Sep-22"), prop("1", "c"))
    rows = P.parse(html)
    assert [r["proposal_text"] for r in rows] == ["a"]
    assert P.parse_stats(html)["drop_meeting_bare_date"] == 2


def test_meeting_prefix_trap():
    html = doc(issuer(), tr("Meeting for ADR Holders"), tr("1", "Approve x", "Management", "For", "Voted - For"))
    rows = P.parse(html)
    assert len(rows) == 1 and rows[0]["proposal_id"] == "1"
    html = doc(issuer(), prop("1", "a"), tr("Meeting of Board of Directors"), prop("2", "b"))
    assert [r["proposal_id"] for r in P.parse(html)] == ["1", "2"]


def test_bad_date_drops_meeting():
    html = doc(issuer(dt="31-Foo-22"), prop("1", "a"))
    assert P.parse(html) == []
    assert P.parse_stats(html)["drop_meeting_bad_date"] == 1


def test_contest_rules():
    assert P.parse(doc(issuer(mtype="Proxy Contest"), prop("1", "a"))) == []
    assert P.parse(doc(issuer(), prop("1", "a"), prop("1", "b"))) == []
    assert P.parse(doc(issuer(), prop("1", "Elect Dissident Nominee"))) == []
    assert P.parse(doc(issuer(), prop("1", "Elect management nominee X"))) == []
    assert P.parse(doc(issuer(), tr("Elect A", "Management", "For", "Voted - For"),
                       tr("Elect A", "Management", "For", "Voted - For"))) == []
    html = doc(issuer(mtype="Contest"), prop("1", "a"), issuer("B", "S2", "B"), prop("1", "ok"))
    assert [r["proposal_text"] for r in P.parse(html)] == ["ok"]


def test_unclosed_proposal_dropped():
    html = doc(issuer(), prop("1", "a"), tr("2", "never closed"), prop("3", "c"))
    assert [r["proposal_id"] for r in P.parse(html)] == ["1", "3"]
    assert P.parse_stats(html)["drop_proposal_unclosed"] == 1
    html = doc(issuer(), tr("2", "never closed"))
    assert P.parse(html) == []


def test_voted_one_year_and_kept_verbatim():
    html = doc(issuer(), prop("1", "Freq", pos="Management", rec="One Year", vote="Voted - One Year"),
               prop("2", "x", vote="Take No Action", rec="N/A"), prop("3", "y", vote="Did Not Vote"))
    rows = P.parse(html)
    assert [(r["rec"], r["vote"]) for r in rows] == [("One Year", "One Year"), ("N/A", "Take No Action"),
                                                      ("For", "Did Not Vote")]


def test_non_column_rows():
    # en dash vote, truncated proponent: not column rows -> unclosed
    html = doc(issuer(), tr("1", "a", "Management", "For", "Voted – For"),
               tr("2", "b", "Management", "For", "Voted - For"))
    assert [r["proposal_id"] for r in P.parse(html)] == ["2"]
    html = doc(issuer(), tr("1", "a", "Sharehold", "For", "Voted - For"))
    assert P.parse(html) == []


def test_column_row_without_proposal_drops_meeting():
    html = doc(issuer(), tr("Management", "For", "Voted - For"), prop("1", "a"))
    assert P.parse(html) == []
    assert P.parse_stats(html)["drop_meeting_unplaceable_row"] == 1


def test_id_followed_by_column_value_is_not_a_start():
    html = doc(issuer(), tr("1", "Management", "For", "Voted - For"))
    rows = P.parse(html)
    assert len(rows) == 1 and rows[0]["proposal_id"] == "" and rows[0]["proposal_text"] == "1"


def test_bad_heading_rejects_document():
    head = ("<tr><td>Proposal</td><td>Proposed by</td><td>Mgt. Position</td>"
            "<td>Registrant Voted</td></tr>")
    html = doc(issuer(), prop("1", "a"), head=head)
    assert P.parse(html) == []
    assert P.parse_stats(html)["doc_rejected"] == 1
    head = tr("A", "B") + HEAD.split("</tr>", 1)[1]
    assert P.parse(doc(issuer(), prop("1", "a"), head=head)) == []


def test_empty_text_drops_proposal():
    html = doc(issuer(), tr("Management", "For", "Voted - For"))
    assert P.parse(html) == []


def test_two_fund_headings_same_doc():
    head2 = HEAD.replace("Democracy International Fund", "Other Fund")
    html = doc(issuer(), prop("1", "a"), "</table><table>" + head2, issuer("B", "S2", "B"), prop("1", "b"))
    assert [r["fund_heading"] for r in P.parse(html)] == ["Democracy International Fund", "Other Fund"]


# ---- amendments HR1-HR5 ----------------------------------------------------

def divs(*vals):
    return "".join(f"<div style='x'>{v}</div>" for v in vals)


def test_hr1_div_rows_between_tables_and_p_heading():
    colhdr = tr("Proposal", "Proposed by", "Mgt. Position", "Registrant Voted")
    html = ("<html><p>Some Fund</p><table>" + colhdr + "</table>"
            + divs("ABB LTD.", "Security ID: 000375204", "Ticker: ABBN", "Meeting Date: 07-Sep-22",
                   "Meeting Type: Extraordinary Shareholders")
            + "<table>" + prop("1", "Approve") + "</table></html>")
    r = P.parse(html)
    assert len(r) == 1
    assert (r[0]["fund_heading"], r[0]["issuer_name"], r[0]["security_id"], r[0]["ticker"],
            r[0]["meeting_type"], r[0]["meeting_date"]) == (
        "Some Fund", "ABB LTD.", "000375204", "ABBN", "Extraordinary Shareholders", "09/07/2022")


def test_hr1_nested_div_and_div_in_table_not_rows():
    html = doc(issuer(), "<div><div>Outer text</div></div>", prop("1", "a"))
    # nested: only the leaf counts, and it is outside a table
    assert len(P.parse(html)) == 1
    inside = doc(issuer(), tr("1", "Elect"), "<tr><td><div>Jane</div></td></tr>",
                 tr("Management", "For", "Voted - For"))
    assert P.parse(inside)[0]["proposal_text"] == "Elect Jane"


def test_hr2_proposal_continues_across_tables():
    html = doc(issuer(), tr("1", "Elect Jane"), "</table><table>", tr("Doe", "Management", "For", "Voted - For"))
    r = P.parse(html)
    assert len(r) == 1 and r[0]["proposal_text"] == "Elect Jane Doe"
    assert P.parse_stats(html)["drop_proposal_unclosed"] == 0


def test_hr3_ticker_and_meeting_type_rows():
    html = doc(tr("<b>FOO</b>"), tr("Security ID: S1"), tr("Ticker: FOO"),
               tr("Meeting Date: 01-Jan-23"), tr("Meeting Type: Annual"), prop("1", "x"))
    r = P.parse(html)[0]
    assert (r["ticker"], r["meeting_type"], r["proposal_text"]) == ("FOO", "Annual", "x")


def test_hr3_meeting_type_row_not_directly_after_date_is_text():
    html = doc(issuer(), prop("1", "a"), tr("Meeting Type: Annual"), tr("Management", "For", "Voted - For"))
    r = P.parse(html)
    assert r[1]["proposal_text"] == "Meeting Type: Annual" and r[1]["meeting_type"] == "Extraordinary Shareholders"


def test_hr4_page_furniture_ignored():
    html = doc(issuer(), tr("1", "Elect"), tr("Page | 3"), tr("Page 4"), tr("12"),
               tr("Jane", "Management", "For", "Voted - For"))
    s = P.parse_stats(html)
    r = P.parse(html)
    assert r[0]["proposal_text"] == "Elect Jane" and s["page_furniture"] == 3


def test_hr4_furniture_does_not_break_adjacency():
    html = doc(tr("<b>FOO</b>"), tr("Page 2"), tr("Security ID: S1"), tr("Page 3"),
               tr("Meeting Date: 01-Jan-23"), prop("1", "x"))
    assert len(P.parse(html)) == 1


def test_hr5_empty_security_id_kept():
    html = doc(tr("<b>FOO</b>"), tr("Security ID:"), tr("Meeting Date: 01-Jan-23"), prop("1", "x"))
    r = P.parse(html)
    assert len(r) == 1 and r[0]["security_id"] == ""
