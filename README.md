# Glasshouse

**A public-interest accountability dataset: what major financial institutions
*say* versus what they *do*.**

Glasshouse is the cleanest, best-documented, most-traceable machine-readable
record of the gap between what the world's largest asset managers **publicly
commit to** (archived stewardship/proxy-voting policies) and what they
**actually do** (SEC N-PX proxy votes, 13-F / N-PORT holdings) — alongside the
**enforcement record**. Built so researchers, journalists, and advocacy
organizations can consume, verify, and cite it.

**The dataset is the product.** Every record traces to a primary source with a
retrieval date; nothing is summed without de-duplication; coverage is stated
honestly. Findings, analysis, and outreach are optional layers built on top —
not the point.

## What's in it

| | Coverage |
|---|---|
| **SAY** | Versioned, content-addressed snapshots of institutions' own proxy-voting / stewardship policies (live + Wayback history). |
| **DO** | SEC N-PX proxy votes (the spine — votes are active choices), de-duplicated; 13-F / N-PORT holdings. |
| **DONE** | Enforcement universe (DOJ FCPA, SEC, OFAC, Federal Reserve, World Bank debarment, NLRB, UNGC, …) with **resolution type preserved** — a DPA is not a conviction; a docket is an allegation, not a finding. |

**14 systemic asset managers** have *full say+do* coverage — both archived
policy and proxy votes — representing **~91% of tracked voting AUM**:
BlackRock, Vanguard, State Street, Fidelity, J.P. Morgan AM, Goldman Sachs AM,
BNY, Invesco, UBS AM, T. Rowe Price, Franklin Templeton, DWS, Northern Trust,
and BNP Paribas AM. Proxy votes span **2020–2025** (machine-readable N-PX
covers 2023–2025 for most filers; earlier years are recovered from legacy
filings where the format allows).

Coverage is **partial by design and stated as such** — see the generated
`COVERAGE.json` / `DATASHEET.md` in each release. Absence of a manager means no
data was collected, not a clean record.

## The release: download, verify, cite

`glasshouse release` builds a versioned, self-describing, **independently
verifiable** bundle — the artifact meant for the world:

```
release/v<DATE>/
  facts/<table>.csv[.gz]    open everywhere (pandas, R, DuckDB, spreadsheets)
  facts/<table>.parquet     typed/columnar for analysis at scale
  datapackage.json          Frictionless schema + provenance + per-file SHA-256
  DATASHEET.md              schema, honest coverage, limitations
  COVERAGE.json             per-institution scope
  MANIFEST.sha256           checksum of every file
  README.md                 how to cite, how to verify, license
```

Verify the bundle without trusting us:

```sh
cd release/v<DATE> && sha256sum -c MANIFEST.sha256
```

Every row carries `source_url` + `retrieval_date`. License: data **CC-BY-4.0**
— cite "Glasshouse" with a link / DOI.

## Provenance guarantees (enforced, not promised)

- Every ledger record carries `source_url` + `retrieval_date`; enforcement rows
  carry a `resolution_type` from a closed legal enum.
- **Never sum `shares_voted` without `is_duplicate = 0`** — de-duplication is
  built into the public views, not left to the consumer.
- `aum_usd_tr` is **managed / voting AUM**, never bank balance-sheet or custody
  assets (custody banks and divested fund arms are corrected to their true
  voting footprint).
- Name-level joins are **leads, never findings**; the public `findings` table
  contains only human-approved claims. Unvalidated/legacy-parsed data is
  quarantined out of releases.
- Free public primary sources only; no paid APIs, no browser impersonation.
  Blocked sources degrade to documented Wayback snapshots.

See [METHODOLOGY.md](METHODOLOGY.md) for the full source list, legal
distinctions, the balanced-index formula, and limitations. Ambiguous items are
held in [PENDING_VERIFICATION.md](PENDING_VERIFICATION.md).

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,release]"      # [release] adds Parquet output (pyarrow)

export GLASSHOUSE_CONTACT="you@example.org"   # required by SEC fair-access policy

glasshouse init-db                            # create the ledger
glasshouse seed                               # curated enforcement snapshots
glasshouse ingest npx --institution blackrock --max-filings 2   # proxy votes
glasshouse ingest commitments --wayback       # versioned policy snapshots
glasshouse integrity                          # ledger integrity checks
glasshouse release                            # build the citable bundle
```

The institution registry lives in [config/institutions.yaml](config/institutions.yaml);
adding a filer is one entry there.

## Optional layers (built on the dataset, not part of its core)

A contradiction engine (SAY × DO), a diff engine, a concern index, a localhost
operator workbench, a static site, and a read-only MCP server all consume the
dataset. They are **human-gated**: name-join leads never auto-promote to
findings, and **nothing is published or sent without explicit human action.**

## Leads, not findings — and corrections

This dataset records **acts, dates, amounts, and votes** — never motive. Any
say-vs-do gap you derive from it is a **lead**: theme matching is lexical, so
confirm each proposal's text and intent, and the policy version in force at the
vote, against the linked primary source before publishing a claim. The
`findings` table contains only human-approved claims (currently none — the data
ships as facts, not accusations).

**Found an error?** Open an issue with the table, the row, and the
primary-source link. Provenance is the core value; corrections are welcomed and
versioned. See [CHANGELOG.md](CHANGELOG.md) and [CITATION.cff](CITATION.cff).

## License

Code: **MIT**. Data outputs: **CC-BY-4.0** — cite "Glasshouse" with a link / DOI.
