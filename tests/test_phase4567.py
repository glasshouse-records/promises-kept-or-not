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
    from glasshouse import firststone
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr(events, "ALERTS_DIR", tmp_path / "alerts")
    # First Stone writes stories to disk; keep tests OUT of the real data dir
    # (a test that calls firststone.run must never clobber the live edition).
    monkeypatch.setattr(firststone, "NEWSROOM_DIR", tmp_path / "newsroom")
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
    # >= 31 not == 31: 'date(now,-31 days)' is UTC while non_response_ledger
    # uses the local date, so the diff is 31 or 32 depending on time of day.
    assert rows[0]["days_without_response"] >= 31
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
    assert (out / "record.html").exists()
    assert (out / "firststone.html").exists()
    assert (out / "firststone-masthead.html").exists()
    assert (out / "detectors.html").exists()
    assert (out / "promise.html").exists()      # the systemic finding leads
    assert (out / "feed.xml").read_text().startswith("<?xml")
    assert stats["pages"] == 10
    assert (out / "findings.html").exists()
    # The public site must NOT publish a candidates page — unreviewed leads
    # are operator-only (workbench). The publish boundary, on the most public
    # surface.
    assert not (out / "candidates.html").exists()
    # Reader guidance must ship with the data, not live only in the repo.
    how = (out / "how-to-read.html").read_text()
    assert "Guilty plea" in how and "Allegation only" in how


_POLICY_FILLER = ("General provisions on proxy operations, ballot processing "
                  "and record-keeping apply across all funds and accounts. " * 10)
_POLICY_CLIMATE = ("We are committed to robust climate risk oversight and support "
                   "emissions reduction at the companies our funds hold.")


def _policy_version(conn, tmp_path, sha, text, wayback="", retrieval="2026-06-01"):
    p = tmp_path / f"{sha[:6]}.txt"
    p.write_text(text)
    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
        "sha256, content_path, content_type, size_bytes, wayback_timestamp) "
        "VALUES ('blackrock','stewardship','https://x/p.pdf',?,?,?,'text/plain',1,?)",
        (retrieval, sha, str(p), wayback))


def test_site_record_page_is_registrar_voice(conn, tmp_path):
    """The public matrix page: rates from the ledger, leads-not-findings
    framing, and never campaign language."""
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    _policy_version(conn, tmp_path, "a" * 64, _POLICY_FILLER + " " + _POLICY_CLIMATE,
                    wayback="20230101000000")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://e','2025-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                 "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                 "('ACC','EXXON','C1','05/21/2024',"
                 "'Report on greenhouse gas emissions reduction targets','AGAINST',5000,0)")
    conn.commit()
    out = tmp_path / "_site"
    site.build(conn, out)
    rec = (out / "record.html").read_text()
    assert "BlackRock Inc." in rec and "100%" in rec
    assert "lead" in rec.lower()                       # the framing ships with the page
    for banned in ("hypocri", "greenwash", "betray"):
        assert banned not in rec.lower()


def test_site_institution_page_has_language_changelog(conn, tmp_path):
    """When archived versions differ, the institution page documents the
    change in registrar voice — dated, linked, uncharacterized."""
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    _policy_version(conn, tmp_path, "a" * 64, _POLICY_FILLER + " " + _POLICY_CLIMATE,
                    wayback="20230101000000")
    _policy_version(conn, tmp_path, "b" * 64, _POLICY_FILLER)
    conn.commit()
    out = tmp_path / "_site"
    site.build(conn, out)
    page = (out / "institution-blackrock.html").read_text()
    assert "not present in" in page
    assert "2023-01-01" in page and "2026-06-01" in page
    assert "climate risk oversight" in page            # the quote itself
    # The old overclaim is retired; changes are documented, not characterized.
    assert "findings in themselves" not in page


def test_site_detectors_page_shows_catalogue_and_validation(conn, tmp_path):
    """The public 'what we check' page lists every detector and — the novel
    part — how each is validated (the tool held accountable for its method)."""
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    conn.commit()
    out = tmp_path / "_site"
    site.build(conn, out)
    page = (out / "detectors.html").read_text()
    assert "Broken promise" in page or "broken-promise" in page
    assert "Soft commitment" in page or "soft-commitment" in page
    assert "validat" in page.lower()          # how each check is validated ships publicly
    # Registrar voice — the catalogue documents method, never accuses.
    for banned in ("hypocri", "liar", "lying"):
        assert banned not in page.lower()


def test_site_firststone_masthead_is_staffed(conn, tmp_path):
    """The public First Stone page reads like a staffed newsroom: editor-in-
    chief, correspondents with beats, an ethics statement and corrections
    policy — and the standing AI disclosure."""
    from glasshouse import firststone
    conn.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    _policy_version(conn, tmp_path, "a" * 64, _POLICY_FILLER + " " + _POLICY_CLIMATE,
                    wayback="20230101000000")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://e','2025-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                 "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                 "('ACC','EXXON','C1','05/21/2024',"
                 "'Report on greenhouse gas emissions reduction targets','AGAINST',5000,0)")
    conn.commit()
    firststone.run(conn, min_votes=1, top_n=2)
    out = tmp_path / "_site"
    site.build(conn, out)
    # The front page carries the standing disclosure and links to the masthead.
    front = (out / "firststone.html").read_text()
    assert "automated" in front.lower()
    # The masthead page is the staffed org chart.
    mast = (out / "firststone-masthead.html").read_text()
    assert firststone.EDITOR["name"] in mast
    # beats contain "&" → html-escaped; match the leading word to stay robust.
    assert any(c["name"] in mast and c["beat"].split()[0] in mast
               for c in firststone.CORRESPONDENTS)
    assert "thics" in mast                                # Ethics section
    assert "orrection" in mast                            # Corrections policy
    assert "automated" in mast.lower()                    # the honesty line ships
