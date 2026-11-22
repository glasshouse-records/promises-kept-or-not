"""Parser A (html.parser DOM walk) for the ISS HTML-table N-PX layout."""

from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest import legacy_isshtml_dom as m

FIX = Path(__file__).parent / "fixtures" / "legacy_isshtml"
KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date", "record_date",
    "meeting_type", "rec_label", "card_label", "proposal_id", "proposal_text", "rec", "vote",
    "sponsor",
}


def load(name: str) -> str:
    return (FIX / f"dom_{name}.htm").read_text(encoding="utf-8")


def test_basic_rows():
    rows = m.parse(load("basic"))
    assert len(rows) == 2
    assert all(set(r) == KEYS and all(isinstance(v, str) for v in r.values()) for r in rows)
    assert rows[0] == {
        "fund_heading": "Alpha & Beta Fund", "issuer_name": "ALNYLAM PHARMACEUTICALS, INC.",
        "ticker": "ALNY", "security_id": "02043Q107", "meeting_date": "2023-05-18",
        "record_date": "2023-03-24", "meeting_type": "Annual", "rec_label": "Mgt Rec",
        "card_label": "", "proposal_id": "1a", "proposal_text": "Elect Director Michael W. Bonney",
        "rec": "For", "vote": "For", "sponsor": "Management",
    }
    assert rows[1]["sponsor"] == "Shareholder" and rows[1]["rec"] == "Against"


def test_cover_lines_are_not_funds_and_no_activity_gives_zero_rows():
    rows = m.parse(load("no_activity"))
    assert {r["fund_heading"] for r in rows} == {"Loud Fund"}
    assert m.parse_stats(load("no_activity"))["funds"] == 2


def test_contest_both_headers_and_cards():
    rows = m.parse(load("contest"))
    assert [(r["rec_label"], r["card_label"], r["rec"], r["vote"]) for r in rows] == [
        ("Mgt Rec", "Management Universal Proxy (White Proxy Card)", "For", "For"),
        ("Diss Rec", "Dissident Universal Proxy (Gold Proxy Card)", "Against", "Did Not Vote"),
    ]
    assert rows[0]["meeting_type"] == "Proxy Contest"


def test_non_card_colspan_ignored():
    rows = m.parse(load("noncard"))
    assert len(rows) == 1 and rows[0]["card_label"] == "" and rows[0]["record_date"] == ""


def test_bad_meeting_date_drops_meeting_bad_record_date_blank():
    text = load("bad_date")
    rows = m.parse(text)
    assert [r["issuer_name"] for r in rows] == ["GOOD CO"]
    assert rows[0]["record_date"] == ""
    assert m.parse_stats(text)["reasons"]["bad_meeting_date"] >= 1


def test_unknown_values_dropped_and_counted():
    text = load("unknown_vote")
    rows = m.parse(text)
    assert [r["proposal_id"] for r in rows] == ["2"]
    reasons = m.parse_stats(text)["reasons"]
    for k in ("bad_vote", "bad_rec", "bad_sponsor", "bad_proposal_id", "empty_proposal_text"):
        assert reasons[k] == 1, (k, dict(reasons))


def test_empty_ticker_and_type_casing():
    rows = m.parse(load("empty_ticker"))
    assert rows[0]["ticker"] == "" and rows[0]["security_id"] == ""
    assert rows[0]["meeting_type"] == "Annual/Special"


def test_br_in_proposal_text():
    rows = m.parse(load("br_text"))
    assert rows[0]["proposal_text"] == "Elect Director Jane Doe (Nominee)"
    assert rows[0]["meeting_type"] == "Written Consent"


def test_row_outside_fund_or_before_header_not_emitted():
    doc = load("basic").replace("<p align='center'>", "<p>")  # no fund heading at all
    assert m.parse(doc) == []
    nohdr = re.sub(r"<tr>\s*<th width='10%'>Proposal No.*?</tr>", "", load("basic"), flags=re.S)
    assert m.parse(nohdr) == []


_ws = st.sampled_from(["", " ", "  ", "\n", "\t", "&nbsp;", " ", "\n  "])


@settings(max_examples=60, deadline=None)
@given(a=_ws, b=_ws, c=_ws)
def test_whitespace_and_entity_variation_does_not_change_output(a, b, c):
    base = load("basic")
    var = base.replace("<td>For</td>", f"<td>{a}For{b}</td>")
    var = var.replace("<td>Management</td>", f"<td>{c}Management{a}</td>")
    var = var.replace("Elect Director Michael", f"Elect{b or ' '} Director&nbsp;{c}Michael")
    var = var.replace("ALNY", "&#65;LNY")
    assert m.parse(var) == m.parse(base)


def test_amendment1_uppercase_literals_emitted_lowercase_and_typos_dropped():
    base = load("basic")
    up = base.replace("<td>For</td>", "<td>FOR</td>", 1).replace("<td>Against</td>", "<td>WITHHOLD</td>")
    rows = m.parse(up)
    assert [(r["rec"], r["vote"]) for r in rows] == [("FOR", "For"), ("WITHHOLD", "For")]
    for lit in ("AGAINST", "ABSTAIN"):
        assert m.parse(base.replace("<td>Against</td>", f"<td>{lit}</td>"))[1]["rec"] == lit
    for bad in ("for", "against", "3", "Unknown", "Againt", "Took No Action", "Non-Voting"):
        d = base.replace("<td>Against</td>", f"<td>{bad}</td>")
        assert len(m.parse(d)) == 1, bad


def test_ab_variant_style_centred_funds_and_two_tr_meeting_block():
    text = load("ab_variant")
    rows = m.parse(text)
    assert [(r["fund_heading"], r["issuer_name"], r["ticker"], r["security_id"],
             r["meeting_date"], r["record_date"], r["meeting_type"], r["proposal_id"],
             r["vote"]) for r in rows] == [
        ("AB All Market Real Return Portfolio", "3I INFRASTRUCTURE PLC", "3IN", "G8873L178",
         "2022-07-07", "2022-07-05", "Annual", "1", "For"),
        ("AB All Market Real Return Portfolio", "3I INFRASTRUCTURE PLC", "3IN", "G8873L178",
         "2022-07-07", "2022-07-05", "Annual", "2", "Against"),
        ("AB Income Fund", "AOS CORP", "AOS", "831865209", "2023-04-11", "2023-02-14",
         "Annual", "1.1", "For"),
    ]
    assert all(r["rec_label"] == "Mgt Rec" and r["card_label"] == "" for r in rows)
    assert not any("FORM" in r["fund_heading"] for r in rows)
    stats = m.parse_stats(text)
    assert stats["reasons"] == {} and stats["bad_meetings"] == 0 and stats["meetings"] == 2
