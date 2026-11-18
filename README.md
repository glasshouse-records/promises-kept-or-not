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

**Status, 2026-11-18:** published. Data: Zenodo,
[doi:10.5281/zenodo.24353272](https://doi.org/10.5281/zenodo.24353272) (latest version, 2026-11-18.3;
all versions: [10.5281/zenodo.24321606](https://doi.org/10.5281/zenodo.24321606)).
Code: <https://github.com/glasshouse-records/promises-kept-or-not>.
The `findings` table is empty: no claim has passed human review. Drafts in
`data/desk/` are unpublished leads; they are not in the release or this repo.

## What is in it

Figures below are from the release `v2026-11-18.3` (its `DATASHEET.md` and
`COVERAGE.json` are authoritative). Counts drift; the commands print current ones.

| Layer | Table(s) | What it holds, honestly |
|---|---|---|
| Archived policy versions | `commitments`, `policy_versions` | 187 captures of 26 managers' proxy-voting documents, 163 distinct text versions (77 from Wayback, 30 our own fetch, 56 printed in fund SAIs on EDGAR). Hashes, dates, URLs; no policy text. Dated by the capture day, or for SAI-printed text by the SAI's filing date (text was public by then). 98 of the 107 non-SAI versions also carry the date the manager's own software wrote the file. Gaps exist. |
| Proxy votes | `votes`, `fund_series`, `voting_advisers`, `voting_scope_notes` | US-registered funds only, from N-PX. Meeting dates 2023-07-01 to 2026-06-30 (three N-PX seasons, named 2024, 2025, 2026: July to June, named by end year). 20,022,329 vote lines after removing duplicates. Only the funds on file, not whole firms. |
| Director votes (DERIVED) | `director_decisions` | 2,288,878 rows: one per director-nominee item per manager and adviser. Rebuilt from `votes` by `glasshouse engine build`. |
| Shareholder proposals (DERIVED) | `proposal_decisions` | 128,474 rows: one per (manager, adviser, company, meeting, proposal). Same rebuild. Other management items (auditors, pay) are in `votes` but not here. |
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
| BlackRock | BIS, BAIS, UNRESOLVED | 2024-26 | all kinds | 4 | 13: 12 of the BIS principles + 1 of the BAIS guidelines (from 2019-08-06) | BIS/BAIS split from 2025-01-01; 10 series cannot be placed (UNRESOLVED), incl. iShares Core S&P 500, whose shareholders choose BIS or a third-party policy from 2025 |
| Vanguard | VANGUARD, VPM, VCM, EXTERNAL | 2024-26 | all kinds | 5 | 8 (from 2022-01-17) | Teams split 2026-01-12; four pre-split editions (2022, 2023, 2024, 2025) cover 2022 to 2026-01-11 |
| State Street | none keyed | 2024-26 | all kinds | 4 | 7 (from 2020-09-29) | 3 SPDR Nuveen muni ETFs may follow Nuveen's policy |
| Fidelity | GEODE, unlabelled | 2024-26 | all kinds | 7 | 10: 6 FMR (from 2023-04-16) + 1 Geode website copy + 3 Geode SAI-printed (from 2024-04-24) | 55 index series (Concord Street, Salem Street, VIP II) keyed GEODE from 2025-07-01, where the series' own SAI gives only Geode's voting policy; all other lines unlabelled, never paired with a policy |
| JPMorgan | none keyed | 2024-26 | all kinds | 2 | 6 (from 2021-01-25) | |
| Goldman Sachs | none keyed | 2024-26 | all kinds | 2 | 2 (from 2022-10-31) | |
| BNY | none keyed | 2024-26 | all kinds | 2 | 1 (2025-07-18) | Sub-advised funds vote under the sub-adviser's own rules |
| Invesco | none keyed | 2024-26 | all kinds | 1 | 2 (from 2024-02-24) | One trust only; sub-adviser policies not checked |
| T. Rowe Price | TRPA, TRPIM | 2024-26 | all kinds | 4 | 12 (from 2023-01-30) | 4 registrants, 5 fund series: 3 registrants (1 series each) TRPA-voted; the 4th (CIK 793347) holds 2 series, Capital Appreciation and Capital Appreciation and Income, both TRPIM-voted |
| Franklin Templeton | none keyed | 2024-26 | all kinds | 2 | 2 (from 2026-06-26) | Sub-adviser use not ruled out for some series |
| Deutsche Bank (DWS) | DIMA | 2024-26 | all kinds | 3 | 2 (from 2026-06-27) | One archived letter is DWS Investment GmbH's, not the US trusts' adviser |
| Northern Trust | none keyed | 2024-26 | all kinds | 1 | 4 (from 2024-05-14) | Multi-manager series use outside sub-advisers |
| Charles Schwab Trust | none keyed | 2024-26 | all kinds | 2 | 0 | No policy archived |
| Capital Group (American Funds) | none keyed | 2024-26 | all kinds | 37 (34 file votes) | 2 (from 2025-04-05) | CRMC votes all 37 trusts (American Funds and Capital Group ETFs); its equity divisions are not separated in the filings |
| Dimensional | DFA, DFA_SOCIAL, DFA_SUSTAINABILITY | 2024-26 | all kinds | 5 (3 trusts + 2 master funds) | 14: 2 Standard + 2 Social/Sustainability website copies + 10 printed in a fund SAI (Standard from 2023-02-28, Social/Sustainability from 2024-02-28) | Master funds (CIK 896162, 896163) added: the feeder SAIs say the Advisor votes for them; 5 Social and 10 Sustainability series (incl. 4 ETFs) keyed to their own guideline text from the SAI that split them (2024-02-28), never paired with the Standard text; 2025 and 2026 reports of two trusts stop at exactly 500,000 records in the SEC file itself: counts are lower bounds |
| Wellington (via Hartford Funds) | WELLINGTON, unlabelled | 2024-26 | all kinds | 3 Hartford trusts | 5: 2 website copies (2026-11-17) + 3 SAI-printed (from 2023-04-13) | Wellington has no fund trust of its own; 45 Hartford series whose SAI names Wellington as sole sub-adviser are keyed WELLINGTON from 2025-07-01; Schroders-advised series, funds of funds and earlier meetings stay unlabelled |
| Parametric (via Eaton Vance) | PARAMETRIC, unlabelled | 2024-26 | all kinds | 2 Eaton Vance trusts | 4 printed in a fund SAI: 3 of Parametric's own text (from 2023-10-26) + 1 MSIM-policy copy keyed PARAMETRIC_MSIM (2026-04-28) | Parametric has no fund trust of its own; 6 series whose SAI names Parametric as sub-adviser with voting delegated to it are keyed PARAMETRIC from 2024-11-01 to 2025-07-01; Eaton Vance-voted series, Morgan Stanley ETF Trust, Eaton Vance Series/Investment/Variable Trusts and Series Fund, Calvert and Innovator ETFs (adviser votes, reviewed 2026-11-18) stay unlabelled; its website blocks honest clients, so no website policy copy |
| Morgan Stanley Investment Management | MSIM, unlabelled | 2024-26 | all kinds | 8 registrants (Institutional Fund Trust, Institutional Fund Inc, Variable Insurance Fund, Europe Opportunity, Insight, ETF Trust, 2 closed-end) | 4 (from 2023-04-28, text printed in a fund SAI) | MSIM votes every series under its Equity Proxy Voting Policy per each registrant's SAI / N-CSR; keyed from the earliest filing read (2023-01-27 to 2023-04-28; closed-end 2023-03-10); the ETF Trust is keyed per series from 2023-10-07 (13 Eaton Vance and Parametric ETFs) and its six Calvert ETFs, which follow Calvert's own policy, stay unlabelled; 387,712 votes (2024-26 N-PX); morganstanley.com blocks honest clients, so the policy is the text printed in a fund SAI |
| Columbia Threadneedle | CMIA, unlabelled | 2024-26 | all kinds | 10 Columbia registrants (6 trusts, 2 variable-insurance trusts, 2 closed-end funds) | 7: 1 website copy (2026-11-18) + 6 printed in a fund SAI (from 2023-02-27) | Columbia Management Investment Advisers votes every series, sub-advised included, per each trust's SAI; keyed from each trust's earliest SAI read (2023-03-01 to 2023-08-01); Pyrford International Stock Fund stays EXTERNAL until 2026-04-30; Variable Insurance Trust keyed from 2023-05-01, closed-end Tri-Continental and Seligman Premium Technology from 2023-03-03, Variable Series Trust (Wanger Advisors Trust until 2025, Columbia Wanger voted) only from 2026-05-01; archived policy is the Corporate Governance Guidelines (the document with the voting stances) |
| Nuveen / TIAA | NUVEEN, unlabelled | 2024-26 | all kinds | 6 trusts | 4 (from 2023-10-27, text printed in a fund SAI) | Nuveen Investment Trust, II, III (Nuveen Asset Management), TIAA-CREF Funds and Life Funds (Teachers Advisors) and College Retirement Equities Fund (TIAA-CREF Investment Management) vote under the Nuveen Proxy Voting Policies; keyed from each trust's earliest SAI read (2023-03-01 to 2023-12-29); the Winslow-sub-advised series stays EXTERNAL; muni closed-end funds not covered; nuveen.com blocks honest clients, so the policy is the text printed in a fund SAI |
| MFS | MFS, unlabelled | 2024-26 | all kinds | 24 registrants (Series Trusts I-XIII, XV-XVII, 3 Variable Insurance Trusts, Massachusetts Investors Trust and Growth Stock Fund, Active ETF Trust, 2 closed-end bond funds) | 6: 2 website copies (live 2026-11-18; Wayback capture of 2022-08-08 shows the 1 February 2020 edition) + 4 printed in the Series Trust I SAI (1 January 2023 to 2026, from 2022-12-28) | MFS votes every series under its own policy per each SAI / N-CSR, no outside sub-adviser named; keyed from the earliest SAI read (2022-01-28 to 2022-12-29; ETF trust 2025-06-27; closed-end 2023-01-19); 316,510 votes (2024-26 N-PX); municipal and money-market trusts not ingested (no equity votes) |
| American Century Investments | AMERICAN_CENTURY, unlabelled | 2024-26 | all kinds | 9 registrants (Mutual Funds, Capital Portfolios, Growth Funds, World Mutual Funds, Strategic Asset Allocations, Quantitative Equity Funds, Variable Portfolios, Investment Trust, ETF Trust incl. Avantis) | 10 distinct text versions: 6 website (the policy body of the page, read from 'American Century Investment Management, Inc. (the Advisor)' to 'Electronic records will be kept of all votes made'; 9 captures: live 2026-11-18, edition 'Last Revised: June 2025', plus 8 Wayback captures 2022-06-25 to 2024-04-23, several differing only in page navigation or trademark spacing) + 4 printed in the Mutual Funds SAI (2022-02-28 to 2026-02-27) | American Century Investment Management votes every series per each SAI, Nomura-sub-advised series included; keyed from each trust's earliest SAI read (2022-02-28 to 2022-12-29); 1,664,486 votes (2024-26 N-PX); bond, municipal and fund-of-funds trusts and the institutional-manager filers not ingested |
| Janus Henderson | JANUS_HENDERSON, unlabelled | 2024-26 | all kinds | 3 registrants (Janus Investment Fund, Janus Aspen Series, Janus Detroit Street Trust ETFs) | 9: 4 website PDFs ('Last Review Date' March 2021, March 2022, February 2025, July 2026; Wayback captures 2021-06-15 to 2025-08-27 plus live 2026-11-18) + 5 printed in the Janus Investment Fund SAI (March 2023 to July 2026, from 2023-10-27) | Janus Henderson Investors US LLC votes every series per each SAI; Intech (its own policy) voted the Intech Managed Volatility funds until 2022-04-05 and Janus Aspen U.S. Low Volatility until 2023, before the dated window, so no series is EXTERNAL; keyed from each trust's first SAI read with the Adviser alone voting (2022-02-28 to 2023-04-28); 105,138 votes (2024-26 N-PX); Clayton Street Trust (fund of funds) and the institutional-manager reports not ingested |
| AllianceBernstein | ALLIANCEBERNSTEIN, unlabelled | 2024-26 | all kinds | 20 registrants (AB Cap Fund, Core Opportunities, Discovery Growth, Equity Income, Large Cap Growth, Relative Value, Sustainable Global and International Thematic, Global Risk Allocation, Global Real Estate, Institutional Funds, Portfolios, Trust, Variable Products Series Fund, Active ETFs, Bond, Global Bond, High Income, Global High Income closed-end, Bernstein Fund) | 12: 8 website PDFs (editions March 2021, August 2021, March 2022, March 2023, September 2023, August 2024, May 2025 from Wayback captures 2021-05-14 to 2025-07-05, October 2025 live 2026-11-18) + 4 printed in the AB Large Cap Growth Fund SAI (2022-10-28 to 2026-10-28) | AllianceBernstein L.P. votes every series per each SAI (the Bernstein Fund, the former Sanford C. Bernstein Fund, prints the same policy), no sub-adviser votes, so no series is EXTERNAL; keyed from each registrant's earliest SAI read (2022-01-28 to 2023-02-14; the closed-end fund from its N-CSR); 280,310 votes (2024-26 N-PX); notice-only registrants (Corporate Shares, Fixed Income Shares, municipal funds, Multi-Manager Alternative, Bernstein Fund II) not ingested |
| Federated Hermes | FEDERATED_HERMES, HERMES_HIML, unlabelled | 2024-26 | all kinds | 15 registrants (Equity Funds, Income Securities Trust, Strategic Dividend Growth, Global Allocation, World Investment Series, Managed Pool Series, MDT Series, Index Trust, Insurance Series, ETF Trust, High Yield Trust, Fixed Income Securities, Institutional Trust, Adviser Series, Sustainable High Yield Bond) | 7: 2 website PDF editions (April 2020 from the Wayback capture of 2020-12-02, January 2024 live 2026-11-18) + 5 printed in the Global Allocation Fund SAI (2022-01-27 to 2026-01-27) | The Federated advisers vote every series per each SAI, except series sub-advised by Hermes Investment Management Limited (own policy, not archived: key HERMES_HIML, never paired with text); keyed from each trust's earliest SAI read (2022-01-26 to 2022-12-27; Adviser Series per series); 218,065 votes (2024-26 N-PX); money-market, municipal, Core Trust and notice-only registrants not ingested |
| Neuberger Berman | NEUBERGER_BERMAN, EXTERNAL, unlabelled | 2024-26 | all kinds | 9 registrants (Equity Funds, Advisers Management Trust, Alternative Funds, ETF Trust, Next Generation Connectivity, Energy Infrastructure & Income, High Yield Strategies, Real Estate Securities Income, Private Markets Access) | 10: 5 website PDF versions (editions January 2022, February 2023, March 2024, February 2025 and a 'Neuberger' re-issue, from Wayback captures 2022-07-26 to 2026-05-11; nb.com answers honest clients with a bot challenge, so no live copy) + 5 printed in the Advisers Management Trust SAI (2022-04-20 to 2026-04-15) | NBIA votes every series per each SAI / N-CSR Item 7 except the Absolute Return Multi-Manager Fund (Subadvisers vote) and the Greater China Equity Fund (Green Court), kept EXTERNAL; keyed from each registrant's earliest SAI or N-CSR read (2022-01-05 to 2022-12-15); 84,839 votes (2024-26 N-PX); municipal, NB Crossroads / Private Markets, trust-company and manager-level reports not ingested |
| Allspring | ALLSPRING, unlabelled | 2024-26 | all kinds | 8 registrants (Funds Trust, Master Trust, Variable Trust, Exchange-Traded Funds Trust, Global Dividend Opportunity, Income Opportunities, Multi-Sector Income, Utilities & High Income) | 12: 7 website versions (approvals November 2021 to 10 February 2026; Wayback captures 2022-05-26 to 2026-07-16 plus the live page) + 5 printed in the Allspring Variable Trust SAI (2022-04-25 to 2026-04-23) | Allspring Funds Management votes every series under the Allspring policy (Board delegation in each SAI; sub-advisers only give input, so no series is EXTERNAL); keyed from each registrant's earliest SAI read (2022-01-25 to 2024-12-02); master portfolios carry the votes, feeders none; 149,791 votes (2024-25 N-PX); the 2026 N-PX is pending a re-ingest; Wells Fargo & Company is a separate institution |
| UBS | none keyed | 2024-26 | pay only | 1 | 2 (from 2024-06-11) | Combined report for several UBS entities |
| BNP Paribas AM | none keyed | 2024-26 | pay only | 1 | 4 (from 2024-04-21) | Ex-AXA IM votes may not follow the archived policy |
| Bank of America | none | 2024-26 | pay only, 30 lines | 1 | 0 | Not a fund manager; holdings and enforcement only |

Citigroup, Allianz (PIMCO) and Wells Fargo have holdings and
enforcement rows but no votes or policy versions. "None keyed": the registry
records no adviser keys, so nothing is split. "From" is the first capture date;
votes before it have no archived policy. Full notes: `facts/voting_scope_notes.csv`.

## Three things to know before comparing a policy with votes

**1. Votes belong to the adviser that cast them, not to the brand.** One manager
can have funds voted by different advisers under different policies. Group by
`adviser_key` (a column of `proposal_decisions`, `director_decisions` and `votes`;
`voting_advisers` holds the rules it is resolved from). Example from this record, Vanguard
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

No network needed once you hold the bundle; it is not downloadable yet. Nothing
here assumes any library is installed. Check the files with the shell alone:

```sh
cd data/releases/v2026-11-18.3
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

Director decisions grouped by `adviser_key` (this exact query was run, with
duckdb 2.0.0):

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

Paste it into the DuckDB shell, or pass it to `duckdb.sql("""...""").show()` in Python.
The same numbers with pyarrow only (run in the bundle directory; run with pyarrow 26.0.1):

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
`proposal_id` and `director_id` are not stable across rebuilds; cite `accession`
and `source_url`.

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
- **Policy text is not in the bundle.** The 89 policy captures are restored with their
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

Cite the version you used:

> Glasshouse (2026). *Glasshouse — institutional accountability evidence dataset
> (say vs. do)*, version 2026-11-18.3 [Data set]. Zenodo.
> https://doi.org/10.5281/zenodo.24353272

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
