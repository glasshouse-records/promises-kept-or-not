"""The systemic finding — does a published commitment predict anything?

This is the project's central claim, and it must be built to survive the
obvious attack. A raw cross-manager comparison (committed cells vs
uncommitted cells) is CONFOUNDED: the committed group is dominated by
managers who vote against nearly everything, so it manufactures a gap that
is really a composition artifact (found live, 2026-07-16 — it made
"committed managers vote against MORE" look true when it is not).

The defensible design is PAIRED: compare each manager against ITSELF —
its against-rate on themes it publicly commits to vs. its own rate on
themes it never promised anything about. That controls for house voting
philosophy, which is the confound.

The module must also be SYMMETRIC: a registrar that can only ever report
fault is a prosecutor. When a manager votes BETTER on the themes it
committed to, that must be reported as plainly as the reverse.
"""

import pytest

from glasshouse import systemic


def _cell(committed, for_, against):
    return {"committed": committed, "for": for_, "against": against,
            "quote": "q" if committed else None, "n": for_ + against,
            "rate": (against / (for_ + against)) if (for_ + against) else 0.0,
            "doc_label": "p", "doc_version": "v", "doc_url": "u", "examples": []}


def _matrix(insts):
    return {"generated": "2026-07-16", "themes": ["climate", "nature", "labor-rights"],
            "institutions": insts}


@pytest.fixture
def matrix():
    return _matrix([
        # votes the SAME on promised and unpromised themes → promise is inert
        {"id": "inert", "name": "Inert AM", "cells": {
            "climate": _cell(True, 20, 80), "nature": _cell(False, 20, 80)}},
        # votes BETTER where it promised → must be reported as better (exculpatory)
        {"id": "better", "name": "Better AM", "cells": {
            "climate": _cell(True, 60, 40), "nature": _cell(False, 10, 90)}},
        # votes WORSE where it promised
        {"id": "worse", "name": "Worse AM", "cells": {
            "climate": _cell(True, 5, 95), "nature": _cell(False, 50, 50)}},
        # too few votes on one side → excluded, not guessed at
        {"id": "tiny", "name": "Tiny AM", "cells": {
            "climate": _cell(True, 1, 2), "nature": _cell(False, 40, 60)}},
        # no uncommitted themes at all → no baseline → excluded
        {"id": "nobase", "name": "NoBase AM", "cells": {
            "climate": _cell(True, 30, 70)}},
    ])


def test_paired_controls_for_house_philosophy(matrix):
    pairs = {p.institution_id: p for p in systemic.paired_comparison(matrix, min_votes=20)}
    assert set(pairs) == {"inert", "better", "worse"}      # tiny + nobase excluded
    assert pairs["inert"].delta == pytest.approx(0.0, abs=1e-9)
    assert pairs["better"].delta < 0            # votes against LESS where it promised
    assert pairs["worse"].delta > 0


def test_direction_is_reported_symmetrically(matrix):
    pairs = {p.institution_id: p for p in systemic.paired_comparison(matrix, min_votes=20)}
    assert pairs["better"].direction == "better"     # the registrar says so plainly
    assert pairs["worse"].direction == "worse"
    assert pairs["inert"].direction == "no difference"


def test_summary_carries_the_confound_warning(matrix):
    s = systemic.industry_summary(matrix, min_votes=20)
    # the raw cross-manager number is reported BUT labelled as confounded
    assert "confound" in s["raw_caveat"].lower()
    assert s["paired_median_delta"] is not None
    assert s["n_managers"] == 3
    # counts both directions — never only the damning one
    assert s["n_better"] == 1 and s["n_worse"] == 1


def test_verdict_states_no_effect_when_paired_median_is_flat(matrix):
    s = systemic.industry_summary(matrix, min_votes=20)
    v = s["verdict"].lower()
    assert "no measurable" in v or "no meaningful" in v
    for banned in ("hypocri", "lying", "greenwash", "betray", "deliberate"):
        assert banned not in v


def test_markdown_shows_both_directions_and_cites_method(matrix):
    md = systemic.summary_markdown(systemic.industry_summary(matrix, min_votes=20))
    assert "Better AM" in md and "Worse AM" in md      # symmetric on the page
    assert "paired" in md.lower()
    assert "confound" in md.lower()
    for banned in ("hypocri", "greenwash", "betray"):
        assert banned not in md.lower()
