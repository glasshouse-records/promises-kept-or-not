"""Tests for the structural legacy ProxyEdge N-PX parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest import legacy_pe_blocks as pe

FIX = Path(__file__).parent / "fixtures" / "legacy_pe"
DASH = "-" * 122
HEADER = (
    "Prop.# Proposal                                                  Proposal      "
    "Proposal Vote                  For/Against\n"
    "                                                                 Type          "
    "                               Management\n"
)


def _row(pid: str, text: str, typ: str, vote: str, fa: str, width: int = 57) -> str:
    chunks = textwrap.wrap(text, width) or [""]
    first = f"{pid:<7}{chunks[0]:<58}{typ:<14}{vote:<31}{fa}".rstrip()
    rest = [" " * 7 + c for c in chunks[1:]]
    return "\n".join([first, *rest]) + "\n"


def _doc(rows: str, *, fund="Test Fund", issuer="ACME CORP", date="05-Jan-2023") -> str:
    return (
        f"{fund}\n{DASH}\n {issuer:<92}Agenda Number:  12345\n{DASH}\n"
        f"        Security:  000111222\n    Meeting Type:  Annual\n"
        f"    Meeting Date:  {date}\n          Ticker:  ACM\n            ISIN:  US0001112220\n"
        f"{DASH}\n\n{HEADER}\n{rows}"
    )


def test_clean_fund_wrapped_text_and_fields():
    rows = pe.parse((FIX / "clean_fund.txt").read_text())
    assert len(rows) == 12
    assert set(rows[0]) == set(pe.KEYS)
    assert rows[0] == {
        "fund_name": "JPMorgan Mid Cap Value Fund",
        "issuer_name": "ACUITY BRANDS, INC.",
        "agenda_number": "935748991",
        "security_id": "00508Y102",
        "ticker": "AYI",
        "isin": "US00508Y1029",
        "meeting_type": "Annual",
        "meeting_date": "2023-01-25",
        "proposal_id": "1a.",
        "proposal_text": "Election of Director: Neil M. Ashe",
        "proposal_type": "Mgmt",
        "vote": "For",
        "for_against_management": "For",
    }
    assert rows[1]["proposal_text"] == "Election of Director: Marcia J. Avedon, Ph.D."
    ey = next(r for r in rows if r["proposal_id"] == "2.")
    assert ey["proposal_text"] == (
        "Ratification of the appointment of Ernst & Young LLP as the independent "
        "registered public accounting firm for fiscal year 2023."
    )


def test_real_excerpt_subrows_novote_split_star_and_empty_fund():
    text = (FIX / "director_split_novote.txt").read_text()
    rows = pe.parse(text)
    stats = pe.parse_stats(text)
    assert stats["meetings_seen"] == 4
    assert stats["proposals_emitted"] == len(rows)
    assert stats["proposals_seen"] == stats["proposals_emitted"] + stats["proposals_dropped"]
    # fund with 'held no voting securities' emits nothing and does not leak its name
    assert {r["fund_name"] for r in rows} == {"JPMorgan Core Plus Bond Fund"}
    dirs = [r for r in rows if r["issuer_name"].startswith("CLEAR CHANNEL")
            and r["proposal_id"] == "1."]
    assert dirs[0]["proposal_text"] == "DIRECTOR John Dionne"
    assert len(dirs) == 9
    # 'Split ..' votes, 'No vote' and '*' for/against are dropped, never guessed
    reasons = stats["dropped_reasons"]
    assert reasons.get("vote_not_in_vocab", 0) >= 2
    assert "for_against_not_in_vocab" not in reasons  # "*" now emits with empty F/A
    assert any(r["issuer_name"].startswith("Icahn".upper()) or r["proposal_text"].startswith("ICAHN")
               for r in rows)
    assert all(r["vote"] in pe.VOTE_VOCAB for r in rows)
    assert not any(r["proposal_text"].startswith("Non-Voting agenda") for r in rows)


def test_cmmt_non_voting_emits_nothing():
    text = (FIX / "cmmt_takenoaction.txt").read_text()
    stats = pe.parse_stats(text)
    assert stats["nonvoting_skipped"] >= 1
    assert all(r["proposal_id"] != "CMMT" for r in pe.parse(text))


def test_take_no_action_with_empty_for_against():
    rows = pe.parse(_doc(_row("2", "ELECTION OF CHAIR", "Mgmt", "Take No Action", "")))
    assert [(r["vote"], r["for_against_management"]) for r in rows] == [("Take No Action", "")]


def test_paren_ids_and_shareholder_proposals():
    rows = pe.parse(_doc(_row("1a)", "Elect Jane", "Mgmt", "For", "For")
                         + _row("7.", "Report on x", "Shr", "Against", "For")))
    assert [(r["proposal_id"], r["proposal_type"]) for r in rows] == [("1a)", "Mgmt"), ("7.", "Shr")]


def test_missing_or_bad_date_drops_meeting():
    body = _row("1", "Elect", "Mgmt", "For", "For")
    for bad in ("", "31-Feb-2023", "2023-01-05", "05-Foo-2023"):
        d = _doc(body, date=bad)
        assert pe.parse(d) == []
        assert pe.parse_stats(d)["meetings_dropped_reasons"] == {"bad_meeting_date": 1}


def test_missing_issuer_drops_meeting():
    assert pe.parse(_doc(_row("1", "Elect", "Mgmt", "For", "For"), issuer="")) == []


def test_meeting_before_any_fund_heading_dropped():
    d = _doc(_row("1", "Elect", "Mgmt", "For", "For"))
    d = d.split("\n", 1)[1]  # remove the fund heading line
    assert pe.parse(d) == []
    assert pe.parse_stats(d)["meetings_dropped_reasons"] == {"no_fund_heading": 1}


def test_empty_vote_and_unknown_vote_dropped():
    rows = _row("1", "A", "Mgmt", "", "") + _row("2", "B", "Mgmt", "Maybe", "") + \
        _row("3", "C", "Mgmt", "For", "For")
    d = _doc(rows)
    assert [r["proposal_id"] for r in pe.parse(d)] == ["3"]
    assert pe.parse_stats(d)["dropped_reasons"] == {"empty_vote": 1, "vote_not_in_vocab": 1}


def test_misaligned_columns_dropped():
    bad = "1      " + "X" * 70 + "For                            For\n"
    d = _doc(bad + _row("2", "ok", "Mgmt", "For", "For"))
    assert [r["proposal_id"] for r in pe.parse(d)] == ["2"]


def test_subrow_under_voted_parent_is_ambiguous():
    d = _doc(_row("1.", "Parent", "Mgmt", "For", "For") + _row("", "child", "Mgmt", "For", "For"))
    assert [r["proposal_id"] for r in pe.parse(d)] == ["1."]
    assert pe.parse_stats(d)["dropped_reasons"] == {"ambiguous_subrow": 1}


def test_unknown_heading_does_not_inherit_stale_fund():
    d = _doc(_row("1", "A", "Mgmt", "For", "For")) + "\nSomething odd\n" + DASH + "\nrandom\n" + \
        _doc(_row("1", "A", "Mgmt", "For", "For")).split("\n", 2)[2]
    rows = pe.parse(d)
    assert len(rows) == 1


def test_trailing_footnote_ends_meeting():
    d = _doc(_row("1", "A", "Mgmt", "For", "For") + "\n* Management position unknown\n")
    assert [r["proposal_text"] for r in pe.parse(d)] == ["A"]


_word = st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=122,
                                       blacklist_characters="[]\\^_`"),
                min_size=1, max_size=12)


@settings(max_examples=60, deadline=None)
@given(words=st.lists(_word, min_size=1, max_size=40), width=st.integers(12, 57))
def test_wrapping_invariance(words, width):
    text = " ".join(words)
    rows = pe.parse(_doc(_row("1", text, "Mgmt", "For", "For", width=width)))
    assert len(rows) == 1
    assert rows[0]["proposal_text"] == " ".join(text.split())


@settings(max_examples=40, deadline=None)
@given(pad=st.integers(0, 5), crlf=st.booleans())
def test_trailing_space_and_line_ending_invariance(pad, crlf):
    base = _doc(_row("1", "Elect the nominee for something long enough to wrap around the text "
                          "column limit", "Mgmt", "Against", "For"))
    want = pe.parse(base)
    noisy = "\n".join(x + " " * pad for x in base.split("\n"))
    if crlf:
        noisy = noisy.replace("\n", "\r\n")
    assert pe.parse(noisy) == want and len(want) == 1


@settings(max_examples=40, deadline=None)
@given(vote=st.sampled_from(sorted(pe.VOTE_VOCAB)), fa=st.sampled_from(["For", "Against", ""]))
def test_vocab_votes_roundtrip(vote, fa):
    rows = pe.parse(_doc(_row("9", "Thing", "Mgmt", vote, fa)))
    assert [(r["vote"], r["for_against_management"]) for r in rows] == [(vote, fa)]


# --- Amendment 1 ---------------------------------------------------------------


def test_amend1_director_heading_subrows():
    d = _doc(_row("1.", "DIRECTOR", "", "", "") + _row("", "Jane  Doe", "Mgmt", "For", "For")
             + _row("", "John Roe", "Mgmt", "Withheld", "Against"))
    got = [(r["proposal_id"], r["proposal_text"], r["vote"]) for r in pe.parse(d)]
    assert got == [("1.", "DIRECTOR Jane Doe", "For"), ("1.", "DIRECTOR John Roe", "Withheld")]


def test_amend1_star_for_against_emitted_empty():
    rows = pe.parse(_doc(_row("1a.", "ICAHN NOMINEE: X", "Mgmt", "For", "*")))
    assert [(r["vote"], r["for_against_management"]) for r in rows] == [("For", "")]
    assert pe.parse_stats(_doc(_row("1a.", "N", "Mgmt", "For", "*")))["proposals_dropped"] == 0


def test_amend1_other_for_against_garbage_still_dropped():
    assert pe.parse(_doc(_row("1", "N", "Mgmt", "For", "Maybe"))) == []


def test_amend1_fund_and_issuer_whitespace_normalised():
    rows = pe.parse(_doc(_row("1", "A", "Mgmt", "For", "For"), fund="Test   Fund", issuer="ACME    CORP"))
    assert (rows[0]["fund_name"], rows[0]["issuer_name"]) == ("Test Fund", "ACME CORP")


def test_amend1_no_vote_and_split_dropped_ids_literal():
    d = _doc(_row("2)", "A", "Mgmt", "No vote", "") + _row("3.", "B", "Mgmt", "Split 50% For 50% Against", "Split")
             + _row("4.", "C", "Mgmt", "For", "For"))
    assert [r["proposal_id"] for r in pe.parse(d)] == ["4."]
