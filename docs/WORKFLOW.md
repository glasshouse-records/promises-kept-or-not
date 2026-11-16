# How work gets done here (orchestrator + workers)

One session **orchestrates**: it reads [ROADMAP.md](ROADMAP.md), takes the top
open item, hands it to the cheapest worker that can do it properly, checks the
result, and ticks the item. The aim is to spend expensive model time only on
judgment.

## The rule: cheapest tier that can do it right

| Tier | Who | Cost | Use for |
|---|---|---|---|
| 0 | **Scripts** — `scripts/gates.sh`, `scripts/routine.sh`, the `glasshouse` CLI | none | Anything whose steps are already known: gates, daily policy capture, enforcement refresh, engine rebuild, integrity, doctor |
| 1 | **`clerk`** (Haiku) | lowest | Running tier-0 commands and reporting back in a few lines, so long output never reaches the orchestrator |
| 2 | **`builder`**, **`source-medic`** (Sonnet) | medium | One specified code change with its test; repairing a broken ingester or a moved URL |
| 3 | **`investigative-journalist`**, **`glasshouse-reviewer`** (Opus) | high | Investigations; the skeptical review before a non-trivial diff is called done |
| 4 | **The orchestrator** (the session's own model) | highest | Deciding what to do next, design choices, writing a worker's brief, judging its result |

Agent definitions live in `.claude/agents/`; the `model:` line in each sets its tier.

## Routing

- A command with a known answer shape → run the script directly, or `clerk`
  if the output would be long.
- "Build X, in file Y, proven by test Z" → `builder`.
- A source that stopped working → `source-medic`, with the failing log lines.
- "What does the record show about …" → `investigative-journalist`. Its draft
  counts only when `glasshouse desk verify` says VERIFIED.
- A diff that touches the ledger schema, the engine build, the verifier, or
  anything that publishes → `glasshouse-reviewer` before commit.
- An unclear design, or two workers disagreeing → the orchestrator decides.

## A worker's brief must contain

The goal in one sentence, the exact files or commands, what "done" looks like
(the test, or the report format), what not to touch, and a word limit for the
report. A worker starts with no memory of the session, so the brief is all it has.

## What no tier may do without the owner's explicit yes

Push to a remote, publish or upload anything, create an account, send or
contact anyone, decide a pending finding, or hand-edit ledger data. These are
listed under "Owner only" in the roadmap and wait there.

## Standing chores

`scripts/routine.sh` once a day: captures every tracked policy page, refreshes
enforcement sources, runs integrity and doctor. It prints one line when all is
well. It exits 1 with the problem lines when a page failed to capture or a
source went stale — that output is the brief for `source-medic`. A line saying
`NEW VERSION` is a policy that changed: that is a lead for the journalist.

## Continuing in a fresh session

Type `/next`. It reads the roadmap and carries on from the top open item, so a
new session does not need the history of the old one.
