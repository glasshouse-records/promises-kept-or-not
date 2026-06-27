"""The findings agent — uses the investigation engine to draft cited stories.

It autonomously does what a researcher would: scan every manager × theme for
the strongest say-vs-do gaps (committed to a theme, votes against it, on enough
votes to be real), then DRAFT a story for each — a headline, a standfirst, and
the full cited evidence pack — and queue them for human review.

HARD GUARDRAILS (the charter's invariants, enforced here):
  • It writes DRAFTS to data/agent/ only — never to the findings table, never
    to the public site, never sent anywhere. Promotion to a finding stays a
    human decision with a written note (review.py).
  • Every draft is stamped an unverified LEAD; every clause is templated from
    cited primary-source data (no free-text generation), so it cannot
    hallucinate a fact.
  • Selection is deterministic and explainable (a transparent score), not a
    black box.

This is the autonomous investigator the charter reserves to the maintenance
bay: it proposes; a person disposes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

from . import investigate, registry
from .http import DATA_DIR

BRIEFS_DIR = DATA_DIR / "agent" / "briefs"

_THEME_LABEL = {"board-diversity": "board diversity", "lobbying-disclosure": "lobbying disclosure",
                "anti-corruption": "anti-corruption", "human-rights": "human rights",
                "climate": "climate"}


def _label(theme: str) -> str:
    return _THEME_LABEL.get(theme, theme.replace("-", " "))


def _cell_record(inst: dict, theme: str, c: dict) -> investigate.ThemeRecord:
    """Reconstruct a ThemeRecord from a matrix cell so we can reuse
    investigate.evidence_pack for the citation block."""
    return investigate.ThemeRecord(
        theme=theme, institution_id=inst["id"], institution_name=inst["name"],
        committed=c["committed"], commitment_quote=c["quote"], doc_label=c["doc_label"],
        doc_version=c["doc_version"], doc_url=c["doc_url"], votes_for=c["for"],
        votes_against=c["against"], votes_abstain=c["abstain"], n_theme=c["n"],
        against_rate=c["rate"], examples=c["examples"],
        tension=c["rate"] if c["committed"] else 0.0)


def _score(rate: float, n: int, aum: float) -> float:
    """Transparent newsworthiness: the gap (rate) is primary, scaled by how
    many votes back it (confidence) and how much the manager matters (AUM)."""
    return round(rate * (n ** 0.25) * ((aum + 0.1) ** 0.3), 4)


def _draft(rec: investigate.ThemeRecord, score: float) -> dict:
    """A templated, fully-cited story draft. Headline + standfirst are composed
    from the data only — no generated facts."""
    label = _label(rec.theme)
    pct = round(rec.against_rate * 100)
    years = sorted({e["meeting_date"][-4:] for e in rec.examples
                    if e["meeting_date"] and e["meeting_date"][-4:].isdigit()})
    span = f"{years[0]}–{years[-1]}" if len(years) > 1 else (years[0] if years else "recent seasons")
    headline = (f"{rec.institution_name} commits to {label} — then votes against "
                f"{pct}% of {label} proposals")
    top = rec.examples[0] if rec.examples else None
    standfirst = (
        f"{rec.institution_name}'s own {rec.doc_label} (version {rec.doc_version}) commits to "
        f"{label}: “{(rec.commitment_quote or '').strip()}” "
        f"Yet across {rec.votes_for + rec.votes_against} shareholder proposals advancing "
        f"{label} ({span}), its funds voted AGAINST {rec.votes_against} ({pct}%).")
    if top:
        standfirst += (f" The largest: {top['issuer_name']}, where it voted against "
                       f"“{top['vote_description']}” with {int(top['shares_voted']):,} shares.")
    body = (f"# {headline}\n\n"
            f"> **DRAFT — automated lead, not a finding.** A human must verify every cited "
            f"source and the polarity/intent of each proposal before publication. "
            f"Selection score {score} (gap × vote-count × manager AUM).\n\n"
            f"{standfirst}\n\n---\n\n"
            + investigate.evidence_pack(rec, hypothesis=f"{rec.institution_name} commits to "
                                        f"{label} but votes against proposals advancing it."))
    if rec.votes_for + rec.votes_against < 10:
        body += "\n> ⚠️ Fewer than 10 theme votes — treat as a weak lead.\n"
    return {"institution_id": rec.institution_id, "institution_name": rec.institution_name,
            "theme": rec.theme, "against_rate": rec.against_rate,
            "votes_against": rec.votes_against, "votes_for": rec.votes_for,
            "score": score, "headline": headline, "standfirst": standfirst, "body": body}


def investigate_and_draft(conn: sqlite3.Connection, *, min_rate: float = 0.6,
                          min_votes: int = 10, top_n: int = 12) -> list[dict]:
    """Scan the matrix, rank the strongest committed say-vs-do gaps, draft a
    cited story for each, and write them to data/agent/briefs/<date>/. Returns
    the briefs (also written to disk). Writes NOTHING to the ledger facts."""
    reg = registry.load()
    bm = investigate.build_matrix(conn)
    scored = []
    for inst in bm["institutions"]:
        aum = float(reg.get(inst["id"], {}).get("aum_usd_tr") or 0)
        for theme, c in inst["cells"].items():
            n = c["for"] + c["against"]
            if c["committed"] and n >= min_votes and c["rate"] >= min_rate:
                scored.append((_score(c["rate"], n, aum), inst, theme, c))
    scored.sort(key=lambda x: -x[0])

    briefs = [_draft(_cell_record(inst, theme, c), s) for s, inst, theme, c in scored[:top_n]]

    out = BRIEFS_DIR / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    for b in briefs:
        (out / f"{b['institution_id']}--{b['theme']}.md").write_text(b["body"])
    index = {"generated": datetime.now(UTC).isoformat(timespec="seconds"),
             "params": {"min_rate": min_rate, "min_votes": min_votes, "top_n": top_n},
             "briefs": [{k: b[k] for k in ("institution_id", "institution_name", "theme",
                         "against_rate", "votes_against", "votes_for", "score", "headline",
                         "standfirst")}
                        for b in briefs]}
    (out / "index.json").write_text(json.dumps(index, indent=2))
    return briefs


def load_latest_briefs() -> dict | None:
    """The most recent agent run (index + each draft's full Markdown body), or
    None if the agent hasn't run. The workbench reads this for human review."""
    if not BRIEFS_DIR.exists():
        return None
    dirs = sorted(p for p in BRIEFS_DIR.iterdir() if p.is_dir() and (p / "index.json").exists())
    if not dirs:
        return None
    latest = dirs[-1]
    idx = json.loads((latest / "index.json").read_text())
    for b in idx["briefs"]:
        md = latest / f"{b['institution_id']}--{b['theme']}.md"
        b["body"] = md.read_text() if md.exists() else ""
    idx["dir"] = str(latest)
    return idx
