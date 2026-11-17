# Roadmap to finished

**Finished means:** a researcher or an investigating agent can pick this up
cold, trust every number, and cite it — and the only steps left are the ones
that need the owner's own hands (publishing, accounts, contact).

Work top to bottom. How items are routed: [WORKFLOW.md](WORKFLOW.md).
Tick with the date and one line of result.

## 1. Keep the record alive
- [x] 2026-11-17 Low-cost workflow: tier scripts, `clerk`/`builder` agents, model tiers, `/next`.
- [x] 2026-11-17 First live routine run: Fidelity's guidelines changed (document dated 2026-10-05) and were captured; Fed +10 actions.
- [x] 2026-11-17 Both policy pages repaired (BlackRock unchanged; UBS came back as a NEW VERSION dated 2026-05-15); doctor now errors on a failed or 14-day-stale capture.
- [x] 2026-11-17 Source freshness now means last successful fetch (`ingest_runs`); the false DOJ error is gone.

## 2. Close the known instrument gaps
- [x] 2026-11-17 `country=` on the director tools (country that issued the ISIN); Vanguard Jan–Jun 2026 splits sum to the overall 79,430.
- [x] 2026-11-17 `country=` with a code no item carries now explains itself (GB, not UK).
- [x] 2026-11-17 T. Rowe Price advisers verified from each fund's 485BPOS (filed 2026-02-25): three funds are TRPA-voted; Capital Appreciation (CIK 793347) is TRPIM-voted. TRPIM's own guidelines now captured.
- [x] 2026-11-17 Votes are kept apart by the adviser that cast them, per fund series and by date; policy-vote pairing is refused across advisers. All 38 registrants' advisers verified from SEC filings (Vanguard split 2026-01-12, BlackRock 2025-01-01).
- [x] 2026-11-17 Review findings fixed: policy versions keyed by date, unlabelled and undated lines held apart, claims select rows by key, stricter wording and quote lints.
- [x] 2026-11-17 Director tools report non-support (against + abstain) and warn on a coding shift; BlackRock's 2025 filings record withheld votes as abstain.
- [ ] Coding-shift warning misses small counts (JPMorgan abstain 60 → 40 → 0). *(builder)*
- [ ] Say-on-pay votes are on file for every manager but not indexed; index them as a third category so pay policy can be set beside pay votes. *(builder, then reviewer)*
- [ ] UBS, BNP Paribas, Bank of America hold pay votes only: find their US fund trusts that file full N-PX reports. *(source-medic)*
- [ ] A tool that returns how many versions of a document are archived (drafts cannot cite a count today). *(builder)*
- [ ] BlackRock: 10 fund series could not be placed under either policy and are held as UNRESOLVED (includes iShares Core S&P 500 ETF). *(source-medic)*
- [ ] Policy editions missing from the archive for advisers whose votes are on file (Vanguard 2023–2025 unified editions; VPM text Jan–Jul 2026). Backfill on 2026-11-17 recovered 9 versions but only looks up each document's current address; earlier addresses must be found. *(source-medic)*
- [x] 2026-11-17 Six verifier and tool faults from the investigations fixed (quote pairing, registrant and series names, unknown country code).
- [x] 2026-11-17 Skeptical review of the day's diff: one high, two medium findings; scripts fixed, the rest with the builder.

## 3. Show what the instrument can do (verified drafts in `data/desk/`)
- [x] 2026-11-17 T. Rowe Price Associates: board-diversity rule reworded in the version captured 2026-03-09; opposition to US nominees flat (3.51%, 4.53%, 4.5%). VERIFIED 84/84, scoped to the three TRPA-voted funds. The pooled draft is in `data/desk/superseded/`.
- [x] 2026-11-17 Deutsche/DWS US trusts: climate support 44 of 51 → 12 of 32 → 3 of 22 over three seasons, lobbying steady; same funds, same companies. VERIFIED. Re-verified with the US adviser and its own policy. Open for a human: proposal sponsors; confirm DIMA votes the Equity 500 Index Portfolio.
- [x] 2026-11-17 BlackRock principles: "well below 2°C" sentence and board-diversity disclosure request gone from the version captured 2026-06-11; non-support of US nominees 4.93% → 4.28% → 4.03%. VERIFIED.
- [x] 2026-11-17 Fidelity October 2026 guidelines: two long-standing sentences removed, poison-pill and supermajority rules softened, burn-rate limits added. VERIFIED 48/48.
- [x] 2026-11-17 UBS policy: numeric board-diversity rules replaced by a discretionary one; text only (pay votes only on file). VERIFIED 64.
- [x] 2026-11-17 Open brief: non-support of board nominees at the same US companies fell 2024 → 2025 at Vanguard, State Street, Northern Trust, Goldman Sachs, Invesco, BNY Mellon; flat or up at T. Rowe, Deutsche, Franklin, Fidelity. VERIFIED 297.

## 4. Make it usable by a stranger
- [x] 2026-11-17 README rewritten; every number sourced from a command run that day. Five false statements removed (full coverage for 14 managers, 2020–2025 span, an unsourced AUM share, stale release contents, a release date that never happened).
- [x] 2026-11-17 DATASHEET numbers are computed at build time; README numbers sourced from commands. (METHODOLOGY still carries a few typed counts — refresh when next edited.)
- [x] 2026-11-17 Release bundle v2026-11-17 built and checksum-verified, with the adviser map, scope notes, policy versions and two derived tables.
- [x] 2026-11-17 Datasheet coverage counts shipped rows and states which kinds of vote each manager has; every shipped column has a definition (a build refuses an undefined one); each vote row carries its manager and adviser key. Bundle rebuilt from a clean commit, checksums verified.
- [ ] A fresh clone cannot build the engine without a full SEC ingest: document the time, or make the engine buildable from the release bundle. *(builder)*
- [x] 2026-11-17 Cold-start test passed: six questions answered correctly from README + bundle alone (2,642 items / 119 not supported matched the engine); the documentation gaps it listed are fixed.

## 5. Hand-over
- [x] 2026-11-17 `docs/HANDOVER.md` written.

## Owner only (waiting, never auto-actioned)
- Allow the daily routine to be scheduled (the app refused it on 2026-11-17); until then `scripts/routine.sh` runs only when a session runs it.
- Decide the 175 old pending findings (recommendation: reject all, with a note that they come from the superseded line-level analysis).
- Whether the release ships the managers' policy documents themselves (copyright) or only dates, links and fingerprints (current).
- Publish: Zenodo deposit and/or GitHub push — runbook in [PUBLISHING.md](PUBLISHING.md).
- Whether any manager is asked for comment on a draft, and by whom.
- Who the finished dataset is offered to (a co-signer or host organisation).
