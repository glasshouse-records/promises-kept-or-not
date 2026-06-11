# Glasshouse Methodology

**Version:** 0.1 (DRAFT — prerequisite for any public claim; no finding may be
published while this document is marked DRAFT)
**Last updated:** 2026-06-11

---

## Purpose

Glasshouse joins three classes of public primary-source records:

1. **SAY** — institutions' own published commitments (stewardship and proxy
   voting policies, ESG reports, signatory statuses), snapshotted and
   versioned.
2. **DO** — institutions' observable choices: proxy votes (SEC Form N-PX),
   holdings (13-F, N-PORT).
3. **DONE** — the documented enforcement record of companies they hold and
   vote on — and of the institutions themselves.

Its output is findings of the form *commitment X (archived DATE) vs. act Y
(primary ref. Z)*, each fully traceable.

## Evidence ledger invariants

Every record in the ledger carries:

- `source_url` — the public primary source it was retrieved from
- `retrieval_date` — when it was retrieved
- `primary_ref` — the agency's own reference number (DOJ press release no.,
  SEC litigation release no., OFAC entity number, NLRB case no.) where one
  exists; records without one are flagged by the integrity checker
- `resolution_type` — the legal character of the action (see below)

Records originating from curated snapshots (hand-verified research imported
from a predecessor project) are marked `source_kind = curated_snapshot` with
the snapshot's extraction date, and are scheduled for re-verification against
live sources before being used in any published claim.

## Resolution types — the legal distinction table

This table is reproduced in every output that references an enforcement
action. The differences are legally material and are never collapsed.

| Resolution type | Criminal conviction? | Admission of guilt? |
|---|---|---|
| **Guilty plea** | Yes | Yes |
| **DPA** (Deferred Prosecution Agreement) | No — charges dismissed if compliant | No |
| **NPA** (Non-Prosecution Agreement) | No — no charges filed | No |
| **Civil settlement** (e.g. SEC) | No (civil only) | Typically no |
| **Civil violation / board order** (NLRB, EPA, etc.) | No (administrative/civil) | N/A |
| **Debarment** (World Bank) | No (administrative) | N/A |
| **Sanction designation** (OFAC) | No (administrative) | N/A |
| **Expulsion** (UN Global Compact) | No (membership action) | N/A |
| **Docket / pending matter** | **Allegation only — never reported as a finding** | — |

Records whose resolution type cannot be determined from the primary source
are stored as `unverified` and quarantined: they cannot appear in any
published output until a human verifies the primary source (see
[PENDING_VERIFICATION.md](PENDING_VERIFICATION.md)).

## Finding classes (strongest first)

1. **Commitment ⟷ vote** — the flagship. A vote is an active choice; the
   "passive index" defense does not apply.
2. **Vote divergence within one manager** — the same manager's fund families
   voting opposite ways on an identical proposal (e.g. ESG-branded funds vs.
   flagship index funds). Validated as a real, recurring pattern (2026-06-10).
3. **Commitment ⟷ the institution's own enforcement record.**
4. **Commitment ⟷ silent policy edits** between snapshots.
5. **Commitment ⟷ holding** — weakest (index alibi exists); still reported,
   labeled as such.

## Entity resolution

Join keys in strict priority order:

1. **CUSIP** (exact)
2. **LEI** (exact; fund-side LEIs from N-PX covers, GLEIF free API)
3. **CIK** (exact)
4. **Normalized-name fuzzy match** — token-set similarity with legal-suffix
   stripping and a length-ratio guard. Threshold 0.85 for any join used in a
   finding. **Every fuzzy match is logged** (query, candidate, score,
   accepted/rejected) in the `match_log` table.

Precision is preferred over recall throughout: a false accusation is fatal;
a missed match is acceptable.

## Data sources (Phase 1)

| Source | What | Access |
|---|---|---|
| SEC EDGAR N-PX | Proxy voting records (vote-level XML exhibits) | Free API, User-Agent required |
| SEC EDGAR 13-F | Quarterly institutional holdings | Free API |
| DOJ FCPA related-enforcement pages (a–z) | FCPA corporate resolutions | Free, HTML |
| OFAC SDN + consolidated list | Sanctions designations | Free bulk CSV |
| World Bank debarred firms | Procurement debarments | Free API |
| UN Global Compact | Expelled participants | Free API |
| Curated snapshots (predecessor project, extracted 2026-05-26) | FCPA, SEC fraud, DOJ antitrust, World Bank, NLRB, UNGC | Hand-verified; re-verification required |

All sources are free and public. No paid APIs are used anywhere.

Source-access notes (probed 2026-06-11): the World Bank debarment API and
CFPB enforcement pages reject non-browser clients at the CDN; the UNGC
participants JSON endpoint and the SEC litigation-release RSS URL both moved
or now serve HTML. Glasshouse does not impersonate browsers to evade CDN
rules — blocked sources stay on curated snapshots until a sanctioned access
path (bulk download, official API) is found.

