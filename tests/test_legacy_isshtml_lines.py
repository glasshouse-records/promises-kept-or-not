"""Parser B (regex tokenizer + state machine) for ISS HTML-table N-PX."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from glasshouse.ingest import legacy_isshtml_lines as p

FX = Path(__file__).parent / "fixtures" / "legacy_isshtml"
KEYS = {"fund_heading", "issuer_name", "ticker", "security_id", "meeting_date", "record_date",
        "meeting_type", "rec_label", "card_label", "proposal_id", "proposal_text", "rec",
        "vote", "sponsor"}


def load(name):
    return (FX / name).read_text()


def test_basic_rows_and_no_activity_fund():
    rows = p.parse(load("lines_basic.htm"))
    assert len(rows) == 3
    assert all(set(r) == KEYS and all(isinstance(v, str) for v in r.values()) for r in rows)
    assert rows[0] == {
        "fund_heading": "Beta & Co Fund", "issuer_name": "ALNYLAM PHARMACEUTICALS, INC.",
        "ticker": "ALNY", "security_id": "02043Q107", "meeting_date": "2023-05-18",
        "record_date": "2023-03-24", "meeting_type": "Annual", "rec_label": "Mgt Rec",
        "card_label": "", "proposal_id": "1a", "proposal_text": "Elect Director Michael W. Bonney",
        "rec": "For", "vote": "For", "sponsor": "Management"}
    assert rows[1]["proposal_text"] == "Ratify Ernst & Young LLP" and rows[1]["vote"] == "Against"
    assert rows[2]["rec"] == "One Year"
    assert all(r["fund_heading"] not in ("FORM N-PX", "Alpha Fund") for r in rows)


def test_contest_header_kinds_and_cards():
    rows = p.parse(load("lines_contest.htm"))
    assert [(r["rec_label"], r["card_label"], r["vote"]) for r in rows] == [
        ("Mgt Rec", "Management Universal Proxy (White Proxy Card)", "For"),
        ("Diss Rec", "Dissident Universal Proxy (Gold Proxy Card)", "Did Not Vote")]
    assert rows[0]["meeting_type"] == "Proxy Contest"


def test_non_card_colspan_ignored():
    rows = p.parse(load("lines_noncard.htm"))
    assert len(rows) == 1
    r = rows[0]
    assert r["card_label"] == "" and r["ticker"] == "" and r["security_id"] == ""
    assert r["record_date"] == "" and r["meeting_type"] == "Annual/Special"


def test_bad_meeting_date_drops_meeting_bad_record_date_blank():
    rows = p.parse(load("lines_bad_date.htm"))
    assert [r["issuer_name"] for r in rows] == ["GOOD INC"]
    assert rows[0]["record_date"] == ""
    assert p.parse_stats(load("lines_bad_date.htm"))["reasons"]["bad_meeting_date"] == 1


def test_unknown_vote_sponsor_and_id_dropped():
    txt = load("lines_unknown_vote.htm")
    rows = p.parse(txt)
    assert [r["proposal_id"] for r in rows] == ["2"]
    reasons = p.parse_stats(txt)["reasons"]
    assert reasons["bad_vote"] == 1 and reasons["bad_sponsor"] == 1
    assert reasons["bad_proposal_id"] == 1


def test_br_in_proposal_text_and_written_consent():
    rows = p.parse(load("lines_br_text.htm"))
    assert rows[0]["proposal_text"] == "Line one line two three"
    assert rows[0]["meeting_type"] == "Written Consent" and rows[0]["sponsor"] == "Shareholder"


def test_no_rows_outside_fund_or_before_header():
    txt = load("lines_basic.htm").replace(
        "<p align='center'>Beta &amp; Co Fund</p>", "").replace(
        "<p align='center'>Alpha Fund</p>", "")
    assert p.parse(txt) == []
    assert p.parse_stats(txt)["reasons"]["no_fund"] >= 1
    no_hdr = load("lines_basic.htm").replace("Proposal No</th>", "Oops</th>")
    assert p.parse(no_hdr) == []


_ws = st.sampled_from([" ", "  ", "\n", "\t", "&nbsp;", "  "])


@given(st.lists(_ws, min_size=1, max_size=3), st.lists(_ws, min_size=1, max_size=3),
       st.sampled_from(["&amp;", "&#38;", "&"]))
def test_whitespace_and_entity_variants_do_not_change_output(ws1, ws2, amp):
    def doc(w1, w2, a):
        return load("lines_br_text.htm").replace(
            "Line one<br>line   two&nbsp;three", f"A{''.join(w1)}b{a}c<br>{''.join(w2)}d"
        ).replace("Eta Fund", f"Eta{''.join(w1)}Fund")
    base = p.parse(doc([" "], [" "], "&amp;"))
    assert base and base[0]["proposal_text"] == "A b&c d"
    assert p.parse(doc(ws1, ws2, amp)) == base


def test_amendment1_uppercase_literals_emitted_lowercase_dropped():
    base = load("lines_unknown_vote.htm")
    up = base.replace(">Maybe<", ">WITHHOLD<").replace(
        "<td>Elect Z</td>\n<td>Management</td>\n<td>For</td>\n<td>For</td>",
        "<td>Elect Z</td>\n<td>Management</td>\n<td>FOR</td>\n<td>FOR</td>")
    rows = p.parse(up)
    assert [(r["proposal_id"], r["rec"], r["vote"]) for r in rows] == [
        ("1", "For", "WITHHOLD"), ("2", "FOR", "FOR")]
    for bad in ("for", "against", "1", "Unknown", "Againt", "Took No Action", "Non-Voting"):
        assert [r["proposal_id"] for r in p.parse(base.replace(">Maybe<", f">{bad}<"))] == ["2"]
    assert p.parse(base.replace(">Maybe<", ">AGAINST<"))[0]["vote"] == "AGAINST"
    assert p.parse(base.replace(">Maybe<", ">ABSTAIN<"))[0]["vote"] == "ABSTAIN"
