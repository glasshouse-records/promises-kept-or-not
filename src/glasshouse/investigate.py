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
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from .contradictions import (
    THEMES,
    _yyyymmdd,
    capture_text,
    commitment_is_discretionary,
    commitment_is_oppositional,
    commitment_sentences,
    is_binding_commitment,
    proposal_is_oppositional,
    score_commitment_sentence,
)
from .http import DATA_DIR
from .ledger import NON_LEGACY_VOTE_SQL, VERSION_DATE_SQL

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
    "nature": ["deforestation", "biodiversity", "natural capital", "nature", "water", "plastic"],
    "labor-rights": ["freedom of association", "collective bargaining", "living wage",
                     "sick leave", "worker safety", "worker health", "workplace safety"],
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
        f"{VERSION_DATE_SQL} AS v "
        "FROM commitments WHERE institution_id=? AND superseded=0", (inst_id,)):
        cp = r["content_path"]
        if not cp or not Path(cp).exists():
            continue
        text = capture_text(inst_id, r["doc_label"], Path(cp))
        if not text:
            continue
        qs = [q for q in commitment_sentences(text, pats)
              if is_binding_commitment(q) and not commitment_is_discretionary(q)
              and not commitment_is_oppositional(q)
              and score_commitment_sentence(q) >= 1.0]
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
            WHERE v.is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL}
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


def theme_trend(conn: sqlite3.Connection, theme: str | None = None, *,
                keywords: list[str] | None = None) -> dict:
    """Against-rate per meeting YEAR, per institution, for a theme — so a
    researcher can see a shift over proxy seasons (e.g. after a manager left a
    climate alliance). Restricted to committed managers (the say-vs-do story).
    Returns {institution_id: {name, years: {YYYY: {for, against, rate}}}}."""
    commitment_pats, proposal_pats, prefilter = _theme_spec(theme, keywords)
    rx = re.compile("|".join(proposal_pats), re.IGNORECASE)
    like = " OR ".join(["v.vote_description LIKE ?"] * len(prefilter))
    params = [f"%{t}%" for t in prefilter]
    agg: dict[str, dict[str, list]] = {}
    for v in conn.execute(
        f"""SELECT f.institution_id AS iid, v.meeting_date, v.vote_description, v.how_voted
            FROM votes v JOIN filings f ON f.accession=v.accession
            WHERE v.is_duplicate=0 AND {NON_LEGACY_VOTE_SQL}
              AND ({like})""", params):
        desc = v["vote_description"] or ""
        if not rx.search(desc) or proposal_is_oppositional(desc):
            continue
        md = (v["meeting_date"] or "").strip()
        year = md[-4:] if len(md) >= 4 and md[-4:].isdigit() else None
        if not year:
            continue
        hv = (v["how_voted"] or "").strip().upper()
        b = agg.setdefault(v["iid"], {}).setdefault(year, [0, 0])
        if hv == "FOR":
            b[0] += 1
        elif hv == "AGAINST":
            b[1] += 1
    names = {i["id"]: i["display_name"] for i in
             conn.execute("SELECT id, display_name FROM institutions")}
    out = {}
    for iid, years in agg.items():
        if not _commitment_for(conn, iid, commitment_pats):
            continue  # no SAY ⇒ no say-vs-do trend
        yd = {}
        for y, (f, a) in sorted(years.items()):
            denom = f + a
            if denom:
                yd[y] = {"for": f, "against": a, "rate": round(a / denom, 4)}
        if yd:
            out[iid] = {"name": names.get(iid, iid), "years": yd}
    return out


