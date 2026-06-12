"""Eval gate for the LLM tier. No model gets wired into triage until it
clears the bar on OUR gold set.

The gold set (tests/gold_pairs.jsonl) is seeded from cases this project
already adjudicated the hard way (Aldar, Oracle, ABB, Goldman, Wells
Fargo) plus the matcher's documented false-positive classes. Extend it
with every reviewed lead — review decisions are free labels.

Decision rule (documented in METHODOLOGY): the adjudicator is trusted as a
TRIAGE layer only if precision on 'match' verdicts ≥ 0.97 and it calls the
Aldar-class cases no_match. 'unsure' is always allowed — it costs review
time, not correctness.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

GOLD_PATH = Path(__file__).resolve().parents[2] / "tests" / "gold_pairs.jsonl"
PRECISION_BAR = 0.97


def run_matcher_eval(conn: sqlite3.Connection, model: str | None = None,
                     gold_path: Path = GOLD_PATH) -> dict:
    from . import llm, triage
    model = model or llm.DEFAULT_MODEL
    cases = [json.loads(line) for line in gold_path.read_text().splitlines() if line.strip()]
    results = []
    for c in cases:
        d = triage.adjudicate_pair(conn, c["a"], c["b"], model=model)
        results.append({"label": c["label"], "verdict": d["verdict"],
                        "why": c["why"], "rationale": d["rationale"]})

    tp = sum(1 for r in results if r["verdict"] == "match" and r["label"] == "match")
    fp = sum(1 for r in results if r["verdict"] == "match" and r["label"] == "no_match")
    fn = sum(1 for r in results if r["verdict"] != "match" and r["label"] == "match")
    n_unsure = sum(1 for r in results if r["verdict"] == "unsure")
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "model": model, "n": len(results),
        "precision_on_match": round(precision, 3),
        "recall_on_match": round(recall, 3),
        "unsure": n_unsure,
        "passes_bar": precision >= PRECISION_BAR and fp == 0,
        "bar": PRECISION_BAR,
        "failures": [r for r in results
                     if (r["verdict"] == "match") != (r["label"] == "match")
                     and r["verdict"] != "unsure"],
    }
