# Glasshouse

Glasshouse is a dataset. It puts three public records side by side: what large
asset managers wrote in their proxy-voting policies, how their US funds voted
(SEC form N-PX), and the public enforcement record. Every row names its source
and the date it was fetched. The dataset records votes, texts and dates. It
makes no claim about why anyone voted or wrote anything.

On top sit an evidence engine (`glasshouse ask`, cited queries) and a checker
(`glasshouse desk verify`, which re-runs every claim in a draft). The dataset is
the product.

**Status, 2026-11-17:** unpublished. No public repository, no DOI. The release
bundle exists on the maintainer's disk (`data/releases/v2026-11-17/`, gitignored).
The `findings` table is empty: no claim has passed human review. Drafts in
`data/desk/` are unpublished leads; they are not in the release or this repo.

## What is in it

Figures below are from the release `v2026-11-17` (its `DATASHEET.md` and
`COVERAGE.json` are authoritative). Counts drift; the commands print current ones.

| Layer | Table(s) | What it holds, honestly |
|---|---|---|
| Archived policy versions | `commitments`, `policy_versions` | 89 captures of 14 managers' proxy-voting documents, 68 distinct text versions (51 from Wayback, 17 our own fetch). Hashes, dates, URLs; no policy text. Dated by the capture day (text was public by then). 66 of 68 also carry the date the manager's own software wrote the file. Gaps exist. |
| Proxy votes | `votes`, `fund_series`, `voting_advisers`, `voting_scope_notes` | US-registered funds only, from N-PX. Meeting dates 2023-07-01 to 2026-06-30 (three N-PX seasons, named 2024, 2025, 2026: July to June, named by end year). 9,684,226 vote lines after removing duplicates. Only the funds on file, not whole firms. |
| Director votes (DERIVED) | `director_decisions` | 977,224 rows: one per director-nominee item per manager and adviser. Rebuilt from `votes` by `glasshouse engine build`. |
| Shareholder proposals (DERIVED) | `proposal_decisions` | 58,087 rows: one per (manager, adviser, company, meeting, proposal). Same rebuild. Other management items (auditors, pay) are in `votes` but not here. |
| Holdings | `holdings` | 580,106 rows from 13-F (long US equity only) and two N-PORT filings. Mostly one quarter (2026-03-31). BlackRock also has 2023-06-30 to 2024-06-30; Vanguard 2025-09-30 to 2026-03-31. A snapshot, not a time series. |
| Enforcement record | `enforcement_actions` | 14,887 rows. 12,533 are OFAC sanctions designations (names on a list, not findings about any manager). 236 are curated snapshots. 489 are `unverified`. 30 are `allegation` (dockets). Each row has a `resolution_type` from a closed list. |
| Findings | `findings` | 0 rows. |

Fidelity votes with meeting dates 2020-07-01 to 2023-06-30 (53,859 lines, parsed
from legacy HTML) are in the working ledger only: unvalidated, not in the release.

### Who is covered

Run `glasshouse ask coverage` for the live table. Snapshot below (release
v2026-11-17 plus `ask coverage`). "Pay only" means the filing holds say-on-pay
votes and no director or shareholder-proposal votes. "Registrants" is how many
fund trusts are on file, often a small part of a large manager.

| Manager | Adviser groups (`adviser_key`) | Seasons | Votes held | Registrants | Policy versions | Scope notes (short) |
|---|---|---|---|---|---|---|
| BlackRock | BIS, BAIS, UNRESOLVED | 2024-26 | all kinds | 4 | 13 (from 2019-08-06) | BIS/BAIS split from 2025-01-01; 10 series cannot be placed (UNRESOLVED), incl. iShares Core S&P 500 |
| Vanguard | VANGUARD, VPM, VCM, EXTERNAL | 2024-26 | all kinds | 5 | 5 (from 2022-01-17) | Teams split 2026-01-12; one pre-split capture (2022) for 2022 to 2026-01-11 |
| State Street | none keyed | 2024-26 | all kinds | 4 | 7 (from 2020-09-29) | 3 SPDR Nuveen muni ETFs may follow Nuveen's policy |
| Fidelity | none keyed | 2024-26 | all kinds | 4 | 6 (from 2023-04-16) | |
| JPMorgan | none keyed | 2024-26 | all kinds | 2 | 6 (from 2021-01-25) | |
| Goldman Sachs | none keyed | 2024-26 | all kinds | 2 | 2 (from 2022-10-31) | |
| BNY | none keyed | 2024-26 | all kinds | 2 | 1 (2025-07-18) | Sub-advised funds vote under the sub-adviser's own rules |
| Invesco | none keyed | 2024-26 | all kinds | 1 | 2 (from 2024-02-24) | One trust only; sub-adviser policies not checked |
| T. Rowe Price | TRPA, TRPIM | 2024-26 | all kinds | 4 | 12 (from 2023-01-30) | 3 funds TRPA-voted, Capital Appreciation TRPIM-voted |
| Franklin Templeton | none keyed | 2024-26 | all kinds | 2 | 2 (from 2026-06-26) | Sub-adviser use not ruled out for some series |
| Deutsche Bank (DWS) | DIMA | 2024-26 | all kinds | 3 | 2 (from 2026-06-27) | One archived letter is DWS Investment GmbH's, not the US trusts' adviser |
| Northern Trust | none keyed | 2024-26 | all kinds | 1 | 4 (from 2024-05-14) | Multi-manager series use outside sub-advisers |
| Charles Schwab Trust | none keyed | 2024-26 | all kinds | 2 | 0 | No policy archived |
| UBS | none keyed | 2024-26 | pay only | 1 | 2 (from 2024-06-11) | Combined report for several UBS entities |
| BNP Paribas AM | none keyed | 2024-26 | pay only | 1 | 4 (from 2024-04-21) | Ex-AXA IM votes may not follow the archived policy |
| Bank of America | none | 2024-26 | pay only, 30 lines | 1 | 0 | Not a fund manager; holdings and enforcement only |

