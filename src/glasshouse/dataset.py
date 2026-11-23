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
from pathlib import Path

from . import __version__
from .contradictions import distinct_versions
from .ledger import iso_meeting_date
from .publish import PUBLIC_TABLES

# Per-table, per-column human descriptions — the public contract. Only public
# tables (publish.PUBLIC_TABLES) are documented; operator tables never ship.
DATA_DICTIONARY: dict[str, dict] = {
    "institutions": {"_": "Tracked institutions (registry).",
        "id": "stable slug used by every other table (institution_id)",
        "display_name": "legal or common name of the institution",
        "cik": "SEC Central Index Key of the institution itself, as recorded in the registry",
        "type": "kind of institution, e.g. asset_manager or bank",
        "country": "ISO country code of the institution"},
    "filings": {"_": "SEC filings ingested (N-PX, 13F-HR, NPORT-P). This is where `votes`, "
        "`holdings` and `fund_series` rows get their source_url and retrieval_date "
        "(join on accession).",
        "accession": "SEC accession number of the filing (primary key)",
        "cik": "CIK of the filer (the registrant that filed it), with leading zeros",
        "institution_id": "→ institutions.id: the tracked institution this filer belongs to",
        "form_type": "SEC form type, e.g. N-PX, 13F-HR, NPORT-P",
        "filing_date": "date the filing was filed with the SEC",
        "period_of_report": "period of report, as filed",
        "report_type": "as filed in N-PX cover field reportType (e.g. FUND VOTING REPORT, "
                       "FUND NOTICE REPORT, INSTITUTIONAL MANAGER VOTING REPORT); LEGACY_NO_COVER "
                       "= pre-2024 filing with no structured cover, skipped; LEGACY_PARSED = such a "
                       "filing read from HTML (its votes are not shipped); LEGACY_PROXYEDGE, LEGACY_ISS, "
                       "LEGACY_ISSHTML = 2022-23 text filings read by two agreeing parsers, and "
                       "the same with _REJECTED when the agreement gate failed or nothing "
                       "parsed (votes quarantined, not shipped; see METHODOLOGY.md); NULL for 13-F and "
                       "N-PORT filings",
        "source_url": "EDGAR directory of the filing (primary source)",
        "retrieval_date": "date Glasshouse fetched the filing",
        "partial": "1 if a limited smoke run stopped before the filing's last table (votes incomplete, replaced on the next ingest); 0 for a complete filing",
        "notes": "free-text note; no ingester writes it, so it is empty in every row"},
    "votes": {"_": "Proxy votes from N-PX, one row per voteRecord (de-duplicated, cast votes "
        "only). Carries no source_url or retrieval_date: join votes.accession → "
        "filings.accession for them. ALWAYS filter is_duplicate = 0 before aggregating "
        "shares_voted (the release already does).",
        "id": "row id in the Glasshouse ledger (an integer assigned at ingest, not an SEC "
              "identifier); derived tables cite it as vote_id",
        "accession": "→ filings.accession: the N-PX filing this line came from",
        "issuer_name": "company voted on, as filed",
        "cusip": "security CUSIP, as filed; on legacy rows (legacy_format set) kept only when "
                 "its check digit validates, else empty",
        "isin": "security ISIN, as filed; on legacy rows kept only when its check digit "
                "validates, else empty",
        "meeting_date": "meeting date as filed, M/D/YYYY text (07/11/2024 or 7/11/2024), not ISO",
        "vote_description": "verbatim proposal text as filed",
        "category_type": "as filed in N-PX field categoryType: the SEC's subject category of the "
                         "item (e.g. DIRECTOR ELECTIONS, SECTION 14A SAY-ON-PAY VOTES, "
                         "CAPITAL STRUCTURE); '' on legacy rows (legacy_format set): the 2022-23 "
                         "text filings print no N-PX category and Glasshouse does not derive one",
        "vote_source": "as filed in N-PX field voteSource: ISSUER (put on the ballot by the "
                       "issuer) or SECURITY HOLDER (shareholder proposal); empty where the "
                       "filer left it blank (see Code lists). On legacy rows: taken from the "
                       "printed sponsor of the item",
        "shares_on_loan": "as filed in N-PX field sharesOnLoan: shares on loan; 0 where not filed",
        "vote_series": "as filed in N-PX field voteSeries: id of the fund series that cast the "
                       "vote (S000…); joins to fund_series.series_id; empty where not filed",
        "how_voted": "as filed in N-PX field howVoted: FOR, AGAINST, WITHHOLD, ABSTAIN or "
                     "another code as filed (see Code lists). Legacy rows (legacy_format set) "
                     "are normalised to the XML spellings",
        "shares_voted": "shares cast on this line, as filed. NULL on legacy rows (legacy_format "
                        "set): the 2022-23 text layouts print no share counts, so the engine "
                        "weights those decisions by line count (see proposal_decisions.weight_basis)",
        "management_recommendation": "as filed in N-PX; engine.py reads it as whether THIS vote "
                                     "went with (FOR) or against (AGAINST) management, not what "
                                     "management recommended: KNOWN-UNRELIABLE, do not rely on it. "
                                     "On legacy rows: copied from ProxyEdge's printed For/Against "
                                     "Management column, or, in the ISS layouts, computed from the "
                                     "printed recommendation and the vote (see METHODOLOGY); FOR, "
                                     "AGAINST or empty",
        "legacy_format": "NULL = a line from an SEC XML N-PX filing. 'proxyedge', 'iss_text', "
                         "'iss_html' or 'issueno' = a line from a 2022-23 (July 2022 - June 2023) text filing "
                         "read by two independent parsers that agreed on it; see METHODOLOGY "
                         "('Legacy N-PX, July 2022 - June 2023'). Such lines have no share counts "
                         "and no category",
        "for_against_management": "ProxyEdge's printed For/Against Management column, as printed; "
                                  "NULL except on 'proxyedge' legacy rows",
        "is_duplicate": "1 = as-filed duplicate of another line; always 0 in the release, "
                        "which excludes duplicates"},
    "holdings": {"_": "13-F / N-PORT holdings (full USD). No source_url or retrieval_date: "
        "join holdings.accession → filings.accession.",
        "id": "row id in the Glasshouse ledger (not an SEC identifier)",
        "accession": "→ filings.accession: the filing this position came from",
        "issuer_name": "company held, as filed",
        "cusip": "security CUSIP, as filed",
        "title_class": "as filed in 13-F infoTable field titleOfClass: title of the security class",
        "value_usd": "position value in full US dollars",
        "shares": "share or principal amount, as filed",
        "shares_type": "as filed in 13-F infoTable field sshPrnamtType: SH = shares, "
                       "PRN = principal amount",
        "put_call": "as filed in 13-F infoTable field putCall; empty for non-option positions",
        "discretion": "as filed in 13-F infoTable field investmentDiscretion",
        "voting_sole": "as filed in 13-F votingAuthority field Sole: shares with sole voting authority",
        "voting_shared": "as filed in 13-F votingAuthority field Shared: shares with shared "
                         "voting authority",
        "voting_none": "as filed in 13-F votingAuthority field None: shares with no voting authority"},
    "enforcement_actions": {"_": "Enforcement universe. resolution_type is "
        "legally material; is_duplicate excludes curated/live overlaps.",
        "id": "row id in the Glasshouse ledger (not an agency identifier)",
        "agency": "issuing body",
        "company_name": "respondent, as named by the agency",
        "action_date": "date of the action",
        "resolution_type": "guilty_plea/dpa/npa/… (closed enum in ledger.py; allegation = pending "
                           "docket, unverified = not yet checked by a human)",
        "penalty_usd": "penalty in US dollars, where the source states one",
        "primary_ref": "agency reference number",
        "description": "description of the action, from the source",
        "source_url": "primary source of the row (provenance)",
        "retrieval_date": "date Glasshouse fetched the source",
        "source_kind": "live | curated_snapshot",
        "is_allegation": "1 = a pending docket, never to be reported as a finding",
        "is_duplicate": "1 = overlaps another row; always 0 in the release"},
    "commitments": {"_": "Versioned, content-addressed policy snapshots (live + Wayback).",
        "id": "row id in the Glasshouse ledger; policy_versions.commitment_id points here",
        "institution_id": "→ institutions.id", "doc_label": "label of the policy document",
        "url": "URL the document was fetched from", "sha256": "SHA-256 of the file bytes",
        "retrieval_date": "date Glasshouse fetched it",
        "content_type": "HTTP content type of the file when fetched",
        "wayback_timestamp": "'' = live fetch, else Wayback Machine capture timestamp",
        "size_bytes": "file size in bytes",
        "text_sha256": "SHA-256 of the raw extracted text as captured; '' if no text could "
                       "be extracted (edgar-sai: hash of the section text with all whitespace "
                       "removed). NOT the version identity: see identity_sha256",
        "identity_sha256": "SHA-256 of the text a policy version is identified by: the "
                           "label's configured `body` span if any, whitespace-normalised, no "
                           "whitespace before a trademark sign or percent sign, ASCII quotes and one dash form "
                           "(see METHODOLOGY); '' = unreadable. Captures sharing it are one "
                           "version. A declared reprint (reprint_of) carries the identity of "
                           "the edition it reprints",
        "identity_version": "version of the identity normaliser identity_sha256 was computed "
                            "under; a stale row is recomputed from its file",
        "reprint_of": "0, or the id of the earlier capture this one is a declared reprint of "
                      "(config `reprints`, with a written reason): kept as a capture, not a "
                      "new version",
        "doc_created_at": "creation date written inside the PDF by the manager's own software; "
                          "'' if none",
        "doc_modified_at": "modification date written inside the PDF; '' if none",
        "doc_producer": "software named in the PDF's producer metadata; '' if none",
        "public_by": "edgar-sai versions only: filing date of the earliest EDGAR filing "
                     "carrying this text (public by then; not the date it was written); '' otherwise",
        "superseded": "internal: 1 = replaced by a rebuild; never shipped (always 0 here)",
        "via": "'' = the manager's own URL; 'edgar-sai' = section extracted from a fund SAI "
               "on EDGAR (url is that SAI document)"},
    "findings": {"_": "HUMAN-APPROVED findings only (status='approved'). The "
        "verified, citable claims; everything unreviewed stays operator-side.",
        "id": "row id in the Glasshouse ledger",
        "fingerprint": "stable id of the underlying candidate", "theme": "theme of the finding",
        "institution_id": "→ institutions.id",
        "status": "review status; only 'approved' rows are shipped",
        "reviewer_note": "why a human approved it", "reviewed_date": "approval date",
        "payload": "JSON citation chain (say + did), frozen at review time"},
    "fund_series": {"_": "N-PX fund series with LEIs. Join from votes on "
        "votes.vote_series = fund_series.series_id AND votes.accession = fund_series.accession.",
        "series_id": "SEC series id (S000…) as filed in the N-PX cover",
        "accession": "→ filings.accession", "name": "series name as filed",
        "lei": "series LEI as filed; empty if none"},
    "entities": {"_": "Resolved issuer identities (GLEIF-enriched).",
        "id": "row id in the Glasshouse ledger; entity_cusips.entity_id points here",
        "canonical_name": "legal name", "normalized_name": "canonical_name lower-cased and "
        "stripped of punctuation and legal suffixes, used for matching",
        "cik": "SEC CIK of the entity where known", "lei": "Legal Entity Identifier",
        "country": "country of the entity"},
    "entity_cusips": {"_": "CUSIP → entity map.", "cusip": "security CUSIP", "entity_id": "→ entities.id"},
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


def coverage_vote_sql() -> tuple[str, str]:
    """The two per-institution vote queries of `coverage` (parameter: institution id).
    The institution's votes are reached through its filings' accessions, so SQLite
    uses the votes.accession index; joining filings to a subquery over all shipped
    votes scanned all 26M lines twice per institution (2026-11-20, >2 h)."""
    shipped = (f"(SELECT * FROM votes {PUBLIC_TABLES['votes']} AND accession IN "
               f"(SELECT accession FROM filings WHERE institution_id = ?))")
    return (f"SELECT COUNT(DISTINCT acc) n, MIN(iso) lo, MAX(iso) hi, COUNT(*) rows "
            f"FROM (SELECT v.accession AS acc, {_ISO} AS iso FROM {shipped} v)",
            f"SELECT {_KIND_SQL} k, COUNT(*) n FROM {shipped} v GROUP BY k")


def coverage(conn: sqlite3.Connection) -> list[dict]:
    """Honest per-institution coverage of the rows that SHIP. Every vote figure
    is computed over publish.PUBLIC_TABLES['votes'] (the very filter the release
    applies), so it equals the row count of the emitted votes file. Counting the
    raw ledger published 3,809,093 BlackRock lines beside 3,669,405 shipped."""
    rows = []
    npx_sql, kind_sql = coverage_vote_sql()
    for inst in conn.execute("SELECT id, display_name FROM institutions ORDER BY id"):
        npx = conn.execute(npx_sql, (inst["id"],)).fetchone()
        by_kind = {r["k"]: r["n"] for r in conn.execute(kind_sql, (inst["id"],))}
        kinds = [k for k in _KINDS if by_kind.get(k)]
        hold = conn.execute(
            "SELECT COUNT(*) FROM holdings h JOIN filings f ON f.accession=h.accession "
            "WHERE f.institution_id=?", (inst["id"],)).fetchone()[0]
        # Version identity is the policy TEXT (shared helper): counting distinct
        # bytes published 63 "versions" where the archive holds 51.
        docs = len(distinct_versions(conn, "institution_id=?", (inst["id"],)))
        # How many of this institution's archived policies carry a date written
        # by ITS OWN software. That is the only dating evidence in the corpus
        # that is not ours or the Internet Archive's, so a consumer deciding how
        # far to trust our timeline needs to see it per institution.
        # Counted over the SAME identity as policy_versions. Counting captures
        # here instead published "7 self-dated of 5 versions".
        dated = len(distinct_versions(
            conn, "institution_id=? AND doc_created_at != ''", (inst["id"],)))
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


UNREADABLE_DATE_SEASON = "date not machine-readable"
# Shown in the datasheet; each must really be unreadable (tested).
UNREADABLE_DATE_EXAMPLES = ("30/07/2023", "02/30/2024")
# A meeting date that is not ISO with a real month after normalisation (as filed: YYYYMMDD,
# day-first, impossible months) is counted under one label, never cut into a fake season.
_SEASON_SQL = ("CASE WHEN iso IS NULL OR iso = '' THEN 'undated' "
               "WHEN NOT (iso GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]' "
               "AND substr(iso,6,2) BETWEEN '01' AND '12') "
               f"THEN '{UNREADABLE_DATE_SEASON}' "
               "WHEN substr(iso,6,2) >= '07' THEN substr(iso,1,4) || '-' || "
               "substr(CAST(substr(iso,1,4) + 1 AS TEXT),3,2) "
               "ELSE CAST(substr(iso,1,4) - 1 AS TEXT) || '-' || substr(iso,3,2) END")


def season_coverage_sql() -> str:
    """The season table's query. The date is read once per row (inner query), then cut
    into seasons; pasting the reading into every branch stalled a release for hours."""
    return (f"SELECT {_SEASON_SQL} AS season, SUM(lf IS NOT NULL) AS legacy_lines, "
            f"SUM(lf IS NULL) AS xml_lines FROM (SELECT {_ISO} AS iso, v.legacy_format AS lf "
            f"FROM votes v {PUBLIC_TABLES['votes'].replace('WHERE ', 'WHERE v.', 1)}) "
            f"GROUP BY season ORDER BY season")


def season_coverage(conn: sqlite3.Connection) -> list[dict]:
    """Shipped vote lines per N-PX season (meetings 1 July to 30 June, e.g. 2022-23 =
    2022-07-01..2023-06-30), split into legacy lines (legacy_format set: 2022-23 text
    filings, two agreeing parsers) and XML lines. Over the same filter the release applies."""
    rows = conn.execute(season_coverage_sql()).fetchall()
    return [{"season": r["season"], "legacy_lines": r["legacy_lines"] or 0,
             "xml_lines": r["xml_lines"] or 0} for r in rows]


def known_gaps(conn: sqlite3.Connection) -> list[str]:
    """What the 2022-23 legacy lines do NOT contain, so absence is never read as a clean record.
    Counts come from the parse log at build time."""
    p = conn.execute(
        "SELECT COUNT(DISTINCT accession) n, "
        "COALESCE(SUM(IFNULL(rows_dropped_disputed,0) + IFNULL(rows_dropped_order,0)),0) d, "
        "SUM(IFNULL(funds_unmapped,'') != '') u FROM legacy_parse").fetchone()
    return [
        "Layouts not parsed, so those filings contribute no 2022-23 lines: Fidelity's own "
        "tables, the Federated flat table, Neuberger Berman / Franklin 'Issue No.' filings, "
        "Diamond Hill and Dodge & Cox.",
        f"Fund headings that could not be mapped to a fund series are dropped ({p['u'] or 0} of "
        f"{p['n'] or 0} parsed legacy documents had unmapped headings).",
        f"Lines the two parsers disputed, or that broke the row-order guard, are dropped "
        f"({p['d']:,} lines across the parse log): precision over recall.",
        "Proxy contests (a dissident card beside management's) are dropped.",
        "Vanguard's pilot policy sections are dropped.",
        "Legacy lines carry no share counts: `shares_voted` is NULL, and every legacy "
        "decision is line-weighted (`weight_basis` = 'lines'), unlike the share-weighted "
        "decisions from July 2023.",
        "Legacy lines carry no N-PX category (`category_type` is ''), so 2022-23 meetings do "
        "not appear in the director-election or say-on-pay tables.",
        "De-duplication collapses same-direction lines of one fund, so line counts are not "
        "comparable across eras (a legacy line count and an XML line count measure different "
        "things).",
    ]


def git_state(repo: Path | str | None = None) -> dict:
    """The commit actually checked out in `repo` (default: this repository) and whether
    the working tree differs from it. An untracked file counts as dirty: it can change
    what the code does. {"commit": "unknown", "dirty": None} when git cannot say."""
    repo = Path(repo) if repo else Path(__file__).resolve().parents[2]

    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, timeout=30, check=True).stdout
    try:
        return {"commit": run("rev-parse", "HEAD").strip() or "unknown",
                "dirty": bool(run("status", "--porcelain").strip())}
    except Exception:
        return {"commit": "unknown", "dirty": None}


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
    git = git_state()
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
        "created": date.today().isoformat(), "git_commit": git["commit"][:7],
        "git": git,
        "provenance_guarantees": [
            "Provenance columns: `filings` and `enforcement_actions` rows carry source_url + "
            "retrieval_date; `commitments` rows carry url + retrieval_date. `votes`, `holdings` "
            "and `fund_series` rows carry neither: each links by accession to its `filings` row "
            "(votes.accession = filings.accession), which does.",
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
        f"Version {pkg['version']} · generated {pkg['created']} · commit {pkg['git_commit']}"
        f"{' (working tree dirty)' if pkg['git']['dirty'] else ''} · license CC-BY-4.0", "",
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
        "## Coverage by N-PX season",
        "", "A season runs for meetings from 1 July to 30 June (2022-23 = 2022-07-01 to "
        "2023-06-30). `legacy lines` are 2022-23 text-filing lines read by two agreeing parsers "
        "(`votes.legacy_format` set); `XML lines` come from SEC XML N-PX. Shipped lines only. "
        f"`{UNREADABLE_DATE_SEASON}` counts lines whose `meeting_date`, as the filer wrote it, "
        "is not a real calendar date written month-first (M/D/YYYY, M/D/YY), as YYYYMMDD or "
        "as ISO (e.g. " + ", ".join(f"`{d}`" for d in UNREADABLE_DATE_EXAMPLES) + "); "
        "they are shipped unchanged but not assigned a season.",
        "", "| Season | legacy lines | XML lines |", "|---|--:|--:|",
        *[f"| {s['season']} | {s['legacy_lines']:,} | {s['xml_lines']:,} |"
          for s in season_coverage(conn)],
        "", "## Known gaps (2022-23 legacy lines)",
        *[f"- {g}" for g in known_gaps(conn)],
        "", "## Tables", "",
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
