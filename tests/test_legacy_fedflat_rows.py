import pytest

from glasshouse.ingest import legacy_fedflat_rows as m
from glasshouse.ingest.legacy_issueno import KEYS

H15 = m.HEADERS[0]
H14 = m.HEADERS[1]


def tr(cells, tag="td"):
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def row(**kw):
    d = {"Issuer Name": "Acme &amp; Co", "Country": "US", "Meeting Date": "6/5/2022",
         "Meeting Type": "Annual", "Record Date": "4/1/2022", "Ticker": "ACM",
         "Security ID": "45174J509", "Symbol Type": "cusip", "Ballot Issue Number": "1.1",
         "Proposal Text": "Elect&nbsp;A  B", "Proponent": "Mgmt", "Mgmt Reco": "For",
         "Vote Cast": "For", "Fund Name": "Fund X", "Logical Ballot Status": "Voted"}
    d.update(kw)
    return d


def doc(header, rows):
    body = tr(header, "th") + "".join(tr([r[h] for h in header]) for r in rows)
    return f"<table>{body}</table>"


def test_happy_15():
    out = m.parse(doc(H15, [row()]))
    assert len(out) == 1 and tuple(out[0]) == KEYS
    o = out[0]
    assert o["security_id"] == "CUSIP 45174J509" and o["meeting_date"] == "2022-06-05"
    assert o["issuer_name"] == "Acme & Co" and o["proposal_text"] == "Elect A B"
    assert o["meeting_status"] == "Voted" and o["for_against"] == ""
    assert o["fund_heading"] == "Fund X" and o["proposal_id"] == "1.1"


def test_14_column_status_inference():
    out = m.parse(doc(H14, [row(**{"Vote Cast": "TNA"}), row()]))
    assert [o["meeting_status"] for o in out] == ["Take No Action", "Voted"]


def test_header_switch_reads_by_label():
    d = doc(H15, [row()]) + doc(H14, [row(Ticker="ZZZ")])
    out = m.parse(d)
    assert [o["ticker"] for o in out] == ["ACM", "ZZZ"]




@pytest.mark.parametrize("kw,reason", [
    ({"Meeting Date": "2022-06-05"}, "bad_meeting_date"),
    ({"Meeting Date": "2/30/2022"}, "bad_meeting_date"),
    ({"Meeting Date": "06/5/22"}, "bad_meeting_date"),
    ({"Proponent": "Board"}, "bad_proponent"),
    ({"Mgmt Reco": "Yes"}, "bad_mgmt_reco"),
    ({"Vote Cast": "Three Years"}, "bad_vote_cast"),
    ({"Symbol Type": "ISIN"}, "bad_symbol_type"),
    ({"Logical Ballot Status": "voted"}, "bad_status"),
    ({"Issuer Name": ""}, "empty_issuer_name"),
    ({"Fund Name": " "}, "empty_fund_name"),
    ({"Proposal Text": "<b></b>"}, "empty_proposal_text"),
])
def test_field_checks_drop(kw, reason):
    d = doc(H15, [row(**kw), row()])
    assert len(m.parse(d)) == 1
    s = m.parse_stats(d)
    assert s[f"dropped_{reason}"] == 1 and s["rows"] == 1


def test_shifted_row_dropped_not_repaired():
    r = row()
    cells = [r[h] for h in H15]
    cells = cells[1:] + [cells[0]]  # shifted: Country lands in Issuer Name slot etc.
    d = "<table>" + tr(H15, "th") + tr(cells) + "</table>"
    assert m.parse(d) == []
    assert sum(v for k, v in m.parse_stats(d).items() if k.startswith("dropped_")) == 1


def test_rows_before_header_ignored():
    r = row()
    d = tr([r[h] for h in H15]) + doc(H15, [row()])
    assert len(m.parse(d)) == 1
    assert m.parse_stats(d)["ignored_before_header"] == 1


def test_wrong_cell_counts():
    r = row()
    short = tr([r[h] for h in H15][:-1])
    empty = tr([""] * 3)
    d = tr(H15, "th") + short + empty + tr([r[h] for h in H15])
    assert len(m.parse(d)) == 1
    s = m.parse_stats(d)
    assert s["dropped_wrong_cell_count"] == 1 and s["ignored_empty_wrong_cell_count"] == 1


def test_day_first_document_rejected():
    d = doc(H15, [row(), row(**{"Meeting Date": "25/12/2022"})])
    assert m.parse(d) == []
    assert m.parse_stats(d)["document_rejected_day_first_date"] == 1


def test_entities_unescaped_once():
    out = m.parse(doc(H15, [row(**{"Proposal Text": "A &amp;lt; B"})]))
    assert out[0]["proposal_text"] == "A &lt; B"


def test_no_header_no_rows():
    assert m.parse("<p>nothing</p>") == []
