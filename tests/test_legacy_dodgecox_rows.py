"""Contract D1-D9 for the regex Dodge & Cox parser (hand-written snippets)."""
from glasshouse.ingest import legacy_dodgecox_rows as P
from glasshouse.ingest.legacy_issueno import KEYS

HEAD = "<p>Cover</p><p>Dodge&nbsp;&amp; Cox Stock Fund </p><p>&nbsp;</p>"


def hdr(ticker="AGN", sec="007924103", date="JAN 17, 2023", typ="Annual", rec="DEC 20, 2022"):
    cells = [("Ticker:", ticker), ("Security ID:", sec), ("Meeting Date:", date),
             ("Meeting Type:", typ), ("Record Date:", rec)]
    rows = "".join(f"<TR><TD>{a}</TD><TD>&nbsp;</TD><TD>{b}</TD></TR>" for a, b in cells)
    return f"<TABLE>{rows}</TABLE>"


COLS = ("<TR><TD><B>#</B></TD><TD>&nbsp;&nbsp;</TD><TD>Proposal</TD><TD></TD><TD>Mgt Rec</TD>"
        "<TD></TD><TD>Vote&nbsp;Cast</TD><TD></TD><TD>Sponsor</TD></TR>")


def prow(n="1", t="Elect X", rec="For", vote="For", sp="Management"):
    return (f"<TR><TD>{n}</TD><TD>&nbsp;</TD><TD>{t}</TD><TD>&nbsp;</TD><TD>{rec}</TD>"
            f"<TD>&nbsp;</TD><TD>{vote}</TD><TD>&nbsp;</TD><TD>{sp}</TD></TR>")


def cont(t):
    return (f"<TR><TD>&nbsp;</TD><TD>&nbsp;</TD><TD>{t}</TD><TD>&nbsp;</TD><TD>&nbsp;</TD>"
            "<TD>&nbsp;</TD><TD>&nbsp;</TD><TD>&nbsp;</TD><TD>&nbsp;</TD></TR>")


def props(*rows):
    return "<TABLE>" + COLS + "".join(rows) + "</TABLE>"


def doc(*meetings, heading=HEAD, tail=""):
    body = "".join(f"<p>{i}</p>{h}{p}" for i, h, p in meetings)
    return heading + body + tail


def one(rows, **kw):
    return doc(("AEGON NV", hdr(**kw), props(*rows)))


def test_basic_row_and_keys():
    out = P.parse(one([prow()]))
    assert len(out) == 1 and tuple(out[0]) == KEYS
    r = out[0]
    assert r["fund_heading"] == "Dodge & Cox Stock Fund"
    assert (r["issuer_name"], r["ticker"], r["security_id"]) == ("AEGON NV", "AGN", "007924103")
    assert r["meeting_date"] == "2023-01-17" and r["meeting_type"] == "Annual"
    assert (r["meeting_status"], r["country"], r["for_against"]) == ("", "", "")
    assert (r["proposal_id"], r["proposal_text"], r["proponent"], r["rec"], r["vote"]) == (
        "1", "Elect X", "Management", "For", "For")
    assert P.parse_stats(one([prow()]))["rows"] == 1


def test_d1_heading_must_match():
    d = doc(("AEGON NV", hdr(), props(prow())), heading="<p>Dodge &amp; Cox Income</p>")
    assert P.parse(d) == [] and P.parse_stats(d)["no_fund_heading"] == 1
    d = doc(("AEGON NV", hdr(), props(prow())), heading="<p>Cox Fund</p>")
    assert P.parse(d) == [] and P.parse_stats(d)["no_fund_heading"] == 1
    d = hdr() + props(prow())
    assert P.parse(d) == [] and P.parse_stats(d)["no_fund_heading"] == 1


def test_d1_d3_page_marker_handling():
    # first meeting: page marker after the issuer is skipped for the issuer, heading precedes issuer
    d = HEAD + "<p>ACME</p><p>Page 4</p>" + hdr() + props(prow())
    out = P.parse(d)
    assert out[0]["issuer_name"] == "ACME" and out[0]["fund_heading"] == "Dodge & Cox Stock Fund"
    # literal D1: a marker between heading and issuer is the block before the issuer -> no heading
    d = HEAD + "<p>Page 3</p><p>ACME</p>" + hdr() + props(prow())
    assert P.parse(d) == [] and P.parse_stats(d)["no_fund_heading"] == 1
    # later meeting: marker before the issuer is not the issuer
    d = (HEAD + "<p>A</p>" + hdr() + props(prow()) + "<p>B</p><p>Page 3</p>"
         + hdr(ticker="T2") + props(prow()))
    assert [r["issuer_name"] for r in P.parse(d)] == ["A", "B"]


def test_d2_header_values_and_labels():
    out = P.parse(one([prow()], rec=""))
    assert len(out) == 1
    # label followed directly by a label: value ''
    t = ("<TABLE><TR><TD>Ticker:</TD><TD>Security ID:</TD><TD>007924103</TD></TR>"
         "<TR><TD>Meeting Date:</TD><TD>JAN 17, 2023</TD><TD>Meeting Type:</TD></TR></TABLE>")
    out = P.parse(doc(("A", t, props(prow()))))
    assert out[0]["ticker"] == "" and out[0]["security_id"] == "007924103"
    assert out[0]["meeting_type"] == ""


