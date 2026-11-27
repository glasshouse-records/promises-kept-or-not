"""Tests for the block-oriented 'Registrant Voted' legacy N-PX parser (Global X layout)."""

from __future__ import annotations

from pathlib import Path

from glasshouse.ingest.legacy_regvoted_blocks import parse, parse_stats

FIX = Path(__file__).parent / "fixtures" / "legacy_regvoted"

KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
    "meeting_status", "meeting_type", "country", "proposal_id",
    "proposal_text", "proponent", "rec", "vote", "for_against",
}


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def by(rows, issuer):
    return [r for r in rows if r["issuer_name"] == issuer]


HDR = " Proposal                                                Proposed by Mgt. Position Registrant Voted"


def doc(body: str, heading: str = "Global X Test ETF") -> str:
    return f"                    {heading}\n{HDR}\n{body}\n"


MEET = "ACME CORP.\n Security ID: 00287Y109  Ticker: ACME\n Meeting Date: 05-May-23           Meeting Type: Annual\n"
ROW = " 1  Elect Jane Doe                                      Management     For          Voted - For\n"


def test_normal_meeting_and_leading_list_yields_nothing():
    rows = parse(fx("blocks_normal.txt"))
    assert {tuple(sorted(r)) for r in rows} == {tuple(sorted(KEYS))}
    assert {r["fund_heading"] for r in rows} == {"Global X Adaptive U.S. Factor ETF"}
    ab = by(rows, "ABBVIE INC.")
    assert len(ab) == 10
    r = ab[0]
    assert (r["ticker"], r["security_id"], r["meeting_date"], r["meeting_type"]) == (
        "ABBV", "00287Y109", "05/05/2023", "Annual")
    assert (r["country"], r["meeting_status"], r["for_against"]) == ("", "", "")
    assert (r["proposal_id"], r["proposal_text"], r["proponent"], r["rec"], r["vote"]) == (
        "1", "Elect Robert J. Alpern", "Management", "For", "For")
    assert not any("Non-Voting Funds" in x["fund_heading"] or "T-Bill" in x["fund_heading"] for x in rows)


def test_wrapped_proposal_text_joined_with_one_space():
    ab = {r["proposal_id"]: r for r in by(parse(fx("blocks_normal.txt")), "ABBVIE INC.")}
    assert ab["8"]["proposal_text"] == (
        "Shareholder Proposal Regarding Report on Political Expenditures and Values Congruency")
    assert ab["8"]["proponent"] == "Shareholder" and ab["8"]["vote"] == "Against"
    assert ab["10"]["proposal_text"].endswith("Application for Secondary and Tertiary Patents")
    assert ab["10"]["rec"] == "Against"


def test_text_overrunning_the_proponent_column_is_still_cut_correctly():
    rows = parse(fx("blocks_pagebreak.txt"))
    r = [x for x in by(rows, "ACTIVISION BLIZZARD, INC.") if x["proposal_id"] == "11"][0]
    assert r["proposal_text"] == "Frequency of Advisory Vote on Executive Compensation"
    assert (r["proponent"], r["rec"], r["vote"]) == ("Management", "1 Year", "1 Year")


def test_page_break_with_repeated_header_continues_the_meeting():
    rows = parse(fx("blocks_pagebreak.txt"))
    act = by(rows, "ACTIVISION BLIZZARD, INC.")
    assert [r["proposal_id"] for r in act] == [str(i) for i in range(1, 16)]
    assert {r["fund_heading"] for r in rows} == {"Global X Adaptive U.S. Factor ETF"}
    p14 = act[13]
    assert p14["proposal_text"] == "Shareholder Proposal Regarding Policy on Freedom of Association"
    assert p14["vote"] == "For" and p14["rec"] == "Against"
    assert act[14]["vote"] == "Abstain"
    assert parse_stats(fx("blocks_pagebreak.txt"))["page_number_line"] == 1


def test_proxy_contest_with_restarted_numbering_dropped_whole_and_counted():
    text = fx("blocks_contest.txt")
    rows = parse(text)
    assert by(rows, "ILLUMINA, INC.") == []
    assert len(by(rows, "INCYTE CORPORATION")) == 2
    assert parse_stats(text)["dropped_duplicate_proposal_id"] == 1


def test_non_voting_rows_kept_verbatim_and_unreadable_meeting_dropped():
    text = fx("blocks_nonvoting.txt")
    rows = parse(text)
    ae = by(rows, "AEDIFICA NV")
    assert [r["vote"] for r in ae] == ["Non-Voting"]
    assert ae[0]["proponent"] == "N/A" and ae[0]["rec"] == "N/A"
    # the fund heading changes at the page break: a new fund, so a new (headerless-meeting) section
    assert len(by(rows, "ACADIA PHARMACEUTICALS INC.")) == 6
    # the Aging Population section holds a second 'Meeting Date:' line with no issuer: nothing guessed
    assert all(r["fund_heading"] != "Global X Aging Population ETF" for r in rows)
    assert parse_stats(text)["orphan_lines_before_first_meeting"] >= 1


