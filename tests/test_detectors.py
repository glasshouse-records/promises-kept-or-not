"""The detector framework: every accountability pattern is a pluggable
'tool/feature' with the same shape — one sharp question over the primary
record, out come cited LEADS, plus a self-describing scorecard.

Invariants under test:
  • Every registered detector declares an id, a technique (taxonomy), and the
    plain-English question it asks.
  • The flagship 'broken-promise' detector (the preserved say-vs-do engine)
    produces cited leads: the commitment quote AND at least one vote with an
    accession/source.
  • Leads are FOOTPRINTS, not verdicts — no motive/intent language leaks into
    a headline.
  • Detectors run over the shared ledger and write NOTHING to it (leads only).
"""

import pytest

from glasshouse import detectors, ledger


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    pol = tmp_path / "blk.txt"
    pol.write_text("Our stewardship approach. We are committed to robust climate "
                   "risk oversight and we will support emissions reduction at the "
                   "companies our funds hold.")
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
              "sha256, content_path, content_type, size_bytes) VALUES "
              "('blackrock','stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
              ("a" * 64, str(pol)))
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://sec.gov/x','2025-01-01')")

    def vote(issuer, desc, how, shares):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                  "('ACC',?,?, '05/21/2024', ?, ?, ?, 0)", (issuer, "C" + issuer[:6], desc, how, shares))
    vote("EXXON", "Shareholder proposal on greenhouse gas emissions reduction targets", "AGAINST", 5000)
    vote("CHEVRON", "Report on climate transition plan and emissions", "AGAINST", 3000)
    vote("SHELL", "Adopt medium-term GHG emissions reduction targets", "AGAINST", 2000)
    vote("APPLE", "Proposal to report on climate risk", "FOR", 1000)
    c.commit()
    return c


def test_registry_is_populated_and_self_describing():
    reg = detectors.registry()
    assert reg, "no detectors registered"
    for d in reg.values():
        assert d.id and d.name and d.technique and d.question
        assert d.technique in detectors.TECHNIQUES, f"{d.id} cites unknown technique {d.technique}"


def test_broken_promise_detector_is_registered():
    """The say-vs-do 'intentions' engine is preserved as the flagship
    detector, not retired."""
    reg = detectors.registry()
    assert "broken-promise" in reg
    d = reg["broken-promise"]
    assert d.technique == "say-vs-do"
    assert "commit" in d.question.lower() or "promise" in d.question.lower()


def test_broken_promise_produces_cited_leads(conn):
    leads = detectors.registry()["broken-promise"].run(conn, min_rate=0.5, min_votes=1)
    assert leads, "flagship detector produced no leads on a clear say-vs-do gap"
    lead = next(x for x in leads if x.institution_id == "blackrock")
    assert lead.detector_id == "broken-promise"
    assert lead.technique == "say-vs-do"
    assert "climate" in lead.subject
    # Cited: the commitment quote AND at least one vote with its accession/source.
    assert "climate risk oversight" in lead.evidence["commitment_quote"]
    votes = lead.evidence["votes"]
    assert votes and votes[0]["accession"] == "ACC"
    assert votes[0].get("source_url")
    assert 0 < lead.strength <= 1


def test_leads_are_footprints_not_verdicts(conn):
    for d in detectors.registry().values():
        for lead in d.run(conn, min_rate=0.5, min_votes=1):
            low = (lead.headline + " " + lead.subject).lower()
            for banned in ("hypocri", "lying", "lied", "malicious", "intent to", "greenwash"):
                assert banned not in low, f"{d.id} leaked motive language: {lead.headline!r}"


def test_detector_scorecard_is_self_describing(conn):
    """Each detector reports how it was validated — the tool held accountable
    for its own method."""
    d = detectors.registry()["broken-promise"]
    sc = d.scorecard(conn, min_rate=0.5, min_votes=1)
    assert sc["detector_id"] == "broken-promise"
    assert "leads" in sc and sc["leads"] >= 1
    assert sc["validation"]            # a non-empty description of how it's validated


def test_running_a_detector_does_not_write_the_ledger(conn):
    before = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    detectors.run_all(conn, min_rate=0.5, min_votes=1)
    after = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    assert before == after


