"""Legacy (pre-2024) N-PX HTML parser.

Machine-readable N-PX only exists for periods ending ~mid-2024; everything
earlier is legacy HTML. To reach real multi-year vote depth we parse the
standard ISS/Broadridge legacy table format. PRECISION IS CARDINAL: the parser
must extract only well-formed votes (issuer + cusip + a real vote), never guess,
and never emit header rows as votes.
"""

from pathlib import Path

from glasshouse.ingest.npx_legacy import iter_legacy_vote_rows

FIXTURE = (Path(__file__).parent / "fixtures" / "legacy_npx_sample.htm").read_bytes()


def _rows():
    return list(iter_legacy_vote_rows(FIXTURE))


def test_extracts_both_securities():
    rows = _rows()
    issuers = {r.issuer_name for r in rows}
    assert "3I GROUP PLC" in issuers
    assert "ADYEN NV" in issuers


def test_first_vote_fields_are_correct():
    r = _rows()[0]
    assert r.issuer_name == "3I GROUP PLC"
    assert r.cusip == "G88473148"
    assert r.meeting_date == "06/29/2023"           # normalized from "JUN 29, 2023"
    assert r.vote_description.startswith("Accept Financial Statements")
    assert r.category_type == "Management"          # "Proposed By"
    assert r.management_recommendation == "For"
    assert r.how_voted == "For"


def test_no_header_or_junk_rows_emitted():
    rows = _rows()
    for r in rows:
        # never emit the column header as a vote
        assert r.vote_description not in ("Proposal", "Proposal No", "")
        assert r.how_voted not in ("Vote Cast", "")
        # every emitted vote must be anchored to a security and a choice
        assert r.issuer_name and r.cusip and r.how_voted


def test_cusip_uppercased_and_clean():
    for r in _rows():
        assert r.cusip == r.cusip.upper().strip()
        assert " " not in r.cusip


def test_undated_security_emits_nothing():
    """If a security's meeting date can't be parsed, its votes are dropped
    (precision): an undated vote can't be time-aligned to a policy version."""
    html = (b"<html><body><table>"
            b"<tr><td colspan='5'>SOME ISSUER INC <br/>MEETING DATE:&nbsp;&nbsp;</td></tr>"
            b"<tr><td colspan='5'>TICKER: X SECURITY ID:&nbsp;&nbsp;123456789</td></tr>"
            b"<tr><th>Proposal No</th><th>Proposal</th><th>Proposed By</th>"
            b"<th>Management Recommendation</th><th>Vote Cast</th></tr>"
            b"<tr><td>1</td><td>Elect Director</td><td>Management</td><td>For</td><td>For</td></tr>"
            b"</table></body></html>")
    assert list(iter_legacy_vote_rows(html)) == []


def test_each_security_has_multiple_proposals():
    rows = _rows()
    by_issuer = {}
    for r in rows:
        by_issuer.setdefault(r.issuer_name, 0)
        by_issuer[r.issuer_name] += 1
    # the ISS format lists several proposals per meeting
    assert all(n >= 2 for n in by_issuer.values())
