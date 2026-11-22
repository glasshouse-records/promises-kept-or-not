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
from datetime import UTC, date, datetime
from pathlib import Path

from .fmt import shares_phrase, vote_vs_mgmt
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
   Vote cast: {how_voted} ({shares_txt}; vote vs management: {mgmt_rec})

Question: how does the vote in (2) implement the policy in (1)?

We will publish your response verbatim and in full alongside this inquiry.
If we receive no response by {deadline}, the inquiry and the absence of a
response will be recorded in our public non-response ledger.
"""

_POST_TEMPLATE = """\
{institution}'s policy ({doc_version}) states: "{commitment_short}" Its funds \
voted {how_voted} ({shares_sh}) on "{proposal_short}" at {issuer}, {meeting_date}. \
N-PX {accession}.
"""

_PITCH_TEMPLATE = """\
To: {reporter} ({outlet}) — beat: {beat}
From: Glasshouse (public-interest accountability project)
Date: {today}

Subject: Documented: {institution} voted {how_voted} on {theme} at {issuer} — \
against its own published policy language

Peg: {issuer}'s {meeting_date} meeting (SEC Form N-PX {accession}).

The records, all public and linked:
1. {institution}'s policy "{doc_label}" (retrieved {doc_version}, SHA-256
   {doc_sha}) states: "{commitment_quote}" — {doc_url}
2. Its funds voted {how_voted} ({shares_txt}) on: "{proposal}"
   (vote vs management: {mgmt_rec}).

We can provide the full evidence pack: archived policy versions, the vote
records as filed, and our methodology including what we exclude and why.
One follow-up at most; we track and publish institutional responses either way.
"""

_FIDUCIARY_TEMPLATE = """\
To: {official} ({jurisdiction})
From: Glasshouse (public-interest accountability project)
Date: {today}

Subject: Public comment for the record — proxy voting by {institution}, a manager
of public beneficiaries' assets

For the investment committee's public record:

1. {institution}'s published policy "{doc_label}" (retrieved {doc_version},
   SHA-256 {doc_sha}) states: "{commitment_quote}" ({doc_url})
2. SEC Form N-PX {accession} reports its funds voted {how_voted}
   ({shares_txt}) on: "{proposal}" at {issuer}, meeting of {meeting_date}.

Question for the record: has the committee assessed whether this voting record
is consistent with the policy on the basis of which the manager was retained?

All sources are public filings; we will publish any response verbatim.
"""

_DATA_OFFER_TEMPLATE = """\
To: {org}
From: Glasshouse (public-interest accountability project)
Date: {today}

Subject: Evidence pack offer — {institution} / {theme} ({issuer}, {meeting_date})

Your campaigns cover {focus}. We hold a documented, citable record that may
serve as a footnote in yours:

- {institution}'s archived policy language: "{commitment_quote}"
  ({doc_label}, retrieved {doc_version}, SHA-256 {doc_sha}, {doc_url})
- Its vote: {how_voted}, {shares_txt}, on "{proposal}" at {issuer}
  ({meeting_date}, SEC Form N-PX {accession}).

