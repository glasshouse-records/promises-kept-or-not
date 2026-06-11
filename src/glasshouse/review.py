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


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM findings GROUP BY status")}
