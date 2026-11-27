"""Contract D1-D9 (docs/research/legacy-npx.md), Dodge & Cox DOM parser."""
from glasshouse.ingest import legacy_dodgecox_dom as m
from glasshouse.ingest.legacy_issueno import KEYS

HEAD = "Dodge&nbsp;&amp; Cox Stock Fund"


def tbl(*rows):
    out = ["<TABLE>"]
    for r in rows:
        out.append("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>")
    out.append("</TABLE>")
    return "".join(out)


def hdr(ticker="AGN", sec="007924103", date="JAN 17, 2023", mtype="Annual",
        rec="DEC 20, 2022", extra=()):
    return tbl(["Ticker:", "", ticker, "Security ID:", "", sec],
               ["Meeting Date:", date, "Meeting Type:", mtype],
               ["Record Date:", rec, "&nbsp;", "&nbsp;"], *extra)


COLS = ["#", "Proposal", "Mgt Rec", "Vote&nbsp;Cast", "Sponsor"]


def prop(n="1", text="Elect X", rec="For", vote="For", sp="Management"):
    return [n, "", text, "", rec, "", vote, "", sp]


def doc(*meetings, heading=HEAD, tail=""):
    s = f"<p>cover</p><p>{heading}</p>"
    for issuer, header, props in meetings:
        s += f"<P>{issuer}</P>" + header + tbl(COLS, *props)
    return s + tail


def one(props, **kw):
    return doc(("AEGON NV", hdr(**kw), props))


def test_basic_row_and_keys():
    rows = m.parse(one([prop()]))
    assert rows == [dict(zip(KEYS, [
        "Dodge & Cox Stock Fund", "AEGON NV", "AGN", "007924103", "2023-01-17",
        "", "Annual", "", "1", "Elect X", "Management", "For", "For", ""]))]
    assert list(rows[0]) == list(KEYS)
    assert m.parse_stats(one([prop()]))["rows"] == 1


def test_d1_heading_bad_or_missing():
    for h in ("Some Other Fund", "Dodge & Cox Stock Trust", "Dodge &amp; CoxFund"):
        s = m.parse_stats(doc(("A", hdr(), [prop()]), heading=h))
        assert s["no_fund_heading"] == 1 and s["rows"] == 0
    assert m.parse(doc(("A", hdr(), [prop()]), heading="Dodge & Cox Stock Fund")) != []


def test_d1_heading_is_block_directly_before_issuer():
    # a page marker between heading and issuer makes the heading the marker
    s = f"<p>{HEAD}</p><p>Page 3</p><p>AEGON NV</p>" + hdr() + tbl(COLS, prop())
    st = m.parse_stats(s)
    assert m.parse(s) == [] and st["no_fund_heading"] == 1


def test_d3_page_marker_before_issuer():
    s = f"<p>{HEAD}</p><p>AEGON NV</p><p>Page 3</p>" + hdr() + tbl(COLS, prop())
    rows = m.parse(s)
    assert rows[0]["issuer_name"] == "AEGON NV"
    assert rows[0]["fund_heading"] == "Dodge & Cox Stock Fund"


def test_d3_no_issuer():
    # only a page marker between two tables -> no issuer for the 2nd meeting
    s = doc(("A", hdr(), [prop()])) + "<p>Page 3</p>" + hdr(ticker="Z") + tbl(COLS, prop())
    st = m.parse_stats(s)
    assert st["no_issuer"] == 1 and st["rows"] == 1


def test_d3_issuer_not_taken_from_previous_meeting_gap():
    a = ("A CORP", hdr(), [prop()])
    s = doc(a) + hdr(ticker="ZZZ") + tbl(COLS, prop())
    st = m.parse_stats(s)
    assert st["no_issuer"] == 1 and st["rows"] == 1


def test_d2_label_twice_and_missing():
    bad = tbl(["Ticker:", "A", "Ticker:", "B"], ["Security ID:", "1", "Meeting Date:", "JAN 1, 2023"])
    assert m.parse_stats(doc(("X", bad, [prop()])))["bad_meeting_header"] == 1
    miss = tbl(["Ticker:", "A", "Security ID:", "1"])
    assert m.parse_stats(doc(("X", miss, [prop()])))["bad_meeting_header"] == 1
    # label followed by label: value ''
    odd = tbl(["Ticker:", "Security ID:", "1", "Meeting Date:", "JAN 1, 2023"])
    assert m.parse_stats(doc(("X", odd, [prop()])))["bad_meeting_header"] == 1


def test_d2_optional_values_blank():
    h = tbl(["Ticker:", "A", "Security ID:", "1", "Meeting Date:", "JAN 1, 2023",
             "Meeting Type:", "Record Date:"])
    r = m.parse(doc(("X", h, [prop()])))
    assert r[0]["meeting_type"] == "" and r[0]["meeting_date"] == "2023-01-01"


