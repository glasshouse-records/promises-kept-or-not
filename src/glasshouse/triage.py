"""LLM triage of quarantined leads — the 99%-vs-91% layer.

Evidence basis: OpenSanctions Pairs (arXiv:2603.11051, Feb 2026) measured
frontier-model pairwise entity adjudication at 98.95% F1 against a
production rule-based matcher's 91.33%, on 755k human-labeled sanctions
pairs — our exact problem shape (the Aldar false-positive class).

What triage does NOT do: publish, promote, or touch quarantine semantics.
A `no_match` verdict lets a human skip a lead faster; a `match` verdict
moves it UP the review queue. The gate is unchanged. Run `glasshouse eval
matcher` first — the adjudicator is only worth wiring in if it clears the
precision bar on our own gold set.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime

from . import llm

_MATCH_SYSTEM = """You adjudicate whether two organization records refer to the SAME legal entity.
You are extremely precise: a false "match" can lead to a false public accusation.

Rules:
- Different jurisdictions/countries with the same name → almost always different entities.
- A subsidiary is NOT the same entity as its parent (answer no_match, note the relationship).
- Generic name overlap (e.g. "Apple Hospitality" vs "Apple Inc") → no_match.
- If identifiers (LEI, CUSIP, country) conflict → no_match. If they agree → strong match signal.
- When evidence is thin either way → unsure.

Answer ONLY with JSON: {"verdict": "match"|"no_match"|"unsure", "confidence": "high"|"medium"|"low", "rationale": "<one sentence>"}"""

_THEME_SYSTEM = """You classify shareholder-meeting proposal texts into themes.
Themes: anti-corruption, human-rights, climate, lobbying-disclosure, board-diversity, none.
"none" means the proposal does not substantively concern any listed theme (routine
director elections, auditor ratification, compensation, share issuance are "none"
unless the text explicitly centers a theme).

Answer ONLY with JSON: {"verdict": "<theme or none>", "confidence": "high"|"medium"|"low", "rationale": "<one sentence>"}"""


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if {"verdict", "confidence", "rationale"} <= set(d) else None
    except json.JSONDecodeError:
        return None


def _store(conn: sqlite3.Connection, kind: str, input_key: str, d: dict,
           model: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO triage (kind, input_key, verdict, confidence, "
        "rationale, model, ts) VALUES (?,?,?,?,?,?,?)",
        (kind, input_key, str(d["verdict"]), str(d["confidence"]),
         str(d["rationale"])[:400], model,
         datetime.now(UTC).isoformat(timespec="seconds")))
    conn.commit()


def adjudicate_pair(conn: sqlite3.Connection, record_a: dict, record_b: dict,
                    model: str = llm.DEFAULT_MODEL) -> dict:
    """One pairwise entity adjudication. Records are small dicts of whatever
    identity evidence exists (name, country, lei, cusip, agency, context)."""
    key = "pair:" + hashlib.sha256(
        json.dumps([record_a, record_b], sort_keys=True).encode()).hexdigest()[:16]
    cached = conn.execute("SELECT verdict, confidence, rationale FROM triage "
                          "WHERE input_key = ?", (key,)).fetchone()
    if cached:
        return dict(cached)
    user = (f"Record A: {json.dumps(record_a, sort_keys=True)}\n"
            f"Record B: {json.dumps(record_b, sort_keys=True)}")
    out = llm.call(conn, purpose="match_adjudication", input_key=key,
                   system=_MATCH_SYSTEM, user=user, model=model)
    d = _parse(out) or {"verdict": "unsure", "confidence": "low",
                        "rationale": "unparseable model output (logged)"}
    _store(conn, "entity_match", key, d, model)
    return d


def triage_leads(conn: sqlite3.Connection, limit: int = 20,
                 model: str = llm.DEFAULT_MODEL) -> dict:
    """Adjudicate the name-join leads behind flagged-votes: voted issuer vs.
    enforcement-record company. Results are advisory ordering for review."""
    from .findings import flagged_votes
    stats = {"match": 0, "no_match": 0, "unsure": 0}
    for fv in flagged_votes(conn, limit=limit):
        a = {"name": fv.issuer_name, "cusip": fv.cusip, "lei": fv.issuer_lei,
             "country": fv.issuer_country, "context": "issuer voted on in SEC N-PX"}
        b = {"name": fv.agency + " record: " + fv.issuer_name, "context":
             f"enforcement record {fv.primary_ref or 'no ref'} ({fv.resolution_type})"}
        d = adjudicate_pair(conn, a, b, model=model)
        stats[d["verdict"] if d["verdict"] in stats else "unsure"] += 1
    return stats


def classify_proposals(conn: sqlite3.Connection, limit: int = 50,
                       model: str = llm.DEFAULT_MODEL) -> dict:
    """Theme-classify distinct AGAINST-voted proposal texts, cached forever
    by content hash. Complements (does not replace) the lexical engine."""
    rows = conn.execute(
        """SELECT DISTINCT v.vote_description FROM votes v
           WHERE v.how_voted='AGAINST' AND v.is_duplicate=0
             AND length(v.vote_description) > 30 LIMIT ?""", (limit * 5,)).fetchall()
    stats: dict[str, int] = {}
    done = 0
    for r in rows:
        if done >= limit:
            break
        text = r[0]
        key = "prop:" + hashlib.sha256(text.encode()).hexdigest()[:16]
        if conn.execute("SELECT 1 FROM triage WHERE input_key=?", (key,)).fetchone():
            continue
        out = llm.call(conn, purpose="proposal_theme", input_key=key,
                       system=_THEME_SYSTEM, user=text[:1200], model=model)
        d = _parse(out) or {"verdict": "none", "confidence": "low",
                            "rationale": "unparseable model output (logged)"}
        _store(conn, "proposal_theme", key, d, model)
        stats[d["verdict"]] = stats.get(d["verdict"], 0) + 1
        done += 1
    return stats