def holdings_weighted(conn: sqlite3.Connection, theme: str | None = None, *,
                      keywords: list[str] | None = None, min_held: int = 8) -> list[dict]:
    """Does a manager vote against a theme MORE at the companies where it holds
    the biggest stake? For each manager, rank its theme votes by the manager's
    own 13-F position size in that company, split at the median, and compare the
    against-rate of its LARGE positions vs its SMALL ones. delta > 0 = votes
    against the theme more where it has the most skin in the game."""
    _commitment_pats, proposal_pats, prefilter = _theme_spec(theme, keywords)
    rx = re.compile("|".join(proposal_pats), re.IGNORECASE)
    like = " OR ".join(["v.vote_description LIKE ?"] * len(prefilter))
    params = [f"%{t}%" for t in prefilter]

    votes_by_inst: dict[str, list[tuple[str, str]]] = {}
    for v in conn.execute(
        f"""SELECT f.institution_id AS iid, v.cusip, v.how_voted, v.vote_description
            FROM votes v JOIN filings f ON f.accession=v.accession
            WHERE v.is_duplicate=0 AND {NON_LEGACY_VOTE_SQL}
              AND v.cusip != '' AND ({like})""", params):
        desc = v["vote_description"] or ""
        if not rx.search(desc) or proposal_is_oppositional(desc):
            continue
        hv = (v["how_voted"] or "").strip().upper()
        if hv in ("FOR", "AGAINST"):
            votes_by_inst.setdefault(v["iid"], []).append((v["cusip"], hv))

    names = {i["id"]: i["display_name"] for i in
             conn.execute("SELECT id, display_name FROM institutions")}
    out = []
    for iid, vts in votes_by_inst.items():
        hold = {r["cusip"]: (r["val"] or 0.0) for r in conn.execute(
            "SELECT h.cusip, MAX(h.value_usd) AS val FROM holdings h "
            "JOIN filings f ON f.accession=h.accession WHERE f.institution_id=? "
            "GROUP BY h.cusip", (iid,))}
        held = [(hold[c], hv) for c, hv in vts if hold.get(c, 0) > 0]
        if len(held) < min_held:
            continue
        held.sort(key=lambda x: -x[0])
        half = len(held) // 2
        large, small = held[:half], held[half:]

        def _rate(rows):
            a = sum(1 for _, hv in rows if hv == "AGAINST")
            return (round(a / len(rows), 4) if rows else 0.0, len(rows))
        lr, ln = _rate(large)
        sr, sn = _rate(small)
        out.append({"institution_id": iid, "institution_name": names.get(iid, iid),
                    "large_rate": lr, "large_n": ln, "small_rate": sr, "small_n": sn,
                    "delta": round(lr - sr, 4), "held_votes": len(held)})
    out.sort(key=lambda r: -r["delta"])
    return out


# Strip legal-form suffixes / share-class noise so name VARIANTS of the SAME
# company collapse, but DISTINCT companies do not.
_COMPANY_SUFFIX = re.compile(
    r"\b(?:INC|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|SA|AG|NV|SE|ASA|AB|"
    r"SPA|GROUP|HOLDING|HOLDINGS|THE|COM|ORD|ADR|ADS|REIT|CLASS|SERIES)\b", re.IGNORECASE)


def _norm_company(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9 ]", " ", (name or "").upper())
    n = _COMPANY_SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _resolve_company(conn: sqlite3.Connection, query: str):
    """Resolve a name query to ONE company — NEVER merge distinct companies.
    Matches the query as a WHOLE WORD (so 'ford' ≠ 'Ashford', 'apple' ≠
    'Pineapple'), groups issuer_name spellings by normalized name, and picks the
    exact-normalized group else the one with the most votes. Returns
    (canonical_display, variants, cusips, other_matches)."""
    qn = _norm_company(query)
    qword = re.compile(r"\b" + re.escape(query.strip()) + r"\b", re.IGNORECASE)
    groups: dict[str, dict] = {}
    for r in conn.execute(
        f"SELECT issuer_name, cusip FROM votes WHERE issuer_name LIKE ? AND is_duplicate=0 "
        f"AND {NON_LEGACY_VOTE_SQL}", (f"%{query}%",)):
        nm = r["issuer_name"] or ""
        if not qword.search(nm):
            continue                       # substring-only match (Pineapple, Ashford) → reject
        g = groups.setdefault(_norm_company(nm), {"variants": Counter(), "cusips": set()})
        g["variants"][nm] += 1
        if r["cusip"]:
            g["cusips"].add(r["cusip"])
    if not groups:
        return query, set(), set(), []
    ordered = sorted(groups.items(),
                     key=lambda kv: (kv[0] != qn, -sum(kv[1]["variants"].values())))
    _, top = ordered[0]
    canonical = top["variants"].most_common(1)[0][0]
    others = [g["variants"].most_common(1)[0][0] for _, g in ordered[1:]]
    return canonical, set(top["variants"]), top["cusips"], others