### N-PX parsing notes (validated 2026-06-10)

- Vote tables are separate XML exhibits in the filing directory (65–124 MB),
  namespace `http://www.sec.gov/edgar/document/npxproxy/informationtable`;
  parsed with a streaming parser (lxml `iterparse`), never regex.
- `primary_doc.xml` is the cover page: series IDs, names, LEIs. Filings with
  `reportType = FUND NOTICE REPORT` are cover-only notices with no votes.
- One `proxyTable` may contain **multiple** `voteRecord` elements; all are
  parsed.
- **Duplicate vote records are endemic in N-PX as filed** (found 2026-06-11
  during an editorial audit): the same voteRecord repeated within one
  exhibit (one copy per share class) and the same series' votes filed in
  two exhibits of the same period — 107,088 of 2,158,394 ingested rows
  (~5%). Rows are kept as filed but marked `is_duplicate`; every analytic
  query excludes them. **Never sum `shares_voted` without this filter.**
  Rows where identical share counts appear FOR and AGAINST the same
  proposal are additionally excluded from divergence visuals as likely
  as-filed duplication, pending verification.
- `managementRecommendation` values look inconsistent with proxy-statement
  norms in some rows (e.g. "FOR" on shareholder proposals). Glasshouse
  reports the field verbatim with its accession; any published claim that
  leans on the management recommendation must first be verified against the
  issuer's proxy statement.

## Scoring — the Concern Index (v0)

For a company's set of resolved enforcement actions:

```
concern_raw = recidivism × Σ severity(resolution_type) × 0.5^(age_years / 5)
score       = 100 × (1 − e^(−concern_raw / 20))
```

- **Severity** (fixed table, anchored to legal weight): guilty plea 10,
  sanction designation 9, DPA 7, NPA 6, debarment 6, civil settlement 5,
  civil violation / board order 4, administrative 3, expulsion 2.
  **Allegations and unverified records score zero** — quarantined data
  never moves a score.
- **Recency**: 5-year half-life; undated actions are discounted as if 10
  years old.
- **Recidivism**: × (1 + 0.15 × (n − 1)), capped at 2.0.
- Duplicate-marked rows are excluded before scoring.

Every score is reproducible from the public ledger
(`glasshouse report concern --company X` prints the full per-action
breakdown). The index is an analytical summary of public records, not a
legal finding. **v0 limitation:** no confidence intervals on gapped data
yet; scores on companies with sparse coverage understate, never overstate,
because absent records contribute nothing.

## Limitations

- 13-F captures only long US equity positions of managers above $100M AUM;
  shorts, derivatives, fixed income, and non-US positions are excluded.
- N-PX reporting periods are annual (July–June), filed by end of August;
  vote data lags the meeting by up to 14 months.
- Curated snapshot data may be stale; entries are marked and re-verified
  before use in claims.
- Fuzzy name matches below threshold are never used in findings.
- GLEIF's ISIN→LEI mapping is opt-in for LEI issuers and therefore partial
  (strong for US/EU issuers, sparse elsewhere — e.g. Aldar Properties PJSC's
  UAE ISIN is unmapped as of 2026-06-11). Issuers without an LEI stay
  name-only leads.
- **Even exact normalized-name matches are only leads.** Validated on the
  first live run (2026-06-11): OFAC's "ALDAR PROPERTIES" (Sudan, SDGT
  program) normalizes identically to Aldar Properties PJSC (Abu Dhabi-listed
  developer) — two different companies. A vote×enforcement join becomes
  finding-grade only with identifier corroboration (CUSIP/LEI/CIK) or human
  verification of the primary source.
- An enforcement action against a held company is not evidence that the
  holder knew of, endorsed, or profited from the conduct. Glasshouse reports
  the conjunction of documented facts; it does not characterize motive.

## Roadmap

1. **Phase 1 (current):** N-PX ingestion, entity resolution, evidence ledger,
   first enforcement sources. Public repo.
2. **Phase 2:** Commitments ledger (scrape + version + Wayback history).
3. **Phase 3:** Contradiction + diff engines → first 10 vote-contradiction
   findings published manually. **Demand test:** audience response reviewed
   before Phase 4 and allowed to re-rank everything after.
4. **Phase 4:** Interfaces — static site, Datasette, RSS, email digest, MCP.
5. **Phase 5:** Daily enforcement/news event trigger + alert path.
6. **Phase 6:** Publicist agent (human-gated approval queue), non-response
   ledger, fiduciary-channel and coalition drafts.
7. **Phase 7:** 13-F/N-PORT expansion + first annual awards cycle.

At each phase boundary: ship publicly, post what's new, record the response,
re-prioritize on distribution evidence — audience signal is a first-class
input, not vanity metrics.
