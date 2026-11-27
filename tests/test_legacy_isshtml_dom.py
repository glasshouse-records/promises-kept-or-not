"""Parser A (html.parser DOM walk) for the ISS HTML-table N-PX layout."""

from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest import legacy_isshtml_dom as m

FIX = Path(__file__).parent / "fixtures" / "legacy_isshtml"
KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date", "record_date",
    "meeting_type", "rec_label", "card_label", "proposal_id", "proposal_text", "rec", "vote",
    "sponsor",
}


def load(name: str) -> str:
    return (FIX / f"dom_{name}.htm").read_text(encoding="utf-8")


def test_basic_rows():
    rows = m.parse(load("basic"))
    assert len(rows) == 2
    assert all(set(r) == KEYS and all(isinstance(v, str) for v in r.values()) for r in rows)
    assert rows[0] == {
        "fund_heading": "Alpha & Beta Fund", "issuer_name": "ALNYLAM PHARMACEUTICALS, INC.",
        "ticker": "ALNY", "security_id": "02043Q107", "meeting_date": "2023-05-18",
        "record_date": "2023-03-24", "meeting_type": "Annual", "rec_label": "Mgt Rec",
        "card_label": "", "proposal_id": "1a", "proposal_text": "Elect Director Michael W. Bonney",
        "rec": "For", "vote": "For", "sponsor": "Management",
    }
    assert rows[1]["sponsor"] == "Shareholder" and rows[1]["rec"] == "Against"


def test_cover_lines_are_not_funds_and_no_activity_gives_zero_rows():
    rows = m.parse(load("no_activity"))
    assert {r["fund_heading"] for r in rows} == {"Loud Fund"}
    assert m.parse_stats(load("no_activity"))["funds"] == 2


def test_contest_both_headers_and_cards():
    rows = m.parse(load("contest"))
    assert [(r["rec_label"], r["card_label"], r["rec"], r["vote"]) for r in rows] == [
        ("Mgt Rec", "Management Universal Proxy (White Proxy Card)", "For", "For"),
        ("Diss Rec", "Dissident Universal Proxy (Gold Proxy Card)", "Against", "Did Not Vote"),
    ]
    assert rows[0]["meeting_type"] == "Proxy Contest"


def test_non_card_colspan_ignored():
    rows = m.parse(load("noncard"))
    assert len(rows) == 1 and rows[0]["card_label"] == "" and rows[0]["record_date"] == ""


def test_bad_meeting_date_drops_meeting_bad_record_date_blank():
    text = load("bad_date")
    rows = m.parse(text)
    assert [r["issuer_name"] for r in rows] == ["GOOD CO"]
    assert rows[0]["record_date"] == ""
    assert m.parse_stats(text)["reasons"]["bad_meeting_date"] >= 1


def test_unknown_values_dropped_and_counted():
    text = load("unknown_vote")
    rows = m.parse(text)
    assert [r["proposal_id"] for r in rows] == ["2"]
    reasons = m.parse_stats(text)["reasons"]
    for k in ("bad_vote", "bad_rec", "bad_sponsor", "bad_proposal_id", "empty_proposal_text"):
        assert reasons[k] == 1, (k, dict(reasons))


def test_empty_ticker_and_type_casing():
    rows = m.parse(load("empty_ticker"))
    assert rows[0]["ticker"] == "" and rows[0]["security_id"] == ""
    assert rows[0]["meeting_type"] == "Annual/Special"


def test_br_in_proposal_text():
    rows = m.parse(load("br_text"))
    assert rows[0]["proposal_text"] == "Elect Director Jane Doe (Nominee)"
    assert rows[0]["meeting_type"] == "Written Consent"


def test_row_outside_fund_or_before_header_not_emitted():
    doc = load("basic").replace("<p align='center'>", "<p>")  # no fund heading at all
    assert m.parse(doc) == []
    nohdr = re.sub(r"<tr>\s*<th width='10%'>Proposal No.*?</tr>", "", load("basic"), flags=re.S)
    assert m.parse(nohdr) == []


_ws = st.sampled_from(["", " ", "  ", "\n", "\t", "&nbsp;", " ", "\n  "])


