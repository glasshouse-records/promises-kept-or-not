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


def _theme_spec(theme: str | None, keywords: list[str] | None):
    """Resolve a built-in theme name OR custom keywords into
    (commitment_patterns, proposal_patterns, prefilter_terms). Custom keywords
    serve as all three — so a journalist can test any hypothesis ('weapons',
    'tobacco', 'forced labor') without it being hardcoded."""
    if keywords:
        pats = [k.strip() for k in keywords if k.strip()]
        if not pats:
            raise ValueError("no usable keywords")
        return pats, pats, pats
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; known: {', '.join(THEMES)} "
                         "(or pass keywords= to test your own)")
    return THEMES[theme]["commitment"], THEMES[theme]["proposal"], _PREFILTER[theme]


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


def _commitment_for(conn: sqlite3.Connection, inst_id: str, commitment_pats: list[str]):
    """Strongest binding, non-discretionary commitment sentence matching the
    given patterns, from the institution's latest policy version that has one.
    Returns (quote, row) or None."""
    pats = commitment_pats
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


def _scan_one(conn: sqlite3.Connection, proposal_pats: list[str],
              prefilter_terms: list[str]) -> dict[str, dict]:
    """ONE pass over the whole vote table for a single theme/hypothesis,
    bucketed by institution (vs. a per-institution scan). Returns
    {institution_id: {for, against, abstain, examples}}."""
    like = " OR ".join(["v.vote_description LIKE ?"] * len(prefilter_terms))  # ASCII-case-insensitive
    params = [f"%{t}%" for t in prefilter_terms]
    rx = re.compile("|".join(proposal_pats), re.IGNORECASE)
    out: dict[str, dict] = {}
    for v in conn.execute(
        f"""SELECT f.institution_id AS iid, v.accession, v.issuer_name, v.meeting_date,
                   v.vote_description, v.how_voted, v.shares_voted, f.source_url
            FROM votes v JOIN filings f ON f.accession = v.accession
            WHERE v.is_duplicate = 0 AND IFNULL(v.vote_source,'') != 'legacy_html'
              AND ({like})""", params):
        desc = v["vote_description"] or ""
        if not rx.search(desc) or proposal_is_oppositional(desc):
            continue
        hv = (v["how_voted"] or "").strip().upper()
        b = out.setdefault(v["iid"], {"for": 0, "against": 0, "abstain": 0, "examples": []})
        if hv == "FOR":
            b["for"] += 1
        elif hv == "AGAINST":
            b["against"] += 1
            b["examples"].append({"issuer_name": v["issuer_name"], "meeting_date": v["meeting_date"],
                                  "vote_description": desc[:200], "how_voted": "AGAINST",
                                  "shares_voted": v["shares_voted"] or 0.0,
                                  "accession": v["accession"], "source_url": v["source_url"] or ""})
        elif hv == "ABSTAIN":
            b["abstain"] += 1
    for b in out.values():
        b["examples"].sort(key=lambda e: -(e["shares_voted"] or 0.0))
        b["examples"] = b["examples"][:_EXAMPLE_LIMIT]
    return out


