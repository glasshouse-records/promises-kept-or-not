# Corrections

Every error found in a published release is recorded here: what was wrong, which
releases carry it, how big it is, and which release fixes it. Published files on
Zenodo cannot be changed, so earlier versions stay as they were; use the latest.

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
not cover every vote line in the ledger. Fixed from the release after 2026-11-18.2.
