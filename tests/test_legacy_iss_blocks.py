"""Legacy ISS-text N-PX parser (structural approach). Excerpts are real."""

from __future__ import annotations

import textwrap
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest.legacy_iss_blocks import parse, parse_stats

FX = Path(__file__).parent / "fixtures" / "legacy_iss"

HDR = "#     Proposal                                Mgt Rec   Vote Cast    Sponsor"


def fx(name: str) -> str:
    return (FX / name).read_text()


def prop_line(pid: str, text: str, rec: str, vote: str, sp: str) -> str:
    return f"{pid:<6}{text:<40}{rec:<10}{vote:<13}{sp}"


def doc(*proposal_lines: str, heading: str = "FUND A", date: str = "JUL 12, 2022") -> str:
    return "\n".join(
        [
            f"================= {heading} =================",
            "",
            "ACME, INC.",
            "",
            "Ticker:       ACM            Security ID:  123456789",
            f"Meeting Date: {date}   Meeting Type: Annual",
            "Record Date:  MAY 17, 2022",
            "",
            HDR,
            *proposal_lines,
            "",
        ]
    )


def test_basic_meeting_fields_and_wrapped_proposal():
    rows = parse(fx("vanguard_basic.txt"))
    assert rows, "fixture must yield rows"
    first = rows[0]
    assert first == {
        "fund_heading": "VANGUARD S&P SMALL-CAP 600 GROWTH INDEX FUND",
        "issuer_name": "8X8, INC.",
        "ticker": "EGHT",
        "security_id": "282914100",
        "meeting_date": "2022-07-12",
        "meeting_type": "Annual",
        "record_date": "2022-05-17",
        "rec_label": "Mgt Rec",
        "card_label": "",
        "proposal_id": "1.1",
        "proposal_text": "Elect Director Jaswinder Pal Singh",
        "rec": "For",
        "vote": "For",
        "sponsor": "Management",
    }
    wrapped = [r for r in rows if r["proposal_text"].startswith("Advisory Vote to Ratify")][0]
    assert wrapped["proposal_text"] == "Advisory Vote to Ratify Named Executive Officers' Compensation"
    assert {r["issuer_name"] for r in rows} >= {"8X8, INC.", "A10 NETWORKS, INC."}


def test_proxy_contest_card_labels_and_diss_rec():
    rows = parse(fx("contest.txt"))
    assert rows
    r = rows[0]
    assert r["meeting_type"] == "Proxy Contest"
    assert r["rec_label"] == "Diss Rec"
    assert r["card_label"] == "Management Universal Proxy (White Proxy Card)"
    assert r["proposal_id"] == "1A"
    assert r["proposal_text"] == "Elect Management Nominee Director Frances Arnold"
    # the heading text line is not a proposal and is not glued to one
    assert not any("From the Combined List" in x["proposal_text"] for x in rows)


def test_wrapped_meeting_type():
    rows = parse(fx("wrapped_type.txt"))
    assert rows and rows[0]["meeting_type"] == "Annual and Special Meeting"


def test_wrapped_fund_heading_joined_with_single_space():
    rows = parse(fx("wrapped_heading.txt"))
    assert rows[0]["fund_heading"] == (
        "VANGUARD RUSSELL 1000 INDEX FUND - VANGUARD-ADVISED FUNDS POLICY"
    )


def test_html_pre_block_is_reduced_to_text():
    rows = parse(fx("blackrock.htm"))
    assert rows
    assert rows[0]["fund_heading"] == "BlackRock Global Allocation Fund, Inc."
    assert rows[0]["issuer_name"] == "3M COMPANY"
    assert rows[0]["proposal_text"] == 'Elect Director Thomas "Tony" K. Brown'


def test_html_entities_decoded():
    body = doc(
        prop_line("1", "Approve S&P Plan", "For", "For", "Management"),
        heading="BlackRock S&P 500 Index V.I. Fund",
    ).replace("&", "&amp;")
    rows = parse("<html><body><pre>\n" + body + "\n</pre></body></html>")
    assert rows[0]["fund_heading"] == "BlackRock S&P 500 Index V.I. Fund"
    assert rows[0]["proposal_text"] == "Approve S&P Plan"


def test_literal_values_kept_and_unknown_dropped():
    t = doc(
        prop_line("1", "Say on Pay Frequency", "One Year", "One Year", "Management"),
        prop_line("2", "Something", "None", "Do Not Vote", "Shareholder"),
        prop_line("3", "Bad vote", "For", "Maybe", "Management"),
        prop_line("4", "Bad rec", "Sometimes", "For", "Management"),
        prop_line("5", "Bad sponsor", "For", "For", "Other"),
        prop_line("6", "Empty vote", "For", "", "Management"),
    )
    rows = parse(t)
    assert [(r["proposal_id"], r["rec"], r["vote"], r["sponsor"]) for r in rows] == [
        ("1", "One Year", "One Year", "Management"),
        ("2", "None", "Do Not Vote", "Shareholder"),
    ]
    s = parse_stats(t)
    assert s["proposals_seen"] == 6 and s["proposals_emitted"] == 2 and s["proposals_dropped"] == 4
    assert s["reasons"]["proposal:vote_not_in_vocab"] == 1
    assert s["reasons"]["proposal:empty_vote"] == 1
    assert s["reasons"]["proposal:rec_not_in_vocab"] == 1
    assert s["reasons"]["proposal:sponsor_not_in_vocab"] == 1