def theme_records(conn: sqlite3.Connection, theme: str | None = None, *,
                  keywords: list[str] | None = None,
                  label: str | None = None) -> list[ThemeRecord]:
    """One ThemeRecord per institution, ranked so committed-hypocrisy surfaces
    first (committed → high against-rate → volume).

    Pass a built-in `theme`, OR `keywords` to test your own hypothesis (the
    keywords match both the commitment text and the proposal text)."""
    commitment_pats, proposal_pats, prefilter = _theme_spec(theme, keywords)
    name = label or theme or "+".join(keywords or [])[:30] or "custom"
    scan = _scan_one(conn, proposal_pats, prefilter)
    recs: list[ThemeRecord] = []
    for inst in conn.execute("SELECT id, display_name FROM institutions ORDER BY id"):
        c = _commitment_for(conn, inst["id"], commitment_pats)
        s = scan.get(inst["id"], {"for": 0, "against": 0, "abstain": 0, "examples": []})
        f, a, ab, examples = s["for"], s["against"], s["abstain"], s["examples"]
        denom = f + a
        rate = (a / denom) if denom else 0.0
        committed = c is not None
        recs.append(ThemeRecord(
            theme=name, institution_id=inst["id"], institution_name=inst["display_name"],
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
    """All themes for one institution — the per-manager investigation view.
    Derived from the single build_matrix pass (one vote scan, not one per theme)."""
    bm = build_matrix(conn)
    inst = next((i for i in bm["institutions"] if i["id"] == inst_id), None)
    if not inst:
        return {}
    out = {}
    for theme, c in inst["cells"].items():
        out[theme] = ThemeRecord(
            theme=theme, institution_id=inst_id, institution_name=inst["name"],
            committed=c["committed"], commitment_quote=c["quote"],
            doc_label=c["doc_label"], doc_version=c["doc_version"], doc_url=c["doc_url"],
            votes_for=c["for"], votes_against=c["against"], votes_abstain=c["abstain"],
            n_theme=c["n"], against_rate=c["rate"], examples=c["examples"],
            tension=c["rate"] if c["committed"] else 0.0)
    return out


def company_record(conn: sqlite3.Connection, query: str) -> dict:
    """Start from a COMPANY: which managers HOLD it (13-F value), and how they
    VOTED at it — the join a journalist wants for 'who held $Xbn and still
    voted against the climate proposal here?'. Matches the issuer by name; the
    per-manager AGAINST votes are theme-tagged. Leads, not findings."""
    like = f"%{query}%"
    vrows = conn.execute(
        "SELECT issuer_name FROM votes WHERE issuer_name LIKE ? AND is_duplicate=0 "
        "AND IFNULL(vote_source,'')!='legacy_html'", (like,)).fetchall()
    from collections import Counter
    names = Counter(r["issuer_name"] for r in vrows)
    canonical = names.most_common(1)[0][0] if names else query

    holders: dict[str, float] = {}
    for r in conn.execute(
        "SELECT f.institution_id AS iid, MAX(h.value_usd) AS v FROM holdings h "
        "JOIN filings f ON f.accession=h.accession WHERE h.issuer_name LIKE ? "
        "GROUP BY f.institution_id", (like,)):
        holders[r["iid"]] = r["v"] or 0.0

    regexes = {th: _theme_proposal_re(th) for th in THEMES}
    per: dict[str, dict] = {}
    for v in conn.execute(
        """SELECT f.institution_id AS iid, v.meeting_date, v.vote_description,
                  v.how_voted, v.shares_voted, v.accession, f.source_url
           FROM votes v JOIN filings f ON f.accession=v.accession
           WHERE v.issuer_name LIKE ? AND v.is_duplicate=0
             AND IFNULL(v.vote_source,'')!='legacy_html'""", (like,)):
        d = per.setdefault(v["iid"], {"for": 0, "against": 0, "examples": []})
        hv = (v["how_voted"] or "").strip().upper()
        if hv == "FOR":
            d["for"] += 1
        elif hv == "AGAINST":
            d["against"] += 1
            desc = v["vote_description"] or ""
            if not proposal_is_oppositional(desc):
                themes = [th for th, rx in regexes.items() if rx.search(desc)]
                d["examples"].append({
                    "meeting_date": v["meeting_date"], "vote_description": desc[:200],
                    "shares_voted": v["shares_voted"] or 0.0, "accession": v["accession"],
                    "source_url": v["source_url"] or "", "themes": themes})

    names_map = {i["id"]: i["display_name"] for i in
                 conn.execute("SELECT id, display_name FROM institutions")}
    rows = []
    for iid in set(holders) | set(per):
        p = per.get(iid, {"for": 0, "against": 0, "examples": []})
        p["examples"].sort(key=lambda e: -(e["shares_voted"] or 0.0))
        rows.append({
            "institution_id": iid, "institution_name": names_map.get(iid, iid),
            "held_usd": holders.get(iid, 0.0),
            "votes_for": p["for"], "votes_against": p["against"],
            "examples": p["examples"][:_EXAMPLE_LIMIT]})
    rows.sort(key=lambda r: (-r["held_usd"], -r["votes_against"]))
    return {"company": canonical, "query": query, "holders": rows}


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
                   v.vote_description, v.how_voted, v.shares_voted, f.source_url
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
                    "accession": v["accession"], "source_url": v["source_url"] or ""})
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
            c = _commitment_for(conn, inst["id"], THEMES[th]["commitment"])
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


