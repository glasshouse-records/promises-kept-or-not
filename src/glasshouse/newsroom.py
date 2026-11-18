"""The newsroom — story selection made visible.

This is the operator-facing answer to "what's publishable right now, why,
and what would the post say." It ranks the publishable units across the
pipeline (approved findings, contradiction candidates, fresh event
triggers, vote-divergence) by a transparent newsworthiness score, attaches
the analysis behind each, and surfaces the human-gated draft.

Selection is deterministic and explainable on purpose — the "agent picking
stories" is a ranking with stated reasons, not a black box. The LLM tier
can *explain/re-rank* advisorily on top (logged, never auto-sending), but
the spine stays auditable. The hard guardrail is unchanged: the newsroom
drafts; only a human sends.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import fields

from .contradictions import distinct_versions
from .http import DATA_DIR

# Escalation ladder (also in outreach.LADDER) — the newsroom suggests the
# next un-drafted step for each story.
_LADDER = ("social_post", "pitch", "inquiry", "non_response", "fiduciary", "data_offer")


def _shares_weight(shares: float) -> float:
    """Log-scaled so a 100M-share vote outranks a 1M-share one without a
    single mega-vote drowning everything."""
    return math.log10(max(shares, 1.0)) / 9.0  # ~1.0 at a billion shares


def _candidate_from_payload(payload: dict):
    from .contradictions import ContradictionCandidate
    allowed = {f.name for f in fields(ContradictionCandidate) if f.init}
    return ContradictionCandidate(**{k: v for k, v in payload.items() if k in allowed})


def story_queue(conn: sqlite3.Connection, limit: int = 40) -> list[dict]:
    """Ranked publishable units with the analysis and draft state for each."""
    # Drafts already in flight, keyed by finding fingerprint.
    drafted: dict[str, set[str]] = {}
    for r in conn.execute(
            "SELECT finding_fingerprint, kind, status FROM outreach "
            "WHERE finding_fingerprint != ''"):
        drafted.setdefault(r["finding_fingerprint"], set()).add(r["kind"])

    stories: list[dict] = []

    # 1. Approved findings — the strongest unit: human-verified, publishable now.
    for r in conn.execute(
            "SELECT fingerprint, payload, reviewer_note, reviewed_date FROM findings "
            "WHERE status='approved' ORDER BY reviewed_date DESC"):
        p = json.loads(r["payload"])
        shares = float(p.get("shares_voted") or 0)
        steps = drafted.get(r["fingerprint"], set())
        stories.append({
            "key": r["fingerprint"], "kind": "finding", "draftable": True,
            "status": "verified — ready to publish",
            "headline": f"{p['institution_id']} voted {p['how_voted']} on "
                        f"{p['theme']} at {p['issuer_name']}",
            "shares": shares,
            # Verified findings always outrank unverified candidates/triggers
            # (base 2.0 > any candidate's ≤1.5): publishability beats raw weight.
            "score": round(2.0 + _shares_weight(shares), 3),
            "why": ["human-verified finding", f"{int(shares):,} shares voted",
                    f"reviewer: {r['reviewer_note'][:80]}"],
            "payload": p, "drafted": sorted(steps),
            "next_step": next((s for s in _LADDER if s not in steps), None),
        })

    # 2. Contradiction candidates — read from the already-materialized review
    #    queue (pending findings) rather than re-running the contradiction engine
    #    on every call (that was ~37s of PDF-parsing + vote scans per page load,
    #    and it duplicated what review.sync already wrote). This is a fast SELECT
    #    and is consistent by construction with the Review tab.
    approved_fps = {s["key"] for s in stories}
    for r in conn.execute(
            "SELECT fingerprint, payload FROM findings WHERE status='pending'"):
        fp = r["fingerprint"]
        if fp in approved_fps:
            continue
        c = json.loads(r["payload"])
        shares = float(c.get("shares_voted") or 0)
        stories.append({
            "key": fp, "kind": "candidate", "draftable": False,
            "status": "candidate — needs review before publish",
            "headline": f"{c.get('institution_id')} voted {c.get('how_voted')} on "
                        f"{c.get('theme')} at {c.get('issuer_name')}",
            "shares": shares,
            "score": round(0.5 + _shares_weight(shares), 3),
            "why": [f"{c.get('theme')} policy vs. {c.get('how_voted')} vote",
                    f"{int(shares):,} shares", "lexical match — quarantined"],
            "payload": c, "drafted": sorted(drafted.get(fp, set())),
            "next_step": "review",
        })

    # 3. Fresh event triggers — recency makes these the most news-pegged.
    alerts_dir = DATA_DIR / "alerts"
    if alerts_dir.exists():
        for path in sorted(alerts_dir.glob("*.md"), reverse=True)[:10]:
            if path.name.endswith("news_triggers.md"):
                continue
            head = path.read_text(errors="replace").splitlines()[0].lstrip("# ")
            stories.append({
                "key": f"alert:{path.name}", "kind": "event", "draftable": False,
                "status": "fresh trigger — verify against primary source",
                "headline": head, "shares": 0.0,
                "score": 0.9,  # recency-pegged: new enforcement is inside the cycle
                "why": ["new enforcement action joined to a holder/voter",
                        f"alert pack: {path.name}"],
                "payload": {}, "drafted": [], "next_step": "verify",
            })

    stories.sort(key=lambda s: -s["score"])
    return stories[:limit]


def draft_story(conn: sqlite3.Connection, payload: dict, kind: str) -> int:
    """Draft an outbound item for a story from its candidate payload. Routes
    through outreach.draft_from_candidate — i.e. the same human-gated queue;
    this never sends."""
    from . import outreach
    return outreach.draft_from_candidate(conn, _candidate_from_payload(payload), kind=kind)


def pipeline_status(conn: sqlite3.Connection) -> list[dict]:
    """One row per pipeline stage: what it has produced and whether it looks
    alive. Makes 'is the pipeline running proper' answerable at a glance."""
    def one(q, *a):
        return conn.execute(q, a).fetchone()[0]

    votes = one("SELECT COUNT(*) FROM votes WHERE is_duplicate=0")
    holdings = one("SELECT COUNT(*) FROM holdings")
    enf = one("SELECT COUNT(*) FROM enforcement_actions WHERE is_duplicate=0")
    commits = len(distinct_versions(conn))
    insts = one("SELECT COUNT(DISTINCT institution_id) FROM filings "
                "WHERE institution_id IS NOT NULL")
    cands = one("SELECT COUNT(*) FROM findings WHERE status='pending'")
    approved = one("SELECT COUNT(*) FROM findings WHERE status='approved'")
    rejected = one("SELECT COUNT(*) FROM findings WHERE status='rejected'")
    drafts = one("SELECT COUNT(*) FROM outreach WHERE status='draft'")
    sent = one("SELECT COUNT(*) FROM outreach WHERE status='sent'")
    silent = one("SELECT COUNT(*) FROM outreach WHERE status='sent' AND response_date=''")
    signals = one("SELECT COUNT(*) FROM signals")
    last_run = conn.execute("SELECT ts FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    alerts = len(list((DATA_DIR / "alerts").glob("*.md"))) if (DATA_DIR / "alerts").exists() else 0

    return [
        {"stage": "INGEST · votes (N-PX)", "detail": f"{votes:,} deduped across {insts} institutions",
         "ok": votes > 0},
        {"stage": "INGEST · holdings (13-F/N-PORT)", "detail": f"{holdings:,} positions", "ok": holdings > 0},
        {"stage": "INGEST · enforcement", "detail": f"{enf:,} actions", "ok": enf > 0},
        {"stage": "SAY · commitments", "detail": f"{commits} archived policy versions", "ok": commits > 0},
        {"stage": "ANALYZE · contradiction candidates", "detail": f"{cands} pending review", "ok": True},
        {"stage": "REVIEW · findings", "detail": f"{approved} approved · {rejected} rejected · {cands} pending",
         "ok": True, "note": "no findings published yet" if approved == 0 else ""},
        {"stage": "TRIGGER · event alerts", "detail": f"{alerts} alert packs on disk", "ok": True},
        {"stage": "DIFF · last recorded run", "detail": last_run["ts"] if last_run else "never run",
         "ok": last_run is not None},
        {"stage": "DISTRIBUTE · outreach", "detail": f"{drafts} drafts · {sent} sent · {silent} awaiting response",
         "ok": True},
        {"stage": "SIGNAL · distribution evidence", "detail": f"{signals} recorded", "ok": True},
    ]