@settings(max_examples=60, deadline=None)
@given(a=_ws, b=_ws, c=_ws)
def test_whitespace_and_entity_variation_does_not_change_output(a, b, c):
    base = load("basic")
    var = base.replace("<td>For</td>", f"<td>{a}For{b}</td>")
    var = var.replace("<td>Management</td>", f"<td>{c}Management{a}</td>")
    var = var.replace("Elect Director Michael", f"Elect{b or ' '} Director&nbsp;{c}Michael")
    var = var.replace("ALNY", "&#65;LNY")
    assert m.parse(var) == m.parse(base)


def test_amendment1_uppercase_literals_emitted_lowercase_and_typos_dropped():
    base = load("basic")
    up = base.replace("<td>For</td>", "<td>FOR</td>", 1).replace("<td>Against</td>", "<td>WITHHOLD</td>")
    rows = m.parse(up)
    assert [(r["rec"], r["vote"]) for r in rows] == [("FOR", "For"), ("WITHHOLD", "For")]
    for lit in ("AGAINST", "ABSTAIN"):
        assert m.parse(base.replace("<td>Against</td>", f"<td>{lit}</td>"))[1]["rec"] == lit
    for bad in ("for", "against", "3", "Unknown", "Againt", "Took No Action", "Non-Voting"):
        d = base.replace("<td>Against</td>", f"<td>{bad}</td>")
        assert len(m.parse(d)) == 1, bad


def test_ab_variant_style_centred_funds_and_two_tr_meeting_block():
    text = load("ab_variant")
    rows = m.parse(text)
    assert [(r["fund_heading"], r["issuer_name"], r["ticker"], r["security_id"],
             r["meeting_date"], r["record_date"], r["meeting_type"], r["proposal_id"],
             r["vote"]) for r in rows] == [
        ("AB All Market Real Return Portfolio", "3I INFRASTRUCTURE PLC", "3IN", "G8873L178",
         "2022-07-07", "2022-07-05", "Annual", "1", "For"),
        ("AB All Market Real Return Portfolio", "3I INFRASTRUCTURE PLC", "3IN", "G8873L178",
         "2022-07-07", "2022-07-05", "Annual", "2", "Against"),
        ("AB Income Fund", "AOS CORP", "AOS", "831865209", "2023-04-11", "2023-02-14",
         "Annual", "1.1", "For"),
    ]
    assert all(r["rec_label"] == "Mgt Rec" and r["card_label"] == "" for r in rows)
    assert not any("FORM" in r["fund_heading"] for r in rows)
    stats = m.parse_stats(text)
    assert stats["reasons"] == {} and stats["bad_meetings"] == 0 and stats["meetings"] == 2


def test_end_of_report_resets_fund():
    text = load("end_report")
    rows = m.parse(text)
    assert [(r["fund_heading"], r["issuer_name"]) for r in rows] == [
        ("First Fund", "FIRSTCO INC"), ("Second Fund", "SECONDCO INC")]
    assert m.parse_stats(text)["reasons"].get("no_fund") == 1
    assert m.parse_stats(text)["funds"] == 2


def test_signature_ends_fund_and_cover_lines_excluded():
    for end in ("SIGNATURES", "Signature"):
        t = ("<p align='center'>F</p><p>" + end + "</p><table><tr><td colspan='5'>X<br>"
             "Meeting Date: MAY 1, 2023</td></tr></table>")
        assert m.parse_stats(t)["funds"] == 1
    t = "<p align='center'>Date of reporting period: x</p><p align='center'>The Registrant Inc</p>"
    assert m.parse_stats(t)["funds"] == 0


def _fk():
    return load("franklin")


def _ids(rows):
    return [(r["issuer_name"], r["proposal_id"], r["ticker"], r["security_id"], r["vote"])
            for r in rows]


def test_amendment4_td_header_two_row_labels_and_marked_page_breaks():
    rows = m.parse(_fk())
    assert _ids(rows) == [
        ("ABBOTT LABORATORIES", "1.1", "ABT", "002824100", "For"),
        ("ABBOTT LABORATORIES", "1.2", "ABT", "002824100", "Withhold"),
        ("NEXT CO", "1", "NXT", "123456789", "For"),
    ]
    assert rows[0]["proposal_text"] == "Elect Director Robert J. Alpern"
    assert rows[0]["meeting_date"] == "2023-04-28" and rows[0]["rec_label"] == "Mgt Rec"


