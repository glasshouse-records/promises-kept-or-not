---
name: next
description: Continue the Glasshouse roadmap — take the top open item in docs/ROADMAP.md, route it to the cheapest worker that can do it properly, verify, commit, tick it off. Use when asked to continue, carry on, or work the roadmap.
---

You are the orchestrator for Glasshouse. Spend your own tokens on judgment
only; everything else goes to a cheaper tier (see `docs/WORKFLOW.md`).

1. Read `docs/ROADMAP.md` (not the whole repo). Take the first unticked item
   that is not under "Owner only". If the argument names an item, take that one.
2. Decide the tier from `docs/WORKFLOW.md`. Prefer a script over any model.
   Independent items may run as parallel background workers, but never two
   workers editing the same file.
3. Write the worker a complete brief: goal, files/commands, definition of
   done, what not to touch, report length.
4. When the worker returns, check its claim yourself with one cheap command
   (`scripts/gates.sh`, `glasshouse desk verify <draft>`, or the tool run on
   real data). A worker's "done" is a claim, not a fact.
5. Tick the item in `docs/ROADMAP.md` with the date and one line of result;
   add any new item the work revealed; commit.
6. Carry on to the next item. Stop only when every remaining item is under
   "Owner only", then tell the owner in plain language what is waiting on them.

Never, without the owner's explicit yes in chat: push, publish, upload, create
an account, contact anyone, decide a pending finding, or hand-edit ledger data.
