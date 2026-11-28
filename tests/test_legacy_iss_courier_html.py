"""ISS "FORM N-Px" text printed as HTML (one Courier New <P> per line, spaces as &nbsp;):
detected, converted line for line, and read identically to the same content as plain text."""

from __future__ import annotations

from pathlib import Path

from glasshouse.ingest import legacy_iss

RAW = (Path(__file__).parent / "fixtures" / "legacy_iss" / "courier_html.htm").read_text()


def test_not_detected_without_conversion():
    assert legacy_iss._ISS_COLHDR.search(RAW) is None


def test_detected_as_iss():
    assert legacy_iss.doc_format(RAW) == "iss"
    assert legacy_iss.detect_format({"a.htm": RAW}) == "iss"


def test_conversion_keeps_columns_and_one_line_per_p():
    text = legacy_iss.courier_html_to_text(RAW)
    assert text is not None
    assert "&nbsp;" not in text and "<" not in text and "\xa0" not in text
    lines = text.splitlines()
    assert len(lines) == RAW.count("<P style='font:10pt Courier New")
    hdr = next(x for x in lines if x.startswith("# "))
    assert hdr.startswith("#" + " " * 5 + "Proposal")  # "# " + 4 x &nbsp;: one space each
    row = next(x for x in lines if x.startswith("2 ") and "Approve Remuneration Report" in x)
    assert row.startswith("2" + " " * 5 + "Approve")  # " " + 4 x &nbsp;
    # fixed width survives: the rec column sits under the "Mgt Rec" header
    assert abs(row.index("For") - hdr.index("Mgt Rec")) <= 1
    assert row.rstrip().endswith("Management")


def test_none_for_other_shapes():
    plain = "#     Proposal      Mgt Rec  Vote Cast    Sponsor\n1 x For For Management\n"
    assert legacy_iss.courier_html_to_text(plain) is None  # already text
    assert legacy_iss.courier_html_to_text("<P>hello &nbsp; world</P>") is None
    no_p = "<HTML># &nbsp;Proposal &nbsp;Mgt Rec &nbsp;Vote Cast &nbsp;Sponsor</HTML>"
    assert legacy_iss.courier_html_to_text(no_p) is None
    assert legacy_iss.doc_format("<P>nothing</P>") is None


def test_agreed_equals_plain_text_of_same_content():
    converted = legacy_iss.courier_html_to_text(RAW)
    rows, st = legacy_iss.agreed(converted)
    assert st["agreed"] > 30 and st["a_only"] == 0 and st["b_only"] == 0
    assert {r["fund_heading"] for r in rows} == {"Calvert VP EAFE International Index Portfolio"}
    assert len({r["issuer_name"] for r in rows}) == 2
    # same content typed as plain text (independent of the converter) gives the same rows
    plain = "\n".join(
        __import__("html").unescape(__import__("re").sub(r"<[^>]+>", "", ln)).replace("\xa0", " ")
        for ln in RAW.split("\n") if ln.startswith("<P "))
    rows2, _ = legacy_iss.agreed(plain)
    assert rows == rows2
    assert any(r["vote"] == "Against" for r in rows)


def test_refuses_line_breaks_or_tabs_inside_a_paragraph():
    # Review 2026-11-23: a <BR> or newline/tab inside one <P> would merge two text lines
    # (or shift a fixed-width column) identically for BOTH parsers: refuse to convert.
    doc = RAW
    i = doc.index("Proposal")
    for bad in ("<BR>", "<br/>", "\t", "\n"):
        assert legacy_iss.courier_html_to_text(doc[:i] + bad + doc[i:]) is None, repr(bad)


# -- Courier <div> lines (Pioneer / Victory Capital, e.g. 0001102598-23-000050) ----------

_D = ("<div style=\"font-family: 'Courier New',Courier,monospace; color: rgb(0, 0, 0);\">"
      "{}</div>\n    ")
