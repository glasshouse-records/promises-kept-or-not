# Glasshouse: archived proxy-voting policies of US fund managers beside their funds' recorded votes, 2023–2026

*Data descriptor. DRAFT for the owner's review: not submitted anywhere.
Figures are from release 2026-11-17.2 (commit 34d811d); every one is reproducible
from the files named beside it.*

## Abstract

Fund managers publish proxy-voting policies, and their US registered funds report
every vote they cast on Form N-PX. The two records are rarely put side by side,
because policies are rewritten in place on corporate websites and earlier
versions disappear. Glasshouse is an open dataset that archives dated versions
of these policies and links them to the N-PX votes they governed. Release
2026-11-17.2 covers 18 institutions with votes on file: 12,674,571 de-duplicated
vote lines from 321 N-PX filings (meetings 1 July 2023 – 30 June 2026), and 75
archived policy versions, 73 of which carry a creation date written by the
manager's own document software. Each vote is attributed to the adviser that cast
it, and a policy version is paired only with votes by the same adviser at
meetings held on or after the day the version was demonstrably public. Three
derived tables count each decision once (73,873 shareholder-proposal decisions,
1,219,260 director-election items, 98,964 say-on-pay items). The dataset makes no
claim about any institution; it is a register of public records, each traceable
to its source filing or archived document. Data: CC BY 4.0,
doi:10.5281/zenodo.24321606 (all versions). Code: MIT licence,
github.com/glasshouse-records/promises-kept-or-not.

## Background and motivation

Since the SEC's 2022 amendments to Form N-PX (effective for votes from 1 July
2023), fund votes are filed as structured XML with standardised categories,
share counts and a flag separating issuer from shareholder proposals. That made
fund voting machine-readable at scale, and investor groups (for example ICCR's
annual asset-manager proxy-voting analysis) and academic studies now use it.

The *policies* that are meant to govern those votes have no equivalent filing.
They sit on manager websites as PDFs or HTML, are revised (often annually, often
in January), and the old version is replaced at the same URL. A reader in 2026
asking how a 2024 vote compares with the policy then in force usually cannot
recover that policy. Wayback Machine coverage is partial and some URLs have
already rotted.

Glasshouse addresses that gap, and a second one: within one institution,
different advisers vote under different policies (BlackRock's BIS and BAIS teams;
Vanguard's two stewardship teams from January 2026; T. Rowe Price's TRPA and
TRPIM). Pooling their votes, or comparing one team's votes with another's
policy, produces false results. The dataset therefore carries the voting adviser
on every vote and every policy version.

## Methods

### Vote records

N-PX filings are retrieved from SEC EDGAR with a declared, non-impersonating
client identifier, as the SEC requires. Vote tables (XML exhibits, up to ~120 MB)
are parsed with a streaming parser; every `voteRecord` in a `proxyTable` is kept.
Filings of type FUND NOTICE REPORT carry no votes and are skipped.

**Duplicates.** N-PX as filed repeats records: the same vote once per share class
within an exhibit, and the same series filed in two exhibits for one period. Of
14,034,157 vote lines in the working ledger, 793,769 (5.7%) are marked
`is_duplicate` and excluded from every shipped table and count. Lines are never
deleted from the ledger, only marked.

**Release filter.** The shipped `votes` table holds de-duplicated, validated,
cast votes only. Pre-2024 votes parsed from HTML filings (`vote_source =
legacy_html`) are not validated and are not in the release.

**Adviser attribution.** A registry (`config/institutions.yaml`, shipped as
`voting_advisers`) names the voting adviser for each registrant, citing the
prospectus or SAI statement it comes from. Rules can be dated (an adviser change
on a given day) and can override per fund series. The adviser is resolved per
vote line from the meeting date. Series advised by an outside manager are keyed
`EXTERNAL`; a meeting date that cannot be placed against a dated rule is
`UNDATED`; neither is ever paired with a policy.

### Policy versions

For each tracked policy URL, the current document is captured on a routine run;
earlier versions are recovered from the Internet Archive where it holds them.
A version's identity is its extracted text, not its bytes: content-delivery
networks inject tracking code that changes a file's hash without changing a word,
which on first build produced 12 phantom versions out of 63. A PDF shorter than
its declared length, or lacking an end-of-file marker, is a failed capture, never
a new version.

