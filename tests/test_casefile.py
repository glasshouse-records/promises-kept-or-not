"""Case files — the forensic synthesis on top of the detector library.

A single detector produces a footprint. A CASE is what a publisher needs: all
the independent footprints that converge on one manager × theme, each cited,
each labelled by how much evidentiary weight it can carry.

The honesty that makes this safe:
  • Footprints are CLASSED, never blended into an invented composite score. An
    active vote choice (strong) is not a passive holding with an index alibi
    (supporting) is not a descriptive-only signal.
  • Manager-level footprints (own rap sheet, internal vote splits) are CONTEXT,
    not corroboration of a theme-specific claim.
  • Ranking is by INDEPENDENT strong corroboration — nothing about motive.
"""

import pytest

from glasshouse import casefile, detectors, ledger
from glasshouse.ledger import EnforcementAction

FILLER = ("General provisions on proxy operations, ballot processing and "
          "record-keeping apply across all funds and accounts. " * 8)


def test_every_detector_declares_an_evidence_class():
    """A detector that can't say how much weight it carries has no business in
    a case file."""
    for d in detectors.registry().values():
        assert d.evidence_class in ("strong", "supporting", "descriptive"), \
            f"{d.id} has no valid evidence_class"


def test_vote_based_detectors_are_strong_holdings_are_supporting():
    reg = detectors.registry()
    assert reg["broken-promise"].evidence_class == "strong"      # active vote choice
    assert reg["fossil-exposure"].evidence_class == "supporting"  # index alibi
    assert reg["soft-commitment"].evidence_class == "descriptive"  # no discrimination proven


@pytest.fixture
def converged(tmp_path):
    """One manager where several independent footprints converge on climate."""
    c = ledger.connect(tmp_path / "cf.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock Inc.')")

    def ver(sha, text, wayback="", retrieval="2026-06-01"):
        p = tmp_path / f"{sha[:6]}.txt"
        p.write_text(text)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                  "sha256, content_path, content_type, size_bytes, wayback_timestamp) VALUES "
                  "('blk','stewardship','https://x/p.pdf',?,?,?,'text/plain',?,?)",
                  (retrieval, sha, str(p), len(text), wayback))
    # Two versions: climate commitment SOFTENS (expect → ask) → commitment-decay.
    ver("a" * 64, FILLER + " We expect every company to disclose how it manages "
        "climate risk in its operations.", wayback="20220101000000")
    ver("b" * 64, FILLER + " We ask every company to disclose how it manages "
        "climate risk in its operations.")
    # Votes AGAINST climate proposals → broken-promise.
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('NPX','1','blk','N-PX','https://s','2025-01-01')")
    for i, how in enumerate(["AGAINST", "AGAINST", "AGAINST", "FOR"]):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                  "('NPX',?,?, '05/21/2024', 'Shareholder proposal on greenhouse gas "
                  "emissions reduction targets', ?, 100, 0)", (f"CO{i}", f"C{i}", how))
    # The manager's OWN enforcement resolution → manager-level CONTEXT (not theme corroboration).
    ledger.insert_enforcement(c, [EnforcementAction(
        agency="SEC", company_name="BlackRock Inc.", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="SEC-1",
        source_url="https://sec/1", description="settlement")])
    c.commit()
    return c


def test_cases_group_theme_footprints_and_count_strong(converged):
    cases = casefile.build_cases(converged, min_rate=0.5, min_votes=1)
    assert cases, "no case built from converging footprints"
    case = cases[0]
    assert case.institution_id == "blk" and case.subject == "climate"
    techniques = {f.technique for f in case.footprints}
    assert "say-vs-do" in techniques          # broken-promise fired
    assert "commitment-decay" in techniques   # the walk-back fired
    assert case.n_strong >= 2                 # both are strong (active choice / documented change)


def test_manager_level_footprints_are_context_not_theme_corroboration(converged):
    case = casefile.build_cases(converged, min_rate=0.5, min_votes=1)[0]
    ctx = {f.technique for f in case.manager_context}
    assert "own-enforcement" in ctx           # the rap sheet is context…
    # …and it must NOT be counted as corroboration of the climate claim.
    assert "own-enforcement" not in {f.technique for f in case.footprints}


def test_cases_ranked_by_independent_strong_corroboration(converged):
    cases = casefile.build_cases(converged, min_rate=0.5, min_votes=1)
    strengths = [(c.n_strong, len(c.footprints)) for c in cases]
    assert strengths == sorted(strengths, reverse=True)


def test_case_markdown_is_cited_and_never_asserts_motive(converged):
    case = casefile.build_cases(converged, min_rate=0.5, min_votes=1)[0]
    md = casefile.case_markdown(case)
    assert "BlackRock" in md and "climate" in md
    assert "say-vs-do" in md or "Broken promise" in md
    # Evidentiary classes are shown, so a reader can weigh the footprints.
    assert "strong" in md.lower()
    for banned in ("hypocri", "lying", "greenwash", "intent", "motive of"):
        assert banned not in md.lower()


def test_no_case_without_at_least_one_strong_footprint(tmp_path):
    """A case built only from descriptive/supporting signals is not a case —
    it must not be surfaced as one."""
    c = ledger.connect(tmp_path / "weak.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('w','Weak AM')")
    p = tmp_path / "p.txt"
    # Hedged commitment only; no votes, no decay → soft-commitment (descriptive) at most.
    p.write_text(FILLER + " We may consider climate issues and generally encourage "
                 "companies, where appropriate, to disclose.")
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
              "sha256, content_path, content_type, size_bytes) VALUES "
              "('w','stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',10)",
              ("c" * 64, str(p)))
    c.commit()
    assert casefile.build_cases(c, min_rate=0.5, min_votes=1) == []
