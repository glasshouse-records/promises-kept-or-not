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
from glasshouse.ledger import EnforcementAction


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


# ── Detector #3: own enforcement record (claims-vs-enforcement, own side) ────

@pytest.fixture
def own_conn(tmp_path):
    c = ledger.connect(tmp_path / "o.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('goldman_sachs','Goldman Sachs Group Inc.')")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('clean','Clean AM')")
    for mid in ("goldman_sachs", "clean"):
        p = tmp_path / f"{mid}.txt"
        p.write_text("We are committed to business ethics and anti-corruption.")
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes) VALUES "
                  "(?, 'stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
                  (mid, mid * 20, str(p)))
    ledger.insert_enforcement(c, [
        EnforcementAction(agency="SEC", company_name="Goldman Sachs Group Inc.",
                          action_date="2020-10-22", resolution_type="civil_settlement",
                          primary_ref="SEC-1MDB", source_url="https://sec/1",
                          description="1MDB FCPA $2.9B settlement"),
        # An allegation (docket) — NEVER a finding, must be excluded:
        EnforcementAction(agency="Federal docket", company_name="Goldman Sachs Group Inc.",
                          action_date="2026-01-01", resolution_type="allegation",
                          primary_ref="Docket-1", source_url="https://c/1",
                          description="pending", is_allegation=True),
        # OFAC SDN name-collision (the Aldar class) — must be excluded:
        EnforcementAction(agency="OFAC (SDN)", company_name="Goldman Sachs Group Inc.",
                          action_date="2020-01-01", resolution_type="sanction_designation",
                          primary_ref="SDN-1", source_url="https://o/1", description="collision"),
    ])
    c.commit()
    return c


def test_own_record_detector_is_registered():
    reg = detectors.registry()
    assert "own-record" in reg
    assert reg["own-record"].technique == "own-enforcement"


def test_own_record_surfaces_real_resolutions_only(own_conn):
    leads = detectors.registry()["own-record"].run(own_conn)
    ids = {ld.institution_id for ld in leads}
    assert "goldman_sachs" in ids       # has a real resolution
    assert "clean" not in ids           # commitment but no enforcement
    lead = next(ld for ld in leads if ld.institution_id == "goldman_sachs")
    types = [r["resolution_type"] for r in lead.evidence["resolutions"]]
    assert "civil_settlement" in types            # the real resolution is surfaced
    assert "allegation" not in types              # allegations excluded (never a finding)
    assert "sanction_designation" not in types    # OFAC collision excluded (Aldar class)
    assert lead.evidence["quarantined"] is True   # name-join → lead, not finding
    # resolution_type preserved verbatim (legal distinctions never collapsed).
    assert lead.evidence["resolutions"][0]["primary_ref"] == "SEC-1MDB"


def test_own_record_is_footprints_not_verdict(own_conn):
    lead = detectors.registry()["own-record"].run(own_conn)[0]
    low = (lead.headline + " " + str(lead.evidence)).lower()
    for banned in ("hypocri", "lying", "criminal mastermind", "corrupt "):
        assert banned not in low


def test_own_record_scorecard_reports_selectivity(own_conn):
    sc = detectors.registry()["own-record"].scorecard(own_conn)
    assert sc["universe"] == 2 and sc["flagged"] == 1   # 2 managers market stewardship; 1 has a record
    assert sc["selectivity"] == 0.5


# ── Detector #4: commitment-decay (walk-back quantified) ────────────────────

_DFILLER = ("General provisions on proxy operations, ballot processing and "
            "record-keeping apply across all funds and accounts. " * 8)


@pytest.fixture
def decayed(tmp_path):
    c = ledger.connect(tmp_path / "d.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")

    def ver(sha, text, wayback="", retrieval="2026-06-01"):
        p = tmp_path / f"{sha[:6]}.txt"
        p.write_text(text)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes, wayback_timestamp) VALUES "
                  "('blackrock','stewardship','https://x/p.pdf',?,?,?,'text/plain',?,?)",
                  (retrieval, sha, str(p), len(text), wayback))
    # v1 (2022): HARD climate commitment ("we expect every company to …").
    ver("a" * 64, _DFILLER + " We expect every company to disclose how it manages "
        "climate risk in its operations.", wayback="20220101000000")
    # v2 (2026): SOFTER — expect → ask (the real BlackRock walk-back shape).
    ver("b" * 64, _DFILLER + " We ask every company to disclose how it manages "
        "climate risk in its operations.")
    c.commit()
    return c


def test_commitment_decay_is_registered():
    d = detectors.registry().get("commitment-decay")
    assert d and d.technique == "commitment-decay"


def test_commitment_decay_flags_softening(decayed):
    leads = detectors.registry()["commitment-decay"].run(decayed)
    assert leads, "did not flag a real expect→ask softening"
    ld = leads[0]
    assert ld.institution_id == "blackrock" and "climate" in ld.subject
    soft = ld.evidence["softenings"]
    assert any("expect" in s["from"] and "ask" in s["to"] for s in soft)
    assert soft[0]["from_url"] and soft[0]["to_url"]   # both versions cited


def test_commitment_decay_flags_shrinkage(tmp_path):
    """The main real-world signal: the COUNT of binding commitment sentences
    for a theme falls between versions (BlackRock: many → few)."""
    c = ledger.connect(tmp_path / "sh.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock Inc.')")

    def ver(sha, text, wayback="", retrieval="2026-06-01"):
        p = tmp_path / f"{sha[:6]}.txt"
        p.write_text(text)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes, wayback_timestamp) VALUES "
                  "('blk','stewardship','https://x/p.pdf',?,?,?,'text/plain',?,?)",
                  (retrieval, sha, str(p), len(text), wayback))
    # v1: TWO binding climate commitments; v2: only ONE remains.
    ver("a" * 64, _DFILLER + " We expect every company to disclose its climate risk. "
        "We will vote against directors who fail on climate risk oversight.",
        wayback="20200101000000")
    ver("b" * 64, _DFILLER + " We expect every company to disclose its climate risk.")
    c.commit()
    ld = detectors.registry()["commitment-decay"].run(c)[0]
    assert ld.evidence["shrink"] and ld.evidence["shrink"]["from_n"] > ld.evidence["shrink"]["to_n"]


def test_commitment_decay_is_footprints_not_verdict(decayed):
    ld = detectors.registry()["commitment-decay"].run(decayed)[0]
    low = (ld.headline + " " + str(ld.evidence)).lower()
    for banned in ("hypocri", "lying", "backtrack", "betray", "broke its promise"):
        assert banned not in low


def test_commitment_decay_ignores_strengthening(tmp_path):
    """A commitment that gets STRONGER (ask→expect) is not a decay lead."""
    c = ledger.connect(tmp_path / "s.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X AM')")

    def ver(sha, text, wayback="", retrieval="2026-06-01"):
        p = tmp_path / f"{sha[:6]}.txt"
        p.write_text(text)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes, wayback_timestamp) VALUES "
                  "('x','stewardship','https://x/p.pdf',?,?,?,'text/plain',?,?)",
                  (retrieval, sha, str(p), len(text), wayback))
    ver("a" * 64, _DFILLER + " We ask every company to disclose climate risk in "
        "its operations.", wayback="20220101000000")
    ver("b" * 64, _DFILLER + " We expect every company to disclose climate risk in "
        "its operations.")
    c.commit()
    assert detectors.registry()["commitment-decay"].run(c) == []
