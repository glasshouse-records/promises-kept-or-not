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
from .ledger import iso_meeting_date

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
    issuer_lei: str = ""       # GLEIF-corroborated issuer identity, when enriched
    issuer_country: str = ""


@dataclass
class OwnRecordRow:
    institution: str
    institution_id: str
    agency: str
    company_name: str          # as it appears in the enforcement record
    action_date: str
    resolution_type: str
    penalty_usd: int
    primary_ref: str
    description: str
    source_url: str
    quarantined: bool          # always True: name join + needs subsidiary check


def own_record(conn: sqlite3.Connection) -> list[OwnRecordRow]:
    """Finding class (c): the tracked institutions' OWN enforcement records.

    An institution's rap sheet vs. its marketing is a first-class finding.
    Joined by exact normalized name against the registry's display name —
    quarantined like every name join, and doubly so here because enforcement
    often names a subsidiary (e.g. a securities arm) rather than the parent;
    a human must confirm the corporate relationship before use.
    """
    conn.create_function("gh_norm", 1, normalize_name)
    rows = conn.execute(
        """SELECT i.display_name AS institution, i.id AS institution_id,
                  e.agency, e.company_name, e.action_date, e.resolution_type,
                  e.penalty_usd, e.primary_ref, e.description, e.source_url
           FROM institutions i
           JOIN enforcement_actions e
             ON gh_norm(e.company_name) = gh_norm(i.display_name)
           WHERE e.is_duplicate = 0
             -- OFAC SDN designations name WHO is sanctioned (adversaries,
             -- vessels, aliases). A tracked mainstream manager appearing there
             -- by normalized name is a collision (the Aldar lesson), not its
             -- own record — exclude. Real OFAC penalties use other types.
             AND e.resolution_type != 'sanction_designation'
           ORDER BY i.display_name, e.action_date DESC""").fetchall()
    return [OwnRecordRow(**dict(r), quarantined=True) for r in rows]


@dataclass
class VoteDivergence:
    institution: str
    issuer_name: str
    cusip: str
    meeting_date: str
    vote_description: str
    ways: dict[str, float]          # how_voted -> total shares voted that way
    n_records: int


def vote_divergence(conn: sqlite3.Connection, *, shareholder_proposals_only: bool = False,
                    limit: int = 100) -> list[VoteDivergence]:
    """Finding class (b), validated 2026-06-10: the same manager's funds
    voting BOTH ways on an identical proposal (same issuer, meeting, text).

    No external join, no entity-resolution risk — the contradiction is
    internal to one filer's own N-PX report, which makes these the cleanest
    finding-grade rows in Phase 1. Split votes inside a single proxyTable
    (multiple voteRecords) and splits across a manager's filings both count.
    """
    sql = """
        SELECT COALESCE(i.display_name, f.cik) AS institution,
               v.issuer_name, v.cusip, v.meeting_date, v.vote_description,
               COUNT(*) AS n_records,
               COUNT(DISTINCT v.how_voted) AS n_ways
        FROM votes v
        JOIN filings f ON f.accession = v.accession
        LEFT JOIN institutions i ON i.id = f.institution_id
        WHERE v.how_voted != '' AND v.is_duplicate = 0
        GROUP BY institution, v.cusip, v.meeting_date, v.vote_description
        HAVING n_ways > 1
        ORDER BY n_records DESC
        LIMIT ?
    """
    out = []
    for r in conn.execute(sql, (limit,)).fetchall():
        if shareholder_proposals_only:
            desc = (r["vote_description"] or "").lower()
            if not any(h in desc for h in _SHAREHOLDER_HINTS):
                continue
        shares = conn.execute(
            """SELECT v.how_voted, SUM(v.shares_voted) AS total
               FROM votes v JOIN filings f ON f.accession = v.accession
               LEFT JOIN institutions i ON i.id = f.institution_id
               WHERE COALESCE(i.display_name, f.cik) = ? AND v.cusip = ?
                 AND v.meeting_date = ? AND v.vote_description = ? AND v.how_voted != '' AND v.is_duplicate = 0
               GROUP BY v.how_voted""",
            (r["institution"], r["cusip"], r["meeting_date"], r["vote_description"]),
        ).fetchall()
        out.append(VoteDivergence(
            institution=r["institution"], issuer_name=r["issuer_name"],
            cusip=r["cusip"], meeting_date=r["meeting_date"],
            vote_description=(r["vote_description"] or "")[:200],
            ways={s["how_voted"]: s["total"] or 0.0 for s in shares},
            n_records=r["n_records"],
        ))
    return out


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
               e.agency, e.resolution_type, e.primary_ref, e.action_date,
               COALESCE(ent.lei, '') AS issuer_lei,
               COALESCE(ent.country, '') AS issuer_country
        FROM votes v
        JOIN filings f ON f.accession = v.accession
        LEFT JOIN institutions i ON i.id = f.institution_id
        LEFT JOIN entity_cusips ec ON ec.cusip = v.cusip
        LEFT JOIN entities ent ON ent.id = ec.entity_id
        JOIN enforcement_actions e
          ON gh_norm(e.company_name) = gh_norm(v.issuer_name)
         AND gh_norm(v.issuer_name) != ''
        WHERE v.how_voted != '' AND v.is_duplicate = 0
          -- OFAC SDN designations name WHO is sanctioned; matching a voted
          -- portfolio issuer to one by name alone is the documented Aldar
          -- false-positive class ("ALDAR PROPERTIES" SDN ≠ Aldar PJSC). Drop
          -- them from this name-join (43 pure collisions in the live data).
          AND e.resolution_type != 'sanction_designation'
        ORDER BY e.resolution_type != 'unverified' DESC, {ISO_V} DESC
        LIMIT ?
    """.format(ISO_V=iso_meeting_date("v.meeting_date"))
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
            issuer_lei=r["issuer_lei"], issuer_country=r["issuer_country"],
        ))
    return out
