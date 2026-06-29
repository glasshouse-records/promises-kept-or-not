# Changelog

All notable changes to the Glasshouse dataset and tooling. The **dataset** is
versioned by release date (`release/v<DATE>/`); each release is checksummed
(`MANIFEST.sha256`) and self-describing (`datapackage.json`, `DATASHEET.md`).

## v1 (2026-06-29) — first public release candidate

The cleanest, best-documented machine-readable record of what major financial
institutions **say** (archived proxy-voting / stewardship policies) versus what
they **do** (SEC N-PX votes, 13-F / N-PORT holdings), plus the enforcement
record.

**Coverage**
- 14 systemic asset managers with full *say + do* (~91% of tracked voting AUM):
  BlackRock, Vanguard, State Street, Fidelity, J.P. Morgan AM, Goldman Sachs AM,
  BNY, Invesco, UBS AM, T. Rowe Price, Franklin Templeton, DWS, Northern Trust,
  BNP Paribas AM.
- ~3.2M de-duplicated proxy votes (2023–2025; earlier years for some filers),
  ~580k holdings, ~14k enforcement actions, versioned policy snapshots.

**Trust & provenance**
- Every row carries `source_url` + `retrieval_date`; votes de-duplicated; the
  public release contains cast votes only and human-approved findings only
  (currently 0 published — the data ships as facts, not accusations).
- Independently verifiable (`sha256sum -c MANIFEST.sha256`); spot-checked
  against EDGAR ground truth.

**Hardening (pre-release audit)** — fixed false-positive / disclosure classes:
binding-commitment validation (no TOC fragments / non-commitments), anti-DEI
polarity guard, OFAC-SDN name-join exclusion, company-name conflation,
normalizer over-collapse, and removal of non-votes + a local-path column from
the public release.

_Publication is the maintainer's decision; see docs/PUBLISHING.md._
