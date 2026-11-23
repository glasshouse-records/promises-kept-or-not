"""Tests for the row-oriented legacy 'Issue No.' HTML-table N-PX parser."""

from __future__ import annotations

import random
import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from glasshouse.ingest import legacy_issueno_html_rows as m

FIX = Path(__file__).parent / "fixtures" / "legacy_issueno_html_rows"

KEYS = {
    "fund_heading", "issuer_name", "ticker", "security_id", "meeting_date",
    "meeting_status", "meeting_type", "country", "proposal_id", "proposal_text",
    "proponent", "rec", "vote", "for_against",
}


def _row(cells: list[str], tag: str = "TR") -> str:
    return f"<{tag}>" + "".join(f"<TD>{c}</TD>" for c in cells) + f"</{tag}>\n"


def _doc(*rows: str, fund: str = "Fund A") -> str:
    head = _row(["", "<B>Fund Name :</B>", fund])
    return "<TABLE>" + head + "".join(rows) + "</TABLE>"


def _meeting(issuer="Acme Corp", ticker="ACM", sec="CUSIP 123456789",
             date="06/13/2023", status="Voted", mtype="Annual", country="United States",
             props=(("1", "Elect A", "Mgmt", "For", "For", "For"),)) -> str:
    out = [
        _row(["", issuer]),
        _row(["", "", "Ticker", "Security ID:", "", "Meeting Date", "", "Meeting Status"]),
        _row(["", "", ticker, sec, "", date, "", status]),
        _row(["", "", "Meeting Type", "Country of Trade"]),
        _row(["", "", mtype, country]),
        _row(["", "", "Issue No.", "Description", "", "Proponent", "Mgmt Rec",
              "Vote Cast", "For/Agnst Mgmt"]),
    ]
    for p in props:
        out.append(_row(["", "", p[0], p[1], "", *p[2:]]))
    return "".join(out)


SEP = "<TR height=50><TD></TD><TD colspan=8><HR noShade size=2></TD></TR>\n"


def test_putnam_malformed_rows():
    rows = m.parse((FIX / "putnam_malformed.htm").read_text())
    assert len(rows) == 5 + 1
    assert all(set(r) == KEYS for r in rows)
    first = rows[0]
    assert first == {
        "fund_heading": "Putnam Dynamic Asset Allocation Balanced Fund",
        "issuer_name": "2seventy bio, Inc.", "ticker": "TSVT",
        "security_id": "CUSIP 901384107", "meeting_date": "2023-06-13",
        "meeting_status": "Voted", "meeting_type": "Annual", "country": "United States",
        "proposal_id": "1.1", "proposal_text": "Elect Daniel S. Lynch",
        "proponent": "Mgmt", "rec": "For", "vote": "For", "for_against": "For",
    }
    assert rows[5]["issuer_name"] == "3i Group plc"
    assert rows[5]["country"] == "United Kingdom"


def test_neuberger_div_cells():
    rows = m.parse((FIX / "neuberger_divs.htm").read_text())
    assert len(rows) == 8
    assert rows[0]["fund_heading"] == "Neuberger Berman Dividend Growth Fund"
    assert rows[0]["issuer_name"] == "Agilent Technologies, Inc."
    assert rows[0]["ticker"] == "A"
    assert rows[0]["meeting_date"] == "2023-03-15"
    assert rows[0]["meeting_type"] == "Annual"
    assert rows[0]["country"] == ""  # this layout prints no Country of Trade column
    assert (rows[0]["vote"], rows[0]["for_against"]) == ("Against", "Against")
    assert rows[7]["rec"] == "1 Year" and rows[7]["for_against"] == "For"


def test_blank_ticker():
    rows = m.parse(_doc(SEP, _meeting(ticker="")))
    assert len(rows) == 1 and rows[0]["ticker"] == ""


def test_colspan_positions():
    # label cell colspan=2 pushes later columns right; values follow the same positions
    doc = (
        "<TABLE>" + _row(["Fund Name : F"])
        + "<TR><TD>Issuer X</TD></TR>"
        + "<TR><TD></TD><TD colspan=2>Ticker</TD><TD>Security ID:</TD>"
          "<TD>Meeting Date</TD><TD>Meeting Status</TD></TR>"
        + "<TR><TD></TD><TD colspan=2>XX</TD><TD>CINS Z1</TD><TD>01/31/2023</TD><TD>Voted</TD></TR>"
        + "<TR><TD></TD><TD>Meeting Type</TD></TR>"
        + "<TR><TD></TD><TD>Special</TD></TR>"
        + "<TR><TD></TD><TD>Issue No.</TD><TD colspan=3>Description</TD><TD>Proponent</TD>"
          "<TD>Mgmt Rec</TD><TD>Vote Cast</TD><TD>For/Against Mgmt</TD></TR>"
        + "<TR><TD></TD><TD>1</TD><TD colspan=3>Do it</TD><TD>Mgmt</TD><TD>For</TD>"
          "<TD>For</TD><TD>For</TD></TR>"
        + "</TABLE>"
    )
    rows = m.parse(doc)
    assert len(rows) == 1
    r = rows[0]
    assert (r["ticker"], r["security_id"], r["meeting_date"]) == ("XX", "CINS Z1", "2023-01-31")
    assert (r["proposal_id"], r["proposal_text"], r["proponent"]) == ("1", "Do it", "Mgmt")