DIV_DOC = "<html><body>" + "".join(_D.format(x) for x in (
    "================ Pioneer Fund ================",
    "<br>\n    ",
    "ADOBE\n      INC.",
    "Ticker:&#160;\n      ADBE&#160; &#160; Security ID: 00724F101",
    "Meeting\n      Date: APR 20, 2023&#160; &#160; Meeting Type: Annual",
    "Record\n      Date: FEB 21, 2023",
    "#&#160;\n      &#160;&#160; Proposal&#160; &#160; &#160; &#160; &#160; &#160; Mgt Rec&#160; "
    "&#160; Vote Cast&#160; &#160; Sponsor",
    "1a&#160;\n      &#160; Elect Director Amy Banse&#160; &#160; &#160;&#160; For&#160; "
    "&#160; &#160;&#160; For&#160; &#160; &#160; &#160; &#160; Management",
)) + "</body></html>"


def test_courier_div_lines_convert_with_html_whitespace_rules():
    text = legacy_iss.courier_html_to_text(DIV_DOC)
    assert text is not None
    lines = text.split("\n")
    assert lines[1] == ""                                # a <div><br></div> is a blank line
    assert lines[2] == "ADOBE INC."                      # source wrapping is one space
    assert "Ticker:" in lines[3] and "00724F101" in lines[3]
    assert legacy_iss.is_iss_text(text)


def test_courier_div_with_a_break_inside_text_is_refused():
    bad = DIV_DOC.replace("ADOBE\n      INC.", "ADOBE<br>INC.")
    assert legacy_iss.courier_html_to_text(bad) is None


def test_div_documents_without_the_iss_header_are_left_alone():
    assert legacy_iss.courier_html_to_text(DIV_DOC.replace("Vote Cast", "Vote")) is None


# -- Courier HTML holding the "Issue No." layout (Wellington 2023) --------------------------

def _courier_issueno_doc():
    from test_legacy_issueno import make_doc
    plain = make_doc([("Mgmt", "For", "For", "For"), ("ShrHoldr", "Against", "Against", "For")])
    # a stray ISS-style column header line, as in the real mixed documents
    plain = "#     Proposal      Mgt Rec  Vote Cast    Sponsor\n" + plain
    ps = "\n".join(
        "<P style='font:10pt Courier New;margin:0'>" + ln.replace(" ", "&nbsp;") + "</P>"
        for ln in plain.splitlines())
    return "<DOCUMENT>\n<TYPE>N-PX\n<TEXT>\n<HTML><BODY>\n" + ps + "\n</BODY></HTML>\n", plain


def test_courier_issueno_is_issueno_not_iss():
    from glasshouse.ingest import legacy_issueno
    raw, plain = _courier_issueno_doc()
    assert legacy_iss.is_issueno(legacy_iss.prepare(raw))
    assert legacy_iss.doc_format(raw) == "issueno"
    assert legacy_iss.detect_format({"a.htm": raw}) == "issueno"
    assert legacy_iss.doc_format(plain) == "issueno"
    rows, st = legacy_issueno.agreed(legacy_iss.prepare(raw))
    assert len(rows) == 2 and st["disagreement_rate"] == 0


def test_courier_iss_fixture_stays_iss():
    assert legacy_iss.doc_format(RAW) == "iss"
    assert legacy_iss.doc_format(legacy_iss.prepare(RAW)) == "iss"


def test_courier_issueno_ingests_end_to_end(tmp_path):
    import test_legacy_issueno as t

    from glasshouse.ingest import legacy_issueno
    raw, _ = _courier_issueno_doc()
    conn = t._conn(tmp_path)
    n = legacy_issueno.ingest_filing(conn, t._filing(), "sc", "2026-11-28",
                                     {"doc.htm": raw}, t.HDR)
    assert n == 2
    assert conn.execute("SELECT report_type FROM filings WHERE accession=?",
                        (t.ACC,)).fetchone()[0] == "LEGACY_ISSUENO"
