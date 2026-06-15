"""The review council — an agentic, multi-perspective evaluation of each
contradiction candidate that does the legwork so the human decision becomes
a fast ratification instead of an hour of investigation.

ADVISORY BY CONSTRUCTION. The council never promotes a candidate to a
finding, never publishes, never touches the human gate. It writes a
recommendation + full reasoning to the `triage` table (and every call to
`llm_log`), tiered so the operator can bulk-dismiss clear rejects, ratify
strong ones in seconds, and spend real attention only on genuine judgment
calls. The accountable approval stays a human click — the survival
condition for a watchdog where a false accusation is fatal.

Four independent passes per candidate (an evaluator–debate pattern):
  - skeptic   : argue this is NOT a defensible finding
  - advocate  : argue it IS
  - libel     : is the framing acts/dates/votes only, no motive, libel-safe?
  - theme     : does the proposal text actually concern the policy's theme,
                or is it a lexical false match?
A synthesizer weighs them into {finding | reject | needs_human} + confidence.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime

from . import llm

_ROLES = {
    "skeptic": (
        "You are a skeptical fact-checker. Argue, in 2-3 sentences, the strongest "
        "case that this is NOT a defensible public finding — boilerplate quote, "
        "theme mismatch, vote misread, or anything a libel lawyer would seize on. "
        "End with VERDICT: reject | weak | holds."),
    "advocate": (
        "You make the accountability case. Argue, in 2-3 sentences, the strongest "
        "case that this IS a defensible, news-shaped finding: a real commitment in "
        "the policy language vs. a contrary vote, both cited. End with "
        "VERDICT: strong | moderate | none."),
    "libel": (
        "You are a libel lawyer. The claim may state only acts, dates, amounts, "
        "votes, silences — never motive or characterization. In 2 sentences, say "
        "whether the pairing as given is safe to publish verbatim. End with "
        "VERDICT: safe | needs_edit | unsafe."),
    "theme": (
        "Does the PROPOSAL text genuinely concern the same theme as the POLICY "
        "quote, or is it a lexical coincidence? One sentence. End with "
        "VERDICT: on_theme | off_theme | unclear."),
}

_SYNTH = (
    "You are the editor. Given four reviewers' notes on a say-vs-do candidate, "
    "decide whether it should go to a human as a likely FINDING, be REJECTED as a "
    "false/weak match, or genuinely NEEDS_HUMAN judgment. Be conservative: if the "
    "skeptic or libel reviewer raised a real problem, prefer needs_human or reject. "
    'Answer ONLY JSON: {"verdict":"finding|reject|needs_human","confidence":'
    '"high|medium|low","rationale":"<=2 sentences"}')


def _candidate_brief(p: dict) -> str:
    return (f"POLICY ({p['institution_id']}, theme={p['theme']}, doc={p['doc_label']} "
            f"@ {p['doc_version']}):\n  \"{p['commitment_quote']}\"\n"
            f"VOTE (SEC N-PX {p['accession']}, {p['issuer_name']}, {p['meeting_date']}):\n"
            f"  voted {p['how_voted']} with {int(float(p['shares_voted'])):,} shares; "
            f"management recommendation as filed: {p.get('management_recommendation', '—')}\n"
            f"  proposal: \"{p['vote_description']}\"")


def evaluate(conn: sqlite3.Connection, payload: dict, *, key: str,
             model: str = llm.DEFAULT_MODEL) -> dict:
    """Run the four role passes + synthesis for one candidate. Returns the
    council recommendation; stores it (advisory) in triage and logs every
    call. Cached by key so re-runs are free."""
    cached = conn.execute(
        "SELECT verdict, confidence, rationale FROM triage WHERE kind='council' "
        "AND input_key=?", (key,)).fetchone()
    if cached:
        return {**dict(cached), "cached": True}

    brief = _candidate_brief(payload)
    notes = {}
    for role, system in _ROLES.items():
        out = llm.call(conn, purpose=f"council_{role}", input_key=f"{key}:{role}",
                       system=system, user=brief, model=model, max_tokens=220)
        notes[role] = out.strip()

    synth_user = brief + "\n\nREVIEWERS:\n" + "\n".join(
        f"- {r}: {n}" for r, n in notes.items())
    raw = llm.call(conn, purpose="council_synth", input_key=f"{key}:synth",
                   system=_SYNTH, user=synth_user, model=model, max_tokens=200)
    rec = _parse(raw) or {"verdict": "needs_human", "confidence": "low",
                          "rationale": "unparseable synthesis (logged) — defer to human"}
    rec["notes"] = notes

    conn.execute(
        "INSERT OR REPLACE INTO triage (kind, input_key, verdict, confidence, "
        "rationale, model, ts) VALUES ('council', ?, ?, ?, ?, ?, ?)",
        (key, str(rec["verdict"]), str(rec["confidence"]),
         json.dumps({"rationale": rec["rationale"], "notes": notes})[:2000],
         model, datetime.now(UTC).isoformat(timespec="seconds")))
    conn.commit()
    return {**rec, "cached": False}


def evaluate_pending(conn: sqlite3.Connection, limit: int = 50,
                     model: str = llm.DEFAULT_MODEL) -> dict:
    """Run the council over pending review-queue findings. Returns a tier
    tally; per-candidate recommendations live in triage for the workbench."""
    from .review import queue
    tally = {"finding": 0, "reject": 0, "needs_human": 0}
    for f in queue(conn, "pending"):
        if limit <= 0:
            break
        rec = evaluate(conn, f["payload"], key=f["fingerprint"], model=model)
        tally[rec["verdict"] if rec["verdict"] in tally else "needs_human"] += 1
        limit -= 1
    return tally


def recommendations(conn: sqlite3.Connection) -> dict[str, dict]:
    """fingerprint → council recommendation, for surfacing in the workbench."""
    out = {}
    for r in conn.execute(
            "SELECT input_key, verdict, confidence, rationale FROM triage "
            "WHERE kind='council'").fetchall():
        try:
            detail = json.loads(r["rationale"])
        except (json.JSONDecodeError, TypeError):
            detail = {"rationale": r["rationale"], "notes": {}}
        out[r["input_key"]] = {"verdict": r["verdict"], "confidence": r["confidence"],
                               **detail}
    return out


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if {"verdict", "confidence", "rationale"} <= set(d) else None
    except json.JSONDecodeError:
        return None