Citigroup, Morgan Stanley, Allianz (PIMCO) and Wells Fargo have holdings and
enforcement rows but no votes or policy versions. "None keyed": the registry
records no adviser keys, so nothing is split. "From" is the first capture date;
votes before it have no archived policy. Full notes: `facts/voting_scope_notes.csv`.

## Three things to know before comparing a policy with votes

**1. Votes belong to the adviser that cast them, not to the brand.** One manager
can have funds voted by different advisers under different policies. Group by
`adviser_key` (in `proposal_decisions` and `director_decisions`; for raw
`votes` resolve it from `voting_advisers`). Example from this record, Vanguard
director items from meetings in 2026, non-support (against or abstain) in the
release: VCM 7.4%, VPM 3.1%, the EXTERNAL fund 1.6%, and the pre-split VANGUARD
key (2026-01-01 to 01-11) 19.0% on 195 items. Pooled, the figure is 6.1%, and it
describes no one's policy. `UNRESOLVED`, `EXTERNAL`, `UNDATED` and `unlabelled`
are never comparable with any policy.

**2. A policy version speaks only for votes cast by the same adviser while it
was the archived version, and the archive has gaps.** Check `policy_in_force`
before pairing. Example: UBS has two archived versions. The 2026 text was
written 2026-05-15 and first captured 2026-11-17, after every vote on file (the
last meeting is 2026-06-30). Votes in 2026 are compared with the 2024 text, or
not at all. Vanguard's 2022 text is the only capture before 2026-01-12.

**3. N-PX never says why, and filers code withheld votes differently.** A
withheld director vote may be filed as WITHHOLD or as ABSTAIN. N-PX does not
define the choice, and a change of filing agent changes it. Compare
`not_supported` (against plus abstain), not `opposed`. Example from this
record (`director_record institution=blackrock adviser=BIS country=US`,
January to June): `opposed` fell from 1,069 (2024) to 508 (2025) while
`abstain` rose from 12 to 438; non-support went from 1,081 to 946. The record
cannot say what drove either number.

Also: `isin_country` is the country that issued the ISIN, not where the
company runs. Never sum `shares_voted` without `is_duplicate = 0` (the release
`votes` table already applies it).

## Quickstart A: the release bundle (about ten minutes)

No network needed once you hold the bundle; it is not downloadable yet.

```sh
cd data/releases/v2026-11-17
shasum -a 256 -c MANIFEST.sha256          # Linux: sha256sum -c ... ; every line must say OK
pip install duckdb                        # or: pip install pandas pyarrow
```

Director decisions grouped by `adviser_key` (this exact query was run):

```sql
SELECT coalesce(adviser_key, 'ALL (pooled)') AS adviser_key,
       count(*) AS items,
       round(100.0 * count(*) FILTER (position IN ('AGAINST','ABSTAIN'))
             / count(*) FILTER (position IN ('FOR','AGAINST','ABSTAIN')), 1) AS non_support_pct
FROM 'facts/director_decisions.parquet'
WHERE institution_id = 'vanguard' AND meeting_date >= '2026-01-01'
GROUP BY ROLLUP(adviser_key) ORDER BY items;
```
```
 VANGUARD     195  19.0
 EXTERNAL    1172   1.6
 VPM        33607   3.1
 VCM        77876   7.4
 ALL (pooled) 112850  6.1
```

Run it in the DuckDB shell or with `duckdb.sql(...)`. In pandas:
`pd.read_parquet('facts/director_decisions.parquet')`. `proposal_id` and
`director_id` are not stable across rebuilds; cite `accession` and `source_url`.

## Quickstart B: the evidence engine

