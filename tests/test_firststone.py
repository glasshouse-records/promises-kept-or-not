"""First Stone — the AI newsroom on top of the Glasshouse registrar.

The newsroom must FEEL like a publishing house (desks, bylines, standards,
an editor) while every charter invariant holds:
  • stories are drafts until a human publisher acts, with a written note;
  • the fact-check desk RECOMPUTES numbers from the ledger, and a
    discrepancy spikes the story;
  • the standards desk enforces the written code: no motive language,
    right-of-reply present, lead-not-finding banner present;
  • the whole pipeline runs without an LLM API key.
"""

import pytest

from glasshouse import firststone, ledger

FILLER = ("General provisions on proxy operations, ballot processing and "
          "record-keeping apply across all funds and accounts. " * 8)
CLIMATE = ("We are committed to robust climate risk oversight and support "
           "emissions reduction at the companies our funds hold.")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(firststone, "NEWSROOM_DIR", tmp_path / "newsroom")
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    old = tmp_path / "old.txt"
    old.write_text(FILLER + " " + CLIMATE)
    new = tmp_path / "new.txt"
    new.write_text(FILLER + " " + CLIMATE)  # commitment still present (live doc)
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
              "sha256, content_path, content_type, size_bytes, wayback_timestamp) VALUES "
              "('blackrock','stewardship','https://x/p.pdf','2023-01-01',?,?,'text/plain',1,"
              "'20230101000000')", ("a" * 64, str(old)))
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
              "sha256, content_path, content_type, size_bytes) VALUES "
              "('blackrock','stewardship','https://x/p.pdf','2026-06-01',?,?,'text/plain',1)",
              ("b" * 64, str(new)))
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC','1','blackrock','N-PX','https://e','2025-01-01')")
    for i, (issuer, how) in enumerate([("EXXON", "AGAINST"), ("CHEVRON", "AGAINST"),
                                       ("SHELL", "AGAINST"), ("APPLE", "FOR")]):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, shares_voted, is_duplicate) VALUES "
                  "('ACC',?,?,'05/21/2024','Report on greenhouse gas emissions reduction "
                  "targets',?,?,0)", (issuer, f"C{i}", how, 1000 * (i + 1)))
    c.commit()
    return c


def test_every_theme_has_a_correspondent():
    """A big paper covers every beat — no theme should file without a named
    correspondent."""
    from glasshouse.contradictions import THEMES
    for th in THEMES:
        c = firststone.correspondent_for(th)
        assert c and c["name"] and c["beat"], f"theme {th} has no correspondent"


def test_byline_is_deterministic_and_beat_specific(conn):
    """Same beat → same correspondent every run; different beats → different
    correspondents. The byline is real furniture, printed in the body."""
    s = firststone.run(conn, min_votes=1, top_n=1)[0]
    assert s["beat"] and s["byline"]
    assert s["byline"] == firststone.correspondent_for("climate")["name"]
    assert (firststone.correspondent_for("climate")["name"]
            != firststone.correspondent_for("board-diversity")["name"])
    assert s["byline"] in s["body"]
    assert s["beat"] in s["body"]


def test_masthead_is_staffed(conn):
    """The masthead names an editor-in-chief and correspondents covering the
    beats — it reads like an organization, not a script."""
    from glasshouse.contradictions import THEMES
    m = firststone.MASTHEAD
    assert m["editor"]["name"] and m["editor"]["role"]
    assert len(m["correspondents"]) >= 3
    covered = {th for c in m["correspondents"] for th in c["themes"]}
    assert set(THEMES) <= covered, f"beats not covered: {set(THEMES) - covered}"
    assert m["ethics"] and m["corrections"]


def test_ai_disclosure_present_on_every_surface(conn):
    """Honesty invariant (never mislead a reader that the staff are human):
    the AI disclosure appears in the masthead AND in every story body."""
    assert "automated" in firststone.DISCLOSURE.lower()
    assert "automated" in (firststone.MASTHEAD["about"] + " "
                           + firststone.DISCLOSURE).lower()
    s = firststone.run(conn, min_votes=1, top_n=1)[0]
    assert "automated" in s["body"].lower()
    # The byline itself flags the correspondent as automated, not a person.
    assert "automated correspondent" in s["body"].lower()


