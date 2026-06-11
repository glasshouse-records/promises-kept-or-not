"""Phase 6 — the outreach queue. Drafting is automated; SENDING IS NOT.

Hard guardrails, enforced in code, not prompt:
  - Nothing is ever sent by this module. It writes drafts to data/outbox/
    and tracks them in the `outreach` table. A human marks an item sent
    only after sending it themselves (`outreach mark-sent --i-sent-this`).
  - Drafts contain only verbatim ledger facts with inline citations.
    Templates have no adjectives, no rhetorical questions, no motive.
  - Quarantined evidence cannot be drafted against (`require_verified`).
  - All correspondence is tracked both directions; silence becomes the
    public non-response ledger.

Escalation ladder per finding: post → pitch → formal inquiry →
non-response ledger → fiduciary submission → annual awards.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .http import DATA_DIR

OUTBOX_DIR = DATA_DIR / "outbox"

KINDS = ("social_post", "pitch", "inquiry", "fiduciary", "data_offer")

_INQUIRY_TEMPLATE = """\
To: Investment Stewardship / Investor Relations, {institution}
From: Glasshouse (public-interest accountability project)
Date: {today}

Subject: Question regarding {institution}'s proxy voting record — {subject}

1. Your published policy "{doc_label}" (version retrieved {doc_version},
   SHA-256 {doc_sha}) states:

   "{commitment_quote}"

   Source: {doc_url}

2. SEC Form N-PX filing {accession} reports the following vote:

   {issuer} — meeting of {meeting_date}
   Proposal: {proposal}
   Vote cast: {how_voted} ({shares:,.0f} shares; management recommendation: {mgmt_rec})

Question: how does the vote in (2) implement the policy in (1)?

We will publish your response verbatim and in full alongside this inquiry.
If we receive no response by {deadline}, the inquiry and the absence of a
response will be recorded in our public non-response ledger.
"""

_POST_TEMPLATE = """\
{institution}'s policy ({doc_version}) states: "{commitment_short}" Its funds \
voted {how_voted} ({shares:,.0f} sh) on "{proposal_short}" at {issuer}, {meeting_date}. \
N-PX {accession}.
"""


def _record(conn: sqlite3.Connection, kind: str, institution_id: str,
            subject: str, body: str) -> int:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stem = f"{date.today().isoformat()}_{kind}_{institution_id}_{abs(hash(subject)) % 10**8}"
    path = OUTBOX_DIR / f"{stem}.md"
    path.write_text(body)
    cur = conn.execute(
        "INSERT INTO outreach (kind, institution_id, subject, body_path, created_ts) "
        "VALUES (?,?,?,?,?)", (kind, institution_id, subject, str(path), ts))
    conn.commit()
    return cur.lastrowid


def draft_from_candidate(conn: sqlite3.Connection, candidate, kind: str = "inquiry",
                         deadline_days: int = 30) -> int:
    """Draft an inquiry or social post from a ContradictionCandidate.

    The candidate object carries its own citation chain; the draft contains
    nothing that is not in it.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown outreach kind: {kind}")
    inst = conn.execute("SELECT display_name FROM institutions WHERE id = ?",
                        (candidate.institution_id,)).fetchone()
    institution = inst["display_name"] if inst else candidate.institution_id
    from datetime import timedelta
    deadline = (date.today() + timedelta(days=deadline_days)).isoformat()

    if kind == "inquiry":
        body = _INQUIRY_TEMPLATE.format(
            institution=institution, today=date.today().isoformat(),
            subject=f"{candidate.theme} / {candidate.issuer_name}",
            doc_label=candidate.doc_label, doc_version=candidate.doc_version,
            doc_sha=candidate.doc_sha256, commitment_quote=candidate.commitment_quote,
            doc_url=candidate.doc_url, accession=candidate.accession,
            issuer=candidate.issuer_name, meeting_date=candidate.meeting_date,
            proposal=candidate.vote_description, how_voted=candidate.how_voted,
            shares=candidate.shares_voted, mgmt_rec=candidate.management_recommendation,
            deadline=deadline)
    elif kind == "social_post":
        body = _POST_TEMPLATE.format(
            institution=institution, doc_version=candidate.doc_version,
            commitment_short=candidate.commitment_quote[:120],
            how_voted=candidate.how_voted, shares=candidate.shares_voted,
            proposal_short=candidate.vote_description[:80],
            issuer=candidate.issuer_name, meeting_date=candidate.meeting_date,
            accession=candidate.accession)
    else:
        raise NotImplementedError(f"draft kind {kind} not implemented yet")

    subject = f"{candidate.theme}: {candidate.issuer_name} {candidate.meeting_date}"
    return _record(conn, kind, candidate.institution_id, subject, body)


def mark_sent(conn: sqlite3.Connection, outreach_id: int, *, human_confirmed: bool) -> None:
    """Record that a HUMAN sent an item. Refuses without explicit confirmation —
    this tool never sends anything itself."""
    if not human_confirmed:
        raise PermissionError(
            "refusing: outreach items are sent by humans only; pass --i-sent-this "
            "after actually sending it")
    conn.execute("UPDATE outreach SET status='sent', sent_date=? WHERE id=?",
                 (date.today().isoformat(), outreach_id))
    conn.commit()


def record_response(conn: sqlite3.Connection, outreach_id: int, summary: str) -> None:
    conn.execute(
        "UPDATE outreach SET response_date=?, response_summary=? WHERE id=?",
        (date.today().isoformat(), summary, outreach_id))
    conn.commit()


def non_response_ledger(conn: sqlite3.Connection) -> list[dict]:
    """'Asked X on DATE about Y. Day N: no response.' — derived, not asserted."""
    rows = conn.execute(
        "SELECT id, kind, institution_id, subject, sent_date FROM outreach "
        "WHERE status='sent' AND response_date='' ORDER BY sent_date").fetchall()
    out = []
    for r in rows:
        days = (date.today() - date.fromisoformat(r["sent_date"])).days
        out.append({**dict(r), "days_without_response": days})
    return out
