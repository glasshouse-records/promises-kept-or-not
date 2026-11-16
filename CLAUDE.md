# Glasshouse — working conventions

Public-interest accountability **dataset**: the cleanest, best-documented,
most-trustworthy machine-readable record of what financial institutions SAY
(archived policies) vs. what they DO (N-PX votes, 13-F/N-PORT holdings) and
the enforcement record.

**The dataset is the product** (decided 2026-06-15). Its quality, provenance,
coverage honesty, and self-description are the core values — built so other
researchers, journalists, and advocacy orgs can consume and cite it. Findings,
the newsroom, outreach, and the static site are OPTIONAL LAYERS built on top
of the dataset, not the point of it. A false data point is fatal; precision
beats recall everywhere; every record is self-describing and traceable.

## The development loop (follow it in order)

1. **Brainstorm before building.** For any non-trivial change, state the
   problem, at least two approaches, and why the chosen one fits the
   constraints (zero data budget, solo maintainer, legal exposure,
   reproducibility) — in the plan, the PR, or the commit message.
2. **Red before green.** Write the failing test first; run it; watch it
   fail; then implement. Bug fixes start from a regression test that
   reproduces the bug. No fix ships without its test. For pure functions
   (parsers, the entity matcher, scoring) reach for property-based tests
   (Hypothesis, `tests/test_properties.py`): roundtrip/idempotence/invariant
   properties find the edge cases examples miss.
3. **Verify against reality, not fixtures alone.** Anything touching a
   data source gets a live smoke check; anything touching the site or
   workbench gets checked in a real browser (screenshots have caught real
   bugs here: flex-clamped charts, locale formatting, soft-404s).
4. **Review before done.** Run the `glasshouse-reviewer` agent (or an
   equivalent skeptical pass) over the diff: correctness, the invariants
   below, concurrency, and security. Then the gates: `ruff check src/ tests/`,
   `semgrep --config .semgrep.yml src/`, `pytest`, `glasshouse integrity`,
   `glasshouse doctor`. The invariants below are enforced mechanically —
   `.semgrep.yml` (LLM-no-ledger-write, no-UA-spoofing, source_url required)
   and `tests/test_invariants.py` (the dedupe-filter and no-self-send rules).

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
- `engine.py` — THE query surface: a derived, proposal-level index
  (`data/engine.db`, `glasshouse engine build`) with cited tools
  (`glasshouse ask <tool> k=v`). New analysis goes through it. `desk.py`
  re-checks an agent's draft claim by claim (`glasshouse desk verify`);
  `.claude/agents/investigative-journalist.md` is the agent that uses both.
  `investigate`/`systemic`/`detectors`/`casefile` are the older LINE-level
  layer: their rates are not comparable to engine rates.
- `ledger.py` (schema + invariants), `findings.py` / `contradictions.py`
  (analysis), `review.py` (human gate), `site.py` (static output),
  `workbench.py` (localhost operator desk), `doctor.py` + 
  `.claude/agents/source-medic.md` (maintenance loop)
- `data/` is gitignored artifact space; the SQLite ledger is the product
- `metrics.py` (balanced index + trend) + `improve.py` (self-improvement
  loop) — score the dataset, rank highest-leverage moves, auto-apply only
  the safe idempotent hygiene tier; coverage/code/source moves go
  agent→PR→merge-on-green or to a human. Data decisions and publication are
  NEVER auto-actioned.

## Design language (site + workbench)

"Through glass, stamped": cool glass-white/blue-black, registrar-blue
accent, condensed-caps display, reading serif, monospace for every
machine-verifiable identifier, rubber-stamp status marks. Do not regress
to the cream/serif/terracotta default.
