"""Contract tests for legacy_regvoted_lines (docs/research/legacy-npx.md, last section).

Fixtures lines_normal/pagebreak/contest/nonvoting are real excerpts of Global X's
0001135428-23-000255; lines_edge.txt is synthetic (rules the excerpts do not exercise).
"""

from pathlib import Path

from glasshouse.ingest import legacy_issueno
from glasshouse.ingest import legacy_regvoted_lines as m

FX = Path(__file__).parent / "fixtures" / "legacy_regvoted"


def _t(name):
    return (FX / name).read_text()


def _rows(name):
    return m.parse(_t(name))


def test_keys_are_exactly_the_issueno_keys():
    rows = _rows("lines_normal.txt")
    assert rows and all(tuple(r) == legacy_issueno.KEYS for r in rows)


def test_normal_meeting_and_leading_nonvoting_list_yields_nothing():
    rows = _rows("lines_normal.txt")
    assert {r["fund_heading"] for r in rows} == {"Global X Adaptive U.S. Factor ETF"}
    assert [r["issuer_name"] for r in rows].count("ABBVIE INC.") == 10
    first = rows[0]
    assert first == {
        "fund_heading": "Global X Adaptive U.S. Factor ETF", "issuer_name": "ABBVIE INC.",
        "ticker": "ABBV", "security_id": "00287Y109", "meeting_date": "05/05/2023",
        "meeting_status": "", "meeting_type": "Annual", "country": "",
        "proposal_id": "1", "proposal_text": "Elect Robert J. Alpern",
        "proponent": "Management", "rec": "For", "vote": "For", "for_against": "",
    }
    assert len(rows) == 15


def test_wrapped_proposal_text_joined_with_one_space():
    rows = _rows("lines_normal.txt")
    r8 = next(r for r in rows if r["proposal_id"] == "8")
    assert r8["proposal_text"] == (
        "Shareholder Proposal Regarding Report on Political Expenditures and Values Congruency"
    )
    assert (r8["proponent"], r8["rec"], r8["vote"]) == ("Shareholder", "Against", "Against")
    r10 = next(r for r in rows if r["proposal_id"] == "10")
    assert r10["proposal_text"].endswith("Application for Secondary and Tertiary Patents")


def test_one_year_frequency_and_vote_prefix_stripped():
    rows = _rows("lines_pagebreak.txt")
    r = next(r for r in rows if r["proposal_id"] == "11")
    assert (r["rec"], r["vote"]) == ("1 Year", "1 Year")


def test_page_break_with_same_heading_continues_meeting():
    rows = _rows("lines_pagebreak.txt")
    atvi = [r for r in rows if r["issuer_name"] == "ACTIVISION BLIZZARD, INC."]
    assert [r["proposal_id"] for r in atvi] == ["11", "12", "13", "15"]
    assert atvi[2]["proposal_text"] == "Shareholder Proposal Regarding Severance Approval Policy"
    assert {r["fund_heading"] for r in atvi} == {"Global X Adaptive U.S. Factor ETF"}
    assert atvi[3]["vote"] == "Abstain"


def test_different_heading_starts_a_new_fund_and_page_number_is_noise():
    rows = _rows("lines_pagebreak.txt")
    ae = [r for r in rows if r["issuer_name"] == "AEDIFICA NV"]
    assert ae and {r["fund_heading"] for r in ae} == {"Global X Aging Population ETF"}
    assert next(r for r in rows if r["issuer_name"] == "AGNC INVESTMENT CORP.")["meeting_date"] == "04/20/2023"


def test_nonvoting_rows_kept_verbatim_and_odd_votes_verbatim():
    rows = _rows("lines_nonvoting.txt")
    assert [(r["proposal_id"], r["proponent"], r["rec"], r["vote"]) for r in rows] == [
        ("1", "N/A", "N/A", "Non-Voting"),
        ("2", "N/A", "N/A", "Non-Voting"),
        ("3", "Management", "For", "For"),
        ("4", "Management", "For", "Voted -Abstain"),
    ]
    assert rows[2]["proposal_text"] == "Increase in Authorised Capital (With Preemptive Rights)"


def test_split_vote_kept_verbatim_and_unnumbered_text_ending_nonvoting_is_text():
    rows = _rows("lines_pagebreak.txt")
    jef = [r for r in rows if r["issuer_name"].startswith("JEFFERIES")]
    assert jef[0]["proposal_text"] == "Amendment to to Authorize a New Class of Non-Voting Common Stock"
    assert jef[0]["vote"] == "For" and jef[1]["vote"] == "Voted - Split"
    assert jef[0]["ticker"] == "JEF" and jef[0]["security_id"] == "47233W109"