The engine reads the ledger (`data/glasshouse.db`, about 3.4 GB on the maintainer's
disk). A fresh clone has no ledger and cannot rebuild the release. You must ingest
from SEC EDGAR, which needs network access and a contact string for SEC fair
access. Use your own; the code does not hide who you are.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,release]"
export GLASSHOUSE_CONTACT="your-name-and-your-own-email"   # sent in the User-Agent
glasshouse init-db                                          # 0.2 s; registers 20 institutions
glasshouse ingest npx --institution bnp_paribas --max-filings 1   # about 2 s, one small filing
glasshouse engine build                                     # 0.2 s on that tiny ledger
glasshouse ask tools                                        # every question the engine answers
```

The commands from `init-db` on were run on an empty data directory
(`GLASSHOUSE_DATA_DIR` moves it); `pip install` was not re-run. A full ledger means
many large downloads (N-PX exhibits are 65 to 124 MB each); a full ingest was not
timed. On the full ledger `engine build` took 2 min 4 s. `ingest commitments
--wayback` fetches the policy archive.

Run `glasshouse ask coverage` first. Real calls on the full ledger (trimmed, reformatted):

```
$ glasshouse ask policy_versions institution=ubs
  commitment_id 45  captured 2024-06-11  authored 2024-01-31  via wayback
  commitment_id 82  captured 2026-11-17  authored 2026-05-15  via live
  caveat: authored 2026-05-15 but first captured 2026-11-17 (186 days later):
          votes between those dates are not covered by an archived text.
```

Every answer is JSON with `result` and `caveats`; read the caveats. A
multi-adviser manager queried without `adviser=` gets a POOLED ADVISERS warning.

Checking a draft: JSON in `data/desk/` where every factual sentence carries a claim
(format: top of `src/glasshouse/desk.py`; agent brief:
`.claude/agents/investigative-journalist.md`).

```
$ glasshouse desk verify data/desk/ubs-policy-2026.json
  ok  c1  policy_versions→[commitment_id=45].captured = '2024-06-11'
  ...
  VERIFIED — LEAD — unpublished; human review required before any use
```

The verifier re-runs each claim against the engine and rejects uncited figures,
quotations not in the archived text, and words that assert motive or wrongdoing.

## How trust is enforced

- Every ledger row has `source_url` and `retrieval_date`. Enforcement rows have a
  `resolution_type` from a closed list; dockets are `allegation`, doubt is `unverified`.
- N-PX as filed repeats vote lines. 793,769 of 10,733,655 ledger vote lines are
  flagged `is_duplicate`; the release keeps only the rest.
- Quarantine: name-level joins are leads. Nothing reaches `findings` without a
  human decision and a note. LLM output never enters ledger facts. Free public
  sources only; blocked ones are documented, not bypassed.
- Gates before every commit: `scripts/gates.sh` (ruff, semgrep, pytest, `glasshouse
  integrity`). Invariants are tested in `tests/test_invariants.py`, `test_properties.py`
  (Hypothesis), `test_release.py`, `test_publish.py`; `.semgrep.yml` blocks LLM ledger
  writes and UA spoofing.
- Method and known failures (Aldar name-match, anti-DEI polarity): [METHODOLOGY.md](METHODOLOGY.md).

## What it cannot tell you

- Why a fund voted a way, or why a policy changed.
- What a manager as a whole did. N-PX covers US-registered funds only, a handful of
  registrants per manager. Separate accounts and non-US funds are absent.
- What a policy said between captures. Capture dates mean "public by then".
- Anything about managers with no votes on file. Absence of data is not a clean record.
- `management_recommendation` is as filed and known to be unreliable. Theme tags are
  lexical (word matching): leads, not classifications.
- Whether an enforcement action against a held company implies anything about the
  holder. OFAC rows name sanctioned parties; name matches are leads only.

## Status, citing, corrections, licence

Unpublished; no DOI. Once a Zenodo deposit exists, cite its concept DOI with the
version and commit in the bundle's `DATASHEET.md` (today: "Glasshouse evidence
dataset, v0.1.0 (commit 44958db), 2026-11-17", not citable as published).
Metadata: `CITATION.cff`. Steps: [docs/PUBLISHING.md](docs/PUBLISHING.md); open
work: [docs/ROADMAP.md](docs/ROADMAP.md).

Corrections: send the maintainer the table, the row and the primary-source link
(no public tracker yet). They are applied in a new release and listed in
[CHANGELOG.md](CHANGELOG.md). Unverified items: [PENDING_VERIFICATION.md](PENDING_VERIFICATION.md).

Leads, not findings: any say-versus-do gap you derive is a lead. Check the proposal
text, the adviser, and the policy in force on the meeting date first.

Licence: code MIT (`LICENSE`); data CC-BY-4.0 (declared in `datapackage.json` and
`CITATION.cff`; no separate data licence file in the repo).
