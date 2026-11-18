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

## The evidence engine (proposal-level; supersedes line-level rates)

`engine.py` builds a derived index (`data/engine.db`, rebuildable, never a
source of truth) that every investigation now goes through. It differs from
the say-vs-do analysis described below in three ways, each a correction:

- **The unit is the proposal, not the ballot line.** N-PX reports one line per
  fund per ballot item. As of 2026-11-16 (three N-PX seasons, 2024–2026) the ledger's 280,687
  shareholder-proposal lines are 56,164 distinct (manager, company, meeting, proposal) decisions. Rates over
  lines weight a proposal by how many of a manager's funds hold the stock;
  the engine counts each decision once. The position is SHARE-weighted:
  funds routinely file a sliver the other way (0.2–2.5% of shares at State
  Street), so the minority side must carry at least 5% of shares voted before
  the position is `SPLIT`. Counting lines instead called 801 State Street and
  604 BlackRock proposals split and dropped them from every rate; share
  weighting leaves 7 and 3. `SPLIT` is outside the support rate
  (FOR / (FOR + AGAINST)) and reported beside it.
- **Coverage is a handful of fund registrants per manager** (BlackRock,
  State Street and T. Rowe Price: four each; Vanguard: five; index trusts
  only for the largest three, added 2026-11-16). Figures describe "the funds on file", not the firm.
- **Scope is shareholder-sponsored proposals** (`vote_source = SECURITY
  HOLDER`), de-duplicated, plus **management's director nominees**
  (`vote_source = ISSUER`, category `DIRECTOR ELECTIONS`) in a separate table
  with their own tools. Director items are counted per nominee item as filed
  and per meeting; `opposed` is AGAINST or WITHHOLD, share-weighted. N-PX
  never records the reason for a vote, so a director-opposition rate cannot
  be attributed to any one policy provision (diversity, overboarding, pay).
  Managers are compared on shared MEETINGS (CUSIP + date), not on matched
  nominees: filers word nominee items differently. Other management
  proposals stay in the ledger but are not indexed.
  Each director item carries `isin_country`, the first two letters of the
  ISIN on its fund lines. That is the country that *issued the ISIN*, not
  where the company is run (a Cayman-registered company is `KY`); it is NULL
  where no line has an ISIN, the prefix is malformed, or the lines disagree.
  The director tools accept `country=` (`US`, `US,CA` or `non-US`); items with
  no usable country are excluded then, and the number excluded is stated in
  the result's caveats. `director_record` splits US / non-US / unknown.
  **Withhold vs abstain is the filer's coding, not ours.** In a US plurality
  election a withheld vote can be filed as WITHHOLD (counted in `opposed`) or
  as ABSTAIN, and N-PX does not define the choice; a change of filing agent
  changed it (BlackRock BIS, US ISINs, calendar years: `opposed` 1,216 in 2024
  against 617 in 2025 while `abstain` went from 166 to 570). The director tools
  therefore also report `not_supported` = `opposed` + `abstain` and
  `non_support_rate` = `not_supported` / (`for` + `opposed` + `abstain`); SPLIT
  and NONE items are in neither, as for `opposed`. A result that lists several
  periods of one group carries a `CODING SHIFT` caveat, with the abstain counts,
  whenever the abstain share of `not_supported` differs by more than 15 points
  between two of them (and one holds at least 30 abstain items): `opposed` is
  then not comparable across the periods. For comparisons over time use
  non-support. The desk verifier refuses a draft paragraph that cites `opposed`
  or `opposition_rate` from such a result without the matching `not_supported`
  or `non_support_rate` claim. `peers` and `director_peers` accept
  `institution=` (and `adviser=`) to show one group's row without changing any figure.
  **Say-on-pay is a third indexed category.** `pay_record` covers management items filed under N-PX category SECTION 14A SAY-ON-PAY VOTES (one row per manager and adviser per ballot item, same grouping, `is_duplicate = 0`, `adviser=`, `country=` and `CODING SHIFT` rules as director votes); say-on-pay *frequency* items (1/2/3 years) are not for/against, so they are excluded from every count and reported only as `frequency_items`.
- **Peer comparison is on identical proposals.** `peers` matches the same
  ballot item across managers by company, meeting date and the proposal's
  significant words. Matching is deliberately strict: an unmatched proposal
  costs a comparison; a false merge would compare votes on different items.