def test_stray_value_in_unlabelled_column_drops_row():
    good = ("1", "Elect A", "Mgmt", "For", "For", "For")
    doc = _doc(SEP, _meeting(props=(good,)))
    stray = _row(["", "", "2", "Elect B", "STRAY", "Mgmt", "For", "For", "For"])
    doc = doc.replace("</TABLE>", stray + _row(["", "", "3", "Elect C", "", "Mgmt", "For", "For", "For"]) + "</TABLE>")
    rows = m.parse(doc)
    assert [r["proposal_id"] for r in rows] == ["1", "3"]
    st_ = m.parse_stats(doc)
    assert st_["proposals_dropped"] == 1 and st_["proposals_emitted"] == 2
    assert sum(st_["reasons"].values()) >= 1


def test_no_carry_between_meetings():
    # the second meeting has no ticker/date header: nothing may inherit the first one's values
    broken = _row(["", "Other Corp"]) + _row(["", "", "Issue No.", "Description", "", "Proponent",
                                              "Mgmt Rec", "Vote Cast", "For/Agnst Mgmt"]) \
        + _row(["", "", "9", "Orphan", "", "Mgmt", "For", "For", "For"])
    rows = m.parse(_doc(SEP, _meeting(), SEP, broken))
    assert [r["proposal_id"] for r in rows] == ["1"]


def test_no_carry_of_fund_before_heading():
    rows = m.parse("<TABLE>" + SEP + _meeting() + "</TABLE>")
    assert rows == []
    two = _doc(SEP, _meeting()) + _doc(SEP, _meeting(issuer="Other"), fund="Fund B")
    assert [r["fund_heading"] for r in m.parse(two)] == ["Fund A", "Fund B"]


def test_bad_date_drops_meeting_only():
    doc = _doc(SEP, _meeting(date="02/30/2023"), SEP, _meeting(issuer="Good Co"))
    rows = m.parse(doc)
    assert [r["issuer_name"] for r in rows] == ["Good Co"]
    s = m.parse_stats(doc)
    assert s["meetings_seen"] == 2 and s["meetings_dropped"] == 1


def test_day_first_date_dropped():
    assert m.parse(_doc(SEP, _meeting(date="25/12/2023"))) == []


def test_out_of_vocabulary_proposal_dropped():
    bad = ("1", "Elect A", "Mgmt", "For", "Maybe", "For")
    ok = ("2", "Elect B", "Mgmt", "For", "N/A", "N/A")
    rows = m.parse(_doc(SEP, _meeting(props=(bad, ok))))
    assert [r["proposal_id"] for r in rows] == ["2"]


def test_issuer_row_ends_block_without_separator():
    doc = _doc(_meeting(issuer="One"), _row([""]), _meeting(issuer="Two", ticker="TWO"))
    assert [r["issuer_name"] for r in m.parse(doc)] == ["One", "Two"]


def test_fund_without_meetings_and_registrant_ignored():
    doc = "<TABLE>" + _row(["Registrant : R"]) + _row(["Fund Name : Empty"]) \
        + _row(["Fund Name :", "", "Next Fund"]) + SEP + _meeting() + "</TABLE>"
    assert [r["fund_heading"] for r in m.parse(doc)] == ["Next Fund"]


def test_continuation_row_never_merged():
    cont = _row(["", "", "", "wrapped description text"])
    rows = m.parse(_doc(SEP, _meeting(), cont))
    assert len(rows) == 1


# ---------------------------------------------------------------- property

def _retag(mt: re.Match, rnd: random.Random) -> str:
    slash, name, attrs = mt.groups()
    name = rnd.choice([name.lower(), name.upper()])
    if not slash and name.lower() in ("td", "tr", "th"):
        attrs += rnd.choice(["", " vAlign=top", ' style="color:red"', " class=x"])
    return f"<{slash}{name}{attrs}{rnd.choice(['', ' ', chr(10)])}>"


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000))
def test_markup_noise_does_not_change_output(seed):
    base = (FIX / "putnam_malformed.htm").read_text()
    assert m.parse(_noisy_text(base, seed)) == m.parse(base)
    nb = (FIX / "neuberger_divs.htm").read_text()
    assert m.parse(_noisy_text(nb, seed)) == m.parse(nb)


def _noisy_text(doc: str, seed: int) -> str:
    rnd = random.Random(seed)
    return re.sub(r"<(/?)([A-Za-z]+)([^>]*)>", lambda mt: _retag(mt, rnd), doc)