def company_record(conn: sqlite3.Connection, query: str) -> dict:
    """Start from a COMPANY: which managers HOLD it (13-F value), and how they
    VOTED at it — the join a journalist wants for 'who held $Xbn and still
    voted against the climate proposal here?'. Resolves the query to ONE company
    (never conflates distinct issuers); per-manager AGAINST votes are
    theme-tagged. Leads, not findings."""
    canonical, variants, cusips, others = _resolve_company(conn, query)
    if not variants:
        return {"company": query, "query": query, "holders": [], "other_matches": []}
    vph = ",".join("?" * len(variants))

    holders: dict[str, float] = {}
    hq = ("SELECT f.institution_id AS iid, MAX(h.value_usd) AS v FROM holdings h "
          f"JOIN filings f ON f.accession=h.accession WHERE h.issuer_name IN ({vph})")
    hp = list(variants)
    if cusips:
        hq += f" OR h.cusip IN ({','.join('?' * len(cusips))})"
        hp += list(cusips)
    hq += " GROUP BY f.institution_id"
    for r in conn.execute(hq, hp):
        holders[r["iid"]] = r["v"] or 0.0

    regexes = {th: _theme_proposal_re(th) for th in THEMES}
    per: dict[str, dict] = {}
    for v in conn.execute(
        f"""SELECT f.institution_id AS iid, v.meeting_date, v.vote_description,
                  v.how_voted, v.shares_voted, v.accession, f.source_url
           FROM votes v JOIN filings f ON f.accession=v.accession
           WHERE v.issuer_name IN ({vph}) AND v.is_duplicate=0
             AND {NON_LEGACY_VOTE_SQL}""", (*variants,)):
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
    return {"company": canonical, "query": query, "holders": rows,
            "other_matches": others[:5]}


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
            WHERE v.is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL}
              AND ({like})""", params):
        desc = v["vote_description"] or ""
        if proposal_is_oppositional(desc):
            continue
        hv = (v["how_voted"] or "").strip().upper()
        for th, rx in regexes.items():
            if not rx.search(desc):
                continue
            b = out.setdefault(v["iid"], {}).setdefault(
                th, {"for": 0, "against": 0, "abstain": 0, "examples": [], "years": {}})
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
            md = (v["meeting_date"] or "").strip()
            yr = md[-4:] if len(md) >= 4 and md[-4:].isdigit() else None
            if yr and hv in ("FOR", "AGAINST"):       # per-year trend, for/against only
                yb = b["years"].setdefault(yr, [0, 0])
                yb[0 if hv == "FOR" else 1] += 1
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
            s = isc.get(th, {"for": 0, "against": 0, "abstain": 0, "examples": [], "years": {}})
            f, a, ab = s["for"], s["against"], s["abstain"]
            n = f + a + ab
            if c is None and n == 0:
                continue  # nothing to show for this cell
            denom = f + a
            trend = {y: {"for": yf, "against": ya, "rate": round(ya / (yf + ya), 4)}
                     for y, (yf, ya) in sorted(s.get("years", {}).items()) if yf + ya}
            cells[th] = {
                "committed": c is not None,
                "quote": (c[0] if c else None),
                "doc_label": (c[1]["doc_label"] if c else None),
                "doc_version": (c[1]["v"] if c else None),
                "doc_url": (c[1]["url"] if c else None),
                "for": f, "against": a, "abstain": ab, "n": n,
                "rate": round(a / denom, 4) if denom else 0.0,
                "low_confidence": denom < 5,
                "examples": s["examples"], "trend": trend,
            }
        if cells:
            institutions.append({"id": inst["id"], "name": inst["display_name"], "cells": cells})
    return {"generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "themes": list(THEMES), "institutions": institutions}


def cache_matrix(conn: sqlite3.Connection) -> Path:
    """Compute and persist the full matrix (incl. per-cell holdings-weighted
    'skin-in-the-game' split) so the workbench loads everything instantly."""
    m = build_matrix(conn)
    # Attach holdings-weighted big-vs-small against-rates per cell (offline cost).
    for theme in m["themes"]:
        hw = {r["institution_id"]: r for r in holdings_weighted(conn, theme, min_held=8)}
        for inst in m["institutions"]:
            r = hw.get(inst["id"])
            if r and theme in inst["cells"]:
                inst["cells"][theme]["hw"] = {
                    "large_rate": r["large_rate"], "small_rate": r["small_rate"],
                    "delta": r["delta"], "held_votes": r["held_votes"]}
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
