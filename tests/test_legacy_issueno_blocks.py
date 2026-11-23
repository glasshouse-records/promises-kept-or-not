"""Tests for the block-oriented legacy N-PX 'Issue No.' parser."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest.legacy_issueno_blocks import parse, parse_stats

FIX = Path(__file__).parent / "fixtures" / "legacy_issueno_blocks"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
    "meeting_status", "meeting_type", "country", "proposal_id",
    "proposal_text", "proponent", "rec", "vote", "for_against",
}


def by_id(rows):
    return {r["proposal_id"]: r for r in rows}


def block(ticker="MMM", extra_rows="", status="Voted", date="05/09/2023", issuer="3M Company"):
    return (
        "Fund Name : Test Fund\n"
        + "_" * 80 + "\n"
        + f"{issuer}\n"
        + "Ticker     Security ID:             Meeting Date          Meeting Status\n"
        + f"{ticker:<11}CUSIP 88579Y101          {date:<22}{status}\n"
        + "Meeting Type                        Country of Trade\n"
        + "Annual                              United States\n"
        + "Issue No.  Description              Proponent  Mgmt Rec   Vote Cast  For/Against\n"
        + "                                                                      Mgmt\n\n"
        + extra_rows
    )


ROW1 = "1          Elect Thomas K. Brown    Mgmt       For        For        For\n"


def test_schwab_wrapped_rows_and_keys():
    rows = parse(fx("schwab_excerpt.txt"))
    assert all(set(r) == KEYS for r in rows)
    r = by_id(rows)
    assert len(rows) == 13
    assert r["5"]["proposal_text"] == "Elect James R. Fitterling"
    assert r["12"]["proposal_text"] == "Advisory Vote on Executive Compensation"
    assert r["13"]["rec"] == "1 Year" and r["13"]["vote"] == "1 Year"
    assert r["13"]["for_against"] == "For"
    one = r["1"]
    assert one == {
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


def test_echo_vote_literal_multiword():
    rows = parse(fx("schwab_echo.txt"))
    assert rows and all(r["vote"] == "Echo Vote" and r["for_against"] == "N/A" for r in rows)
    assert rows[0]["meeting_status"] == "Echo Vote"
    assert by_id(rows)["1.2"]["proposal_text"] == "Elect Frank C. Herringer"


def test_proxy_contest_tna_emitted():
    rows = parse(fx("schwab_contest.txt"))
    assert rows
    assert {r["meeting_type"] for r in rows} == {"Proxy Contest"}
    assert {r["meeting_status"] for r in rows} == {"Take No Action"}
    assert rows[0]["vote"] == "TNA"
    assert rows[0]["proposal_text"] == "Elect Management Nominee Frances Arnold"


def test_vaneck_funds_without_meetings():
    text = fx("vaneck_excerpt.txt")
    assert parse(text) == []
    st_ = parse_stats(text)
    assert st_["meetings_seen"] == 0 and st_["proposals_emitted"] == 0


def test_hartford_html_pre():
    rows = parse(fx("hartford_excerpt.htm"))
    r = by_id(rows)
    assert r["1"]["fund_heading"] == "Hartford Balanced HLS Fund"
    assert r["1"]["ticker"] == "ACN" and r["1"]["security_id"] == "CUSIP G1151C101"
    assert r["1"]["meeting_date"] == "2023-02-01"
    assert r["6"]["proposal_text"] == "Elect Venkata Renduchintala"
    assert r["12"]["proposal_text"] == "Appointment of Auditor and Authority to Set Fees"
    assert r["2"]["vote"] == "Against" and r["2"]["for_against"] == "Against"


def test_html_entities_decoded():
    text = "<PRE>\n" + block(issuer="Procter &amp; Gamble") + ROW1 + "</PRE>\n"
    rows = parse(text)
    assert rows[0]["issuer_name"] == "Procter & Gamble"


def test_russell_sgml_variant():
    rows = parse(fx("russell_excerpt.txt"))
    r = by_id(rows)
    assert len(rows) == 3 + 12
    assert r["3"]["proposal_text"] in (
        "Adjustment Of Estimated Guarantee Quota For Subsidiaries In 2022",
        "Accounts and Reports",
    )
    first = rows[0]
    assert first["fund_heading"] == "RIC Emerging Markets Fund"
    assert first["issuer_name"] == "37 INTERACTIVE ENTERTAINMENT NETWORK TECHNOLOGY GROUP CO., LTD."
    assert first["ticker"] == "002555" and first["security_id"] == "CINS Y9717X105"
    assert first["meeting_date"] == "2022-09-15" and first["country"] == "China"
    assert first["for_against"] == "For" and first["proposal_id"] == "1"
    na = [x for x in rows if x["proposal_text"] == "Non-Voting Meeting Note"]
    assert na and all(x["vote"] == "N/A" and x["proponent"] == "N/A" for x in na)
    wrapped = [x for x in rows if x["proposal_text"].endswith("Subsidiaries In 2022")]
    assert wrapped[0]["proposal_text"] == (
        "Adjustment Of Estimated Guarantee Quota For Subsidiaries In 2022"
    )


def test_blank_ticker():
    rows = parse(block(ticker="") + ROW1)
    assert len(rows) == 1 and rows[0]["ticker"] == ""
    assert rows[0]["security_id"] == "CUSIP 88579Y101"


def test_drop_bad_date_and_missing_issuer():
    assert parse(block(date="13/45/2023") + ROW1) == []
    assert parse(block(date="") + ROW1) == []
    assert parse(block(issuer="") + ROW1) == []


def test_drop_proposal_outside_vocab_keeps_neighbours():
    bad = "2          Elect X                  Mgmt       Maybe      For        For\n"
    rows = parse(block() + ROW1 + bad)
    assert [r["proposal_id"] for r in rows] == ["1"]
    s = parse_stats(block() + ROW1 + bad)
    assert s["proposals_seen"] == 2 and s["proposals_emitted"] == 1
    assert s["proposals_dropped"] == 1 and s["reasons"]


def test_unplaceable_line_drops_proposal():
    junk = "garbage in the first column\n"
    rows = parse(block() + ROW1 + junk)
    assert rows == []


def test_continuation_after_page_break_drops_not_merges():
    text = block() + ROW1 + "\f\n            Fitterling\n"
    assert parse(text) == []


def test_no_carry_over_between_meetings_and_funds():
    second = (
        "Fund Name : Other Fund\n"
        + "_" * 80 + "\nAcme Corp\n"
        + "Ticker     Security ID:             Meeting Date          Meeting Status\n"
        + "ACME       ISIN US0000000000        01/02/2023            Voted\n"
        + "Meeting Type                        Country of Trade\n"
        + "Special                             Canada\n"
        + "Issue No.  Description              Proponent  Mgmt Rec   Vote Cast  For/Against\n"
        + "                                                                      Mgmt\n\n"
        + "1          Approve Merger           Mgmt       For        For        For\n"
    )
    rows = parse(block() + ROW1 + second)
    assert [r["fund_heading"] for r in rows] == ["Test Fund", "Other Fund"]
    assert rows[1]["ticker"] == "ACME" and rows[1]["country"] == "Canada"
    assert rows[1]["security_id"] == "ISIN US0000000000"


def test_meeting_before_fund_heading_dropped():
    text = block().split("\n", 1)[1] + ROW1
    assert parse(text) == []
    assert parse_stats(text)["meetings_dropped"] == 1


def test_stats_shape():
    s = parse_stats(fx("schwab_excerpt.txt"))
    assert set(s) >= {
        "meetings_seen", "meetings_dropped", "proposals_seen",
        "proposals_emitted", "proposals_dropped", "reasons",
    }
    assert s["meetings_seen"] == 1 and s["proposals_emitted"] == 13


@settings(max_examples=60, deadline=None)
@given(
    words=st.lists(st.sampled_from(["Elect", "Smith", "Ratify", "Auditor", "Plan", "of", "Pay"]),
                   min_size=1, max_size=8),
    # continuation lines start at column 12 inside a description column that ends at 35
    # (as in the filings): at most 23 characters, or the line abuts Proponent (unplaceable)
    width=st.integers(min_value=8, max_value=23),
    ticker=st.sampled_from(["", "AB", "XYZ"]),
)
def test_wrapping_invariance(words, width, ticker):
    """However the description is wrapped inside its column, text is the same."""
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    if any(len(x) > 24 for x in lines):
        return
    rows = "1          " + f"{lines[0]:<25}" + "Mgmt       For        For        For\n"
    for cont in lines[1:]:
        rows += "            " + cont + "\n"
    out = parse(block(ticker=ticker) + rows)
    assert len(out) == 1
    assert out[0]["proposal_text"] == " ".join(words)
    assert out[0]["ticker"] == ticker


def test_stray_unplaceable_line_counted_as_dropped_proposal():
    text = block() + ROW1 + "\nSIGNATURES\n"
    s = parse_stats(text)
    assert s["proposals_emitted"] == 1
    assert s["proposals_dropped"] == 1 and s["proposals_seen"] == 2


def test_uppercase_vocab_emitted_literally():
    row = "1          Elect X                  MGMT       FOR        FOR        FOR\n"
    rows = parse(block() + row)
    assert rows[0]["proponent"] == "MGMT" and rows[0]["vote"] == "FOR"


def test_sgml_markup_does_not_decode_entities():
    text = "<PAGE>\n" + block(issuer="AT&amp;T Inc") + ROW1
    assert parse(text)[0]["issuer_name"] == "AT&amp;T Inc"
