"""Contract F1-F6 (docs/research/legacy-npx.md) for the tokenizer parser."""
from __future__ import annotations

from glasshouse.ingest import legacy_fedflat_cells as m
from glasshouse.ingest.legacy_issueno import KEYS

H15 = ["Issuer Name", "Country", "Meeting Date", "Meeting Type", "Record Date",
       "Ticker", "Security ID", "Symbol Type", "Ballot Issue Number",
       "Proposal Text", "Proponent", "Mgmt Reco", "Vote Cast", "Fund Name",
       "Logical Ballot Status"]
H14 = H15[:14]


def good(**kw):
    d = dict(zip(H15, ["Acme &amp; Co", "US", "5/9/2023", "Annual", "3/1/2023", "ACM",
                       "45174J509", "cusip", "1.1", "Elect  Dir A", "Mgmt", "For",
                       "For", "Fund One", "Voted"]))
    d.update(kw)
    return d


def tr(cells, tag="td"):
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def doc(rows, header=H15):
    body = tr(header, "th") + "".join(tr([r[h] for h in header]) for r in rows)
    return f"<html><table>{body}</table></html>"


def test_good_row_15():
    out = m.parse(doc([good()]))
    assert len(out) == 1
    r = out[0]
    assert set(r) == set(KEYS)
    assert r["issuer_name"] == "Acme & Co"
    assert r["security_id"] == "CUSIP 45174J509"
    assert r["meeting_date"] == "2023-05-09"
    assert r["proposal_text"] == "Elect Dir A"
    assert r["fund_heading"] == "Fund One"
    assert r["meeting_status"] == "Voted"
    assert r["for_against"] == ""
    assert r["proposal_id"] == "1.1"
    assert (r["proponent"], r["rec"], r["vote"]) == ("Mgmt", "For", "For")


def test_cins_and_tna_15():
    out = m.parse(doc([good(**{"Symbol Type": "cins", "Vote Cast": "TNA",
                               "Logical Ballot Status": "Take No Action"})]))
    assert out[0]["security_id"] == "CINS 45174J509"
    assert out[0]["meeting_status"] == "Take No Action"


def test_14_column_status_inference():
    rows = [good(**{"Vote Cast": "TNA"}), good(**{"Vote Cast": "Against"})]
    out = m.parse(doc(rows, H14))
    assert [r["meeting_status"] for r in out] == ["Take No Action", "Voted"]


def test_bad_logical_status_dropped():
    assert m.parse(doc([good(**{"Logical Ballot Status": "Maybe"})])) == []


def test_f3_failures_dropped():
    bad = [
        good(**{"Meeting Date": "2023-05-09"}),
        good(**{"Meeting Date": "2/30/2023"}),
        good(Proponent="Board"),
        good(**{"Vote Cast": "Fund One"}),
        good(**{"Mgmt Reco": "Maybe"}),
        good(**{"Symbol Type": "ISIN"}),
        good(**{"Issuer Name": ""}),
        good(**{"Fund Name": ""}),
        good(**{"Proposal Text": ""}),
    ]
    d = doc(bad + [good()])
    assert len(m.parse(d)) == 1
    assert sum(m.parse_stats(d).values()) > 0


def test_shifted_row_dropped():
    assert m.parse(doc([good(**{"Vote Cast": "Some Fund Name", "Fund Name": "For"})])) == []


def test_day_first_rejects_whole_document():
    rows = [good(), good(**{"Meeting Date": "25/12/2023"})]
    assert m.parse(doc(rows)) == []


def test_rows_before_header_ignored():
    pre = tr([good()[h] for h in H15])
    out = m.parse("<table>" + pre + "</table>" + doc([good()]))
    assert len(out) == 1


def test_wrong_cell_count_dropped_and_empty_ignored():
    short = tr(["a", "b", "c"])
    empty = tr([""] * 3)
    d = "<table>" + tr(H15, "th") + short + empty + tr([good()[h] for h in H15]) + "</table>"
    assert len(m.parse(d)) == 1
    s = m.parse_stats(d)
    assert sum(s.values()) >= 2


def test_header_switch_reads_by_label():
    d = ("<table>" + tr(H15, "th") + tr([good()[h] for h in H15]) + tr(H14, "th")
         + tr([good(**{"Vote Cast": "TNA"})[h] for h in H14]) + "</table>")
    out = m.parse(d)
    assert [r["meeting_status"] for r in out] == ["Voted", "Take No Action"]


def test_unknown_header_is_not_header():
    d = "<table>" + tr(["x", "y"], "th") + tr(["1", "2"]) + "</table>"
    assert m.parse(d) == []
