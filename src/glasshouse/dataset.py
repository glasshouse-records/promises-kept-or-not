"""The dataset as a first-class, self-describing product.

The core deliverable is the published evidence dataset — and a dataset others
cite must document its own schema, provenance, coverage, and honest limits.
This module generates, from the live ledger:
  - a coverage report (what's actually in, per institution, with date ranges)
  - a data dictionary (the public table/column contract + provenance fields)
  - a human DATASHEET.md and a machine-readable datapackage.json

All of it is generated from the data, never hand-maintained, so it can't drift
out of sync with reality. Bundled alongside the public snapshot by
`glasshouse export`.
"""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import date

from . import __version__
from .ledger import iso_meeting_date
from .publish import PUBLIC_TABLES

# Per-table, per-column human descriptions — the public contract. Only public
# tables (publish.PUBLIC_TABLES) are documented; operator tables never ship.
DATA_DICTIONARY: dict[str, dict] = {
    "institutions": {"_": "Tracked institutions (registry).",
        "id": "stable slug", "display_name": "legal name", "cik": "SEC CIK",
        "type": "bank | asset_manager | …", "country": "ISO country"},
    "filings": {"_": "SEC filings ingested (N-PX, 13F-HR, NPORT-P).",
        "accession": "SEC accession (primary key)", "cik": "filer CIK",
        "institution_id": "→ institutions.id", "form_type": "SEC form",
        "filing_date": "date filed", "period_of_report": "reporting period",
        "source_url": "EDGAR directory (provenance)", "retrieval_date": "when fetched"},
    "votes": {"_": "Proxy votes from N-PX, one row per voteRecord. "
        "ALWAYS filter is_duplicate = 0 before aggregating shares_voted.",
        "accession": "→ filings.accession", "issuer_name": "company voted on",
        "cusip": "security CUSIP", "isin": "security ISIN", "meeting_date": "meeting date",
        "vote_description": "verbatim proposal text", "how_voted": "FOR/AGAINST/ABSTAIN/…",
        "shares_voted": "shares cast", "management_recommendation": "as filed (KNOWN-UNRELIABLE)",
        "is_duplicate": "1 = as-filed duplicate, exclude from analytics"},
    "holdings": {"_": "13-F / N-PORT holdings (full USD).",
        "accession": "→ filings.accession", "issuer_name": "company held",
        "cusip": "security CUSIP", "value_usd": "position value (full dollars)",
        "shares": "share/principal amount"},
    "enforcement_actions": {"_": "Enforcement universe. resolution_type is "
        "legally material; is_duplicate excludes curated/live overlaps.",
        "agency": "issuing body", "company_name": "respondent",
        "action_date": "date", "resolution_type": "guilty_plea/dpa/npa/… (closed enum)",
        "penalty_usd": "penalty", "primary_ref": "agency reference number",
        "source_url": "provenance", "retrieval_date": "when fetched",
        "source_kind": "live | curated_snapshot", "is_duplicate": "exclude when 1"},
    "commitments": {"_": "Versioned, content-addressed policy snapshots (live + Wayback).",
        "institution_id": "→ institutions.id", "doc_label": "document",
        "url": "source URL", "sha256": "content hash", "retrieval_date": "when fetched",
        "wayback_timestamp": "'' = live fetch, else Wayback ts", "size_bytes": "size"},
    "findings": {"_": "HUMAN-APPROVED findings only (status='approved'). The "
        "verified, citable claims; everything unreviewed stays operator-side.",
        "fingerprint": "stable id", "theme": "theme", "institution_id": "→ institutions.id",
        "reviewer_note": "why a human approved it", "reviewed_date": "approval date",
        "payload": "JSON citation chain (say + did)"},
    "fund_series": {"_": "N-PX fund series with LEIs.", "series_id": "series id",
        "accession": "→ filings.accession", "name": "series name", "lei": "series LEI"},
    "entities": {"_": "Resolved issuer identities (GLEIF-enriched).",
        "canonical_name": "legal name", "lei": "LEI", "country": "country"},
    "entity_cusips": {"_": "CUSIP → entity map.", "cusip": "CUSIP", "entity_id": "→ entities.id"},
}


# Coverage bounds are PUBLISHED — they tell a consumer the dataset's real
# boundaries. Sorted as stored they were off by six months.
_ISO = iso_meeting_date("v.meeting_date")