def test_different_heading_after_header_starts_new_fund():
    text = doc(MEET + ROW, "Fund A") + doc(MEET.replace("ACME", "BETA") + ROW, "Fund B")
    rows = parse(text)
    assert [(r["fund_heading"], r["issuer_name"]) for r in rows] == [
        ("Fund A", "ACME CORP."), ("Fund B", "BETA CORP.")]


def test_same_heading_repeat_with_new_issuer_starts_new_meeting_same_fund():
    text = doc(MEET + ROW) + doc(MEET.replace("ACME", "BETA") + ROW)
    rows = parse(text)
    assert {r["fund_heading"] for r in rows} == {"Global X Test ETF"}
    assert [r["issuer_name"] for r in rows] == ["ACME CORP.", "BETA CORP."]


def test_missing_ticker_and_security_id_are_empty_strings():
    m = "ACME CORP.\n Security ID:  Ticker:\n Meeting Date: 05-May-23           Meeting Type: Annual\n"
    r = parse(doc(m + ROW))[0]
    assert (r["security_id"], r["ticker"]) == ("", "")
    m = "ACME CORP.\n Security ID: B0130A108\n Meeting Date: 05-May-23           Meeting Type: Annual\n"
    r = parse(doc(m + ROW))[0]
    assert (r["security_id"], r["ticker"]) == ("B0130A108", "")


def test_unreadable_date_drops_meeting_and_date_converts():
    bad = MEET.replace("05-May-23", "32-Foo-23")
    assert parse(doc(bad + ROW)) == []
    assert parse_stats(doc(bad + ROW))["dropped_bad_date"] == 1
    assert parse(doc(MEET.replace("05-May-23", "01-Dec-22") + ROW))[0]["meeting_date"] == "12/01/2022"


def test_dotted_and_lettered_proposal_ids_and_two_digit_id_with_single_space():
    body = MEET + (
        " 1.1 Elect A                                            Management     For          Voted - For\n"
        " 1A  Elect B                                            Management     For          Voted - For\n"
        " 1.A Elect C                                            Management     For          Voted - For\n"
        " 10 Elect D                                             Management     For          Voted - For\n")
    assert [r["proposal_id"] for r in parse(doc(body))] == ["1.1", "1A", "1.A", "10"]


def test_columns_on_two_lines_or_none_drop_that_proposal_only():
    body = MEET + (
        " 1  Elect A                                             Management     For          Voted - For\n"
        " 2  Elect B                                             Management     For          Voted - For\n"
        "      continued                                         Management     For          Voted - For\n"
        " 3  Elect C with no columns at all\n"
        " 4  Elect D                                             Management     For          Voted - For\n")
    text = doc(body)
    assert [r["proposal_id"] for r in parse(text)] == ["1", "4"]
    st = parse_stats(text)
    assert st["dropped_columns_on_two_lines"] == 1 and st["dropped_no_columns"] == 1


def test_vote_normalisation_only_exact_voted_dash_prefix():
    def vote(v):
        line = f" 1  Elect A                                             Management     For          {v}\n"
        return parse(doc(MEET + line))[0]["vote"]
    assert vote("Voted - For") == "For"
    assert vote("Voted - Withheld") == "Withheld"
    assert vote("Take No Action") == "Take No Action"
    assert vote("Voted - 1 Year") == "1 Year"
    for odd in ("Non-Voting", "Voted - Split", "Voted -Abstain", "Voted -- For", "Voted"):
        assert vote(odd) == odd


def test_contest_in_meeting_type_dropped_any_case():
    m = MEET.replace("Annual", "Proxy ConTest")
    assert parse(doc(m + ROW)) == []
    assert parse_stats(doc(m + ROW))["dropped_contest"] == 1


def test_unrecognised_line_inside_meeting_drops_meeting():
    body = MEET + ROW + "Some stray footer sentence\n" + MEET.replace("ACME", "BETA") + ROW
    text = doc(body)
    assert [r["issuer_name"] for r in parse(text)] == ["BETA CORP."]
    assert parse_stats(text)["dropped_unrecognised_line"] == 1


def test_html_tags_and_entities_are_removed():
    text = "<html><body><pre>" + doc(
        MEET.replace("ACME CORP.", "AT&amp;T INC.") + ROW) + "</pre></body></html>"
    r = parse(text)[0]
    assert r["issuer_name"] == "AT&T INC."


def test_no_input_and_text_without_fund_sections():
    assert parse("") == []
    assert parse("Non-Voting Funds\nGlobal X Foo ETF\nno votes\n") == []


def test_cut_inside_the_vote_field_is_unaligned_not_guessed():
    # the vote column starts left of the header's offset, so its cut lands inside 'Voted - For'
    body = MEET + " 1  Elect A                                  Management     For     Voted - For\n"
    assert parse(doc(body)) == []
    assert parse_stats(doc(body))["dropped_unaligned_line"] == 1