def test_amendment4_no_continuation_across_unmarked_or_text_gaps():
    marked = "<!-- PAGEBREAK_START --><p style=\"x\"><hr style=\"y\"/></p><!-- PAGEBREAK_END -->"
    for gap in ("<hr>", "<p>more</p>", "text", "<!-- PAGEBREAK_START --><p>x</p>",
                "<!-- PAGEBREAK_START --><p>x</p><br><!-- PAGEBREAK_END -->",
                "<!-- PAGEBREAK_START -->t<!-- PAGEBREAK_END -->", ""):
        rows = m.parse(_fk().replace(marked, gap))
        assert [r["issuer_name"] for r in rows] == ["NEXT CO"], gap
    # a fund paragraph between the tables also breaks the continuation
    rows = m.parse(_fk().replace(marked, "<p align='center'>Other Fund</p>"))
    assert [r["issuer_name"] for r in rows] == ["NEXT CO"]
    # only the second break unmarked: header continues across the first, rows do not
    second = _fk().replace(marked, "<hr>", 1)
    assert [r["proposal_id"] for r in m.parse(second)] == ["1"]
    third = _fk()
    k = third.rfind(marked.split("<p")[0], 0, third.index("Elect Director Two"))
    third = third[:k] + "<hr>" + third[k + len(marked):]
    assert [r["proposal_id"] for r in m.parse(third)] == ["1.1", "1"]


def test_amendment4_missing_security_id_drops_meeting():
    text = _fk().replace("<tr><td><p>Security ID:&#160;&#160;002824100</p></td></tr>", "")
    assert [r["issuer_name"] for r in m.parse(text)] == ["NEXT CO"]
    st_ = m.parse_stats(text)
    assert st_["reasons"]["incomplete_meeting_header"] == 2
    assert st_["meeting_reasons"]["incomplete_meeting_header"] == 1
    no_ticker = _fk().replace("<tr><td colspan=\"5\"><p><font>Ticker:&#160;&#160;ABT</font></p></td></tr>", "")
    assert [r["issuer_name"] for r in m.parse(no_ticker)] == ["NEXT CO"]


def test_amendment4_labels_in_one_cell_and_ticker_value_may_be_empty():
    text = _fk().replace("Ticker: NXT<br>Security ID: 123456789", "Ticker: <br>Security ID: ")
    assert _ids(m.parse(text))[-1] == ("NEXT CO", "1", "", "", "For")


def test_amendment5_split_row_drops_whole_meeting_only():
    frag = "<tr><td></td><td><p>rest of text</p></td><td></td><td></td><td></td></tr>"
    text = _fk().replace(
        "<tr><td><p>1.2</p>", frag + "<tr><td><p>1.2</p>")  # fragment starts the 2nd table
    rows = m.parse(text)
    assert [r["issuer_name"] for r in rows] == ["NEXT CO"]  # 1.1 (before) and 1.2 (after) gone
    st_ = m.parse_stats(text)
    assert st_["meeting_reasons"]["split_row"] == 1 and st_["reasons"]["split_row"] == 1


def test_amendment5_empty_id_without_pagebreak_unchanged():
    text = _fk().replace("<!-- PAGEBREAK_START -->", "").replace("<!-- PAGEBREAK_END -->", "")
    text = text.replace("<tr><td><p>1.2</p>",
                        "<tr><td></td><td>x</td><td>Management</td><td>For</td><td>For</td></tr>"
                        "<tr><td><p>1.2</p>")
    assert "split_row" not in m.parse_stats(text)["reasons"]


def _drops(text, reason):
    """Abbott's meeting is dropped whole for `reason`; the next meeting reads normally."""
    assert [r["issuer_name"] for r in m.parse(text)] == ["NEXT CO"], reason
    st_ = m.parse_stats(text)
    assert st_["meeting_reasons"][reason] == 1, st_["meeting_reasons"]
    assert st_["reasons"][reason] >= 1