The full pack (machine-readable, with methodology and limitations) is yours
to use with attribution. No exclusivity, no conditions.
"""


def _contacts() -> dict:
    import yaml
    path = Path(__file__).resolve().parents[2] / "config" / "contacts.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _record(conn: sqlite3.Connection, kind: str, institution_id: str,
            subject: str, body: str, finding_fingerprint: str = "") -> int:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    stem = f"{date.today().isoformat()}_{kind}_{institution_id}_{abs(hash(subject)) % 10**8}"
    path = OUTBOX_DIR / f"{stem}.md"
    path.write_text(body)
    cur = conn.execute(
        "INSERT INTO outreach (kind, institution_id, subject, body_path, created_ts, "
        "finding_fingerprint) VALUES (?,?,?,?,?,?)",
        (kind, institution_id, subject, str(path), ts, finding_fingerprint))
    conn.commit()
    return cur.lastrowid


# The escalation ladder, in order. A finding moves down it one human-sent
# step at a time; `ladder()` reports where each finding stands.
LADDER = ("social_post", "pitch", "inquiry", "non_response", "fiduciary", "data_offer")


def ladder(conn: sqlite3.Connection) -> list[dict]:
    """Per finding: which escalation steps have been drafted/sent."""
    rows = conn.execute(
        """SELECT finding_fingerprint, kind, status, sent_date FROM outreach
           WHERE finding_fingerprint != '' ORDER BY finding_fingerprint, id""").fetchall()
    by_f: dict[str, dict] = {}
    for r in rows:
        f = by_f.setdefault(r["finding_fingerprint"], {"steps": {}})
        f["steps"][r["kind"]] = f"{r['status']}{' ' + r['sent_date'] if r['sent_date'] else ''}"
    out = []
    for fp, d in by_f.items():
        next_step = next((s for s in LADDER if s not in d["steps"]), None)
        out.append({"fingerprint": fp, "steps": d["steps"], "next": next_step})
    return out


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

    common = {
        "institution": institution, "today": date.today().isoformat(),
        "theme": candidate.theme, "doc_label": candidate.doc_label,
        "doc_version": candidate.doc_version, "doc_sha": candidate.doc_sha256,
        "commitment_quote": candidate.commitment_quote, "doc_url": candidate.doc_url,
        "accession": candidate.accession, "issuer": candidate.issuer_name,
        "meeting_date": candidate.meeting_date, "proposal": candidate.vote_description,
        "how_voted": candidate.how_voted,
        "shares_txt": shares_phrase(candidate.shares_voted),
        "mgmt_rec": vote_vs_mgmt(candidate.management_recommendation)}
    contacts = _contacts()

    if kind == "inquiry":
        body = _INQUIRY_TEMPLATE.format(
            subject=f"{candidate.theme} / {candidate.issuer_name}",
            deadline=deadline, **common)
    elif kind == "social_post":
        body = _POST_TEMPLATE.format(
            institution=institution, doc_version=candidate.doc_version,
            commitment_short=candidate.commitment_quote[:120],
            how_voted=candidate.how_voted,
            shares_sh=shares_phrase(candidate.shares_voted, "sh"),
            proposal_short=candidate.vote_description[:80],
            issuer=candidate.issuer_name, meeting_date=candidate.meeting_date,
            accession=candidate.accession)
    elif kind == "pitch":
        match = next((r for r in contacts.get("reporters") or []
                      if candidate.theme in (r.get("beats") or [])), None)
        body = _PITCH_TEMPLATE.format(
            reporter=match["name"] if match else "[CONTACT — add to config/contacts.yaml]",
            outlet=match["outlet"] if match else "[OUTLET]",
            beat=candidate.theme, **common)
    elif kind == "fiduciary":
        match = next(iter(contacts.get("officials") or []), None)
        body = _FIDUCIARY_TEMPLATE.format(
            official=match["name"] if match else "[OFFICIAL — add to config/contacts.yaml]",
            jurisdiction=match["jurisdiction"] if match else "[JURISDICTION]",
            **common)
    elif kind == "data_offer":
        match = next((o for o in contacts.get("advocacy_orgs") or []
                      if candidate.theme in (o.get("focus") or [])), None)
        body = _DATA_OFFER_TEMPLATE.format(
            org=match["name"] if match else "[ORG]",
            focus=", ".join(match.get("focus", [])) if match else "[FOCUS AREAS]",
            **common)
    else:
        raise ValueError(f"unknown draft kind {kind}")

    from .review import fingerprint
    subject = f"{candidate.theme}: {candidate.issuer_name} {candidate.meeting_date}"
    return _record(conn, kind, candidate.institution_id, subject, body,
                   finding_fingerprint=fingerprint(candidate))


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