def test_proxy_contest_with_restarted_numbering_dropped_whole_and_counted():
    text = _t("lines_contest.txt")
    rows = m.parse(text)
    assert "ILLUMINA, INC." not in {r["issuer_name"] for r in rows}
    assert [r["issuer_name"] for r in rows] == ["INCYTE CORPORATION"]
    assert [r["proposal_id"] for r in rows] == ["1"]
    s = m.parse_stats(text)
    assert s["meeting_duplicate_proposal_id"] == 1


def test_edge_cases_and_stats():
    text = _t("lines_edge.txt")
    rows = m.parse(text)
    by = {}
    for r in rows:
        by.setdefault(r["issuer_name"], []).append(r)
    assert set(by) == {"ACME CORP", "LAST CO"}
    acme = by["ACME CORP"]
    assert [r["proposal_id"] for r in acme] == ["1", "3"]
    assert (acme[0]["security_id"], acme[0]["ticker"]) == ("", "ACM")
    last = by["LAST CO"]
    assert [r["proposal_id"] for r in last] == ["1.A", "1.B"]
    assert last[1]["proponent"] == "Shareholder"
    s = m.parse_stats(text)
    assert s["proposal_without_columns"] == 2  # ACME 2 (no vote) and LAST 2 (Voted - Voted)
    assert s["meeting_bad_date"] == 1
    assert s["meeting_unplaced_line"] == 1
    assert s["meeting_contest"] == 1
    # SIGNATURES text must not become a continuation of the last proposal
    assert "Pursuant" not in last[-1]["proposal_text"]


def test_text_without_votes_is_empty():
    assert m.parse("") == []
    assert m.parse("nothing here\n") == []
    assert sum(m.parse_stats("").values()) == 0


def test_parse_is_deterministic_and_html_tags_removed():
    text = _t("lines_normal.txt")
    assert m.parse(text) == m.parse(text)
    wrapped = "<pre>" + text.replace("\n", "</pre>\n<pre>") + "</pre>"
    assert m.parse(wrapped) == m.parse(text)
    assert m.parse(text.replace("Alpern", "&amp;Alpern"))[0]["proposal_text"] == "Elect Robert J. &Alpern"


def _doc(*body):
    return (
        "                    Global X Test ETF\n"
        " Proposal                                                Proposed by Mgt. Position Registrant Voted\n"
        + "".join(b + "\n" for b in body)
    )


P = " 1   Reclassification of Common Stock                     Management     For          Voted - For"


def test_r1_second_meeting_of_same_issuer_inherits_identity():
    # real shape (Constellation Brands): the second meeting prints only a Meeting Date line
    text = _doc(
        "CONSTELLATION BRANDS, INC.",
        " Security ID: 21036P108  Ticker: STZ",
        " Meeting Date: 19-Jul-22           Meeting Type: Annual",
        P,
        " Meeting Date: 09-Nov-22           Meeting Type: Special",
        P,
    )
    rows = m.parse(text)
    assert [(r["issuer_name"], r["security_id"], r["ticker"], r["meeting_date"], r["meeting_type"])
            for r in rows] == [
        ("CONSTELLATION BRANDS, INC.", "21036P108", "STZ", "07/19/2022", "Annual"),
        ("CONSTELLATION BRANDS, INC.", "21036P108", "STZ", "11/09/2022", "Special"),
    ]
    assert m.parse_stats(text)["meeting_date_without_issuer"] == 0


def test_r1_inherits_across_page_break_and_not_across_funds():
    text = _doc(
        "ACME CORP", " Security ID: 111111111  Ticker: ACM",
        " Meeting Date: 19-Jul-22           Meeting Type: Annual", P,
        "", "7", "",
        "                    Global X Test ETF",
        " Proposal                                                Proposed by Mgt. Position Registrant Voted",
        " Meeting Date: 09-Nov-22           Meeting Type: Special", P,
        "                    Global X Other ETF",
        " Proposal                                                Proposed by Mgt. Position Registrant Voted",
        " Meeting Date: 10-Nov-22           Meeting Type: Special", P,
    )
    rows = m.parse(text)
    assert [(r["issuer_name"], r["meeting_date"]) for r in rows] == [
        ("ACME CORP", "07/19/2022"), ("ACME CORP", "11/09/2022")]
    s = m.parse_stats(text)
    assert s["meeting_date_without_issuer"] == 1
    assert s["page_number"] == 1


def test_r1_proposals_before_any_meeting_dropped_and_counted():
    text = _doc(P, P.replace(" 1 ", " 2 "))
    assert m.parse(text) == []
    assert m.parse_stats(text)["proposal_without_meeting"] == 2


def test_r2_sub_adviser_line_is_not_the_heading():
    text = (
        "                    Global X Emerging Markets ETF\n"
        "          Sub-Adviser: Mirae Asset Global Investments\n"
        " Proposal                                                Proposed by Mgt. Position Registrant Voted\n"
        "ACME CORP\n Security ID: 111111111  Ticker: ACM\n"
        " Meeting Date: 19-Jul-22           Meeting Type: Annual\n" + P + "\n"
        "6\n"
        "                    Global X Emerging Markets ETF\n"
        "          Sub-Adviser: Mirae Asset Global Investments\n"
        " Proposal                                                Proposed by Mgt. Position Registrant Voted\n"
        " 2   Another                                              Management     For          Voted - For\n"
    )
    rows = m.parse(text)
    assert [r["fund_heading"] for r in rows] == ["Global X Emerging Markets ETF"] * 2
    assert [r["proposal_id"] for r in rows] == ["1", "2"]  # repeat header continued the meeting