- **Say is time-aligned to do.** A vote is set only against the policy
  version archived on or before the meeting date. Capture dates are "public
  by", so the true window opens earlier and votes just before a capture are
  attributed to the previous version.

Figures produced by the older line-level modules (`investigate`, `systemic`,
`detectors`, `casefile`) are NOT comparable to engine figures and should not
be cited alongside them. The 175 rows in `findings` predate the temporal
guard — 25 of them pair a vote with a policy version archived after it — and
all remain `pending`; none is publishable.

**Drafts are machine-checked.** An investigating agent files a draft to
`data/desk/` in which every factual sentence carries a claim (`quote`,
`absent`, `stat`, `proposal`, `enforcement`). `glasshouse desk verify`
re-executes each claim against the engine, rejects uncited figures and
unbacked quotations, and rejects words asserting motive or wrongdoing. A
verified draft is an unpublished lead; publication remains a human act.

**Which adviser votes.** One institution can hold fund registrants whose
shares are voted by different advisers under different published policies
(T. Rowe Price: TRPA and TRPIM, which run controls against sharing proxy
decisions). `config/institutions.yaml` names the voting adviser per registrant
(`adviser_key`, with the prospectus cited in `adviser_source`) and the adviser
that owns each policy document. Only an explicit `adviser_key` separates
advisers; a free-text `adviser` label alone does not. For an institution with
two or more known advisers the engine never aggregates lines voted by different
advisers into one item: each adviser's decision is its own row, peers tools
list each as `institution/ADVISER`, every vote tool takes `adviser=` (an
unknown adviser is refused), and an unscoped answer carries a POOLED ADVISERS
caveat. Tools that pair policy text with votes (`say_vs_do`) refuse without
`adviser=` and use only that adviser's documents; `policy_in_force` needs the
adviser or document. The draft verifier rejects a vote claim about such an
institution that does not carry the adviser. Registrants with no `adviser_key`
are "unknown", not assumed to share anyone's policy.

The group is resolved per vote line, not per registrant: a registrant's
`adviser_key` is its default; `adviser_key_history` (inclusive `from`/`until`
ISO dates, compared with the MEETING date) and `series_adviser` (per fund
series, optionally dated) override it, in that order (series rule, then
history, then default). A meeting date that does not parse, on a series or
registrant that has any dated rule, resolves to `UNDATED`: its own group, never
paired with a policy (the adviser in force cannot be told). Rule bounds are
validated at build (ISO days, `from` <= `until`, no overlaps) and a bad rule
stops the build. A policy document takes its key the same way, from its own
`adviser_key_history`, on each version's CAPTURE date (the day the text was
demonstrably public), not its authored date: a policy is often written days
before it takes effect (Vanguard's VPM text was authored 2026-01-06, effective
2026-01-12). Tools say when a version was authored over 30 days before its
first capture, and how many votes precede an adviser's first archived text.
Vote lines with no key on record are a group of their own (`unlabelled`)
whenever the institution has any keyed registrant or document. An institution
is multi-group when its lines resolve to
two or more keys, its documents carry two or more keys, or a document's key is
none of the registrants' keys (a policy that does not govern the votes on
file: Deutsche's DWS Investment GmbH letter versus US trusts voted by DIMA).
Pairing tools use only documents keyed to the adviser asked for and refuse,
rather than fall back to another group's text, when that adviser has none.
The key `EXTERNAL` marks series advised by an outside manager: a group like
any other, never paired with any policy document. An institution's
`voting_scope_notes` are appended verbatim as caveats to its vote and policy
tool results.

### SAI-printed policy versions (added 2026-11-18)

Where a sub-adviser's own website has no archive history (Geode, Wellington),
the funds it votes for reproduce its proxy policy in an appendix of their
Statement of Additional Information (EDGAR forms 485BPOS). For these managers
Glasshouse extracts that one section from each SAI, between two configured
heading texts, and records it as a policy version under a SEPARATE document
label (`...-as-printed-in-sai`; the source is shown as `edgar-sai`), never
under the website PDF's label, because the printed formatting differs and a
shared label would invent alternating versions. The date of such a version is
the EDGAR filing date of the earliest filing carrying that text, and it means
only that the text was public by that day: it is not the date the manager wrote
or adopted it. Version identity is the extracted section text, ignoring all
whitespace and (for Wellington) printed page numbers; identical text in later
filings is the same version. If a start heading is not found cleanly, or the end
heading does not follow it, that filing yields nothing (a multi-SAI filing that
prints the section several times is accepted only when every copy is identical).
Filings that cannot be extracted are therefore missing versions, not guesses;
a policy edit between two extracted filings is dated to the later one's
filing, so the version in force may have been public earlier than shown.

