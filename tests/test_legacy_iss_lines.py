"""Line-by-line parser for legacy "FORM N-Px REPORT" (ISS text) documents."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest.legacy_iss_lines import parse, parse_stats

FIX = Path(__file__).parent / "fixtures" / "legacy_iss"
KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
    "meeting_type", "record_date", "rec_label", "card_label", "proposal_id",
    "proposal_text", "rec", "vote", "sponsor",
}
HEAD = "=" * 10 + " VANGUARD GNMA FUND - WELLINGTON " + "=" * 10 + "\n\n\n"


def fx(name: str) -> str:
    return (FIX / name).read_text()


def meeting(body: str, date: str = "APR 28, 2023", issuer: str = "ACME CORP") -> str:
    return (
        f"{issuer}\n\nTicker:       ACM            Security ID:  001\n"
        f"Meeting Date: {date}   Meeting Type: Annual\nRecord Date:  MAR 01, 2023\n\n"
        "#     Proposal                                Mgt Rec   Vote Cast    Sponsor\n"
        f"{body}\n\n--------------------------------------------------------------------------------\n"
    )


def test_basic_rows_and_wrapped_text():
    rows = parse(HEAD + fx("vanguard_basic_lines.txt"))
    assert rows and all(set(r) == KEYS for r in rows)
    r = next(x for x in rows if x["proposal_id"] == "1.2" and x["issuer_name"] == "ABBOTT LABORATORIES")
    assert r == {
        "fund_heading": "VANGUARD GNMA FUND - WELLINGTON",
        "issuer_name": "ABBOTT LABORATORIES",
        "ticker": "ABT",
        "security_id": "002824100",
        "meeting_date": "2023-04-28",
        "meeting_type": "Annual",
        "record_date": "2023-03-01",
        "rec_label": "Mgt Rec",
        "card_label": "",
        "proposal_id": "1.2",
        "proposal_text": "Elect Director Claire Babineaux-Fontenot",
        "rec": "For",
        "vote": "For",
        "sponsor": "Management",
    }
    last = rows[-1]
    assert last["issuer_name"] == "ABBVIE INC." and last["proposal_id"] == "1.3"
    assert {x["sponsor"] for x in rows} == {"Management", "Shareholder"}


def test_no_votes_note_gives_nothing():
    assert parse(fx("no_votes.txt")) == []
    assert parse_stats(fx("no_votes.txt"))["meetings_seen"] == 0


def test_html_pre_block_is_reduced_and_entities_decoded():
    rows = parse(fx("blackrock_pre.htm"))
    assert rows[0]["fund_heading"] == "BlackRock Global Allocation Fund, Inc."
    assert rows[0]["issuer_name"] == "3M COMPANY"
    assert rows[0]["proposal_text"] == 'Elect Director Thomas "Tony" K. Brown'
    assert len(rows) == 13


def test_html_entities_are_decoded_only_for_html():
    html = "<PRE>\n" + HEAD + meeting("1     Ratify Ernst &amp; Young LLP as    For       For          Management\n      Auditors")
    assert parse(html)[0]["proposal_text"] == "Ratify Ernst & Young LLP as Auditors"
    plain = HEAD + meeting("1     Ratify Ernst &amp; Young LLP as    For       For          Management")
    assert parse(plain)[0]["proposal_text"] == "Ratify Ernst &amp; Young LLP as"


def test_proxy_contest_labels():
    rows = parse(fx("contest_lines.txt"))
    by_id = {}
    for r in rows:
        by_id.setdefault((r["card_label"], r["proposal_id"]), r)
    white = by_id[("Management Universal Proxy (White Proxy Card)", "1A")]
    assert white["rec_label"] == "Diss Rec"  # most recent header in the meeting
    assert white["proposal_text"] == "Elect Management Nominee Director Frances Arnold"
    assert white["vote"] == "For" and white["rec"] == "For"
    gold = by_id[("Dissident Universal Proxy (Gold Proxy Card)", "1.1")]
    assert gold["vote"] == "Did Not Vote" and gold["sponsor"] == "Shareholder"
    assert gold["proposal_text"] == "Elect Dissident Nominee Director Vincent J. Intrieri"
    # heading text lines ("From the Combined List...") never leak into any row
    assert not any("Combined List" in r["proposal_text"] for r in rows)
    assert {r["card_label"] for r in rows} == {
        "Management Universal Proxy (White Proxy Card)",
        "Dissident Universal Proxy (Gold Proxy Card)",
    }
    assert {r["issuer_name"] for r in rows} == {"ILLUMINA, INC."}
    assert {r["meeting_type"] for r in rows} == {"Proxy Contest"}


def test_long_heading_wraps_are_joined():
    doc = (
        "=" * 8 + " VANGUARD VERY LONG NAME FOR A FUND THAT KEEPS " + "=" * 8 + "\n"
        + "=" * 8 + " GOING AND GOING - GLASS LEWIS ESG POLICY " + "=" * 8 + "\n\n\n"
        + meeting("1     Elect Someone                           For       For          Management")
    )
    rows = parse(doc)
    assert rows[0]["fund_heading"] == (
        "VANGUARD VERY LONG NAME FOR A FUND THAT KEEPS GOING AND GOING - GLASS LEWIS ESG POLICY"
    )


def test_literal_vocab_values_survive():
    body = (
        "1     Advisory Vote on Say on Pay Frequency   One Year  One Year     Management\n"
        "2     Advisory Vote on Say on Pay Frequency   Three     1 Year       Management\n"
        "3     Advisory Vote on Say on Pay Frequency   Two Years One Year     Management\n"
        "4     Elect Director X                        For       Withhold     Management\n"
        "5     Something                               None      Do Not Vote  Shareholder\n"
        "6     Elect Y                                 For       TNA          Management\n"
    )
    got = [(r["proposal_id"], r["rec"], r["vote"], r["sponsor"]) for r in parse(HEAD + meeting(body))]
    assert got == [
        ("1", "One Year", "One Year", "Management"),
        # 2: a bare "Three" never stands alone in the real 2023 documents (7,267 of 7,267
        # continue with "Years" on the next line), so an unfinished stub is dropped.
        ("3", "Two Years", "One Year", "Management"),
        ("4", "For", "Withhold", "Management"),
        ("5", "None", "Do Not Vote", "Shareholder"),
        ("6", "For", "TNA", "Management"),
    ]


def test_unknown_vocab_and_empty_text_are_dropped_with_reasons():
    body = (
        "1     Good one                                For       For          Management\n"
        "2     Weird vote                              For       Maybe        Management\n"
        "3     Weird rec                               Perhaps   For          Management\n"
        "4     Weird sponsor                           For       For          Regulator\n"
        "5                                             For       For          Management\n"
        "6     Blank vote                              For                    Management\n"
    )
    doc = HEAD + meeting(body)
    rows = parse(doc)
    assert [r["proposal_id"] for r in rows] == ["1"]
    st_ = parse_stats(doc)
    assert st_["proposals_seen"] == 6 and st_["proposals_emitted"] == 1 and st_["proposals_dropped"] == 5
    assert sum(st_["reasons"].values()) >= 5


def test_meeting_drops():
    ok = "1     Elect Someone                           For       For          Management"
    assert parse(HEAD + meeting(ok, date="XXX 99, 2023")) == []
    assert parse(HEAD + meeting(ok, date="FEB 30, 2023")) == []
    no_issuer = meeting(ok).split("\n", 2)[2]
    assert parse(HEAD + "\n" + no_issuer) == []
    assert parse(meeting(ok)) == []  # before any fund heading
    s = parse_stats(HEAD + meeting(ok, date="XXX 99, 2023") + meeting(ok))
    assert s["meetings_seen"] == 2 and s["meetings_dropped"] == 1
    assert s["proposals_seen"] == 2 and s["proposals_emitted"] == 1


def test_two_line_issuer_is_dropped():
    ok = "1     Elect Someone                           For       For          Management"
    doc = HEAD + "FIRST LINE\n" + meeting(ok, issuer="SECOND LINE")
    assert parse(doc) == []


def test_new_heading_resets_fund_and_end_marker_clears_it():
    ok = "1     Elect Someone                           For       For          Management"
    h2 = "=" * 5 + " OTHER FUND " + "=" * 5 + "\n\n"
    rows = parse(HEAD + meeting(ok) + h2 + meeting(ok, issuer="B CORP"))
    assert [r["fund_heading"] for r in rows] == ["VANGUARD GNMA FUND - WELLINGTON", "OTHER FUND"]
    rows = parse(HEAD + meeting(ok) + "========== END NPX REPORT\n\n" + meeting(ok, issuer="B CORP"))
    assert [r["issuer_name"] for r in rows] == ["ACME CORP"]


def test_id_shapes():
    ids = ["1", "1.1", "1a", "1A", "A1", "A", "2.a", "4(a)", "8.1.A", "1a."]
    body = "\n".join(f"{i:<6}Text {n}                              For       For          Management" for n, i in enumerate(ids))
    assert [r["proposal_id"] for r in parse(HEAD + meeting(body))] == ids


@st.composite
def _proposals(draw):
    n = draw(st.integers(1, 6))
    words = st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=9).map(lambda w: "x" + w)
    return [
        (f"{i + 1}", draw(st.lists(words, min_size=1, max_size=14)), draw(st.sampled_from(["For", "Against", "None", "One Year"])),
         draw(st.sampled_from(["For", "Against", "Abstain", "Withhold", "Do Not Vote"])),
         draw(st.sampled_from(["Management", "Shareholder"])))
        for i in range(n)
    ]


def _render(props, width):
    out = []
    for pid, ws, rec, vote, sp in props:
        lines, cur = [], ""
        for w in ws:
            if cur and len(cur) + 1 + len(w) > width:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        lines.append(cur)
        out.append(f"{pid:<6}{lines[0]:<40} {rec:<9} {vote:<12} {sp}")
        out.extend("      " + ln for ln in lines[1:])
    return "\n".join(out)


@settings(max_examples=60, deadline=None)
@given(_proposals(), st.integers(12, 40), st.integers(12, 40))
def test_wrapping_invariance(props, w1, w2):
    a = parse(HEAD + meeting(_render(props, w1)))
    b = parse(HEAD + meeting(_render(props, w2)))
    assert a == b
    assert [(r["proposal_id"], r["proposal_text"], r["rec"], r["vote"], r["sponsor"]) for r in a] == [
        (p[0], " ".join(p[1]), p[2], p[3], p[4]) for p in props
    ]


def test_meeting_type_wrapped_onto_next_line_is_joined():
    doc = HEAD + (
        "BROOKFIELD ASSET MANAGEMENT LTD.\n\nTicker:       BAM            Security ID:  113004105\n"
        "Meeting Date: JUN 09, 2023   Meeting Type: Annual and\nSpecial Meeting\nRecord Date:  APR 20, 2023\n\n"
        "#     Proposal                                Mgt Rec   Vote Cast    Sponsor\n"
        "1     DIRECTOR                                For       For          Management\n"
    )
    rows = parse(doc)
    assert [r["meeting_type"] for r in rows] == ["Annual and Special Meeting"]
    assert rows[0]["record_date"] == "2023-04-20"


def test_no_vote_is_a_valid_rec_and_blank_rec_is_dropped():
    body = (
        "1.    Routine Business                        No Vote   No Vote      Management\n"
        "2     Elect Director Jane Doe                           For          Management\n"
    )
    doc = HEAD + meeting(body)
    assert [(r["proposal_id"], r["rec"], r["vote"]) for r in parse(doc)] == [("1.", "No Vote", "No Vote")]
    assert parse_stats(doc)["reasons"] == {"proposal:unknown_rec": 1}


def test_malformed_id_is_dropped():
    body = "3,    Shareholder Proposal Regarding Report   Against   Against      Shareholder"
    assert parse(HEAD + meeting(body)) == []


WRAPPED_FREQ = (
    "5     Advisory Vote on Say on Pay Frequency   Three     One Year     Management\n"
    "                                              Years\n"
    "6     Report on Lobbying Payments and Policy  Against   Against      Shareholder")


def test_frequency_rec_wrapped_onto_the_next_line():
    # Vanguard 2023 N-PX (0001104659-23-095672): "Three" / "Years" wraps in the Mgt Rec column.
    rows = parse(HEAD + meeting(WRAPPED_FREQ))
    assert [(r["proposal_id"], r["proposal_text"], r["rec"], r["vote"]) for r in rows] == [
        ("5", "Advisory Vote on Say on Pay Frequency", "Three Years", "One Year"),
        ("6", "Report on Lobbying Payments and Policy", "Against", "Against")]


def test_a_bare_number_rec_that_never_completes_is_dropped():
    body = "5     Advisory Vote on Say on Pay Frequency   Three     One Year     Management"
    assert parse(HEAD + meeting(body)) == []


def test_heading_whose_frame_closes_on_the_next_line():
    # State Street 2023 N-PX (0001193125-23-286247).
    head = ("===================== SPDR MSCI USA Gender Diversity ETF (formerly SPDR SSGA\n"
            "Gender Diversity Index ETF) =====================\n\n\n")
    body = "1     Elect Director X                        For       For          Management"
    assert {r["fund_heading"] for r in parse(head + meeting(body))} == {
        "SPDR MSCI USA Gender Diversity ETF (formerly SPDR SSGA Gender Diversity Index ETF)"}