def test_wrapped_recommendation_is_dropped_not_guessed():
    t = doc(
        prop_line("1", "Say on Pay Frequency", "Three", "One Year", "Management"),
        " " * 47 + "Years",
        prop_line("2", "Fine", "For", "For", "Management"),
    )
    assert [r["proposal_id"] for r in parse(t)] == ["2"]


def test_word_crossing_column_boundary_is_dropped():
    bad = "1     " + "X" * 40 + "For       For          Management"
    assert parse(doc(bad)) == []


def test_bad_meeting_date_and_missing_issuer_drop_meeting():
    good = prop_line("1", "Elect", "For", "For", "Management")
    assert parse(doc(good, date="FEB 30, 2022")) == []
    assert parse(doc(good, date="")) == []
    t = doc(good).replace("ACME, INC.\n\n", "")
    assert parse(t) == []
    s = parse_stats(t)
    assert s["meetings_seen"] == 1 and s["meetings_dropped"] == 1
    assert s["reasons"]["meeting:issuer_missing"] == 1


def test_meeting_before_any_fund_heading_dropped():
    t = doc(prop_line("1", "Elect", "For", "For", "Management"))
    t = t.split("\n", 2)[2]  # strip the heading line
    assert parse(t) == []
    assert parse_stats(t)["reasons"]["meeting:no_fund_heading"] == 1


def test_fund_without_votes_and_blocks_separated_by_dashes():
    t = (
        "================= EMPTY FUND =================\n\nNo votes were cast.\n\n"
        + doc(prop_line("1", "Elect", "For", "For", "Management"), heading="FUND B")
        + "\n"
        + "-" * 80
        + "\n\nOTHER CO\n\n"
        "Ticker:                      Security ID:  987654321\n"
        "Meeting Date: AUG 01, 2022   Meeting Type: Special\n"
        "Record Date:\n\n"
        + HDR
        + "\n"
        + prop_line("1", "Approve Merger", "For", "Against", "Management")
        + "\n"
    )
    rows = parse(t)
    assert [(r["fund_heading"], r["issuer_name"], r["ticker"], r["record_date"]) for r in rows] == [
        ("FUND B", "ACME, INC.", "ACM", "2022-05-17"),
        ("FUND B", "OTHER CO", "", ""),
    ]
    assert parse_stats(t)["meetings_seen"] == 2


def test_parenthesised_proposal_ids_kept():
    rows = parse(doc(prop_line("4(a)", "Elect X", "For", "For", "Management")))
    assert rows[0]["proposal_id"] == "4(a)"


WORD = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABC.,'", min_size=1, max_size=14)


@settings(max_examples=60, deadline=None)
@given(st.lists(WORD, min_size=1, max_size=25), st.integers(min_value=15, max_value=33))
def test_wrapping_invariance(words, width):
    """Wherever the text wraps, the joined proposal_text is the same."""
    text = " ".join(words)
    chunks = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    lines = [prop_line("1", chunks[0], "For", "Against", "Shareholder")]
    lines += [" " * 6 + c for c in chunks[1:]]
    lines.append(prop_line("2", "Next", "For", "For", "Management"))
    rows = parse(doc(*lines))
    assert [r["proposal_id"] for r in rows] == ["1", "2"]
    assert rows[0]["proposal_text"] == text
    assert (rows[0]["rec"], rows[0]["vote"], rows[0]["sponsor"]) == ("For", "Against", "Shareholder")


def test_fund_heading_without_space_after_the_frame():
    # Invesco's 2023 N-PX (0001193125-23-204844) frames headings as "=Name====", no space.
    doc = ("=Invesco Active U.S. Real Estate ETF==================================\n\n\n"
           "Acadia Realty Trust\n\n\n"
           "Ticker: AKR                  Security ID: 004239109\n"
           "Meeting Date: MAY 4, 2023    Meeting Type: Annual\n"
           "Record Date: MAR 7, 2023\n\n\n"
           "#     Proposal                                Mgt Rec   Vote Cast    Sponsor\n"
           "1a    Elect Director Kenneth F. Bernstein     For       For          Management\n")
    rows = parse(doc)
    assert [(r["fund_heading"], r["proposal_id"], r["vote"]) for r in rows] == [
        ("Invesco Active U.S. Real Estate ETF", "1a", "For")]
