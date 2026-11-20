# Corrections

Every error found in a published release is recorded here: what was wrong, which
releases carry it, how big it is, and which release fixes it. Published files on
Zenodo cannot be changed, so earlier versions stay as they were; use the latest.

## 2026-11-19: votes restated by an N-PX/A shipped twice

**What was wrong.** When a fund files an amended N-PX (N-PX/A) that restates
votes with different share counts, the original line and the amended line are
not exact duplicates, so both stayed live and both shipped. Duplicate marking
only collapsed identical lines. Found while adding First Trust, whose 2026
N-PX/A for four trusts restated 56,840 lines (never published).

**Which releases, how many lines** (shipped vote `id`s matched against the
ledger's flags after re-running the marking with the fix):

| Release | DOI | Shipped votes | Superseded lines | Share | By institution |
|---|---|--:|--:|--:|---|
| 2026-11-18.3 | 10.5281/zenodo.24353272 | 20,022,329 | 290 | 0.001% | Morgan Stanley 290 |
| 2026-11-19 | 10.5281/zenodo.24357331 | 20,663,049 | 290 | 0.001% | Morgan Stanley 290 |
| 2026-11-19.2 | 10.5281/zenodo.24376068 | 23,395,801 | 290 | 0.001% | Morgan Stanley 290 |

Releases before 2026-11-18.3 are unaffected (re-checked: their only marked lines
are the ones in the 2026-11-18 correction below).

**Effect.** The 290 lines are votes of one Morgan Stanley ETF registrant (CIK
1676326) for the 2025 season, as filed on 2025-08-11; its N-PX/A of 2025-12-09
restated them and is also shipped, so those votes are counted twice (0.09% of
Morgan Stanley's shipped lines). No other institution is affected.

**Fix.** Duplicate marking now also marks a line when a later N-PX/A of the same
filer and period carries the same ballot item (issuer, CUSIP, meeting, proposal,
series); the latest amendment wins, an amendment that only adds records leaves
the original's other lines alone, and two original N-PX are never collapsed
(`tests/test_amendment_supersession.py`). Fixed in release 2026-11-20
(doi:10.5281/zenodo.24384338): none of its shipped votes is a marked duplicate or a
superseded line. A correction note was added to the description of each affected
Zenodo version on 2026-11-20.

## 2026-11-18: duplicate vote lines shipped as distinct votes

**What was wrong.** N-PX filings repeat some vote records (the same vote once per
share class, or the same series in two exhibits). The ledger marks these
`is_duplicate = 1` and every release excludes them. When new fund registrants
were added, their votes were ingested but the duplicate marking was not re-run
before the release was built, and the release step did not check for that. The
repeated lines of those registrants therefore shipped in `votes` as if they were
separate votes.

**Which releases, how many lines** (counted by matching each shipped vote `id`
against the ledger's duplicate flags after a full re-run of the marking):

| Release | DOI | Shipped votes | Duplicate lines | Share | By institution |
|---|---|--:|--:|--:|---|
| 2026-11-17 | 10.5281/zenodo.24321607 | 9,684,226 | 0 | 0.00% | none |
| 2026-11-17.2 | 10.5281/zenodo.24324314 | 12,674,571 | 87,093 | 0.69% | Dimensional 86,432; Capital Group 661 |
| 2026-11-17.3 | 10.5281/zenodo.24326076 | 15,206,245 | 97,514 | 0.64% | Dimensional 86,432; Fidelity 9,489; Wellington 867; Capital Group 726 |
| 2026-11-18 | 10.5281/zenodo.24329615 | 16,742,083 | 103,809 | 0.62% | Dimensional 86,432; Fidelity 9,489; Nuveen 4,310; Parametric 1,481; Wellington 867; Capital Group 726; Columbia 504 |
| 2026-11-18.2 | 10.5281/zenodo.24339801 | 17,267,886 | 106,362 | 0.62% | Dimensional 88,970; Fidelity 9,489; Nuveen 4,310; Parametric 1,481; Wellington 867; Capital Group 726; Columbia 519 |

**Effect.** Line counts and share sums for the institutions named above are
overstated in those releases (for Dimensional by about 3%). The derived decision
tables count each decision once, so their row counts are largely unaffected, but
their share-weighted positions summed the repeated lines. Results for other
institutions are unaffected.

**Fix.** Ingesting votes now marks duplicates before it returns, and `glasshouse
release` and `glasshouse doctor` refuse to proceed when the duplicate flags do
not cover every vote line in the ledger. Fixed in release 2026-11-18.3
(doi:10.5281/zenodo.24353272): none of its shipped votes is a marked duplicate. A correction
note was added to the description of each affected Zenodo version on 2026-11-18.