def test_run_all_returns_leads_grouped_by_detector(conn):
    out = detectors.run_all(conn, min_rate=0.5, min_votes=1)
    assert "broken-promise" in out
    assert all(lead.detector_id == "broken-promise" for lead in out["broken-promise"])


# ── Detector #2: commitment-strength (soft-commitment) ──────────────────────

def test_commitment_strength_scores_hard_vs_soft():
    d = detectors.registry()["soft-commitment"]
    hard, _, _ = d.strength("We are committed to climate oversight and will vote "
                            "for emissions reduction; we require disclosure.")
    soft, _, _ = d.strength("We may consider climate issues and generally encourage "
                            "companies, where appropriate, to disclose.")
    assert hard > 0.75 and soft < 0.35 and hard > soft


@pytest.fixture
def two_managers(tmp_path):
    c = ledger.connect(tmp_path / "w.db")

    def mgr(mid, name, quote, hows):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (mid, name))
        p = tmp_path / f"{mid}.txt"
        p.write_text("Our stewardship approach. " + quote)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes) VALUES "
                  "(?,'stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
                  (mid, mid * 32, str(p)))
        acc = f"ACC-{mid}"
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                  "retrieval_date) VALUES (?,?,?,'N-PX','https://sec.gov/x','2025-01-01')",
                  (acc, mid, mid))
        for i, how in enumerate(hows):
            c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                      "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                      "(?,?,?, '05/21/2024', 'Shareholder proposal on greenhouse gas "
                      "emissions reduction targets', ?, 100, 0)",
                      (acc, f"CO{i}", f"C{mid}{i}", how))
    # HARD commitment, keeps it (votes mostly FOR):
    mgr("h", "Hard AM", "We are committed to climate oversight and we will vote for "
        "emissions reduction and require disclosure.", ["FOR", "FOR", "FOR", "AGAINST"])
    # SOFT commitment, breaks it (votes mostly AGAINST):
    mgr("s", "Soft AM", "We may consider climate issues and generally encourage "
        "companies, where appropriate, to disclose.", ["AGAINST", "AGAINST", "AGAINST", "FOR"])
    c.commit()
    return c


def test_soft_commitment_flags_the_hedged_manager(two_managers):
    leads = detectors.registry()["soft-commitment"].run(two_managers, max_strength=0.5)
    flagged = {ld.institution_id for ld in leads}
    assert "s" in flagged and "h" not in flagged
    lead = next(ld for ld in leads if ld.institution_id == "s")
    assert lead.technique == "soft-commitment"
    assert "encourage" in lead.evidence["commitment_quote"]
    assert lead.evidence["strength"] < 0.5


def test_broken_promise_reports_selectivity(two_managers):
    """Selectivity = of all the units it could flag, what fraction it does. A
    detector that flags everyone isn't finding a rare few; one that flags a
    subset is. This is the 'stayed quiet on M% of the universe' metric."""
    d = detectors.registry()["broken-promise"]
    sc = d.scorecard(two_managers, min_rate=0.6, min_votes=1)
    # two committed climate cells; one breaks it (flagged), one keeps it (not).
    assert sc["universe"] == 2 and sc["flagged"] == 1
    assert sc["selectivity"] == 0.5
    assert sc["selectivity_note"]


def test_soft_commitment_scorecard_has_selectivity(two_managers):
    sc = detectors.registry()["soft-commitment"].scorecard(two_managers)
    assert "universe" in sc and "selectivity" in sc
    assert sc["flagged"] == sc["leads"]


def test_soft_commitment_scorecard_self_validates(two_managers):
    """The scorecard reports whether softer commitments actually predict worse
    follow-through in OUR OWN data — the detector proving itself, no external
    labels."""
    sc = detectors.registry()["soft-commitment"].scorecard(two_managers)
    assert "soft_against_rate" in sc and "hard_against_rate" in sc
    # In this fixture soft breaks it, hard keeps it → soft rate must be higher.
    assert sc["soft_against_rate"] > sc["hard_against_rate"]
    assert "n_soft" in sc and "n_hard" in sc
    # The scorecard must be HONEST about whether it discriminates, with a note.
    assert "discriminates" in sc and isinstance(sc["discriminates"], bool)
    assert sc["note"]
