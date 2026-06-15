"""Tests for 13-F parsing, the outreach queue guardrails, the non-response
ledger, the event-alert join, and the static site build."""

from pathlib import Path

import pytest

from glasshouse import events, ledger, outreach, site
from glasshouse.contradictions import ContradictionCandidate
from glasshouse.ingest.thirteenf import iter_holdings
from glasshouse.ledger import EnforcementAction

FIXTURE_13F = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ORACLE CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>68389X105</cusip>
    <value>7100000000</value>
    <shrsOrPrnAmt><sshPrnamt>41000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>41000000</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>"""


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr(events, "ALERTS_DIR", tmp_path / "alerts")
    return ledger.connect(tmp_path / "test.db")


def _candidate():
    return ContradictionCandidate(
        theme="climate", institution_id="blackrock",
        doc_label="stewardship", doc_version="2026-06-11", doc_sha256="abc123" * 10,
        doc_url="https://x/p.pdf",
        commitment_quote="Our approach to climate risk informs our voting.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025",
        vote_description="SHAREHOLDER PROPOSAL REQUESTING ALTERNATIVE EMISSIONS REPORTING",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=114_697_391.0)


def test_13f_parser(tmp_path):
    p = tmp_path / "infotable.xml"
    p.write_text(FIXTURE_13F)
    rows = list(iter_holdings(p))
    assert len(rows) == 1
    assert rows[0]["cusip"] == "68389X105"
    assert rows[0]["value_usd"] == 7_100_000_000
    assert rows[0]["voting_sole"] == 41_000_000


def test_outreach_draft_contains_only_ledger_facts_and_never_sends(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    oid = outreach.draft_from_candidate(conn, _candidate(), kind="inquiry")
    body = Path(conn.execute("SELECT body_path FROM outreach WHERE id=?", (oid,))
                .fetchone()["body_path"]).read_text()
    # Verbatim facts with citations; commitment quote and N-PX accession present.
    assert "Our approach to climate risk informs our voting." in body
    assert "ACC-1" in body and "114,697,391" in body
    assert "non-response ledger" in body
    # Guardrail: cannot mark sent without explicit human confirmation.
    with pytest.raises(PermissionError):
        outreach.mark_sent(conn, oid, human_confirmed=False)
    assert conn.execute("SELECT status FROM outreach WHERE id=?", (oid,)).fetchone()[0] == "draft"


def test_non_response_ledger_counts_days(conn):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    oid = outreach.draft_from_candidate(conn, _candidate(), kind="inquiry")
    outreach.mark_sent(conn, oid, human_confirmed=True)
    conn.execute("UPDATE outreach SET sent_date=date('now','-31 days') WHERE id=?", (oid,))
    conn.commit()
    rows = outreach.non_response_ledger(conn)
    assert rows[0]["days_without_response"] == 31
    outreach.record_response(conn, oid, "they replied")
    assert outreach.non_response_ledger(conn) == []


def test_event_alert_joins_new_action_to_votes(conn, monkeypatch):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('ACC-1','1100663','blackrock','N-PX','https://s','2026-06-11')")
    conn.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                 "vote_description, how_voted) VALUES "
                 "('ACC-1','ORACLE CORP','68389X105','2024-11-15','Proposal X','AGAINST')")

    fake = [EnforcementAction(agency="SEC", company_name="Oracle Corporation",
                              action_date="2026-06-01", resolution_type="civil_settlement",
                              primary_ref="SEC LR-99999", source_url="https://sec.gov/x")]
    from glasshouse.ingest import doj_fcpa, ofac, ungc, worldbank
    monkeypatch.setattr(ofac, "fetch", lambda: fake)
    for mod in (doj_fcpa, worldbank, ungc):
        monkeypatch.setattr(mod, "fetch", list)

    stats = events.scan(conn)
    assert stats == {"new_actions": 1, "alerts": 1}
    alert = next(events.ALERTS_DIR.glob("*.md")).read_text()
    assert "Oracle Corporation" in alert and "LEADS" in alert and "voted AGAINST" in alert
    # Idempotent: second scan inserts nothing, alerts nothing.
    assert events.scan(conn) == {"new_actions": 0, "alerts": 0}


def test_site_build(conn, tmp_path):
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock', 'BlackRock Inc.')")
    out = tmp_path / "_site"
    stats = site.build(conn, out)
    assert (out / "index.html").exists()
    assert (out / "institutions.html").exists()
    assert (out / "institution-blackrock.html").exists()
    assert (out / "how-to-read.html").exists()
    assert (out / "feed.xml").read_text().startswith("<?xml")
    assert stats["pages"] == 5
    assert (out / "findings.html").exists()
    # The public site must NOT publish a candidates page — unreviewed leads
    # are operator-only (workbench). The publish boundary, on the most public
    # surface.
    assert not (out / "candidates.html").exists()
    # Reader guidance must ship with the data, not live only in the repo.
    how = (out / "how-to-read.html").read_text()
    assert "Guilty plea" in how and "Allegation only" in how