# The kinds of vote a shipped line can be, in display order. Computed from the
# filed N-PX fields (vote_source, category_type), never from our own matching.
_KINDS = ("shareholder_proposals", "director_elections", "say_on_pay", "management_other")
_KIND_SQL = ("CASE WHEN IFNULL(v.vote_source,'')='SECURITY HOLDER' THEN 'shareholder_proposals' "
             "WHEN IFNULL(v.category_type,'')='DIRECTOR ELECTIONS' THEN 'director_elections' "
             "WHEN IFNULL(v.category_type,'')='SECTION 14A SAY-ON-PAY VOTES' THEN 'say_on_pay' "
             "ELSE 'management_other' END")
_KIND_LABEL = {"shareholder_proposals": "shareholder proposals",
               "director_elections": "director elections", "say_on_pay": "say-on-pay",
               "management_other": "other management proposals"}


def _kinds_note(kinds: list[str]) -> str:
    if not kinds:
        return "no votes shipped"
    names = [_KIND_LABEL[k] for k in kinds]
    if len(kinds) == 1:
        return (f"{names[0]} votes only: the shipped votes for this institution do not "
                "include the other kinds of vote, so this is not its full voting record")
    return "shipped vote kinds: " + ", ".join(names)


def coverage(conn: sqlite3.Connection) -> list[dict]:
    """Honest per-institution coverage of the rows that SHIP. Every vote figure
    is computed over publish.PUBLIC_TABLES['votes'] (the very filter the release
    applies), so it equals the row count of the emitted votes file. Counting the
    raw ledger published 3,809,093 BlackRock lines beside 3,669,405 shipped."""
    rows = []
    shipped_votes = f"(SELECT * FROM votes {PUBLIC_TABLES['votes']})"
    for inst in conn.execute("SELECT id, display_name FROM institutions ORDER BY id"):
        npx = conn.execute(
            f"SELECT COUNT(DISTINCT f.accession) n, MIN({_ISO}) lo, "
            f"MAX({_ISO}) hi, COUNT(*) rows FROM filings f "
            f"JOIN {shipped_votes} v ON v.accession=f.accession "
            "WHERE f.institution_id=?", (inst["id"],)).fetchone()
        by_kind = {r["k"]: r["n"] for r in conn.execute(
            f"SELECT {_KIND_SQL} k, COUNT(*) n FROM filings f "
            f"JOIN {shipped_votes} v ON v.accession=f.accession "
            "WHERE f.institution_id=? GROUP BY k", (inst["id"],))}
        kinds = [k for k in _KINDS if by_kind.get(k)]
        hold = conn.execute(
            "SELECT COUNT(*) FROM holdings h JOIN filings f ON f.accession=h.accession "
            "WHERE f.institution_id=?", (inst["id"],)).fetchone()[0]
        docs = conn.execute(
            # Version identity is the policy TEXT: counting distinct bytes
            # published 63 "versions" where the archive holds 51.
            "SELECT COUNT(DISTINCT CASE WHEN text_sha256='' THEN 'raw:'||sha256 ELSE text_sha256 END) "
            "FROM commitments WHERE institution_id=?",
            (inst["id"],)).fetchone()[0]
        # How many of this institution's archived policies carry a date written
        # by ITS OWN software. That is the only dating evidence in the corpus
        # that is not ours or the Internet Archive's, so a consumer deciding how
        # far to trust our timeline needs to see it per institution.
        # Counted over the SAME identity as policy_versions. Counting captures
        # here instead published "7 self-dated of 5 versions".
        dated = conn.execute(
            "SELECT COUNT(DISTINCT CASE WHEN text_sha256='' THEN 'raw:'||sha256 "
            "ELSE text_sha256 END) FROM commitments WHERE institution_id=? "
            "AND doc_created_at != ''", (inst["id"],)).fetchone()[0]
        if not (npx["n"] or hold or docs):
            continue  # registered but not yet ingested — omit from coverage
        rows.append({
            "institution": inst["display_name"],
            "npx_filings": npx["n"] or 0, "votes": npx["rows"] or 0,
            "vote_dates": f"{npx['lo']} → {npx['hi']}" if npx["lo"] else "—",
            "vote_kinds": kinds, "vote_kinds_note": _kinds_note(kinds),
            "votes_by_kind": {k: by_kind[k] for k in kinds},
            "holdings": hold, "policy_versions": docs,
            "policies_self_dated": dated})
    return rows


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for t, where in PUBLIC_TABLES.items():
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t} {where}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = 0
    return out


