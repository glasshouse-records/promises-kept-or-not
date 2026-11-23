"""Tests for the cell-tokenizer parser of the legacy 'Issue No.' HTML layout."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest.legacy_issueno_html_cells import parse, parse_stats

FIX = Path(__file__).parent / "fixtures" / "legacy_issueno_html_cells"

FIELDS = [
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
    "meeting_status", "meeting_type", "country", "proposal_id",
    "proposal_text", "proponent", "rec", "vote", "for_against",
]


def row(*cells, hr=False):
    out = []
    for c in cells:
        span = 1
        if isinstance(c, tuple):
            c, span = c
        attr = f" colspan={span}" if span != 1 else ""
        out.append(f"<TD{attr}>{c}</TD>")
    if hr:
        out.append("<TD><HR></TD>")
    return "<TR>" + "".join(out) + "</TR>\n"


def fund(name="Fund X"):
    return row("", "<B>Fund Name :</B>", name)


def meeting(issuer="Acme Corp", ticker="ACME", sec="CUSIP 123456789",
            date="06/13/2023", status="Voted", mtype="Annual",
            country="United States", props=None):
    props = props if props is not None else [
        ("1", "Elect A", "Mgmt", "For", "For", "For")]
    s = row("", issuer)
    s += row("", "", "<B>Ticker</B>", "<B>Security ID:</B>", "<B>Meeting Date</B>",
             "<B>Meeting Status</B>")
    s += row("", "", ticker, sec, date, status)
    s += row("", "", "<B>Meeting Type</B>", "<B>Country of Trade</B>")
    s += row("", "", mtype, country)
    s += row("", "", "<B>Issue No.</B>", "<B>Description</B>", "<B>Proponent</B>",
             "<B>Mgmt Rec</B>", "<B>Vote Cast</B>", "<B>For/Agnst Mgmt</B>")
    for p in props:
        s += row("", "", *p)
    return s


def doc(*parts):
    return "<html><body><table>" + "".join(parts) + "</table></body></html>"


def test_putnam_malformed_rows_real_excerpt():
    rows = parse((FIX / "putnam_excerpt.htm").read_text())
    assert len(rows) == 7
    assert set(rows[0]) == set(FIELDS)
    assert rows[0] == {
        "fund_heading": "Putnam Dynamic Asset Allocation Balanced Fund",
        "issuer_name": "2seventy bio, Inc.", "ticker": "TSVT",
        "security_id": "CUSIP 901384107", "meeting_date": "2023-06-13",
        "meeting_status": "Voted", "meeting_type": "Annual",
        "country": "United States", "proposal_id": "1.1",
        "proposal_text": "Elect Daniel S. Lynch", "proponent": "Mgmt",
        "rec": "For", "vote": "For", "for_against": "For",
    }
    assert [r["issuer_name"] for r in rows[5:]] == ["3i Group plc"] * 2
    assert rows[5]["country"] == "United Kingdom"
    assert rows[5]["meeting_date"] == "2023-06-29"


def test_neuberger_div_cells_real_excerpt():
    rows = parse((FIX / "neuberger_excerpt.htm").read_text())
    assert len(rows) == 3
    r = rows[0]
    assert r["fund_heading"] == "Neuberger Berman Dividend Growth Fund"
    assert r["issuer_name"] == "Aena S.M.E. S.A."
    assert (r["ticker"], r["security_id"]) == ("AENA", "CINS E526K0106")
    assert r["meeting_date"] == "2023-04-20"
    assert r["meeting_status"] == "Voted"
    assert r["meeting_type"] == "Ordinary"
    assert r["country"] == ""  # this filer prints no Country of Trade column
    assert (r["proposal_id"], r["proposal_text"]) == ("1", "Non-Voting Meeting Note")
    assert r["vote"] == "N/A"


def test_blank_ticker_is_empty_string():
    rows = parse(doc(fund(), meeting(ticker="")))
    assert len(rows) == 1 and rows[0]["ticker"] == ""
    assert rows[0]["security_id"] == "CUSIP 123456789"


def test_colspan_positions_follow_the_label_column():
    # description spans two columns; later cells shift but labels are at the
    # same starting position in both rows
    head = row("", ("Issue No.", 1), ("Description", 2), "Proponent",
               "Mgmt Rec", "Vote Cast", "For/Against Mgmt")
    prop = row("", "7", ("Say on pay", 2), "Mgmt", "For", "Against", "Against")
    s = meeting(props=[])
    s = s[: s.rindex("<TR>")] + head + prop
    rows = parse(doc(fund(), s))
    assert len(rows) == 1
    assert rows[0]["proposal_text"] == "Say on pay"
    assert (rows[0]["proponent"], rows[0]["vote"]) == ("Mgmt", "Against")
    # a value one column off its label is not read
    bad = row("", "8", "", "Text", "Mgmt", "For", "For", "For")
    s2 = s + bad
    assert len(parse(doc(fund(), s2))) == 1


def test_stray_value_outside_labelled_column_drops_the_row():
    props = [("1", "Elect A", "Mgmt", "For", "For", "For"),
             ("2", "Elect B", "Mgmt", "For", "For", "For", "stray")]
    text = doc(fund(), meeting(props=props))
    rows = parse(text)
    assert [r["proposal_id"] for r in rows] == ["1"]
    st_ = parse_stats(text)
    assert st_["proposals_seen"] == 2 and st_["proposals_dropped"] == 1
    assert st_["reasons"]["stray_cell"] == 1


def test_empty_issue_no_or_description_drops_the_row():
    props = [("", "Elect A", "Mgmt", "For", "For", "For"),
             ("2", "", "Mgmt", "For", "For", "For"),
             ("3", "ok", "Mgmt", "For", "For", "For")]
    assert [r["proposal_id"] for r in parse(doc(fund(), meeting(props=props)))] == ["3"]


def test_out_of_vocabulary_value_drops_the_row():
    props = [("1", "a", "Mgmt", "For", "Frobnicate", "For"),
             ("2", "b", "Mgmt", "For", "For", "For")]
    rows = parse(doc(fund(), meeting(props=props)))
    assert [r["proposal_id"] for r in rows] == ["2"]


def test_literal_values_kept():
    props = [("1", "a", "MGMT", "1 Year", "Echo Vote", "N/A"),
             ("2", "b", "ShrHoldr", "TNA", "TNA", "N/A")]
    rows = parse(doc(fund(), meeting(props=props)))
    assert rows[0]["proponent"] == "MGMT" and rows[0]["vote"] == "Echo Vote"
    assert rows[1]["rec"] == "TNA"


def test_no_carry_between_meetings():
    # second meeting has no value row for the meeting header: nothing of the
    # first meeting may leak into it
    m1 = meeting(issuer="One", ticker="ONE")
    broken = row("", "Two") + row("", "", "<B>Ticker</B>", "<B>Security ID:</B>",
                                  "<B>Meeting Date</B>", "<B>Meeting Status</B>")
    broken += row("", "", "<B>Issue No.</B>", "<B>Description</B>", "<B>Proponent</B>",
                  "<B>Mgmt Rec</B>", "<B>Vote Cast</B>", "<B>For/Agnst Mgmt</B>")
    broken += row("", "", "1", "Elect Z", "Mgmt", "For", "For", "For")
    rows = parse(doc(fund(), m1, row("", "", hr=True), broken))
    assert [r["issuer_name"] for r in rows] == ["One"]


def test_no_carry_between_funds_and_meetings_before_fund_dropped():
    text = doc(meeting(issuer="Orphan"), fund("F1"), row(hr=True),
               meeting(issuer="A"), fund("F2"), meeting(issuer="B"))
    rows = parse(text)
    assert [(r["fund_heading"], r["issuer_name"]) for r in rows] == [
        ("F1", "A"), ("F2", "B")]


def test_fund_label_and_value_in_one_cell():
    rows = parse(doc(row("Fund Name : Combined Fund"), meeting()))
    assert rows[0]["fund_heading"] == "Combined Fund"


def test_bad_date_drops_the_meeting():
    for bad in ["02/30/2023", "13/01/2023", "2023-06-13", "6/13/2023", ""]:
        text = doc(fund(), meeting(date=bad))
        assert parse(text) == [], bad
        s = parse_stats(text)
        assert s["meetings_seen"] == 1 and s["meetings_dropped"] == 1


def test_stats_counts_and_reasons():
    text = doc(fund(), meeting(), meeting(date="99/99/9999"))
    s = parse_stats(text)
    assert s["meetings_seen"] == 2 and s["meetings_dropped"] == 1
    assert s["proposals_emitted"] == 1
    assert s["proposals_seen"] == s["proposals_emitted"] + s["proposals_dropped"]


def test_entities_and_whitespace_decoded():
    text = doc(fund("A&amp;B&nbsp;&#160;Fund"),
               meeting(issuer="  Foo\n  &amp;   Bar  "))
    r = parse(text)[0]
    assert r["fund_heading"] == "A&B Fund" and r["issuer_name"] == "Foo & Bar"


def test_empty_row_inside_a_meeting_resets_it():
    props = [("1", "a", "Mgmt", "For", "For", "For")]
    m = meeting(props=props) + row("", "") + row("", "", "2", "b", "Mgmt", "For", "For", "For")
    assert [r["proposal_id"] for r in parse(doc(fund(), m))] == ["1"]


# ---------- property: markup noise must not change the output ----------

def _noisy(text, data):
    import re

    return re.sub(r"<(/?)(tr|td)\b([^>]*)>", lambda m: tag_noise2(m, data), text)


def tag_noise2(m, data):
    close, name, attrs = m.group(1), m.group(2), m.group(3)
    name = "".join(c.upper() if data.draw(st.booleans()) else c.lower() for c in name)
    if close:
        return f"</{name}{data.draw(st.sampled_from(['', ' ', chr(10)]))}>"
    extra = data.draw(st.sampled_from(
        ["", " vAlign=top", ' style="x:y"', " height=50", "\n  width='5%'"]))
    return f"<{name}{attrs}{extra}>"


@settings(max_examples=60, deadline=None)
@given(st.data())
def test_markup_noise_does_not_change_output(data):
    base = doc(fund(), meeting(props=[
        ("1.1", "Elect A &amp; B", "Mgmt", "For", "For", "For"),
        ("2", "Shareholder item", "ShrHoldr", "Against", "Against", "For")]),
        row(hr=True), meeting(issuer="Other", ticker=""))
    ws = data.draw(st.sampled_from(["", " ", "\n", "\t  "]))
    noisy = _noisy(base, data).replace("</TD><TD", "</TD>" + ws + "<TD")
    # tag-end dropping: rows may also lose their </TR> (malformed Putnam style)
    if data.draw(st.booleans()):
        import re

        noisy = re.sub(r"(?i)</tr\s*>", "", noisy)
    assert parse(noisy) == parse(base)
    assert len(parse(base)) == 3
