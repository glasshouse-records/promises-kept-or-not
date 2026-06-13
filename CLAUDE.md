# Glasshouse — working conventions

Public-interest watchdog: joins what financial institutions SAY (archived
policies) with what they DO (N-PX votes, 13-F/N-PORT holdings) and the
enforcement record. The atomic output is a defensible, cited claim. A false
accusation is fatal; precision beats recall everywhere.

## The development loop (follow it in order)

1. **Brainstorm before building.** For any non-trivial change, state the
   problem, at least two approaches, and why the chosen one fits the
   constraints (zero data budget, solo maintainer, legal exposure,
   reproducibility) — in the plan, the PR, or the commit message.
2. **Red before green.** Write the failing test first; run it; watch it
   fail; then implement. Bug fixes start from a regression test that
   reproduces the bug. No fix ships without its test.
3. **Verify against reality, not fixtures alone.** Anything touching a
   data source gets a live smoke check; anything touching the site or
   workbench gets checked in a real browser (screenshots have caught real
   bugs here: flex-clamped charts, locale formatting, soft-404s).
4. **Review before done.** Run the `glasshouse-reviewer` agent (or an
   equivalent skeptical pass) over the diff: correctness, the invariants
   below, concurrency, and security. Then `pytest`, then
   `glasshouse integrity`, then `glasshouse doctor`.

## Invariants the review must always check

- **Provenance:** every ledger record carries source_url + retrieval_date;
  enforcement rows have a resolution_type from the closed enum in
  `ledger.py`. Dockets are `allegation`; ambiguity is `unverified`.
- **Quarantine:** name-level joins are leads, never findings. Nothing
  reaches `findings` without a human decision with a written note.
- **Never sum `shares_voted` without `is_duplicate = 0`.**
- **LLM output is advisory only** — it lands in `triage`/`llm_log`, never
  in ledger facts. Agents fix code, never data; output is a branch/PR.
- **Nothing sends itself.** Outreach requires explicit human confirmation,
  enforced server-side.
- **Honest access only:** free public sources, no browser impersonation;
  blocked sources degrade to curated snapshots and are documented in
  METHODOLOGY.md.
- **No write locks across network waits** (commit per loop iteration);
  reads must not write (workbench GETs, reports).

## Layout

- `src/glasshouse/ingest/` — one module per source; streaming parsers
- `ledger.py` (schema + invariants), `findings.py` / `contradictions.py`
  (analysis), `review.py` (human gate), `site.py` (static output),
  `workbench.py` (localhost operator desk), `doctor.py` + 
  `.claude/agents/source-medic.md` (maintenance loop)
- `data/` is gitignored artifact space; the SQLite ledger is the product

## Design language (site + workbench)

"Through glass, stamped": cool glass-white/blue-black, registrar-blue
accent, condensed-caps display, reading serif, monospace for every
machine-verifiable identifier, rubber-stamp status marks. Do not regress
to the cream/serif/terracotta default.
