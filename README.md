# Glasshouse

**An autonomous institutional-accountability watchdog.**

Glasshouse makes the gap between what major financial institutions **publicly
commit to** and what they **actually do** — hold, vote, finance, stay silent
about — permanently visible, machine-verifiable, and hard to ignore.

> This repo is public from day 1, before it is good. It ships deltas.

## What it produces

Not database rows. **Defensible, cited, news-shaped claims.** Example shape:

> BlackRock's stewardship policy (archived 2026-01-12, p.4) commits to
> anti-corruption. Oracle has two SEC FCPA settlements (Rel. 34-67574,
> 34-95971). At Oracle's 2024 AGM, BlackRock's flagship funds voted AGAINST
> the accountability proposal — while holding $7.1B.

Every claim must satisfy three properties:

1. **Every clause traces to a primary source** with a reference number and
   retrieval date.
2. **It survives the "passive index" defense** — choices (votes, engagement,
   silence) are preferred over mere holdings.
3. **A libel lawyer would shrug at the phrasing.** Acts, dates, amounts,
   votes, silences. Never motive.

## How it works

| Layer | What |
|---|---|
| **SAY** | Versioned snapshots of institutions' own published commitments (stewardship policies, ESG reports, PRI status), incl. Wayback history. *(Phase 2)* |
| **DO** | SEC EDGAR N-PX proxy votes (the spine — votes are active choices), 13-F / N-PORT holdings. |
| **DONE** | Enforcement universe: DOJ FCPA, SEC litigation, OFAC SDN, World Bank debarment, NLRB, UNGC expulsions, and more — with **resolution type preserved** (a DPA is not a conviction; a docket is an allegation, not a finding). |
| **Join** | Entity resolution: CUSIP → LEI → CIK → guarded fuzzy match. Precision over recall; every fuzzy match is logged with its score. |
| **Findings** | The contradiction engine joins SAY × DO; the diff engine makes every change a publishable delta. *(Phase 3)* |

See [METHODOLOGY.md](METHODOLOGY.md) for formulas, source list, legal
distinctions, and limitations. Ambiguous findings are quarantined in
[PENDING_VERIFICATION.md](PENDING_VERIFICATION.md) until a human verifies the
primary source.

## Status

**Phase 1** (current): N-PX streaming ingestion, evidence ledger,
entity resolution, first enforcement sources. See roadmap in
[METHODOLOGY.md](METHODOLOGY.md#roadmap).

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

glasshouse init-db                       # create data/glasshouse.db
glasshouse seed                          # load curated enforcement snapshots
glasshouse ingest enforcement --source ofac        # live OFAC SDN bulk
glasshouse ingest npx --cik 1100663 --max-filings 1  # iShares Trust proxy votes (large download)
glasshouse report flagged-votes          # votes at enforcement-flagged issuers
glasshouse integrity                     # ledger integrity checks
```

Set a contact email for SEC requests (required by SEC fair-access policy):

```bash
export GLASSHOUSE_CONTACT="you@example.org"
```

## Hard rules

- Free public primary sources only. No paid APIs.
- Resolution type (guilty plea / DPA / NPA / civil settlement) is preserved
  and disclosed in every output.
- Court dockets are labeled **allegations**, never findings.
- Nothing is published autonomously. Every outbound action requires explicit
  human approval. *(Publicist agent: Phase 6.)*

## License

Code: MIT. Data outputs: CC-BY 4.0 — cite "Glasshouse" with a link.
