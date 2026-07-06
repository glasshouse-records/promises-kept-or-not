"""The walk-back timeline engine: document, as pure fact, how a manager's
policy language changed across archived versions — paired with vote trends.

Precision invariants under test (a false "removed their commitment" claim is
the fatal-data-point class for this feature):
  • an extraction failure (empty/short text) must NEVER read as a removal;
  • a reworded sentence is a REVISION, not a removal + addition;
  • versions are only diffed within the same document lineage (doc_label);
  • every event carries full provenance (both versions' dates + URLs).
"""

import json

import pytest

from glasshouse import ledger, timeline

FILLER = ("General provisions on proxy operations, ballot processing and "
          "record-keeping apply across all funds and accounts. " * 8)

CLIMATE_SENTENCE = ("We are committed to robust climate risk oversight and "
                    "support emissions reduction at the companies our funds hold.")

REWORDED = ("We are committed to sound climate risk oversight and support "
            "reducing emissions at companies our funds hold.")


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    return c


def _add_version(conn, tmp_path, *, inst="blackrock", doc="stewardship", text,
                 sha, wayback="", retrieval="2026-06-01", url="https://x/p.pdf"):
    p = tmp_path / f"{sha[:8]}.txt"
    p.write_text(text)
    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
        "sha256, content_path, content_type, size_bytes, wayback_timestamp) "
        "VALUES (?,?,?,?,?,?,'text/plain',?,?)",
        (inst, doc, url, retrieval, sha, str(p), len(text), wayback))
    conn.commit()


def test_removed_sentence_is_an_event(conn, tmp_path):
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER, sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    events = t["themes"]["climate"]["events"]
    assert len(events) == 1
    assert any("climate risk oversight" in s for s in events[0]["removed"])
    assert not events[0]["added"]


def test_events_carry_provenance(conn, tmp_path):
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000", url="https://x/old.pdf")
    _add_version(conn, tmp_path, text=FILLER, sha="b" * 64, url="https://x/new.pdf")
    ev = timeline.institution_timeline(conn, "blackrock")["themes"]["climate"]["events"][0]
    assert ev["from"]["version"] == "20230101" and ev["to"]["version"] == "20260601"
    assert ev["from"]["url"] and ev["to"]["url"]
    assert ev["doc_label"] == "stewardship"


def test_extraction_failure_is_not_a_removal(conn, tmp_path):
    """The fatal false positive: v2's text extraction failed (empty/short) —
    that must produce NO removal event, not 'they deleted everything'."""
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text="", sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"]["climate"]["events"] == []


def test_reworded_sentence_is_revised_not_removed(conn, tmp_path):
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER + " " + REWORDED, sha="b" * 64)
    ev = timeline.institution_timeline(conn, "blackrock")["themes"]["climate"]["events"]
    assert len(ev) == 1
    assert ev[0]["revised"] and not ev[0]["removed"] and not ev[0]["added"]
    old, new = ev[0]["revised"][0]
    assert "robust" in old and "sound" in new


def test_unchanged_language_no_event(conn, tmp_path):
    """Same sentences across versions (even with different hashes/whitespace)
    must not produce an event."""
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER + "  " + CLIMATE_SENTENCE + " ",
                 sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"]["climate"]["events"] == []


def test_different_doc_labels_never_diffed(conn, tmp_path):
    """A stewardship report and separate voting guidelines are different
    lineages; their difference is not a change event."""
    _add_version(conn, tmp_path, doc="stewardship", text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, doc="voting-guidelines", text=FILLER, sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"]["climate"]["events"] == []


def test_hyphenation_artifact_is_not_an_event(conn, tmp_path):
    """Reviewer finding (2026-07-06): PDF extraction renders 'long-term' as
    'long -term'; that difference must never appear as a public revision or
    removal event."""
    a = FILLER + " We are committed to long-term climate risk oversight at our companies."
    b = FILLER + " We are committed to long -term climate risk oversight at our companies."
    _add_version(conn, tmp_path, text=a, sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=b, sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"]["climate"]["events"] == []


def test_sentence_still_in_text_is_never_reported_removed(conn, tmp_path, monkeypatch):
    """Score-threshold flapping guard: if the sentence extractor misses a
    sentence in v2 but the sentence IS verbatim in v2's text, reporting a
    removal would be a false public claim. The raw text is the arbiter."""
    text = FILLER + " " + CLIMATE_SENTENCE
    _add_version(conn, tmp_path, text=text, sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=text + "  ", sha="b" * 64)
    calls = {"n": 0}
    real = timeline.theme_sentences

    def flappy(t, th):
        calls["n"] += 1
        out = real(t, th)
        return [] if calls["n"] > 1 else out   # extractor "misses" it in v2

    monkeypatch.setattr(timeline, "theme_sentences", flappy)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"].get("climate", {}).get("events", []) == []


def test_reappeared_version_is_not_dropped(conn, tmp_path):
    """Reviewer finding: A(2023, has sentence) → B(2024, without) → A again
    (2026 live, same content hash). Global sha-dedupe dropped the 2026
    restoration, leaving a public record whose last word is a removal the
    manager reversed. All three versions must survive; the re-addition must
    be an event."""
    a_text = FILLER + " " + CLIMATE_SENTENCE
    _add_version(conn, tmp_path, text=a_text, sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER, sha="b" * 64, wayback="20240101000000")
    _add_version(conn, tmp_path, text=a_text, sha="a" * 64, retrieval="2026-06-01")
    assert len(timeline.policy_versions(conn, "blackrock")) == 3
    ev = timeline.institution_timeline(conn, "blackrock")["themes"]["climate"]["events"]
    assert len(ev) == 2
    assert ev[0]["removed"] and ev[0]["to"]["version"] == "20240101"
    assert ev[1]["added"] and ev[1]["to"]["version"] == "20260601"


def test_partial_extraction_pair_is_skipped(conn, tmp_path):
    """A v2 whose text is a small fraction of v1's (dropped pages, stub) must
    not be diffed against v1 even if it clears the absolute length floor."""
    _add_version(conn, tmp_path, text=(FILLER * 4) + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER[:800], sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    assert t["themes"]["climate"]["events"] == []


def test_diff_of_identical_lists_is_empty():
    sents = [CLIMATE_SENTENCE, "We will engage boards on workforce matters."]
    d = timeline.diff_sentences(sents, list(sents))
    assert d["added"] == [] and d["removed"] == [] and d["revised"] == []


def test_cache_roundtrip(conn, tmp_path, monkeypatch):
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER, sha="b" * 64)
    monkeypatch.setattr(timeline, "TIMELINES_PATH", tmp_path / "timelines.json")
    p = timeline.cache_timelines(conn)
    data = json.loads(p.read_text())
    assert "blackrock" in data["institutions"]
    loaded = timeline.load_timelines()
    assert loaded["institutions"]["blackrock"]["themes"]["climate"]["events"]


def test_markdown_is_registrar_voice(conn, tmp_path):
    """The rendered timeline states facts with citations and never uses
    accusatory language."""
    _add_version(conn, tmp_path, text=FILLER + " " + CLIMATE_SENTENCE,
                 sha="a" * 64, wayback="20230101000000")
    _add_version(conn, tmp_path, text=FILLER, sha="b" * 64)
    t = timeline.institution_timeline(conn, "blackrock")
    md = timeline.timeline_markdown(t)
    assert "climate risk oversight" in md          # the quote is shown
    assert "https://x/p.pdf" in md                 # the source is linked
    for banned in ("hypocri", "greenwash", "betray", "broke its promise"):
        assert banned not in md.lower()