def test_run_produces_stamped_stories(conn):
    stories = firststone.run(conn, min_votes=1, top_n=3)
    assert stories, "the newsroom produced no stories from a clear gap"
    s = stories[0]
    assert s["state"] == "awaiting_publisher"
    desks = [t["desk"] for t in s["trail"]]
    for d in ("assignment", "records", "ledger", "standards", "copy", "editor"):
        assert d in desks, f"desk {d} left no stamp"
    body = s["body"]
    assert "ACC" in body                      # vote citation
    assert "https://x/p.pdf" in body          # policy citation
    assert "DRAFT" in body                    # not published
    assert "Right of reply" in body
    assert "lead" in body.lower()             # lead-not-finding language
    # Persisted for the workbench:
    run = firststone.load_run()
    assert run and run["stories"][0]["slug"] == s["slug"]


def test_factcheck_spikes_on_number_mismatch(conn):
    stories = firststone.run(conn, min_votes=1, top_n=1)
    s = dict(stories[0])
    s["votes_against"] = s["votes_against"] + 5   # tampered number
    verdict = firststone._desk_ledger(conn, s)
    assert verdict["verdict"] == "spike"
    assert "recount" in verdict["note"].lower() or "mismatch" in verdict["note"].lower()


def test_ledger_desk_tolerates_pdf_hyphenation_artifacts(conn, tmp_path):
    """Live bug (first real run, 2026-07-06): PDF extraction renders
    'long-term' as 'long -term' (line-break hyphenation), and the verbatim
    quote check spiked a true quote. Hyphen-adjacent whitespace must be
    normalized on BOTH sides of the comparison."""
    art = tmp_path / "art.txt"
    art.write_text(FILLER + " We are committed to long \n-term climate risk "
                   "oversight at portfolio companies.")
    conn.execute("UPDATE commitments SET content_path=? WHERE sha256=?",
                 (str(art), "b" * 64))
    conn.commit()
    stories = firststone.run(conn, min_votes=1, top_n=1)
    s = dict(stories[0])
    s["quote"] = "We are committed to long-term climate risk oversight at portfolio companies."
    s["doc_label"] = "stewardship"
    verdict = firststone._desk_ledger(conn, s)
    assert verdict["verdict"] == "pass", verdict["note"]


def test_standards_spikes_on_banned_language(conn):
    stories = firststone.run(conn, min_votes=1, top_n=1)
    s = dict(stories[0])
    s["body"] = s["body"] + "\nThis proves their hypocrisy."
    verdict = firststone._desk_standards(s)
    assert verdict["verdict"] == "spike"
    assert "hypocrisy" in verdict["note"]


def test_assignment_desk_requires_strong_say(conn, tmp_path):
    """The newsroom's bar is HIGHER than the registrar's: 'we will consider
    climate oversight' belongs in the matrix (with framing) but must not
    become a story headlined 'commits to climate'. Weak-verb quotes are not
    assigned. (Live case: Vanguard 'will also consider…climate risk'.)"""
    weak = tmp_path / "weak.txt"
    weak.write_text(FILLER + " The fund will also consider the board's overall "
                    "governance of and effective independent oversight of climate risk.")
    conn.execute("UPDATE commitments SET content_path=?, sha256=?",
                 (str(weak), "c" * 64))
    conn.execute("DELETE FROM commitments WHERE sha256 != ?", ("c" * 64,))
    conn.commit()
    stories = firststone.run(conn, min_votes=1, top_n=5)
    assert stories == [], "a weak 'will consider' quote was assigned a story"


def test_publish_is_human_gated_with_note(conn):
    stories = firststone.run(conn, min_votes=1, top_n=1)
    slug = stories[0]["slug"]
    with pytest.raises(PermissionError):
        firststone.publish(slug, note="checked both sources", human_confirmed=False)
    with pytest.raises(ValueError):
        firststone.publish(slug, note="", human_confirmed=True)
    rec = firststone.publish(slug, note="checked both sources", human_confirmed=True)
    assert rec["state"] == "published" and rec["publisher_note"] == "checked both sources"
    pub = firststone.load_published()
    assert [p["slug"] for p in pub] == [slug]
    # A published story's file exists and no longer carries the DRAFT banner.
    assert "DRAFT" not in rec["body"]


