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

import re
import sqlite3
from dataclasses import dataclass, field
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


def theme_matrix(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """{institution_id: {theme: against_rate}} for institutions that have a
    commitment on at least one theme — the data behind a hypocrisy heatmap."""
    matrix: dict[str, dict[str, float]] = {}
    for theme in THEMES:
        for r in theme_records(conn, theme):
            if r.committed and r.n_theme:
                matrix.setdefault(r.institution_id, {})[theme] = r.against_rate
    return matrix
