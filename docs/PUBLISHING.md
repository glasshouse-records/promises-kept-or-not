# Publishing Glasshouse

This is the runbook for making the dataset public and citable. **Nothing here
runs automatically** — every step is a deliberate, authenticated action you take.
The agent prepares everything *up to* these steps; it cannot (and must not) push,
authenticate, or publish on your behalf.

There are two independent things you can publish:

1. **The dataset** → a versioned bundle with a **DOI** (the citable artifact for
   researchers). This is the point of the project.
2. **The code** → the public GitHub repository (optional, supports
   reproducibility and "honest access").

You can do either, both, or neither. The dataset DOI is the high-value one.

---

## 0. Pre-flight (do this first)

```sh
# Rebuild a fresh, verified bundle from the current ledger:
glasshouse release --version "$(date +%F)"

# Verify it end-to-end (must print no failures):
cd data/releases/v$(date +%F) && sha256sum -c MANIFEST.sha256 && cd -

# Sanity-check what's inside (coverage is stated honestly here):
cat data/releases/v$(date +%F)/DATASHEET.md
```

Edit [`.zenodo.json`](../.zenodo.json): set `creators[].name` ("Family, Given"),
add `orcid` / `affiliation` if you have them, and confirm `version`.

---

## 1. Publish the dataset to Zenodo (gets a DOI)

Zenodo (https://zenodo.org, free, run by CERN) mints a permanent DOI and stores
up to 50 GB per record. This is the canonical path for a citable dataset.

**Manual deposit (recommended — gives the *data* a DOI, not just the code):**

1. Sign in to https://zenodo.org → **New upload**.
2. Upload the files from `data/releases/v<DATE>/` — at minimum:
   `facts/*.parquet`, `facts/*.csv[.gz]`, `datapackage.json`, `DATASHEET.md`,
   `COVERAGE.json`, `MANIFEST.sha256`, `README.md`.
   (Tip: zip the directory first — `zip -r glasshouse-v<DATE>.zip data/releases/v<DATE>` — and upload the zip plus MANIFEST.sha256 alongside it.)
3. Metadata: **Upload type** = Dataset, **License** = CC-BY-4.0. Copy the
   title/description/keywords from `.zenodo.json`.
4. **Publish.** Zenodo issues a DOI immediately. Use the *concept DOI* (the
   "all versions" one) when you cite — later releases become new versions under it.
5. Put the DOI in `README.md` (the "Cite it" section) and in future releases'
   `README.md` template (`src/glasshouse/release.py:_readme`).

---

## 2. Publish the code repository (optional)

```sh
gh auth login                                    # one-time
gh repo create glasshouse --public --source . --remote origin --push
```

Then, if you want each tagged release archived to Zenodo automatically:

1. Enable the repo at https://zenodo.org/account/settings/github/ (flip the
   switch for `glasshouse`).
2. Cut a GitHub release — Zenodo archives the **source** and mints a DOI for it:
   ```sh
   gh release create v$(date +%F) --title "Glasshouse v$(date +%F)" \
     --notes "Dataset + code snapshot. See DATASHEET.md for coverage."
   ```
   Note: the GitHub-Zenodo integration archives the *repo* (code), not the
   gitignored 236 MB data bundle. For the **data** DOI, use the manual Zenodo
   deposit in step 1. You can also attach bundle files to the GitHub release:
   ```sh
   gh release upload v$(date +%F) data/releases/v$(date +%F)/facts/votes.parquet
   ```

---

## What stays private regardless

- The operator working ledger (triage, llm_log, outreach drafts, signals).
- Any finding a human has **not** approved (`findings` ships approved-only).
- Legacy/unvalidated parsed votes (quarantined out of releases by construction).

These boundaries are enforced in code (`publish.PUBLIC_TABLES`) and pinned by
tests (`tests/test_release.py`, `tests/test_publish.py`) — not left to this
checklist.

## Each time you publish a new version

1. `glasshouse release --version <DATE>` → fresh bundle.
2. `sha256sum -c MANIFEST.sha256` → verify.
3. New Zenodo version under the same concept DOI (and/or a new GitHub release).
4. Update the DOI/date references if needed.
