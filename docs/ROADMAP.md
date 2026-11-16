# Roadmap to finished

**Finished means:** a researcher or an investigating agent can pick this up
cold, trust every number, and cite it — and the only steps left are the ones
that need the owner's own hands (publishing, accounts, contact).

Work top to bottom. How items are routed: [WORKFLOW.md](WORKFLOW.md).
Tick with the date and one line of result.

## 1. Keep the record alive
- [x] 2026-11-17 Low-cost workflow: tier scripts, `clerk`/`builder` agents, model tiers, `/next`.
- [x] 2026-11-17 First live routine run: Fidelity's guidelines changed (document dated 2026-10-05) and were captured; Fed +10 actions.
- [ ] Repair the two policy pages that stopped serving (BlackRock global principles, UBS policy); doctor must notice a failed capture. *(source-medic)*
- [ ] Daily routine scheduled on this machine (the GitHub schedule has never run because there is no remote).

## 2. Close the known instrument gaps
- [ ] Region/country filter for director votes (US vs non-US meetings). *(builder)*
- [ ] T. Rowe Price: entity label vs the adviser named on the archived document. *(orchestrator decides, builder applies)*
- [ ] Verifier: straight-quote pairing in the quotation check; a caveat-only paragraph must cite a relevant claim. *(builder)*
- [ ] Skeptical review of the engine + desk as they now stand. *(glasshouse-reviewer)*

## 3. Show what the instrument can do (verified drafts in `data/desk/`)
- [x] T. Rowe Price board-composition wording vs director votes — VERIFIED 47/47.
- [ ] Deutsche Bank (DWS) climate votes across three seasons. *(journalist)*
- [ ] BlackRock global principles: what left the text between 2025-09-30 and 2026-06-11. *(journalist)*
- [ ] Fidelity guidelines: what changed in the October 2026 version. *(journalist)*
- [ ] One open brief: "find the largest change in the record nobody asked about". *(journalist)*

## 4. Make it usable by a stranger
- [ ] README rewritten to the truth as of today (three seasons 2024–2026, the engine, the desk, the agent), with a ten-minute quickstart. *(builder, orchestrator edits)*
- [ ] METHODOLOGY and DATASHEET numbers regenerated from the ledger, not typed.
- [ ] Fresh release bundle built and checksum-verified locally; it must include director votes and policy versions. *(clerk runs, orchestrator checks)*
- [ ] Cold-start test: a fresh agent with only the README answers three questions from the bundle and its answers are checked.

## 5. Hand-over
- [ ] `docs/HANDOVER.md`: one page — what exists, what it can and cannot support, and the exact owner-only steps in order.

## Owner only (waiting, never auto-actioned)
- Decide the 175 old pending findings (recommendation: reject all, with a note that they come from the superseded line-level analysis).
- Publish: Zenodo deposit and/or GitHub push — runbook in [PUBLISHING.md](PUBLISHING.md).
- Whether any manager is asked for comment on a draft, and by whom.
- Who the finished dataset is offered to (a co-signer or host organisation).