def build_datapackage(conn: sqlite3.Connection) -> dict:
    """Frictionless-style descriptor so the dataset is machine-self-describing."""
    counts = _counts(conn)
    resources = []
    for table, fields in DATA_DICTIONARY.items():
        resources.append({
            "name": table, "rowCount": counts.get(table, 0),
            "description": fields.get("_", ""),
            "schema": {"fields": [{"name": k, "description": v}
                                  for k, v in fields.items() if k != "_"]},
        })
    return {
        "name": "glasshouse-evidence", "version": __version__,
        "title": "Glasshouse — institutional accountability evidence dataset",
        "description": "What major financial institutions say (archived policies) "
                       "vs. do (SEC N-PX votes, 13-F/N-PORT holdings) and the "
                       "enforcement record. Public, primary-source-cited, deduplicated.",
        "licenses": [{"name": "CC-BY-4.0",
                      "path": "https://creativecommons.org/licenses/by/4.0/"}],
        "created": date.today().isoformat(), "git_commit": _git_commit(),
        "provenance_guarantees": [
            "Every record carries source_url + retrieval_date.",
            "votes/enforcement de-duplicated; filter is_duplicate = 0.",
            "Enforcement resolution_type is from a closed legal enum; "
            "dockets are allegations; ambiguous rows are 'unverified'.",
            "findings contains ONLY human-approved claims.",
            "Contradiction findings quote the policy version in force at the vote date.",
        ],
        "resources": resources,
    }


def build_datasheet(conn: sqlite3.Connection) -> str:
    pkg = build_datapackage(conn)
    cov = coverage(conn)
    lines = [
        "# Glasshouse evidence dataset — datasheet", "",
        f"Version {pkg['version']} · generated {pkg['created']} · commit {pkg['git_commit']} · "
        "license CC-BY-4.0", "",
        pkg["description"], "",
        "## Provenance guarantees",
        *[f"- {g}" for g in pkg["provenance_guarantees"]],
        "", "## Coverage (what is actually in this snapshot — partial by design)",
        "", "Every figure below counts the rows shipped in `facts/` (the release filter is "
        "applied first: de-duplicated, validated, cast votes only), not the working ledger.",
        "", "| Institution | N-PX filings | votes | vote dates | kinds of votes shipped "
        "| holdings | policy versions |",
        "|---|--:|--:|---|---|--:|--:|",
        *[f"| {r['institution']} | {r['npx_filings']} | {r['votes']:,} | {r['vote_dates']} "
          f"| {r['vote_kinds_note']} | {r['holdings']:,} | {r['policy_versions']} |"
          for r in cov],
        "", "_Institutions in the registry but not yet ingested are omitted — "
        "absence here means no data, not a clean record._", "",
        "## Tables", "",
    ]
    for res in pkg["resources"]:
        lines.append(f"### `{res['name']}` ({res['rowCount']:,} rows)")
        lines.append(res["description"])
        for f in res["schema"]["fields"]:
            lines.append(f"- **{f['name']}** — {f['description']}")
        lines.append("")
    lines += [
        "## How to read this dataset (please read before citing)",
        "- This is a **factual compilation** from primary sources (SEC N-PX / 13-F / "
        "N-PORT, archived policies, public enforcement records). It records acts, "
        "dates, amounts, and votes — it makes **no claims about motive or intent**.",
        "- Any say-vs-do gap derived from it is a **LEAD, not a finding**: theme "
        "matching is lexical, so confirm each proposal's text and intent, and the "
        "in-force policy version, against the linked primary source before publishing.",
        "- The `findings` table contains only claims a human reviewer approved "
        f"(currently {next((r['rowCount'] for r in pkg['resources'] if r['name'] == 'findings'), 0)}). "
        "Everything unreviewed stays out of this dataset.",
        "- `aum_usd_tr` (in any derived analysis) is **managed / voting AUM**, never "
        "balance-sheet or custody assets.",
        "",
        "## Corrections",
        "Found an error? Please open an issue at the project repository (or contact the "
        "maintainer) with the table, the row, and the primary-source link. Provenance "
        "is the core value — corrections are welcomed and versioned.",
        "",
        "## Limitations", "See METHODOLOGY.md for the full source list, the "
        "resolution-type table, the say-vs-do precision rules, and known-blocked "
        "sources. This is a partial, growing snapshot; the coverage table above states "
        "the current boundary — absence means uncollected, not clean.",
        "",
        f"_License: data CC-BY-4.0. Cite as: Glasshouse evidence dataset, v{pkg['version']} "
        f"(commit {pkg['git_commit']}), {pkg['created']}._",
    ]
    return "\n".join(lines) + "\n"