def evidence_pack(rec: ThemeRecord, *, hypothesis: str = "") -> str:
    """A tested say-vs-do record → a self-contained, cited Markdown evidence
    pack a journalist can paste into an article or hand to an editor. Every
    number traces to a primary source; it is framed as a LEAD to verify, not a
    published claim."""
    pct = round(rec.against_rate * 100)
    lines = [
        f"# {rec.institution_name} — {rec.theme}: what it says vs. how it votes", "",
        f"_Generated by Glasshouse · {datetime.now(UTC).date()} · "
        "CC-BY-4.0 · this is a LEAD — verify each primary source before publishing._", "",
    ]
    if hypothesis:
        lines += [f"**Hypothesis tested:** {hypothesis}", ""]
    if not rec.committed:
        lines += [f"> No binding `{rec.theme}` commitment found in this institution's archived "
                  "policy, so there is no say-vs-do gap to assert here.", ""]
    else:
        lines += [
            "## What it says (SAY)",
            f"> “{rec.commitment_quote}”", "",
            f"— {rec.doc_label} (version {rec.doc_version}) · source: {rec.doc_url}", "",
            "## What it does (DO)",
            f"Voted **AGAINST {rec.votes_against} of {rec.votes_for + rec.votes_against} "
            f"({pct}%)** shareholder proposals advancing {rec.theme}."
            + (f"  \n_FOR {rec.votes_for} · AGAINST {rec.votes_against} · "
               f"ABSTAIN {rec.votes_abstain}._")
            + ("  \n⚠️ **Small sample (<5 votes)** — treat with caution."
               if (rec.votes_for + rec.votes_against) < 5 else ""), "",
            "### Cited votes (the evidence)", "",
            "| Meeting date | Company | Shares | Proposal | Source (N-PX) |",
            "|---|---|--:|---|---|",
        ]
        for e in rec.examples:
            desc = (e["vote_description"] or "").replace("|", "\\|")[:120]
            src = e.get("source_url") or e["accession"]
            lines.append(f"| {e['meeting_date']} | {e['issuer_name']} | "
                         f"{int(e['shares_voted']):,} | {desc} | [{e['accession']}]({src}) |")
    lines += [
        "", "## Method & caveats",
        "- Votes are SEC N-PX, de-duplicated (`is_duplicate = 0`); unvalidated "
        "legacy-parsed votes are excluded.",
        "- Proposals working *against* the theme (anti-ESG/anti-DEI) are excluded by a "
        "polarity guard, so an AGAINST vote here means voting against advancing the theme.",
        "- Theme matching is lexical — confirm each proposal's text and intent against the "
        "linked filing before publishing.",
        "- The commitment is the strongest binding sentence in the institution's own "
        "archived policy; read it in full at the source link above.", "",
    ]
    return "\n".join(lines) + "\n"


def theme_matrix(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """{institution_id: {theme: against_rate}} for committed cells with votes —
    derived from the single-pass build_matrix (used by the CLI matrix view)."""
    return {i["id"]: {t: c["rate"] for t, c in i["cells"].items()
                      if c["committed"] and c["n"]}
            for i in build_matrix(conn)["institutions"]}
