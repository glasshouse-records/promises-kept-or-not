"""Tests for the line-by-line legacy ProxyEdge N-PX parser."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest.legacy_pe_lines import parse, parse_stats

FIX = Path(__file__).parent / "fixtures" / "legacy_pe"
DASH = "-" * 120


def _doc(rows: str, *, fund: str = "Test Fund", date: str = "25-Jan-2023",
         issuer: str = "ACME CORP") -> str:
    return (
        f"{fund}\n{DASH}\n {issuer:<90}Agenda Number:  12345\n{DASH}\n"
        f"        Security:  00508Y102\n    Meeting Type:  Annual\n"
        f"    Meeting Date:  {date}\n          Ticker:  AYI\n"
        f"            ISIN:  US00508Y1029\n{DASH}\n\n"
        "Prop.# Proposal                                                  Proposal      "
        "Proposal Vote                  For/Against\n"
        "                                                                 Type          "
        "                               Management\n\n"
        f"{rows}\n\n{DASH}\n"
    )


def _row(pid: str, text: str, typ: str, vote: str, fa: str = "") -> str:
    return f"{pid:<7}{text:<58}{typ:<14}{vote:<31}{fa}".rstrip()


def test_basic_fixture():
    rows = parse((FIX / "basic.txt").read_text())
    assert rows
    r = rows[0]
    assert r["fund_name"] == "JPMorgan Mid Cap Value Fund"
    assert r["issuer_name"] == "ACUITY BRANDS, INC."
    assert r["agenda_number"] == "935748991"
    assert r["security_id"] == "00508Y102"
    assert r["ticker"] == "AYI"
    assert r["isin"] == "US00508Y1029"
    assert r["meeting_type"] == "Annual"
    assert r["meeting_date"] == "2023-01-25"
    assert r["proposal_id"] == "1a."
    assert set(r) == {
        "fund_name", "issuer_name", "agenda_number", "security_id", "ticker", "isin",
        "meeting_type", "meeting_date", "proposal_id", "proposal_text",
        "proposal_type", "vote", "for_against_management",
    }
    wrapped = [x for x in rows if x["proposal_text"].endswith("Ph.D.")]
    assert wrapped[0]["proposal_text"] == "Election of Director: Marcia J. Avedon, Ph.D."


def test_swiss_fixture_nonvoting_split_and_nofund_note():
    text = (FIX / "swiss.txt").read_text()
    rows = parse(text)
    st_ = parse_stats(text)
    assert all(r["proposal_type"] != "Non-Voting" for r in rows)
    assert all(r["fund_name"] == "JPMorgan Access Balanced Fund" for r in rows)
    assert st_["reasons"]["split_vote"] == 1
    ids = {r["proposal_id"] for r in rows if r["issuer_name"] == "ABB LTD"}
    assert ids >= {"1", "2", "4"}
    assert "3" not in ids
    assert st_["meetings_seen"] == 2


def test_contested_star_is_empty():
    text = "Fund X\n" + (FIX / "icahn.txt").read_text()
    rows = parse(text)
    assert [r["vote"] for r in rows] == ["For"] * 5
    assert {r["for_against_management"] for r in rows} == {""}
    assert rows[-1]["proposal_text"] == "ACCEPTABLE COMPANY NOMINEE: Caroline D. Dorsa"


def test_vote_vocabulary_and_for_against():
    rows = parse(_doc("\n\n".join([
        _row("1", "A", "Mgmt", "For", "For"),
        _row("2", "B", "Shr", "Against", "For"),
        _row("3", "C", "Mgmt", "1 Year", "For"),
        _row("4", "D", "Mgmt", "Withheld", "Against"),
        _row("5", "E", "Mgmt", "Abstain"),
        _row("6", "F", "Mgmt", "Take No Action"),
        _row("7", "G", "Mgmt", "3 Years", "Against"),
    ])))
    assert [(r["proposal_id"], r["vote"], r["for_against_management"]) for r in rows] == [
        ("1", "For", "For"), ("2", "Against", "For"), ("3", "1 Year", "For"),
        ("4", "Withheld", "Against"), ("5", "Abstain", ""), ("6", "Take No Action", ""),
        ("7", "3 Years", "Against"),
    ]


def test_drops_are_counted_with_reasons():
    text = _doc("\n\n".join([
        _row("1", "A", "Mgmt", "No vote"),
        _row("2", "B", "Mgmt", "Split 9% For", "Split"),
        _row("3", "C", "Mgmt", "Bogus", "For"),
        _row("4", "D", "Mgmt", "For", "For"),
        _row("CMMT", "NOTE", "Non-Voting", ""),
    ]))
    rows = parse(text)
    s = parse_stats(text)
    assert [r["proposal_id"] for r in rows] == ["4"]
    assert s["meetings_seen"] == 1
    assert s["proposals_seen"] == 5
    assert s["proposals_emitted"] == 1
    assert s["proposals_dropped"] == 3  # Non-Voting carries no vote: not a drop
    assert s["reasons"]["no_vote"] == 1
    assert s["reasons"]["split_vote"] == 1
    assert s["reasons"]["unknown_vote"] == 1


def test_far_right_single_token_is_ambiguous_not_a_vote():
    # Vote column empty, For/Against column filled: must NOT be read as vote=For.
    line = f"{'1':<7}{'A':<58}{'Mgmt':<45}For"
    text = _doc(line)
    assert parse(text) == []
    assert parse_stats(text)["reasons"]["ambiguous_vote"] == 1


def test_empty_vote_dropped():
    text = _doc(_row("1", "A", "Mgmt", ""))
    assert parse(text) == []
    assert parse_stats(text)["reasons"]["empty_vote"] == 1


def test_meeting_dropped_on_bad_date_or_missing_issuer():
    row = _row("1", "A", "Mgmt", "For", "For")
    assert parse(_doc(row, date="")) == []
    assert parse(_doc(row, date="31-Foo-2023")) == []
    assert parse(_doc(row, date="31-Feb-2023")) == []
    assert parse(_doc(row, issuer="")) == []
    assert len(parse(_doc(row))) == 1


def test_meeting_before_fund_heading_dropped():
    text = _doc(_row("1", "A", "Mgmt", "For", "For"))
    body = text.split("\n", 1)[1]  # strip the fund heading line
    assert parse(body) == []
    assert parse_stats(body)["reasons"]["no_fund"] == 1


def test_fund_name_tracks_latest_heading():
    a = _doc(_row("1", "A", "Mgmt", "For", "For"), fund="Fund One")
    b = _doc(_row("1", "B", "Mgmt", "Against", "For"), fund="Fund Two")
    rows = parse(a + "\n" + b)
    assert [r["fund_name"] for r in rows] == ["Fund One", "Fund Two"]


def test_trailing_html_residue_is_not_appended_to_text():
    text = _doc(_row("1", "A", "Mgmt", "For", "For")) + "\n</TABLE>\n<PAGE>\nSIGNATURES\n"
    assert parse(text)[0]["proposal_text"] == "A"


def test_orphan_text_after_blank_does_not_attach_to_prior_proposal():
    rows = parse(_doc(_row("1", "A", "Mgmt", "For", "For") + "\n\n       STRAY TEXT"))
    assert rows[0]["proposal_text"] == "A"


def test_unrecognised_type_id_line_blocks_its_continuations():
    rows = parse(_doc(
        _row("1", "A", "Mgmt", "For", "For") + "\n"
        + _row("2", "B", "Weird", "For", "For") + "\n       CONT OF B"
    ))
    assert [r["proposal_text"] for r in rows] == ["A"]


def test_wide_gap_continuation_drops_proposal():
    rows = parse(_doc(
        _row("1", "A", "Mgmt", "For", "For") + "\n       B" + " " * 30 + "Against"
    ))
    assert rows == []


def test_empty_text_not_emitted():
    assert parse(_doc(_row("1", "", "Mgmt", "For", "For"))) == []


def test_duplicate_label_drops_meeting():
    text = _doc(_row("1", "A", "Mgmt", "For", "For")).replace(
        "    Meeting Type:  Annual\n", "    Meeting Type:  Annual\n    Meeting Type:  Special\n")
    assert parse(text) == []


@settings(max_examples=60, deadline=None)
@given(
    words=st.lists(st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.,]{0,9}", fullmatch=True),
                   min_size=1, max_size=40),
    width=st.integers(min_value=10, max_value=40),
    pad=st.integers(min_value=1, max_value=3),
)
def test_wrapping_invariance(words, width, pad):
    """Same words wrapped at any width yield the same single proposal text."""
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    first = f"{'1.':<7}{lines[0]:<58}{'Mgmt':<14}{'For':<31}For"
    cont = [" " * 7 + (" " * (pad - 1)) + ln for ln in lines[1:]]
    rows = parse(_doc("\n".join([first, *cont])))
    assert len(rows) == 1
    assert rows[0]["proposal_text"] == " ".join(words)


def _sub(name: str, vote: str = "For", fa: str = "For", typ: str = "Mgmt") -> str:
    return f"{'':<7}{name:<58}{typ:<14}{vote:<31}{fa}".rstrip()


def test_amend_director_subrows_become_proposals():
    rows = parse(_doc("\n".join([
        "1.     DIRECTOR",
        _sub("Jane Doe"),
        _sub("John  Roe", "Withheld", "Against"),
        _row("2.", "Ratify auditors", "Mgmt", "For", "For"),
    ])))
    assert [(r["proposal_id"], r["proposal_text"], r["vote"]) for r in rows] == [
        ("1.", "DIRECTOR Jane Doe", "For"),
        ("1.", "DIRECTOR John Roe", "Withheld"),
        ("2.", "Ratify auditors", "For"),
    ]
    assert rows[1]["for_against_management"] == "Against"


def test_amend_heading_with_type_drops_subrows():
    rows = parse(_doc("\n".join([
        _row("1.", "DIRECTOR", "Mgmt", "For", "For"),
        _sub("Jane Doe"),
    ])))
    assert [r["proposal_text"] for r in rows] == ["DIRECTOR"]


def test_amend_subrows_do_not_leak_past_blank_or_next_id():
    rows = parse(_doc("1.     DIRECTOR\n" + _sub("Jane Doe") + "\n\n" + _sub("Stray Name")))
    assert [r["proposal_text"] for r in rows] == ["DIRECTOR Jane Doe"]


def test_amend_star_for_against_is_empty():
    rows = parse(_doc(_row("1", "A", "Mgmt", "For", "*")))
    assert rows[0]["for_against_management"] == ""


def test_amend_names_whitespace_normalised():
    rows = parse(_doc(_row("1", "A", "Mgmt", "For", "For"), fund="Fund   One", issuer="ACME   CORP"))
    assert rows[0]["fund_name"] == "Fund One"
    assert rows[0]["issuer_name"] == "ACME CORP"


# -- amendment PE-I: capital I printed as lower-case i ------------------------

def _mangled():
    return parse((FIX / "mangled_i_lines.txt").read_text())


def test_pe_i_rows_come_out_and_labels_with_i_read():
    rows = _mangled()
    assert [r["proposal_id"] for r in rows] == ["1", "2", "3", "1a.", "2"]
    r = rows[0]
    assert r["meeting_type"] == "AGM" and r["meeting_date"] == "2023-05-30"
    assert r["agenda_number"] == "717129628"


def test_pe_i_identifiers_uppercased_and_check_digits_valid():
    from glasshouse.ingest.legacy_pe import classify_security_id, isin_valid
    r = _mangled()[0]
    assert r["isin"] == "CNE100000GR6" and isin_valid(r["isin"])
    assert r["security_id"] == "Y0029J108"
    assert classify_security_id(r["isin"]) == ("", "CNE100000GR6")
    assert _mangled()[3]["isin"] == "US9113121068"


def test_pe_i_free_text_kept_exactly_as_printed():
    rows = _mangled()
    assert rows[0]["issuer_name"] == "AiER EYE HOSPiTAL GROUP CO LTD"
    assert rows[1]["proposal_text"] == "APPROVE REPORT OF THE BOARD OF DiRECTORS"
    assert rows[2]["proposal_text"] == "APPROVE AMENDMENTS TO ARTiCLES OF"
    assert rows[3]["issuer_name"] == "UNiTED PARCEL SERViCE INC"
    assert rows[4]["proposal_type"] == "Shr" and rows[4]["vote"] == "Against"


def test_pe_i_style_fragments_never_become_text():
    rows = _mangled()
    assert {r["fund_name"] for r in rows} == {
        "JPMorgan Active China ETF", "JPMorgan BetaBuilders MSCi US REiT ETF"}
    bad = ("mso-", "font-family", "&quot;", "height:", "justify;")
    for r in rows:
        for k in ("fund_name", "issuer_name", "proposal_text", "proposal_id"):
            assert not any(b in r[k] for b in bad), (k, r[k])


def test_pe_i_fragment_line_is_not_a_fund_heading_or_proposal():
    doc = _doc(_row("1", "ELECT A", "Mgmt", "For", "For"))
    frag = 'mso-fareast-font-family:&quot;Times New Roman&quot;"'
    # fragment directly above the real heading, and inside the proposal block
    mangled = frag + "\n" + doc.replace("\n\n1 ", "\n\nheight:15.75pt\"\n1 ", 1)
    rows = parse(mangled)
    assert [r["fund_name"] for r in rows] == ["Test Fund"]
    assert all("height" not in r["proposal_text"] for r in rows)