Each version carries two dates. The **capture date** is the earliest day the text
was demonstrably public (our capture or the archive's). The **authored date**,
where present, comes from the document's own metadata, written by the manager's
software; 73 of 75 versions carry one, and none is later than its capture.
Pairing uses the capture date, so a vote is set against a version only if that
version was public on or before the meeting. Tools flag a version authored more
than 30 days before its first capture, since the true window then opens earlier.

### Derived decision tables

N-PX reports one line per fund per ballot item, so a line count weights a
proposal by how many of a manager's funds held the stock. The derived tables
count each decision once per (institution, adviser, company, meeting, item):

- `proposal_decisions` (73,873 rows): shareholder-sponsored proposals.
- `director_decisions` (1,219,260 rows): management's director nominees.
- `pay_decisions` (98,964 rows): say-on-pay approval items. Say-on-pay
  *frequency* items (one, two or three years) are not for/against votes and are
  excluded.

The position is share-weighted. Funds often file a sliver the other way, so a
decision is `SPLIT` only when the minority side carries at least 5% of shares
voted. Counting lines instead would have called 801 State Street and 604
BlackRock proposals split; share weighting leaves 7 and 3.

**Withhold versus abstain.** In US plurality elections a withheld vote may be
filed as WITHHOLD or as ABSTAIN, and N-PX does not define the choice. A change of
filing agent can switch it between years. The director and pay tables therefore
report non-support (opposed + abstain) beside opposition, and any result spanning
periods whose coding differs carries a `CODING SHIFT` warning.

## Data records

The release is one directory, with every table as Parquet and CSV:

| Table | Rows | What |
|---|--:|---|
| `institutions` | 22 | Tracked institutions (18 with votes on file) |
| `filings` | 2,377 | Source filings, each with source URL and retrieval date |
| `votes` | 12,674,571 | De-duplicated cast votes, with adviser key |
| `proposal_decisions` | 73,873 | One row per shareholder-proposal decision |
| `director_decisions` | 1,219,260 | One row per director-nominee item |
| `pay_decisions` | 98,964 | One row per say-on-pay approval item |
| `policy_versions` | 75 | Dated policy versions, with adviser key |
| `commitments` | 96 | Policy captures, with URL and retrieval date |
| `voting_advisers` | 82 | Registrant/series → adviser rules, with sources |
| `voting_scope_notes` | 30 | Per-institution caveats, to read before pooling |
| `holdings` | 580,106 | 13-F holdings rows |
| `enforcement_actions`, `entities`, `findings` | — | See DATASHEET.md |

`DATASHEET.md` describes every column; `COVERAGE.json` gives per-institution
counts by kind of vote; `MANIFEST.sha256` lists a checksum for every file.

**Coverage by kind of vote** (shipped lines): director elections 6,356,487; other
management proposals 5,305,643; say-on-pay 659,193; shareholder proposals 353,248.

**Coverage by institution.** The five largest by vote lines are BlackRock
(3,669,405), Dimensional (2,671,496), Vanguard (2,587,321), State Street
(2,341,749) and Northern Trust (354,497). Three institutions (Bank of America,
BNP Paribas, UBS) ship say-on-pay votes only. Four registry institutions
(Citigroup, Morgan Stanley, PIMCO, Wells Fargo) ship holdings but no votes.
Coverage is a set of named fund registrants per institution, not the whole firm.

## Technical validation

- **Checksums.** Every shipped file is listed in `MANIFEST.sha256`; the
  release was verified against it after build (0 failures).
- **Provenance.** Every `filings` and `enforcement_actions` row carries a source
  URL and retrieval date; votes link to their filing by accession. The test
  suite enforces this, and a static check rejects code that writes a record
  without a source URL.
- **Invariant tests.** Automated tests cover the duplicate filter, adviser
  resolution (overlapping or malformed dated rules stop the build), the
  temporal pairing guard, the split threshold, and the frequency-item exclusion.
- **Policy dates.** Of 75 versions, 73 carry manager-authored dates; none
  postdates its capture, and none inverts the order of versions.
- **Truncated filings.** Some 2025–2026 Dimensional N-PX exhibits (CIKs 355437
  and 1816125) contain exactly 500,000 `proxyTable` records in the SEC file
  itself; the XML is well-formed but appears capped. Counts for those filings are
  lower bounds.
- **Independent re-count.** Spot counts run directly against the ledger have
  matched the derived tables; one discrepancy found in review was traced to the
  hand count, not the tool.

## Usage notes

1. Group by `adviser_key` before comparing anything with a policy. Never pair
   `UNRESOLVED`, `EXTERNAL`, `UNDATED` or `unlabelled` votes with a policy.
2. Pair a policy version only with votes at meetings on or after its capture
   date, by the same adviser.
3. Use the decision tables, not raw line counts, for rates.
4. Compare director and pay results over time with non-support, not
   opposition, unless the coding is shown to be stable.
5. N-PX never records why a vote was cast. A vote that differs from a policy's
   wording is a lead for reading the proxy statement, not evidence of a breach.
6. `isin_country` is the country that issued the ISIN, not the company's home.
7. Absence of data means no data, not a clean record.

## Limitations

- Coverage is partial: named fund registrants for 18 institutions. Several large
  voters are absent because their policies cannot be retrieved honestly (a site
  blocks declared clients), or their votes sit in other firms' fund trusts as
  sub-adviser (documented in the repository's roadmap).
- Policy archives start where captures or the Internet Archive start; some
  institutions have one or two versions.
- The capture date is "public by", so a version's true start can be earlier.
- N-PX has a reporting lag of up to 14 months after the meeting.
- `managementRecommendation` as filed is sometimes inconsistent with proxy
  statements and is shipped verbatim.

## Code availability

All ingest, de-duplication, attribution and release code is public at
github.com/glasshouse-records/promises-kept-or-not. `glasshouse release`
rebuilds the bundle from the ledger; `glasshouse restore` loads a bundle into a
working ledger. The DATASHEET records the exact commit used.

## Data availability

Zenodo, concept doi:10.5281/zenodo.24321606 (resolves to the latest version).
Licence CC BY 4.0. Corrections via GitHub issues.