## Say-vs-do analysis (legacy line-level engine)

The engine connects each institution's **commitment (SAY)** to its **voting
record (DO)** on a theme, as a quantified, cited result. It is an
investigative *assist*, not an oracle — every output is a quarantined **lead**.
Precision rules, each enforced in code and tested:

- **Themes** (currently 7: climate, nature, board-diversity, labor-rights,
  lobbying-disclosure, anti-corruption, human-rights) are matched **lexically**
  against proposal text and policy text. Lexical matching means cross-theme
  overlap is possible (a "lobbying alignment with climate goals" proposal hits
  both) — the proposal text is always shown so a human judges. Researchers can
  also test **custom keyword** hypotheses.
- **Binding-commitment guard.** A policy sentence may anchor a claim only if it
  is real prose (not a PDF table-of-contents / title-case list), the manager is
  binding *itself* (first-person / fund agent), and it contains an actual
  commitment verb — not a description of an issue or an expectation of
  *companies*.
- **Polarity guard.** Voting AGAINST a proposal is a gap only if the proposal
  *advances* the theme. Anti-ESG / anti-DEI proposals ("cease/revisit/reconsider
  DEI", "report on the risks **of** DEI", counter-reports, "risks to
  beneficiaries" framings) are excluded — voting them down is consistent, not
  hypocritical.
- **Temporal alignment.** A vote is compared only to the policy version in force
  **at or before** the vote date — never a later commitment.
- **AUM = managed / voting AUM.** Coverage weighting uses the assets a manager
  actually votes, never balance-sheet, custody, or divested-arm assets.
- **OFAC SDN name-joins are excluded** from enforcement leads: a sanctions
  *designation* names who is sanctioned; matching a tracked manager or a held
  issuer to one by name alone is the documented [Aldar] false-positive class.

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
| SEC EDGAR N-PORT | Monthly mutual-fund portfolios (extends beyond 13-F filers) | Free API |
| Federal Reserve enforcement actions | The banks' own records (administrative actions, bulk CSV) | Free CSV |
| EPA ECHO (`case_downloads.zip`) | Environmental enforcement cases (weekly bulk CSV dump) | Free bulk zip |
| CourtListener / RECAP | Federal dockets — **allegations only, never findings; score zero** | Free API |
| Curated snapshots (predecessor project, extracted 2026-05-26) | FCPA, SEC fraud, DOJ antitrust, World Bank, NLRB, UNGC | Hand-verified; re-verification required |

All sources are free and public. No paid APIs are used anywhere.

Source-access notes (probed 2026-06-11): the World Bank debarment API and
CFPB enforcement pages reject non-browser clients at the CDN; the UNGC
participants JSON endpoint and the SEC litigation-release RSS URL both moved
or now serve HTML. Glasshouse does not impersonate browsers to evade CDN
rules — blocked sources stay on curated snapshots until a sanctioned access
path (bulk download, official API) is found.

### EPA ECHO parsing notes (added 2026-07-16)

Scope is deliberately narrow, precision-first:

- Only defendants whose **normalized name exactly equals** a company on the
  hand-verified fossil-fuel list (`fossil.py`). Subsidiaries (e.g. "BP
  Products North America") do **not** match parents ("BP plc") — parent
  attribution is a human judgment, so the ingest undercounts rather than
  guesses.
- Only **concluded** cases: assessed penalty > 0, a case-status date, and the
  defendant named in the settlement. This excludes open matters and multi-PRP
  Superfund pileups where a major appears among dozens of parties with no
  penalty of its own.
- Judicial → `civil_violation`; administrative → `administrative_action`;
  criminal cases are **skipped** (outcome semantics are ambiguous in bulk).
- `company_name` is the defendant **as filed**; every row carries the ECHO
  case-report URL and case number. The bulk file is EPA's own weekly dump —
  no scraping, no keys.

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
  (9.3% of rows — 350,732 of 3,765,999 as of 2026-11). Rows are kept as filed but marked `is_duplicate`; every analytic
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