def test_a6a_split_meeting_header():
    t = _fk().replace("<br><font>Record Date:&#160;&#160;MAR 01, 2023</font><br><font>"
                      "Meeting Type:&#160;&#160;ANNUAL</font>", "")
    assert "Record Date:&#160" not in t.split("NEXT CO")[0]
    t = t.replace("</table>\n<!-- PAGEBREAK_START -->",
                  "<tr><td colspan=\"5\"><p>Record Date: MAR 01, 2023<br>Meeting Type: ANNUAL"
                  "</p></td></tr></table>\n<!-- PAGEBREAK_START -->", 1)
    _drops(t, "split_meeting_header")


def test_a6b_late_label_after_column_header():
    t = _fk().replace("<tr><td><p>1.1</p>", "<tr><td><p>Ticker: ZZZ</p></td></tr><tr><td><p>1.1</p>")
    _drops(t, "late_label")
    t = _fk().replace("<tr><td><p>1.2</p>",
                      "<tr><td><p>Security ID: 999</p></td></tr><tr><td><p>1.2</p>")
    _drops(t, "late_label")


def test_a6c_split_column_header():
    for stray in ("<td>Proposal</td><td>Vote Cast</td>", "<td>No</td><td>x</td>",
                  "<td>x</td><td>Proposed By</td>", "<td>x</td><td>Recommendation</td>"):
        t = _fk().replace("<tr><td><p>1.1</p>", f"<tr>{stray}</tr><tr><td><p>1.1</p>")
        _drops(t, "split_column_header")


def test_a6d_fragment_first_row_of_continued_table():
    t = _fk().replace("<tr><td><p>1.2</p>", "<tr><td colspan=\"5\"><p>stray</p></td></tr>"
                      "<tr><td><p>1.2</p>")
    _drops(t, "fragment")
    # a fewer-than-5-cell row that is not first in the table, or in a non-continued table, is
    # not A6d
    plain = _fk().replace("<tr><td><p>1.1</p>", "<tr><td colspan=\"5\"><p>stray</p></td></tr>"
                          "<tr><td><p>1.1</p>")
    assert "fragment" not in m.parse_stats(plain)["meeting_reasons"]


def test_amendment6_not_applied_without_pagebreak():
    t = _fk().replace("<!-- PAGEBREAK_START -->", "").replace("<!-- PAGEBREAK_END -->", "")
    t = t.replace("<tr><td><p>1.1</p>", "<tr><td><p>Ticker: ZZZ</p></td></tr><tr><td><p>1.1</p>")
    assert "late_label" not in m.parse_stats(t)["meeting_reasons"]


def _idline(line):
    t = load("basic").replace("Ticker:&nbsp;&nbsp;ALNY\n<br>Security ID:&nbsp;&nbsp;02043Q107", line)
    assert line in t
    return t


NB = "&#xa0;"


def test_amendment7_ticker_and_security_id_on_one_line():
    for line, want in [
        (f"TICKER:{NB*2}3660{NB*6}SECURITY ID:{NB*2}88557W101", ("3660", "88557W101")),
        (f"SECURITY ID:{NB*2}88557W101{NB*6}TICKER:{NB*2}3660", ("3660", "88557W101")),
        ("ticker: ab security id: 02043Q107", ("ab", "02043Q107")),
        ("Ticker: AB<br>Security ID: ", ("AB", "")),
        ("Ticker: Security ID: 02043Q107", ("", "02043Q107")),
    ]:
        rows = m.parse(_idline(line))
        assert rows and {(r["ticker"], r["security_id"]) for r in rows} == {want}, line


def test_amendment7_label_twice_in_one_line_rejects_meeting():
    for line in ("Ticker: A Security ID: 1 Ticker: B", "Security ID: 1 ticker: A SECURITY ID: 2"):
        t = _idline(line)
        st_ = m.parse_stats(t)
        assert m.parse(t) == []
        assert st_["bad_meetings"] == 1 and st_["meeting_reasons"]["dup_id_label"] == 1


def test_amendment7_two_line_form_unchanged():
    r = m.parse(load("basic"))[0]
    assert (r["ticker"], r["security_id"]) == ("ALNY", "02043Q107")