def test_llm_polish_cannot_alter_facts(conn, monkeypatch):
    """Reviewer finding: the LLM copy pass runs AFTER the fact-check desk, so
    a hallucinated number would ship stamped 'recount matched'. The copy desk
    must reject any polished text whose numbers or quoted spans aren't in the
    deterministic version."""
    from glasshouse import llm as _llm
    stories = firststone.run(conn, min_votes=1, top_n=1)
    s = dict(stories[0])

    def bad_call(conn, **kw):
        return ("HEADLINE: BlackRock Inc. voted against 87% of climate proposals\n"
                "STANDFIRST: A fabricated 9,999 share figure.")
    monkeypatch.setattr(_llm, "call", bad_call)
    det_head = s["headline"]
    verdict = firststone._desk_copy(conn, s, llm=True)
    assert s["headline"] == det_head, "hallucinated number reached the headline"
    assert "discard" in verdict["note"].lower()


def test_publish_note_with_regex_chars(conn):
    stories = firststone.run(conn, min_votes=1, top_n=1)
    rec = firststone.publish(stories[0]["slug"], note=r"checked \1 both sources",
                             human_confirmed=True)
    assert rec["state"] == "published"


def test_publish_rejects_path_traversal_slug(conn):
    firststone.run(conn, min_votes=1, top_n=1)
    with pytest.raises(ValueError):
        firststone.publish("../evil", note="x", human_confirmed=True)


def test_publish_binds_to_the_body_the_human_read(conn):
    """TOCTOU guard: the workbench sends the sha of the body it displayed; a
    re-run between review and click must refuse to publish under that sha."""
    firststone.run(conn, min_votes=1, top_n=1)
    run = firststone.load_run()
    s = run["stories"][0]
    assert s.get("body_sha256")
    with pytest.raises(ValueError):
        firststone.publish(s["slug"], note="ok", human_confirmed=True,
                           body_sha256="0" * 64)
    rec = firststone.publish(s["slug"], note="ok", human_confirmed=True,
                             body_sha256=s["body_sha256"])
    assert rec["state"] == "published"


def test_rerun_same_day_replaces_the_edition(conn):
    """Stale bodies from an earlier same-day run must not survive a re-run."""
    firststone.run(conn, min_votes=1, top_n=1)
    import glob
    run_dir = firststone._latest_run_dir()
    (run_dir / "stale-story.md").write_text("old body")
    firststone.run(conn, min_votes=1, top_n=1)
    assert not (firststone._latest_run_dir() / "stale-story.md").exists()
    assert glob.glob(str(firststone._latest_run_dir() / "*.md"))


def test_spike_records_the_kill(conn):
    stories = firststone.run(conn, min_votes=1, top_n=1)
    slug = stories[0]["slug"]
    firststone.spike(slug, note="proposal intent ambiguous on re-read")
    run = firststone.load_run()
    s = next(x for x in run["stories"] if x["slug"] == slug)
    assert s["state"] == "spiked"
    assert "ambiguous" in s["trail"][-1]["note"]


def test_site_ships_masthead_but_never_unpublished_stories(conn, tmp_path):
    from glasshouse import site
    firststone.run(conn, min_votes=1, top_n=2)
    out = tmp_path / "_site"
    site.build(conn, out)
    fs = (out / "firststone.html").read_text()
    assert "First Stone" in fs
    assert "human" in fs.lower()              # the transparency line
    assert not list(out.glob("firststone-story-*.html")), "unpublished story leaked to the site"
    # After the human publishes, the story page ships.
    slug = firststone.load_run()["stories"][0]["slug"]
    firststone.publish(slug, note="verified", human_confirmed=True)
    site.build(conn, out)
    assert (out / f"firststone-story-{slug}.html").exists()
