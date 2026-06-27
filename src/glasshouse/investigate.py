"""Investigation engine — turn the dataset into findings by connecting SAY↔DO.

`contradictions.py` emits one quarantined candidate per offending vote. That is
review fodder, not an investigation. This module answers the question a
journalist actually asks:

    "Which managers publicly COMMIT to <theme>, yet vote AGAINST shareholder
     proposals advancing it — and how often?"

For each institution it connects:
  • SAY — the binding commitment sentence from its archived policy (cited), and
  • DO — its voting record on proposals on that theme (for / against / abstain),
expressed as an **against-rate** with the top cited examples. It reuses the
precision guards from contradictions.py (polarity: an AGAINST vote on an
ANTI-theme proposal is NOT counted; commitment scoring/discretion) so the
numbers are defensible. Legacy (unvalidated) votes are excluded, matching the
public release.

Output is evidence for a human/agent to turn into a finding — never an
auto-published claim.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from .contradictions import (
    THEMES,
    _yyyymmdd,
    commitment_is_discretionary,
    commitment_sentences,
    extract_text,
    proposal_is_oppositional,
    score_commitment_sentence,
)
from .http import DATA_DIR

MATRIX_CACHE = DATA_DIR / "investigate" / "matrix.json"


@cache
def _theme_proposal_re(theme: str) -> re.Pattern:
    """Compiled proposal-side regex for a theme (the same patterns the
    contradiction engine uses)."""
    return re.compile("|".join(THEMES[theme]["proposal"]), re.IGNORECASE)

# Coarse SQL prefilter per theme (LIKE substrings) so we don't pull millions of
# rows into Python; the compiled theme regex + polarity guard then refine.
_PREFILTER: dict[str, list[str]] = {
    "anti-corruption": ["corruption", "bribery", "ethics"],
    "human-rights": ["human right", "human capital", "forced lab", "child lab"],
    "climate": ["climate", "emission", "greenhouse", "ghg", "carbon", "paris", "net zero", "net-zero"],
    "lobbying-disclosure": ["lobby", "political"],
    "board-diversity": ["diversity", "dei", "civil rights", "inclusion"],
}

_EXAMPLE_LIMIT = 10


@dataclass
class ThemeRecord:
    theme: str
    institution_id: str
    institution_name: str
    committed: bool
    commitment_quote: str | None
    doc_label: str | None
    doc_version: str | None
    doc_url: str | None
    votes_for: int
    votes_against: int
    votes_abstain: int
    n_theme: int
    against_rate: float
    examples: list[dict] = field(default_factory=list)
    tension: float = 0.0


def _commitment_for(conn: sqlite3.Connection, inst_id: str, theme: str):
    """Strongest binding, non-discretionary commitment sentence for a theme,
    from the institution's latest policy version that has one. Returns
    (quote, row) or None."""
    pats = THEMES[theme]["commitment"]
    best = None
    best_v = ""
    for r in conn.execute(
        "SELECT doc_label, url, sha256, content_path, "
        "COALESCE(NULLIF(wayback_timestamp,''), retrieval_date) AS v "
        "FROM commitments WHERE institution_id=?", (inst_id,)):
        cp = r["content_path"]
        if not cp or not Path(cp).exists():
            continue
        text = extract_text(Path(cp))
        if not text:
            continue
        qs = [q for q in commitment_sentences(text, pats)
              if not commitment_is_discretionary(q) and score_commitment_sentence(q) >= 1.0]
        if qs:
            v = _yyyymmdd(r["v"])
            if best is None or v > best_v:
                best, best_v = (qs[0], r), v
    return best


def _theme_votes(conn: sqlite3.Connection, inst_id: str, theme: str):
    """For an institution, the for/against/abstain counts and the cited AGAINST
    examples on proposals that ADVANCE the theme (polarity-guarded)."""
    terms = _PREFILTER[theme]
    like = " OR ".join(["LOWER(v.vote_description) LIKE ?"] * len(terms))
    params = [inst_id] + [f"%{t}%" for t in terms]
    rx = _theme_proposal_re(theme)

    f = a = ab = 0
    against: list[dict] = []
    for v in conn.execute(
        f"""SELECT v.accession, v.issuer_name, v.meeting_date, v.vote_description,
                   v.how_voted, v.shares_voted
            FROM votes v JOIN filings f ON f.accession = v.accession
            WHERE f.institution_id = ? AND v.is_duplicate = 0
              AND IFNULL(v.vote_source,'') != 'legacy_html'
              AND ({like})""", params):
        desc = v["vote_description"] or ""
        if not rx.search(desc) or proposal_is_oppositional(desc):
            continue
        hv = (v["how_voted"] or "").strip().upper()
        if hv == "FOR":
            f += 1
        elif hv == "AGAINST":
            a += 1
            against.append({"issuer_name": v["issuer_name"], "meeting_date": v["meeting_date"],
                            "vote_description": desc[:200], "how_voted": "AGAINST",
                            "shares_voted": v["shares_voted"] or 0.0, "accession": v["accession"]})
        elif hv == "ABSTAIN":
            ab += 1
    against.sort(key=lambda e: -(e["shares_voted"] or 0.0))
    return f, a, ab, against[:_EXAMPLE_LIMIT]


def theme_records(conn: sqlite3.Connection, theme: str) -> list[ThemeRecord]:
    """One ThemeRecord per institution, ranked so committed-hypocrisy surfaces
    first (committed → high against-rate → volume)."""
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; known: {', '.join(THEMES)}")
    recs: list[ThemeRecord] = []
    for inst in conn.execute("SELECT id, display_name FROM institutions ORDER BY id"):
        c = _commitment_for(conn, inst["id"], theme)
        f, a, ab, examples = _theme_votes(conn, inst["id"], theme)
        denom = f + a
        rate = (a / denom) if denom else 0.0
        committed = c is not None
        recs.append(ThemeRecord(
            theme=theme, institution_id=inst["id"], institution_name=inst["display_name"],
            committed=committed,
            commitment_quote=(c[0] if c else None),
            doc_label=(c[1]["doc_label"] if c else None),
            doc_version=(c[1]["v"] if c else None),
            doc_url=(c[1]["url"] if c else None),
            votes_for=f, votes_against=a, votes_abstain=ab, n_theme=f + a + ab,
            against_rate=round(rate, 4), examples=examples,
            tension=round(rate, 4) if committed else 0.0))
    recs.sort(key=lambda r: (r.committed, r.tension, r.votes_against), reverse=True)
    return recs


def institution_record(conn: sqlite3.Connection, inst_id: str) -> dict[str, ThemeRecord]:
    """All themes for one institution — the per-manager investigation view."""
    out = {}
    for theme in THEMES:
        rec = next((r for r in theme_records(conn, theme) if r.institution_id == inst_id), None)
        if rec:
            out[theme] = rec
    return out


def _scan_matrix(conn: sqlite3.Connection) -> dict[str, dict[str, dict]]:
    """ONE pass over the whole vote table (not per institution), bucketed by
    institution × theme. SQLite LIKE is ASCII-case-insensitive, so no LOWER()
    per row. Returns {institution_id: {theme: {for, against, abstain, examples}}}."""
    all_terms = sorted({t for th in THEMES for t in _PREFILTER[th]})
    like = " OR ".join(["v.vote_description LIKE ?"] * len(all_terms))
    params = [f"%{t}%" for t in all_terms]
    regexes = {th: _theme_proposal_re(th) for th in THEMES}
    out: dict[str, dict[str, dict]] = {}
    for v in conn.execute(
        f"""SELECT f.institution_id AS iid, v.accession, v.issuer_name, v.meeting_date,
                   v.vote_description, v.how_voted, v.shares_voted
            FROM votes v JOIN filings f ON f.accession = v.accession
            WHERE v.is_duplicate = 0 AND IFNULL(v.vote_source,'') != 'legacy_html'
              AND ({like})""", params):
        desc = v["vote_description"] or ""
        if proposal_is_oppositional(desc):
            continue
        hv = (v["how_voted"] or "").strip().upper()
        for th, rx in regexes.items():
            if not rx.search(desc):
                continue
            b = out.setdefault(v["iid"], {}).setdefault(
                th, {"for": 0, "against": 0, "abstain": 0, "examples": []})
            if hv == "FOR":
                b["for"] += 1
            elif hv == "AGAINST":
                b["against"] += 1
                b["examples"].append({
                    "issuer_name": v["issuer_name"], "meeting_date": v["meeting_date"],
                    "vote_description": desc[:200], "shares_voted": v["shares_voted"] or 0.0,
                    "accession": v["accession"]})
            elif hv == "ABSTAIN":
                b["abstain"] += 1
    for cells in out.values():
        for s in cells.values():
            s["examples"].sort(key=lambda e: -(e["shares_voted"] or 0.0))
            s["examples"] = s["examples"][:_EXAMPLE_LIMIT]
    return out


def build_matrix(conn: sqlite3.Connection) -> dict:
    """The full hypocrisy matrix: every institution × theme cell with the
    against-rate, the cited commitment (SAY), and the top cited AGAINST votes
    (DO) — everything the interactive heatmap and its drill-downs need, so the
    UI serves entirely from this one cached payload."""
    scan = _scan_matrix(conn)
    institutions = []
    for inst in conn.execute("SELECT id, display_name FROM institutions ORDER BY id"):
        isc = scan.get(inst["id"], {})
        cells = {}
        for th in THEMES:
            c = _commitment_for(conn, inst["id"], th)
            s = isc.get(th, {"for": 0, "against": 0, "abstain": 0, "examples": []})
            f, a, ab = s["for"], s["against"], s["abstain"]
            n = f + a + ab
            if c is None and n == 0:
                continue  # nothing to show for this cell
            denom = f + a
            cells[th] = {
                "committed": c is not None,
                "quote": (c[0] if c else None),
                "doc_label": (c[1]["doc_label"] if c else None),
                "doc_version": (c[1]["v"] if c else None),
                "doc_url": (c[1]["url"] if c else None),
                "for": f, "against": a, "abstain": ab, "n": n,
                "rate": round(a / denom, 4) if denom else 0.0,
                "low_confidence": denom < 5,
                "examples": s["examples"],
            }
        if cells:
            institutions.append({"id": inst["id"], "name": inst["display_name"], "cells": cells})
    return {"generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "themes": list(THEMES), "institutions": institutions}


def cache_matrix(conn: sqlite3.Connection) -> Path:
    """Compute and persist the matrix so the workbench loads it instantly."""
    m = build_matrix(conn)
    MATRIX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_CACHE.write_text(json.dumps(m, default=str))
    return MATRIX_CACHE


def load_matrix() -> dict | None:
    """The cached matrix, or None if it hasn't been built yet."""
    if MATRIX_CACHE.exists():
        return json.loads(MATRIX_CACHE.read_text())
    return None


def theme_matrix(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """{institution_id: {theme: against_rate}} for committed cells with votes —
    derived from the single-pass build_matrix (used by the CLI matrix view)."""
    return {i["id"]: {t: c["rate"] for t, c in i["cells"].items()
                      if c["committed"] and c["n"]}
            for i in build_matrix(conn)["institutions"]}