def test_d2_duplicate_or_missing_label_drops():
    dup = hdr().replace("Record Date:", "Ticker:")
    d = doc(("A", dup, props(prow())))
    assert P.parse(d) == [] and P.parse_stats(d)["bad_meeting_header"] == 1
    miss = hdr().replace("Security ID:", "Sec:")
    d = doc(("A", miss, props(prow())))
    assert P.parse_stats(d)["bad_meeting_header"] == 1


def test_d3_no_issuer():
    d = HEAD.replace("<p>Cover</p>", "") + hdr() + props(prow())
    # only the heading block precedes: it becomes the issuer, heading missing
    assert P.parse(d) == []
    d = "<p>Dodge &amp; Cox Stock Fund</p><p>Page 3</p>" + hdr() + props(prow())
    assert P.parse(d) == []


def test_d3_second_meeting_no_issuer_counted():
    d = HEAD + "<p>A</p>" + hdr() + props(prow()) + "<p>Page 9</p>" + hdr(ticker="B") + props(prow("2"))
    out = P.parse(d)
    assert [r["ticker"] for r in out] == ["AGN", "B"]
    assert out[1]["issuer_name"] == "A"  # literal D3: last non-marker block


def test_d4_dates():
    assert P.parse(one([prow()], date="DEC 05, 2022"))[0]["meeting_date"] == "2022-12-05"
    assert P.parse(one([prow()], date="MAR 5, 2022"))[0]["meeting_date"] == "2022-03-05"
    for bad in ("Jan 17, 2023", "17 JAN 2023", "JAN 17 2023", "XXX 17, 2023", "FEB 30, 2023", ""):
        d = one([prow()], date=bad)
        assert P.parse(d) == [] and P.parse_stats(d)["bad_meeting_date"] == 1, bad


def test_d5_header_row_skipped_signature_ends():
    sig = "<TABLE><TR><TD>Dodge &amp; Cox Funds</TD></TR><TR><TD>(Registrant)</TD></TR></TABLE>"
    d = doc(("A", hdr(), props(prow())), tail=sig)
    assert len(P.parse(d)) == 1 and P.parse_stats(d)["bad_row"] == 0


def test_d5_spacer_rows_ignored_and_four_cells_bad_row():
    spacer = "<TR><TD></TD><TD>&nbsp;</TD></TR>"
    assert len(P.parse(one([spacer, prow()]))) == 1
    four = "<TR><TD>1</TD><TD>t</TD><TD>For</TD><TD>For</TD></TR>"
    d = one([prow(), four])
    assert P.parse(d) == [] and P.parse_stats(d)["bad_row"] == 1


def test_d6_continuation_appends_same_meeting():
    out = P.parse(one([prow(t="Elect"), cont("directors"), cont("all")]))
    assert out[0]["proposal_text"] == "Elect directors all"


def test_d6_orphan_continuation_drops_meeting():
    d = doc(("A", hdr(), props(cont("x"), prow())), ("B", hdr(ticker="B"), props(prow("2"))))
    out = P.parse(d)
    assert [r["ticker"] for r in out] == ["B"]
    assert P.parse_stats(d)["orphan_continuation"] == 1
    # a previous meeting's row is not a valid predecessor
    d = doc(("A", hdr(), props(prow())), ("B", hdr(ticker="B"), props(cont("x"))))
    assert [r["ticker"] for r in P.parse(d)] == ["AGN"]


def test_d7_closed_lists():
    cases = [(prow(n="1-2"), "bad_number"), (prow(rec="Three"), "bad_rec"),
             (prow(rec="Withhold"), "bad_rec"), (prow(vote="Withhold"), "bad_vote"),
             (prow(sp="Issuer"), "bad_sponsor")]
    for row, name in cases:
        d = one([prow("9"), row])
        assert len(P.parse(d)) == 1 and P.parse_stats(d)[name] == 1, name
    ok = one([prow(rec="Three Years", vote="One Year"), prow("2", rec="None", vote="Did Not Vote"),
              prow("3", sp="Shareholder", vote="Abstain", rec="Against")])
    assert len(P.parse(ok)) == 3
    assert len(P.parse(one([prow(n="1a.B")]))) == 1


def test_d8_duplicate_texts_kept_and_security_bare():
    out = P.parse(one([prow("1", "Same"), prow("2", "Same")]))
    assert [r["proposal_id"] for r in out] == ["1", "2"]


def test_d8_continuation_of_dropped_row_is_lost_not_orphan():
    d = one([prow("1", rec="Three"), cont("more"), prow("2")])
    assert len(P.parse(d)) == 1 and P.parse_stats(d)["orphan_continuation"] == 0


def test_entities_and_nbsp():
    out = P.parse(one([prow(t="Meeting with Two Weeks&#146; Notice&nbsp;now")]))
    assert out[0]["proposal_text"] == "Meeting with Two Weeks’ Notice now"


def test_d9_no_ticker_table():
    assert P.parse("<p>Dodge &amp; Cox Stock Fund</p><table><tr><td>x</td></tr></table>") == []
    assert P.parse("") == []
    assert P.parse_stats("")["rows"] == 0


def test_document_order_across_meetings():
    d = doc(("A", hdr(ticker="T1"), props(prow("1"))), ("B", hdr(ticker="T2"), props(prow("1"), prow("2"))))
    assert [(r["ticker"], r["proposal_id"]) for r in P.parse(d)] == [
        ("T1", "1"), ("T2", "1"), ("T2", "2")]
