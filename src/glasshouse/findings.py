"""Phase-1 finding queries over the evidence ledger.

The full contradiction engine (SAY × DO) lands in Phase 3. What exists now
is the validated precursor: votes by tracked institutions at issuers with
documented enforcement records, joined precision-first (exact normalized
name; fuzzy joins only at FINDING_THRESHOLD and always logged).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .entities import normalize_name

# Heuristic for shareholder-proposal votes: management recommended AGAINST
# and the proposal text reads like a shareholder resolution.
_SHAREHOLDER_HINTS = (
    "shareholder proposal", "stockholder proposal", "shareholder resolution",
    "report on", "human rights", "civil rights", "lobbying", "political",
    "climate", "emissions", "diversity", "pay equity", "anti-corruption",
)


@dataclass
class FlaggedVote:
    institution: str
    issuer_name: str
    cusip: str
    meeting_date: str
    how_voted: str
    management_recommendation: str
    vote_description: str
    agency: str
    resolution_type: str
    primary_ref: str
    action_date: str
    join_method: str
    quarantined: bool


def flagged_votes(conn: sqlite3.Connection, *, shareholder_proposals_only: bool = False,
                  limit: int = 200) -> list[FlaggedVote]:
    """Votes at enforcement-flagged issuers (exact normalized-name join).

    EVERY row from this name-equality join is quarantined: identical
    normalized names can be different companies (validated 2026-06-11:
    OFAC's "ALDAR PROPERTIES", a Sudan-based SDGT designee, normalizes
    identically to Aldar Properties PJSC, the Abu Dhabi-listed developer).
    A row only becomes finding-grade once the join is corroborated by an
    identifier (CUSIP/LEI/CIK) or human verification. Rows whose
    enforcement record is itself unverified are doubly quarantined.
    """
    # Build normalized-name → enforcement rows map once (SQLite has no UDF here
    # without registration; registering keeps the join in SQL).
    conn.create_function("gh_norm", 1, normalize_name)

    sql = """
        SELECT COALESCE(i.display_name, f.cik) AS institution,
               v.issuer_name, v.cusip, v.meeting_date, v.how_voted,
               v.management_recommendation, v.vote_description,
               e.agency, e.resolution_type, e.primary_ref, e.action_date
        FROM votes v
        JOIN filings f ON f.accession = v.accession
        LEFT JOIN institutions i ON i.id = f.institution_id
        JOIN enforcement_actions e
          ON gh_norm(e.company_name) = gh_norm(v.issuer_name)
         AND gh_norm(v.issuer_name) != ''
        WHERE v.how_voted != ''
        ORDER BY e.resolution_type != 'unverified' DESC, v.meeting_date DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (limit,)).fetchall()
    out = []
    for r in rows:
        if shareholder_proposals_only:
            desc = (r["vote_description"] or "").lower()
            if not any(h in desc for h in _SHAREHOLDER_HINTS):
                continue
        out.append(FlaggedVote(
            institution=r["institution"], issuer_name=r["issuer_name"],
            cusip=r["cusip"], meeting_date=r["meeting_date"],
            how_voted=r["how_voted"],
            management_recommendation=r["management_recommendation"],
            vote_description=(r["vote_description"] or "")[:200],
            agency=r["agency"], resolution_type=r["resolution_type"],
            primary_ref=r["primary_ref"], action_date=r["action_date"],
            join_method="name_exact",
            quarantined=True,  # name-only join: lead, not finding
        ))
    return out