def test_d4_dates():
    r = m.parse(one([prop()], date="DEC 5, 2022"))
    assert r[0]["meeting_date"] == "2022-12-05"
    for bad in ("Dec 05, 2022", "DECEMBER 5, 2022", "DEC 005, 2022", "2022-12-05", "FOO 5, 2022"):
        st = m.parse_stats(one([prop()], date=bad))
        assert st["bad_meeting_date"] == 1 and st["rows"] == 0, bad


def test_d5_header_with_nbsp_skipped_and_signature_ends():
    sig = tbl(["By", "(Registrant)"], ["junk"])
    s = one([prop()]) + sig + tbl(prop())
    st = m.parse_stats(s)
    assert st["rows"] == 1 and st["bad_row"] == 0


def test_d5_multiple_proposal_tables_until_next_header():
    s = (f"<p>{HEAD}</p><p>A</p>" + hdr() + tbl(COLS, prop("1")) + tbl(COLS, prop("2"))
         + "<p>B</p>" + hdr(ticker="B") + tbl(COLS, prop("1")))
    r = m.parse(s)
    assert [(x["issuer_name"], x["proposal_id"]) for x in r] == [("A", "1"), ("A", "2"), ("B", "1")]


def test_d6_continuation():
    cont = ["", "", "more text", "", "", "", "", "", ""]
    r = m.parse(one([prop(text="Elect"), cont, cont, prop("2", "Next")]))
    assert r[0]["proposal_text"] == "Elect more text more text"
    assert r[1]["proposal_text"] == "Next"


def test_d6_continuation_across_tables_same_meeting():
    cont = ["", "", "tail", "", "", "", "", "", ""]
    s = (f"<p>{HEAD}</p><p>A</p>" + hdr() + tbl(COLS, prop()) + tbl(cont))
    assert m.parse(s)[0]["proposal_text"] == "Elect X tail"


def test_d6_orphan_continuation_drops_meeting():
    cont = ["", "", "more", "", "", "", "", "", ""]
    s = doc(("A", hdr(), [cont, prop()]), ("B", hdr(ticker="B"), [prop()]))
    st = m.parse_stats(s)
    assert st["orphan_continuation"] == 1 and st["rows"] == 1
    assert [r["issuer_name"] for r in m.parse(s)] == ["B"]
    # previous meeting's row is not a valid anchor
    s2 = doc(("A", hdr(), [prop()]), ("B", hdr(ticker="B"), [cont]))
    assert m.parse_stats(s2)["orphan_continuation"] == 1


def test_d6_bad_row_drops_whole_meeting():
    s = one([prop("1"), ["2", "text", "For"], prop("3")])
    st = m.parse_stats(s)
    assert st["bad_row"] == 1 and st["rows"] == 0
    # text in # cell with nothing else is not a continuation
    assert m.parse_stats(one([prop(), ["5", "", "", "", "", "", "", "", ""]]))["bad_row"] == 1


def test_d7_closed_lists():
    cases = [
        (prop(n="1-2"), "bad_number"), (prop(n="a b"), "bad_number"),
        (prop(rec="Three"), "bad_rec"), (prop(rec="Abstain"), "bad_rec"),
        (prop(vote="Withhold"), "bad_vote"), (prop(sp="Mgmt"), "bad_sponsor"),
    ]
    for row, key in cases:
        st = m.parse_stats(one([prop("0"), row]))
        assert st[key] == 1 and st["rows"] == 1, key
    ok = m.parse(one([prop("1.a", rec="One Year", vote="Did Not Vote", sp="Shareholder"),
                      prop("2", rec="Three Years", vote="Three Years"),
                      prop("3", rec="None", vote="None"),
                      prop("4", rec="Against", vote="Abstain")]))
    assert len(ok) == 4


def test_d7_continuation_of_dropped_row_does_not_attach_elsewhere():
    cont = ["", "", "tail", "", "", "", "", "", ""]
    r = m.parse(one([prop("1"), prop("2", rec="Three"), cont]))
    assert len(r) == 1 and r[0]["proposal_text"] == "Elect X"


def test_d8_duplicate_text_kept_and_entities():
    r = m.parse(one([prop("1", "Same&#146;s"), prop("2", "Same&#146;s")]))
    assert len(r) == 2 and r[0]["proposal_text"] == "Same’s"
    assert r[0]["for_against"] == "" and r[0]["country"] == "" and r[0]["meeting_status"] == ""


def test_d9_no_ticker_table_empty():
    assert m.parse(f"<p>{HEAD}</p><p>A</p>" + tbl(COLS, prop())) == []
    assert m.parse("") == []


def test_cell_tags_and_whitespace():
    r = m.parse(one([["1", "", "Open <FONT>(Non-\nVoting)</FONT>&nbsp;&nbsp;x", "", "None", "", "None", "", "Management"]]))
    assert r[0]["proposal_text"] == "Open (Non- Voting) x"
