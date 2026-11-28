# Glasshouse

Glasshouse is a dataset. It puts three public records side by side: what large
asset managers wrote in their proxy-voting policies, how their US funds voted
(SEC form N-PX), and the public enforcement record. Every row traces to its source
and the date it was fetched, directly or through its filing (`votes.accession` →
`filings.accession`). The dataset records votes, texts and dates. It
makes no claim about why anyone voted or wrote anything.

On top sit an evidence engine (`glasshouse ask`, cited queries) and a checker
(`glasshouse desk verify`, which re-runs every claim in a draft). The dataset is
the product.

**Status, 2026-11-24:** published. Data: Zenodo,
[doi:10.5281/zenodo.24486060](https://doi.org/10.5281/zenodo.24486060) (latest version, 2026-11-23;
all versions: [10.5281/zenodo.24321606](https://doi.org/10.5281/zenodo.24321606)).
Code: <https://github.com/glasshouse-records/promises-kept-or-not>.
The `findings` table is empty: no claim has passed human review. Drafts in
`data/desk/` are unpublished leads; they are not in the release or this repo.

## What is in it

Figures below are from the release `v2026-11-23` (its `DATASHEET.md` and
`COVERAGE.json` are authoritative). Counts drift; the commands print current ones.

| Layer | Table(s) | What it holds, honestly |
|---|---|---|
| Archived policy versions | `commitments`, `policy_versions` | 533 captures of proxy-voting documents of 61 institutions, 441 distinct text versions (144 from Wayback, 100 our own fetch, 197 printed in fund SAIs on EDGAR). Hashes, dates, URLs; no policy text. Dated by the capture day, or for SAI-printed text by the SAI's filing date (text was public by then). 179 of the 244 non-SAI versions also carry the date the manager's own software wrote the file. Gaps exist. |
| Proxy votes | `votes`, `fund_series`, `voting_advisers`, `voting_scope_notes` | US-registered funds only, from N-PX. 48,230,383 vote lines from 64 institutions, de-duplicated (`is_duplicate = 0`). 37,064,834 come from SEC XML N-PX; 37,060,017 of those have meetings in the three seasons July 2023 to June 2026 (2023-24, 2024-25, 2025-26; July to June). 11,165,549 are 2022-23 lines read from text and HTML N-PX filings by two agreeing parsers (`votes.legacy_format` set; 11,158,041 meetings in 2022-23, 7,508 in 2021-22). Those legacy lines are partial (some layouts are not parsed; see the DATASHEET "Known gaps"), carry no share counts and no vote category, and their decisions are line-weighted, not share-weighted; do not compare their rates with 2023-26. Only the funds on file, not whole firms. |
| Director votes (DERIVED) | `director_decisions` | 4,931,301 rows: one per director-nominee item per manager and adviser. Rebuilt from `votes` by `glasshouse engine build`. 2022-23 meetings are not in it (legacy lines have no category). |
| Say-on-pay (DERIVED) | `pay_decisions` | 416,500 rows: one per say-on-pay item per manager and adviser, approval and frequency items (`kind`; frequency items are not for/against). Same rebuild. |
| Shareholder proposals (DERIVED) | `proposal_decisions` | 320,149 rows: one per (manager, adviser, company, meeting, proposal), including 2022-23 (line-weighted, `weight_basis`). Same rebuild. Other management items (auditors, capital structure) are in `votes` but not here. |
| Holdings | `holdings` | 580,106 rows from 13-F (long US equity only) and two N-PORT filings. Mostly one quarter (2026-03-31). BlackRock also has 2023-06-30 to 2024-06-30; Vanguard 2025-09-30 to 2026-03-31. A snapshot, not a time series. |
| Enforcement record | `enforcement_actions` | 14,887 rows. 12,533 are OFAC sanctions designations (names on a list, not findings about any manager). 236 are curated snapshots. 489 are `unverified`. 30 are `allegation` (dockets). Each row has a `resolution_type` from a closed list. |
| Findings | `findings` | 0 rows. |

Votes parsed by a single HTML parser (`vote_source = legacy_html`, for example
Fidelity meetings dated 2020-07-01 to 2023-06-30) are unvalidated and are in the working
ledger only, not in the release. Fidelity's 2022-23 lines that two parsers agreed on
(`legacy_format = iss_html`) are in the release; Fidelity's own 2022-23 table layout is
not parsed, so Fidelity's 2022-23 record there is incomplete.

### Who is covered

Run `glasshouse ask coverage` for the live table. The table below is every
institution in the release `v2026-11-23`, largest by vote lines first: vote lines,
dates and kinds are the DATASHEET's coverage table (shipped rows), policy versions are
`COVERAGE.json`'s count, registrants and adviser groups come from `ask coverage` on
the ledger that built the release. "Pay only" means the shipped votes are say-on-pay
only (no director or shareholder-proposal votes). "Registrants" is how many fund
trusts are on file, often a small part of a large manager. Vote dates include the
partial 2022-23 legacy lines; vote lines of different eras are not comparable
(`votes.legacy_format`). "Not split" = one adviser group or none keyed.

| Institution (as named in the DATASHEET) | Vote lines shipped | Vote dates | Kinds | Registrants on file | Adviser groups (`adviser_key`) | Policy versions |
|---|--:|---|---|--:|---|--:|
| BlackRock Inc. | 5,911,545 | 2022-07-01 to 2026-06-30 | all kinds | 11 | BAIS, BIS, UNRESOLVED, unlabelled | 13 |
| The Vanguard Group, Inc. | 5,739,743 | 2022-07-01 to 2026-06-30 | all kinds | 14 | EXTERNAL, UNRESOLVED, VANGUARD, VCM, VPM, unlabelled | 8 |
| Dimensional Fund Advisors LP | 4,147,555 | 2022-07-01 to 2026-06-30 | all kinds | 5 | DFA, DFA_SOCIAL, DFA_SUSTAINABILITY | 16 |
| Fidelity Investments (FMR LLC) | 3,984,292 | 2022-07-01 to 2026-06-30 | all kinds | 20 | GEODE, unlabelled | 10 |
| State Street Corporation | 3,057,653 | 2022-07-01 to 2026-06-30 | all kinds | 4 | not split | 7 |
| American Century Investments (American Century Investment Management, Inc.) | 1,643,635 | 2023-07-01 to 2026-06-30 | all kinds | 9 | not split | 10 |
| Invesco Ltd. | 1,539,197 | 2022-07-01 to 2026-06-30 | all kinds | 10 | INVESCO, unlabelled | 2 |
| John Hancock (John Hancock Investment Management LLC, Manulife) and its subadvisers | 1,459,558 | 2022-07-01 to 2026-06-30 | all kinds | 14 | EXTERNAL, MANULIFE_IM, UNRESOLVED, unlabelled | 3 |
| Nuveen (Nuveen Asset Management, LLC; Nuveen Fund Advisors, LLC; TIAA-CREF Investment Management, LLC; Teachers Advisors, LLC) | 1,419,781 | 2022-07-01 to 2026-06-30 | all kinds | 6 | EXTERNAL, NUVEEN, unlabelled | 4 |
| PGIM (Prudential Financial: PGIM Investments LLC and its subadvisers) | 1,371,296 | 2021-07-01 to 2026-06-30 | all kinds | 34 | EXTERNAL, JENNISON, PGIM_INC, PGIM_QUANT, UNRESOLVED, unlabelled | 17 |
| ProShares (ProShare Advisors LLC) | 1,300,132 | 2022-07-01 to 2026-06-30 | all kinds | 2 | not split | 4 |
| WisdomTree (WisdomTree Asset Management, Inc.) | 1,188,355 | 2022-07-01 to 2026-06-30 | all kinds | 2 | not split | 0 |
| Franklin Resources Inc. (Franklin Templeton) | 1,072,064 | 2022-07-01 to 2026-06-30 | all kinds | 23 | FRANKLIN, PUTNAM, UNRESOLVED, unlabelled | 8 |
| Thrivent (Thrivent Asset Management, LLC; Thrivent Financial for Lutherans) | 941,998 | 2022-07-01 to 2026-06-30 | all kinds | 4 | EXTERNAL, THRIVENT, UNRESOLVED | 6 |
| JPMorgan Chase & Co. | 876,159 | 2022-07-01 to 2026-06-30 | all kinds | 7 | not split | 6 |
| Victory Capital (Victory Capital Management Inc., with the Pioneer funds acquired from Amundi US) | 856,347 | 2022-07-01 to 2026-06-30 | all kinds | 29 | AMUNDI_US, EXTERNAL, UNRESOLVED, VICTORY | 13 |
| First Trust (First Trust Advisors L.P.) | 818,076 | 2022-07-01 to 2026-06-30 | all kinds | 12 | EXTERNAL, FIRST_TRUST, FIRST_TRUST_ISS | 6 |
| Morgan Stanley | 803,775 | 2022-07-01 to 2026-06-30 | all kinds | 16 | CALVERT, MSIM, unlabelled | 9 |
| Guggenheim Investments | 699,620 | 2022-07-01 to 2026-06-30 | all kinds | 5 | GUGGENHEIM, GUGGENHEIM_GPIM | 6 |
| Russell Investments (Russell Investment Management, LLC) | 634,401 | 2022-07-01 to 2026-06-30 | all kinds | 3 | not split | 3 |
| Principal (Principal Global Investors, LLC / Principal Asset Management) | 621,566 | 2022-07-01 to 2026-06-30 | all kinds | 4 | EXTERNAL, ORIGIN, PRINCIPAL, SPECTRUM, UNRESOLVED, unlabelled | 14 |
| Columbia Threadneedle Investments (Columbia Management Investment Advisers, LLC; Ameriprise Financial) | 611,834 | 2022-07-01 to 2026-06-30 | all kinds | 11 | CMIA, EXTERNAL, unlabelled | 8 |
| T. Rowe Price (group: TRPA advisory + TRPIM 13-F filer) | 585,916 | 2022-07-01 to 2026-06-30 | all kinds | 23 | TRPA, TRPIM, UNRESOLVED, unlabelled | 11 |
| Capital Group (Capital Research and Management Company) | 490,867 | 2022-07-01 to 2026-06-30 | all kinds | 38 | not split | 2 |
| Voya (Voya Investments, LLC / Voya Investment Management) | 490,816 | 2022-07-01 to 2026-06-30 | all kinds | 14 | not split | 6 |
| Northern Trust Corporation | 472,052 | 2022-07-01 to 2026-06-30 | all kinds | 1 | not split | 4 |
| MFS Investment Management (Massachusetts Financial Services Company) | 412,692 | 2022-07-01 to 2026-06-30 | all kinds | 24 | MFS, unlabelled | 6 |
| AQR Capital Management | 411,232 | 2022-07-01 to 2026-06-30 | all kinds | 1 | not split | 8 |
| New York Life Investments (New York Life Investment Management LLC) and its subadvisers | 410,693 | 2022-07-05 to 2026-06-30 | all kinds | 6 | AUSBIL, CANDRIAM, EXTERNAL, INDEXIQ, MACKAY_SHIELDS, NYLIM, NYL_INVESTORS, UNRESOLVED, unlabelled | 17 |
| AllianceBernstein (AllianceBernstein L.P.) | 383,402 | 2022-07-01 to 2026-06-30 | all kinds | 20 | ALLIANCEBERNSTEIN, unlabelled | 12 |
| Global X (Global X Management Company LLC) | 374,527 | 2023-07-03 to 2026-06-30 | all kinds | 1 | GLOBAL_X, GLOBAL_X_CATHOLIC, GLOBAL_X_ESG, UNRESOLVED | 1 |
| Goldman Sachs Group Inc. | 345,331 | 2022-07-01 to 2026-06-30 | all kinds | 3 | UNRESOLVED, unlabelled | 2 |
| Allspring Global Investments (Allspring Funds Management, LLC) | 308,330 | 2022-07-01 to 2026-06-30 | all kinds | 8 | not split | 12 |
| GMO (Grantham, Mayo, Van Otterloo & Co.) | 257,616 | 2022-07-01 to 2026-06-30 | all kinds | 1 | not split | 14 |
| Wellington Management Group LLP | 235,903 | 2022-07-07 to 2026-06-30 | all kinds | 3 | WELLINGTON, unlabelled | 5 |
| Pacer Advisors | 233,620 | 2022-07-05 to 2026-06-30 | all kinds | 1 | EXTERNAL, PACER | 1 |
| Natixis Investment Managers (Natixis Advisors) US funds | 229,319 | 2022-07-01 to 2026-06-30 | all kinds | 7 | HARRIS_ASSOCIATES, LOOMIS_SAYLES, UNRESOLVED, unlabelled | 1 |
| Federated Hermes (Federated Hermes, Inc.) | 218,020 | 2023-04-27 to 2026-06-30 | all kinds | 15 | FEDERATED_HERMES, HERMES_HIML | 7 |
| GQG Partners | 208,219 | — | all kinds | 1 | GQG, UNDATED, unlabelled | 6 |
| Parametric Portfolio Associates LLC | 178,340 | 2023-07-03 to 2026-06-30 | all kinds | 2 | PARAMETRIC, PARAMETRIC_MSIM, unlabelled | 4 |
| Lazard (Lazard Asset Management LLC) | 154,082 | 2022-07-01 to 2026-06-30 | all kinds | 4 | not split | 13 |
| Janus Henderson Investors (Janus Henderson Investors US LLC) | 146,571 | 2022-07-01 to 2026-06-30 | all kinds | 3 | JANUS_HENDERSON, unlabelled | 9 |
| VanEck (Van Eck Associates Corporation) | 144,753 | 2022-07-01 to 2026-06-30 | all kinds | 3 | VANECK | 1 |
| Neuberger Berman (Neuberger Berman Investment Advisers LLC) | 107,661 | 2022-07-05 to 2026-06-30 | all kinds | 9 | EXTERNAL, NEUBERGER_BERMAN, unlabelled | 10 |
| Lord Abbett (Lord, Abbett & Co. LLC) | 92,635 | 2022-07-06 to 2026-06-30 | all kinds | 10 | not split | 9 |
| Virtus Investment Partners | 87,311 | 2022-07-06 to 2026-06-30 | all kinds | 5 | EXTERNAL, KAR, UNRESOLVED, unlabelled | 1 |
| Charles Schwab Trust Company | 66,779 | 2022-07-07 to 2026-06-30 | all kinds | 2 | not split | 0 |
| Deutsche Bank AG | 56,257 | 2022-07-11 to 2026-06-30 | all kinds | 3 | DIMA | 2 |
| First Eagle Investment Management | 47,253 | 2022-07-06 to 2026-06-30 | all kinds | 3 | not split | 1 |
| Calamos (Calamos Advisors LLC) | 41,870 | 2022-07-25 to 2026-06-30 | all kinds | 11 | CALAMOS, CALAMOS_SUSTAINABLE, UNRESOLVED | 10 |
| Domini Impact Investments | 39,104 | 2022-07-05 to 2026-06-29 | all kinds | 1 | not split | 6 |
| Artisan Partners (Artisan Partners Limited Partnership) | 38,481 | 2022-07-01 to 2026-06-30 | all kinds | 1 | not split | 13 |
| Baron Capital / BAMCO (Baron Funds) | 37,722 | 2022-07-04 to 2026-06-30 | all kinds | 3 | not split | 1 |
| Brown Advisory | 34,772 | 2022-07-01 to 2026-06-30 | all kinds | 1 | BROWN_ADVISORY, EXTERNAL, UNRESOLVED | 10 |
| Thornburg Investment Management | 32,356 | 2022-07-04 to 2026-06-30 | all kinds | 3 | not split | 4 |
| Cohen & Steers (Cohen & Steers Capital Management, Inc.) | 30,912 | 2022-07-06 to 2026-06-30 | all kinds | 17 | not split | 13 |
| UBS Group AG | 29,255 | 2023-07-05 to 2026-06-30 | pay only | 1 | not split | 2 |
| Dodge & Cox | 25,228 | 2023-07-03 to 2026-06-30 | all kinds | 1 | not split | 9 |
| Harris Associates / Oakmark Funds | 23,252 | 2022-07-19 to 2026-06-29 | all kinds | 2 | not split | 8 |
| Bank of New York Mellon Corp | 18,593 | 2022-07-07 to 2026-06-30 | all kinds | 2 | not split | 1 |
| Diamond Hill Capital Management | 13,658 | 2023-07-17 to 2026-06-30 | all kinds | 1 | not split | 5 |
| Parnassus Investments | 13,101 | 2022-07-12 to 2026-06-30 | all kinds | 2 | not split | 7 |
| BNP Paribas Asset Management Holding S.A. | 3,270 | 2023-07-05 to 2026-06-30 | pay only | 1 | not split | 4 |
| Bank of America Corporation | 30 | 2023-09-14 to 2026-06-17 | pay only | — | not split | 0 |
| Citigroup Inc. | 0 | — | no votes | — | — | 0 |
| Allianz Asset Management GmbH (PIMCO) | 0 | — | no votes | — | — | 0 |
| Wells Fargo & Company | 0 | — | no votes | — | — | 0 |

Citigroup, Allianz (PIMCO) and Wells Fargo have holdings and
enforcement rows but no votes or policy versions. Votes before an institution's first archived policy capture have no archived policy. For three
institutions `COVERAGE.json` counts fewer versions than the shipped `policy_versions`
table holds rows (Lazard 13 against 14, New York Life 17 against 21, Parnassus 7
against 12); the 441 total is the table's row count. Per-institution scope notes
(who votes which series, what is not ingested): `facts/voting_scope_notes.csv`.

## Three things to know before comparing a policy with votes

**1. Votes belong to the adviser that cast them, not to the brand.** One manager
can have funds voted by different advisers under different policies. Group by
`adviser_key` (a column of `proposal_decisions`, `director_decisions` and `votes`;
`voting_advisers` holds the rules it is resolved from). Example from this record, Vanguard
director items from meetings in 2026, non-support (against or abstain) in the
release v2026-11-23: VCM 7.4%, VPM 5.9%, EXTERNAL 3.0%, unlabelled 3.5%, UNRESOLVED 2.5%,
and the pre-split VANGUARD key (2026-01-01 to 01-11) 19.0% on 220 items. Pooled, the figure is 6.4%, and it
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

No network needed once you hold the bundle. Download it from Zenodo
([doi:10.5281/zenodo.24486060](https://doi.org/10.5281/zenodo.24486060), release 2026-11-23). Nothing
here assumes any library is installed. Check the files with the shell alone:

```sh
cd data/releases/v2026-11-23
shasum -a 256 -c MANIFEST.sha256 | grep -vc OK   # Linux: sha256sum -c ... ; prints 0 when every file is OK
```

The manifest covers every file except itself and nothing signs it
(`DATASHEET.md`, Integrity). `DATASHEET.md` also defines every column, every code
(`how_voted`, `position`, `vote_source`, `adviser_key` values) and the joins.
Then pick one way to read the Parquet files:

```sh
pip install duckdb pyarrow        # SQL; or: pip install pandas pyarrow
pip install pyarrow               # the pyarrow-only alternative below needs nothing else
```

Director decisions grouped by `adviser_key`. The SQL is the same ratio as the pyarrow
script below; the figures shown were produced by that script on the v2026-11-23 bundle
(pyarrow 24.0.0), and the SQL was not re-run for this release:

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
 VANGUARD      220  19.0
 unlabelled   3699   3.5
 UNRESOLVED   4295   2.5
 EXTERNAL     9917   3.0
 VPM         41073   5.9
 VCM         78066   7.4
 ALL (pooled) 137270  6.4
```

Paste it into the DuckDB shell, or pass it to `duckdb.sql("""...""").show()` in Python.
The same numbers with pyarrow only (run in the bundle directory; run with pyarrow 24.0.0):

```python
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

t = pq.read_table('facts/director_decisions.parquet',
                  filters=[('institution_id', '=', 'vanguard'), ('meeting_date', '>=', '2026-01-01')],
                  columns=['adviser_key', 'position'])
def count(tbl, *positions):
    return pc.sum(pc.is_in(tbl['position'], pa.array(positions)).cast('int64')).as_py()
groups = sorted(pc.unique(t['adviser_key']).drop_null().to_pylist(),
                key=lambda k: pc.sum(pc.equal(t['adviser_key'], k).cast('int64')).as_py()) + [None]
for key in groups:
    sub = t if key is None else t.filter(pc.equal(t['adviser_key'], key))
    pct = 100 * count(sub, 'AGAINST', 'ABSTAIN') / count(sub, 'FOR', 'AGAINST', 'ABSTAIN')
    print(f"{key or 'ALL (pooled)':14}{sub.num_rows:7}{pct:6.1f}")
```

The ratio is non-support: (AGAINST + ABSTAIN) / (FOR + AGAINST + ABSTAIN). It leaves
`SPLIT` (the manager's own funds voted both ways) and `NONE` (no for, against or
abstain vote) out of both numerator and denominator, because counting them as
support or as opposition would state a position the manager did not take. They
are still in `items`. In pandas: `pd.read_parquet('facts/director_decisions.parquet')`.
`proposal_id` is stable from the 2026-11-28 engine on (a hash of the decision's
identity; read it as a string in JavaScript, it can exceed 2^53); `director_id` is
not stable across rebuilds. Cite `accession` and `source_url` as well.

## Quickstart B: the evidence engine

The engine reads the ledger (`data/glasshouse.db`, about 3.4 GB on the maintainer's
disk). A fresh clone has no ledger. There are two ways to get one.

**Fast path: restore the ledger from the release bundle.** No network, no SEC
contact string. `glasshouse restore` checks every file against `MANIFEST.sha256`,
refuses a bundle that does not verify, refuses to overwrite a ledger that already
holds data, then writes the ledger with the code's own schema:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,release]"               # the release extra brings pyarrow, which restore needs
glasshouse restore data/releases/v2026-11-17  # 5 min 15 s on the v2026-11-17 bundle (9.7 M votes)
glasshouse engine build                       # 2 min 14 s
glasshouse ask director_record institution=vanguard adviser=VCM
```

Restore and build were timed on the maintainer's laptop into an empty
`GLASSHOUSE_DATA_DIR`. What the restored ledger is and is not:

- It holds the bundle's rows only. Votes carry `is_duplicate = 0` because the bundle
  ships only kept rows. The as-filed duplicates, the `legacy_html` rows and the
  administrative lines with no vote (`how_voted` empty) are not in it, so a few
  items the full ledger lists with position `NONE` are absent (Vanguard director
  items for 2026: 7 `none` restored, 163 in the full ledger; Deutsche Bank / DIMA
  shareholder proposals: 1,368 matching restored, 1,417 in the full ledger).
  Every other number in those results matched; ids (`proposal_id`) differ because
  they are not stable across rebuilds.
- **Policy text is not in the bundle.** The policy captures (89 in the v2026-11-17 bundle that was timed here; 533 in v2026-11-23) are restored with their
  URLs, hashes and Wayback timestamps, but the engine has no policy sentences:
  `policy_search` and `policy_diff` return nothing and say so. Re-fetch the public
  wording with `glasshouse ingest commitments --wayback`, then `glasshouse engine
  build` again.
- It is stamped as restored: `ingest_runs` holds one `restore:<bundle>:<hash>` row and
  `engine build` records `restored_from` in the engine's meta. It is not a live ingest
  and `glasshouse doctor` will not treat it as one.

**Slow path: ingest from SEC EDGAR.** This needs network access and a contact string
for SEC fair access. Use your own; the code does not hide who you are.

```sh
export GLASSHOUSE_CONTACT="your-name-and-your-own-email"   # sent in the User-Agent
glasshouse init-db                                          # 0.2 s; registers 20 institutions
glasshouse ingest npx --institution bnp_paribas --max-filings 1   # about 2 s, one small filing
glasshouse engine build                                     # 0.2 s on that tiny ledger
glasshouse ask tools                                        # every question the engine answers
```

The slow-path commands from `init-db` on were run on an empty data directory
(`GLASSHOUSE_DATA_DIR` moves it). A full ledger means many large downloads (N-PX
exhibits are 65 to 124 MB each); a full ingest was not timed. `ingest commitments
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

- Every ledger row has `source_url` and `retrieval_date`, or links by `accession` to a
  `filings` row that has them (that is how `votes` and `holdings` carry theirs). Enforcement rows have a
  `resolution_type` from a closed list; dockets are `allegation`, doubt is `unverified`.
- N-PX as filed repeats vote lines. Lines flagged `is_duplicate` stay in the working
  ledger; the release keeps only the rest.
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

Cite the version you used:

> Glasshouse (2026). *Glasshouse — institutional accountability evidence dataset
> (say vs. do)*, version 2026-11-23 [Data set]. Zenodo.
> https://doi.org/10.5281/zenodo.24486060

To refer to the dataset in general (every version), use
https://doi.org/10.5281/zenodo.24321606. The bundle's `DATASHEET.md` records the
code commit that built it. Metadata: `CITATION.cff`. Steps for a new version:
[docs/PUBLISHING.md](docs/PUBLISHING.md); open work: [docs/ROADMAP.md](docs/ROADMAP.md).

Corrections: open an issue at
<https://github.com/glasshouse-records/promises-kept-or-not/issues> with the table,
the row and the primary-source link. They are applied in a new release and listed in
[CHANGELOG.md](CHANGELOG.md). Errors found in published releases, with their size and the
release that fixes them: [docs/CORRECTIONS.md](docs/CORRECTIONS.md) (2026-11-18: releases
2026-11-17.2 to 2026-11-18.2 shipped 0.6–0.7% duplicate vote lines). Unverified items: [PENDING_VERIFICATION.md](PENDING_VERIFICATION.md).

Leads, not findings: any say-versus-do gap you derive is a lead. Check the proposal
text, the adviser, and the policy in force on the meeting date first.

Licence: code MIT (`LICENSE`); data CC-BY-4.0 (declared in `datapackage.json` and
`CITATION.cff`; no separate data licence file in the repo).
