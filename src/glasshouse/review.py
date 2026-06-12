"""The human review gate: candidates become findings here, or get rejected
with a documented reason. This is the moat the methodology promises —
discarding almost-right findings, on the record.

Workflow:
    glasshouse review sync       # snapshot current candidates as pending
    glasshouse review list       # see the queue
    glasshouse review approve 3 --note "policy p.4 read; proposal verified on EDGAR"
    glasshouse review reject 5 --note "proposal is about reporting format, not the theme"

Approved findings render on the public site WITHOUT the quarantine ribbon;
rejected ones are counted publicly (the discipline is part of the product).
An approval requires a non-empty reviewer note: 'looks right' is not review.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date


def fingerprint(c) -> str:
    key = f"{c.theme}|{c.institution_id}|{c.accession}|{c.cusip}|{c.meeting_date}|{c.vote_description[:120]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def sync(conn: sqlite3.Connection) -> int:
    """Snapshot current contradiction candidates into the review queue.
    Existing rows (any status) are never touched — review decisions are
    durable even when the candidate generator changes."""
    from .contradictions import find_commitment_vote_contradictions
    n = 0
    for c in find_commitment_vote_contradictions(conn, limit_per_theme=25):
        cur = conn.execute(
            "INSERT OR IGNORE INTO findings (fingerprint, theme, institution_id, payload) "
            "VALUES (?,?,?,?)",
            (fingerprint(c), c.theme, c.institution_id,
             json.dumps(asdict(c), default=str)))
        n += cur.rowcount
    conn.commit()
    return n


def decide(conn: sqlite3.Connection, finding_id: int, status: str, note: str) -> None:
    if status not in ("approved", "rejected"):
        raise ValueError("status must be approved or rejected")
    if not note.strip():
        raise ValueError("a reviewer note is required — document the reason, "
                         "especially for rejections (every exclusion is recorded)")
    row = conn.execute("SELECT status FROM findings WHERE id = ?", (finding_id,)).fetchone()
    if row is None:
        raise ValueError(f"no finding #{finding_id} (run `glasshouse review sync` first)")
    conn.execute(
        "UPDATE findings SET status=?, reviewer_note=?, reviewed_date=? WHERE id=?",
        (status, note, date.today().isoformat(), finding_id))
    conn.commit()


def queue(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    where = "WHERE status = ?" if status else ""
    args = (status,) if status else ()
    rows = conn.execute(
        f"SELECT id, fingerprint, theme, institution_id, status, reviewer_note, "
        f"reviewed_date, payload FROM findings {where} ORDER BY id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def dossier(conn: sqlite3.Connection, finding_id: int) -> str:
    """Assemble a verification dossier for one pending candidate: every piece
    of ledger evidence, the exact things a reviewer must check, and the links
    to check them at. Deterministic; if the LLM tier is configured, appends a
    clearly-marked ADVISORY triage note. Returns the file path."""
    import urllib.parse

    from .http import DATA_DIR

    row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
    if row is None:
        raise ValueError(f"no finding #{finding_id}")
    p = json.loads(row["payload"])

    fts = ("https://efts.sec.gov/LATEST/search-index?q="
           + urllib.parse.quote(f'"{p["issuer_name"]}"') + "&forms=DEF+14A")
    versions = conn.execute(
        "SELECT COALESCE(NULLIF(wayback_timestamp,''), retrieval_date) AS v, sha256, "
        "content_path FROM commitments WHERE institution_id=? AND doc_label=? "
        "GROUP BY sha256 ORDER BY v",
        (p["institution_id"], p["doc_label"])).fetchall()

    lines = [
        f"# Verification dossier — finding #{finding_id} [{row['status']}]",
        "",
        f"**{p['institution_id']} · {p['theme']} · {p['issuer_name']} · {p['meeting_date']}**",
        "",
        "## The claim under review",
        f"SAYS: \"{p['commitment_quote']}\"",
        f"  — {p['doc_label']} @ {p['doc_version']}, sha256 {p['doc_sha256']}",
        f"  — source: {p['doc_url']}",
        f"DID: voted {p['how_voted']} with {int(float(p['shares_voted'])):,} shares "
        f"(mgmt rec as filed: {p['management_recommendation'] or '—'})",
        f"  — proposal: \"{p['vote_description']}\"",
        f"  — SEC Form N-PX {p['accession']}",
        "",
        "## Reviewer checklist",
        "1. Open the policy PDF and read the quote IN CONTEXT (page + surrounding",
        f"   paragraph). Local copy: {versions[-1]['content_path'] if versions else 'n/a'}",
        "2. Verify the proposal text against the issuer's proxy statement —",
        "   the N-PX managementRecommendation field is known-unreliable:",
        f"   EDGAR DEF 14A search: {fts}",
        f"3. Confirm the vote rows: sqlite3 data/glasshouse.db \"SELECT how_voted,",
        f"   shares_voted, vote_series FROM votes WHERE accession='{p['accession']}'",
        f"   AND cusip='{p['cusip']}' AND is_duplicate=0\"",
        "4. Does the policy language actually speak to this proposal? (theme match",
        "   is lexical — this is the judgment call only you can make)",
        "5. Decide: glasshouse review approve/reject " + str(finding_id) + " --note '...'",
        "",
        "## Archived policy versions (drift check)",
    ]
    for v in versions:
        lines.append(f"- {v['v']}  sha {v['sha256'][:12]}  {v['content_path']}")

    try:
        from . import llm
        out = llm.call(
            conn, purpose="dossier_draft", input_key=f"dossier:{row['fingerprint']}",
            system=("You prepare a SKEPTICAL pre-review note for a human editor. "
                    "List reasons this candidate might NOT hold up, then reasons it "
                    "might. Never recommend publishing; end with the open questions."),
            user=json.dumps(p, default=str)[:4000], max_tokens=400)
        lines += ["", "## ADVISORY — model pre-review (never a substitute for the checklist)", out]
    except Exception:
        lines += ["", "_(LLM tier not configured — dossier is fully deterministic.)_"]

    out_dir = DATA_DIR / "dossiers"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"finding_{finding_id}_{row['fingerprint']}.md"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM findings GROUP BY status")}
