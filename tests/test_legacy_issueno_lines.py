"""Tests for the line-oriented legacy 'Issue No.' N-PX parser."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest import legacy_issueno_lines as m

FX = Path(__file__).parent / "fixtures" / "legacy_issueno_lines"

HDR = (
    "Ticker     Security ID:             Meeting Date          Meeting Status\n"
    "{t:<10} {sid:<24} 05/09/2023            Voted\n"
    "Meeting Type                        Country of Trade\n"
    "Annual                              United States\n"
    "Issue No.  Description              Proponent  Mgmt Rec   Vote Cast  For/Against\n"
    "                                                                      Mgmt\n\n"
)
SEP = "_" * 80 + "\n"
ROW = "{i:<10} {d:<24} Mgmt       For        For        For\n"


def doc(rows: str, ticker: str = "MMM", fund: str = "Fund Name : Test Fund") -> str:
    return fund + "\n" + SEP + "3M Company\n" + HDR.format(t=ticker, sid="CUSIP 88579Y101") + rows


def fx(name: str) -> str:
    return (FX / name).read_text()


def test_schwab_fixture_rows():
    rows = m.parse(fx("schwab.txt"))
    assert rows[0] == {
        "fund_heading": "Schwab 1000 Index Fund",
        "issuer_name": "3M Company",
        "ticker": "MMM",
        "security_id": "CUSIP 88579Y101",
        "meeting_date": "2023-05-09",
        "meeting_status": "Voted",
        "meeting_type": "Annual",
        "country": "United States",
        "proposal_id": "1",
        "proposal_text": "Elect Thomas K. Brown",
        "proponent": "Mgmt",
        "rec": "For",
        "vote": "For",
        "for_against": "For",
    }
    by_id = {r["proposal_id"]: r for r in rows if r["issuer_name"] == "3M Company"}
    assert by_id["5"]["proposal_text"] == "Elect James R. Fitterling"
    assert by_id["12"]["proposal_text"] == "Advisory Vote on Executive Compensation"
    assert by_id["13"]["rec"] == "1 Year" and by_id["13"]["vote"] == "1 Year"
    assert by_id["13"]["for_against"] == "For"


def test_vaneck_no_meetings():
    assert m.parse(fx("vaneck.txt")) == []


def test_hartford_html_pre():
    rows = m.parse(fx("hartford.htm"))
    assert rows[0]["fund_heading"] == "Hartford Balanced HLS Fund"
    assert rows[0]["issuer_name"] == "Accenture plc"
    assert rows[0]["security_id"] == "CUSIP G1151C101"
    assert rows[0]["meeting_date"] == "2023-02-01"
    r6 = [r for r in rows if r["proposal_id"] == "6"][0]
    assert r6["proposal_text"] == "Elect Venkata Renduchintala"


def test_russell_sgml_table():
    rows = m.parse(fx("russell.txt"))
    assert rows[0]["fund_heading"] == "RIC Emerging Markets Fund"
    assert rows[0]["issuer_name"].startswith("37 INTERACTIVE")
    assert rows[0]["ticker"] == "002555"
    assert rows[0]["security_id"] == "CINS Y9717X105"
    assert rows[0]["country"] == "China"
    r3 = [r for r in rows if r["proposal_id"] == "3"][0]
    assert r3["proposal_text"] == "Adjustment Of Estimated Guarantee Quota For Subsidiaries In 2022"
    assert r3["vote"] == "For" and r3["for_against"] == "For"
    na = [r for r in rows if r["proposal_text"] == "Non-Voting Meeting Note"]
    assert na and na[0]["proponent"] == "N/A" and na[0]["for_against"] == "N/A"


def test_blank_ticker():
    rows = m.parse(doc(ROW.format(i="1", d="Elect A. B."), ticker=""))
    assert len(rows) == 1 and rows[0]["ticker"] == ""
    assert rows[0]["security_id"] == "CUSIP 88579Y101"


def test_bad_date_drops_meeting():
    text = doc(ROW.format(i="1", d="Elect A. B.")).replace("05/09/2023", "13/45/2023")
    assert m.parse(text) == []
    assert m.parse_stats(text)["meetings_dropped"] == 1


def test_unknown_vocab_drops_proposal_only():
    rows = (
        "1          Elect A. B.              Mgmt       Maybe      For        For\n"
        + ROW.format(i="2", d="Elect C. D.")
    )
    out = m.parse(doc(rows))
    assert [r["proposal_id"] for r in out] == ["2"]
    stats = m.parse_stats(doc(rows))
    assert stats["proposals_dropped"] == 1 and stats["proposals_seen"] == 2


def test_misaligned_row_dropped():
    rows = "1          Elect A. B.              Mgmt      For        For        For\n"
    assert m.parse(doc(rows)) == []


def test_orphan_continuation_after_blank_drops_previous():
    rows = (
        ROW.format(i="1", d="Elect A. B.")
        + "\n            Fitterling\n"
        + ROW.format(i="2", d="Elect C. D.")
    )
    assert [r["proposal_id"] for r in m.parse(doc(rows))] == ["2"]


def test_no_carry_between_meetings_and_before_fund():
    text = SEP + "X Co\n" + HDR.format(t="X", sid="CUSIP 1") + ROW.format(i="1", d="Elect A.")
    assert m.parse(text) == []
    two = doc(ROW.format(i="1", d="Elect A."))
    two += SEP + "Bad Co\ngarbage\n" + ROW.format(i="1", d="Elect Z.")
    assert [r["issuer_name"] for r in m.parse(two)] == ["3M Company"]


def test_page_break_between_rows_ok():
    rows = ROW.format(i="1", d="Elect A.") + "<PAGE>\n" + ROW.format(i="2", d="Elect C.")
    assert [r["proposal_id"] for r in m.parse(doc(rows))] == ["1", "2"]


def test_html_entities_and_nbsp():
    body = doc("1          AT&amp;T &lt;x&gt;&nbsp;Plan            Mgmt       For        For        For\n")
    out = m.parse("<PRE>\n" + body + "</PRE>\n")
    assert out[0]["proposal_text"] == "AT&T <x> Plan"


def _render(words, width, ticker):
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    body = ROW.format(i="7", d=lines[0]) + "".join(f"            {c}\n" for c in lines[1:])
    return doc(body, ticker=ticker)


@settings(max_examples=60, deadline=None)
@given(
    words=st.lists(st.from_regex(r"[A-Za-z]{1,8}", fullmatch=True), min_size=1, max_size=12),
    width=st.integers(min_value=9, max_value=24),
    ticker=st.sampled_from(["", "MMM", "AB.C"]),
)
def test_wrapping_and_ticker_invariance(words, width, ticker):
    out = m.parse(_render(words, width, ticker))
    assert len(out) == 1
    assert out[0]["proposal_text"] == " ".join(words)
    assert out[0]["ticker"] == ticker


def test_prose_after_gap_ends_meeting_without_dropping_last_row():
    rows = ROW.format(i="1", d="Elect A.") + "\n\nItem 1: Proxy Voting Record\n"
    stats = m.parse_stats(doc(rows))
    assert stats["proposals_emitted"] == 1 and stats["proposals_dropped"] == 0


def test_columns_on_last_line_of_wrap_and_incomplete_row_dropped():
    rows = (
        "7          Elect A. and\n"
        "            Elect B.                Mgmt       For        For        For\n"
        "8          Lonely first line\n"
        + ROW.format(i="9", d="Elect C.")
    )
    out = m.parse(doc(rows))
    assert [(r["proposal_id"], r["proposal_text"]) for r in out] == [
        ("7", "Elect A. and Elect B."),
        ("9", "Elect C."),
    ]
    assert m.parse_stats(doc(rows))["reasons"] == {"incomplete_row": 1}


def test_shareholder_vocab_and_lowercase_cins_dropped():
    out = m.parse(doc("1          Report                   ShrHoldr   Against    For        Against\n"))
    assert out[0]["proponent"] == "ShrHoldr"
    assert m.parse(doc(ROW.format(i="1", d="x")).replace("CUSIP", "cusip")) == []


def test_multi_year_frequency_votes_are_in_the_vote_vocabulary():
    # The blocks parser accepts 2 Years / 3 Years votes; a vote of a closed-set frequency
    # must not be dropped here alone (that would only cost recall via the agreement gate).
    rows = (
        "13         Frequency of Say on Pay  Mgmt       1 Year     3 Years    Against\n"
        "14         Frequency of Say on Pay  Mgmt       3 Years    2 Years    Against\n"
    )
    out = m.parse(doc(rows))
    assert [(r["rec"], r["vote"]) for r in out] == [("1 Year", "3 Years"), ("3 Years", "2 Years")]
