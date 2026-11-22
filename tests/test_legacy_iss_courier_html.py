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