def test_r2_ticker_glued_to_security_id():
    text = _doc(
        "PKSHA TECHNOLOGY INC.", " Security ID: J6384J101Ticker: 3993",
        " Meeting Date: 23-Dec-22           Meeting Type: Annual", P,
    )
    (r,) = m.parse(text)
    assert (r["security_id"], r["ticker"]) == ("J6384J101", "3993")


def _one(body_line, issuer_gap=""):
    return _doc(
        "ACME CORP", issuer_gap + " Security ID: 1  Ticker: A",
        " Meeting Date: 23-Dec-22           Meeting Type: Annual", body_line,
    )


def test_r3_squeezed_columns_closed_lists():
    rows = m.parse(_one(" 1   Elect A     Management   For Voted - For"))
    assert [(r["proposal_text"], r["proponent"], r["rec"], r["vote"]) for r in rows] == [
        ("Elect A", "Management", "For", "For")]
    r = m.parse(_one(" 1   Frequency Management 1 Year Voted - 1 Year"))[0]
    assert (r["rec"], r["vote"]) == ("1 Year", "1 Year")
    r = m.parse(_one(" 1   Opening     N/A    None   Non-Voting"))[0]
    assert (r["proponent"], r["rec"], r["vote"]) == ("N/A", "None", "Non-Voting")
    r = m.parse(_one(" 1   X     Shareholder    Against   Voted -- For"))[0]
    assert r["vote"] == "Voted -- For"


def test_r3_open_vocabulary_is_not_a_column_line():
    # unknown proponent: not columns, so the proposal has none and is dropped
    text = _one(" 1   Elect A     Chairman   For   Voted - For")
    assert m.parse(text) == []
    assert m.parse_stats(text)["proposal_without_columns"] == 1
    # 'Voted - N/A' is outside the closed vote list
    assert m.parse(_one(" 1   X   Management   For   Voted - N/A")) == []


def test_r3_notes_before_first_proposal_ignored_and_counted():
    text = _doc(
        "ACME CORP", " Security ID: 1  Ticker: A",
        " Meeting Date: 23-Dec-22           Meeting Type: Annual",
        "    Please Note That the Company Notice and Proxy Form",
        "      are available.",
        P, "    Late note after a proposal",
    )
    (r,) = m.parse(text)
    assert r["proposal_text"] == "Reclassification of Common Stock"  # R4: closed proposal
    assert m.parse_stats(text)["note_line_ignored"] == 2
    assert m.parse_stats(text)["note_after_proposal"] == 1


def test_r3_blank_line_between_issuer_and_security_id():
    (r,) = m.parse(_one(P, issuer_gap="\n"))
    assert r["issuer_name"] == "ACME CORP"


def test_r3_three_part_ids_but_not_o1_s1():
    (r,) = m.parse(_one(" 3.1.1   Elect A     Management   For Voted - For"))
    assert r["proposal_id"] == "3.1.1"
    text = _one(" O.1   Elect A     Management   For Voted - For")
    assert m.parse(text) == []
    assert m.parse_stats(text)["meeting_unplaced_line"] == 1


def test_r4_page_break_note_after_closed_proposal_is_not_text():
    # real excerpt: AIA GROUP LTD 18-May-23 proposal 12, then a page break and a note
    text = _doc(
        "AIA GROUP LTD", " Security ID: Y002A1105  Ticker: 1299",
        " Meeting Date: 18-May-23           Meeting Type: Annual",
        " 11 To Approve and Adopt the Employee Share Purchase",
        "      Plan of the Company with the Amended Terms         Management     Against      Voted - Against",
        " 12 To Approve and Adopt the Agency Share Purchase Plan",
        "      of the Company with the Amended Terms              Management     Against      Voted - Against",
        "", "726", "",
        "                    Global X Test ETF",
        "                           Sub-Adviser: Mirae Asset Global Investments",
        " Proposal                                                 Proposed by Mgt. Position Registrant Voted",
        "    19 Apr 2023: Please Note That This is A Revision",
        "      Due to Modification Of-comment. If You Have Already",
        "      Thank You                                           Non-Voting",
    )
    rows = m.parse(text)
    assert [r["proposal_id"] for r in rows] == ["11", "12"]
    assert rows[1]["proposal_text"] == (
        "To Approve and Adopt the Agency Share Purchase Plan of the Company with the Amended Terms")
    assert m.parse_stats(text)["note_after_proposal"] == 3
