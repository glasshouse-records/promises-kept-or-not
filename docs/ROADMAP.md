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
- [x] Coding-shift warning misses small counts (JPMorgan abstain 60 → 40 → 0). *(2026-11-17: also warns when abstain vanishes — ≥30 in one period, 0 in another with ≥30 not_supported; six drafts still verify)*
- [x] Say-on-pay votes are on file for every manager but not indexed; index them as a third category so pay policy can be set beside pay votes. *(2026-11-17: `pay_record`, 87,735 items; reviewed — director tools byte-identical, Fidelity count reconciled to 1,690 exactly; frequency wording slip fixed)*
- [x] `coverage` does not list pay items per institution; no row-level pay tool (`pay_votes`) yet. *(2026-11-17: coverage gives `pay_items_by_year` and per-adviser `pay_items`, frequency excluded; a row-level tool is not needed — `pay_record company=` answers single-company questions)*
- [x] Release bundle ships proposal_decisions and director_decisions but no derived pay table; add `pay_decisions` (approval items, frequency apart) with its column dictionary. *(2026-11-17: shipped in v2026-11-17, 87,735 rows = engine pay_votes, both kinds with a `kind` column; manifest verifies clean)*
- [x] 2026-11-17 `glasshouse doctor` on a restored ledger now opens with `ledger:restored` (a restore of bundle X, NOT a live ingest) and reports source/capture freshness as "restored, not live" (info, not errors); verified on a real restore of v2026-11-17; live verdict unchanged.
- [x] 2026-11-17 UBS, BNP Paribas, Bank of America: searched EDGAR for fund trusts with full N-PX; none attributable, so none added and the three stay pay-votes-only (PACE Select is voted mostly by subadvisors; BNPP USA is a notice report; BofA has no fund trust since Columbia sold 2010). Evidence is in config/institutions.yaml comments.
- [x] A tool that returns how many versions of a document are archived (drafts cannot cite a count today). *(2026-11-17: `policy_counts`, one row per document — versions, readable_versions, first/last capture; cite `[doc_label=…].versions`)*
- [x] 2026-11-17 BlackRock: re-checked all 10 unplaced series against 45 iShares Trust SAIs; none can be keyed (Core S&P 500 ETF has its own voting-choice policy; the rest are named in no 2025-26 SAI), so all stay UNRESOLVED with the reason on record.
- [x] 2026-11-17 Vanguard unified US policy editions 2023, 2024, 2025 recovered via a new `former_urls` field (earlier addresses walked by the Wayback backfill; 3 versions, keyed VANGUARD); the VPM Jan 2026 text was already held. Still open: BlackRock and other advisers' earlier addresses not yet searched; Vanguard editions between captures (e.g. mid-year amendments) unknown. *(source-medic)*
- [x] 2026-11-17 Coverage widened to Capital Group (19 American Funds / Capital Group trusts, CRMC) and Dimensional (3 trusts, the Advisor); see config/institutions.yaml for the evidence behind each.
- [ ] Nuveen / TIAA: Nuveen Investment Trust (CIK 1013881) names Nuveen Asset Management as sub-adviser to each fund, but nuveen.com and documents.nuveen.com block honest-UA requests ("Your request was blocked"), so no policy URL is capturable; the policy exists only as an SAI appendix on EDGAR (re-hashes on every filing). Other Nuveen trusts are muni closed-end funds with almost no votes. Needs a sanctioned policy path or a METHODOLOGY source-access note. *(source-medic)*
- [ ] Columbia Threadneedle (Ameriprise): Columbia Funds Series Trust I/II, Columbia Acorn Trust and the Columbia ETF trusts file N-PX (2026-08-18) under Columbia Management Investment Advisers, but series are widely sub-advised, the SAI describes a Board-adopted policy plus separate Corporate Governance Guidelines, and no stable official PDF was found. Needs a per-series voter read and a policy URL. *(source-medic)*
- [x] 2026-11-17 Wellington Management: 45 Hartford series keyed WELLINGTON by series ID (Hartford Series Fund 12, Hartford Mutual Funds 31, Hartford Mutual Funds II 2), each only where the series' own SAI names Wellington as sole sub-adviser under a voting-delegated-to-sub-adviser section, from 2025-07-01; Wellington policy and 2026 guidelines archived from wellington.com. Left out: Hartford Schroders series, funds of funds, Hybrid and Credit Opportunities; Vanguard Explorer Value stays EXTERNAL (multi-adviser), Vanguard Windsor/Wellington Fund and John Hancock series not tracked or read.
- [x] 2026-11-17 Geode Capital Management: 55 Fidelity index series keyed GEODE by series ID (Concord Street 20, Salem Street 32, VIP Fund II 3), each only where the series' own SAI proxy-voting section is Geode's policy; Geode policy archived from geodecapital.com (year-named PDF, linked from /info). Left out: VIP Index 500 and Strategic Real Return (SAI prints both policies), and 6 index series whose SAI was not located (Mid Cap, Small Cap, Large Cap Growth, Series Large Cap Growth, Flex Mid Cap, Flex Small Cap Index).
- [x] 2026-11-18 Morgan Stanley Investment Management / Parametric: 6 Eaton Vance series keyed PARAMETRIC by series ID (Eaton Vance Mutual Funds Trust 5, Series Trust II 1), each only where the series' own SAI names Parametric as sub-adviser with voting delegated to it, from the earliest SAI date read (2024-11-01 to 2025-07-01); Parametric's own policy archived as 3 SAI-printed versions (2023-10-26, 2024-10-24, 2025-10-27). Left out: Morgan Stanley ETF Trust (SAI says the Adviser MSIM votes), Parametric Tax-Managed International Equity (no SAI located), all Eaton Vance/MSIM-voted series.
- [ ] Parametric: parametricportfolio.com answers honest-UA requests with 403, so no website copy of the policy; the 2026 SAIs print the MSIM Equity Proxy Voting Policy (names Parametric as a covered affiliate) instead of Parametric's own, so Parametric's current policy has no archived edition; needs a sanctioned path or an MSIM-policy label decision. *(source-medic)*
- [ ] Parametric/Eaton Vance follow-ups: Eaton Vance Series Trust, Investment Trust, Variable Trust, Series Fund and the Calvert trusts (Parametric named only in boilerplate, not read per series) and Innovator ETFs sub-advised by Parametric (not read). *(source-medic)*
- [x] 2026-11-18 Closed, nothing to add: Amundi US / Pioneer: Pioneer funds last filed N-PX 2024-08-28 (Pioneer was sold to Victory Capital), Amundi entities are institutional-manager filers only. Not a live US fund voter. *(source-medic)*
- [x] 2026-11-18 Closed, nothing to add: Allianz Global Investors: AllianzGI's US closed-end and mutual funds moved to Virtus (Virtus Strategy Trust, Virtus Investment Trust), so the votes belong to Virtus; the Allianz entities file institutional-manager reports. PIMCO is already tracked. *(source-medic)*
- [x] 2026-11-18 Closed, nothing to add: Legal & General: only institutional-manager N-PX (CIK 1495115, 1559265, 764068); no US registered fund trust found. *(source-medic)*
- [x] 2026-11-17 Capital Group follow-ups: 17 more trusts added, all with N-CSR naming CRMC as adviser and SAI/prospectus on proxy procedures (US Equity Fund, 12 Capital Group ETFs, ETF Trust I, US Small & Mid Cap, Central Fund Series I/II, Completion Fund Series); 55,458 vote rows ingested (Central I/II file notice reports only, 0 votes).
- [ ] Capital Group left out: Fixed Income ETF Trust (CIK 1870117, bond-only), KKR (plus) ETFs (CIKs 2040315, 2040318, 2078301, sub-advised), Portfolio Series (1537151) and the bond-only American Funds trusts; read each SAI for the voting adviser before adding. *(source-medic)*
- [ ] Dimensional master funds (CIK 896162, 896163) and the Sustainability/Social guideline pairing by series. *(source-medic)*
- [x] 2026-11-18 Dated policy text from SAI appendices: section-extracted, filing-dated versions under separate `...-as-printed-in-sai` labels (`ingest/sai_appendix.py`); Geode 3 versions (first 2024-04-24), Wellington 3 (first 2023-04-13), both before the first N-PX vote on file.
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
- [x] 2026-11-17 `glasshouse restore <bundle>` builds the ledger from the release bundle (checksums verified; 5 min 15 s, then `engine build` 2 min 14 s); policy text is not in the bundle and the engine says so. Quickstart B documents it.
- [x] 2026-11-17 Cold-start test passed: six questions answered correctly from README + bundle alone (2,642 items / 119 not supported matched the engine); the documentation gaps it listed are fixed.

## 5. Hand-over
- [x] 2026-11-17 `docs/HANDOVER.md` written.

## Owner only (waiting, never auto-actioned)
- Allow the daily routine to be scheduled (the app refused it on 2026-11-17); until then `scripts/routine.sh` runs only when a session runs it.
- Decide the 175 old pending findings (recommendation: reject all, with a note that they come from the superseded line-level analysis).
- Whether the release ships the managers' policy documents themselves (copyright) or only dates, links and fingerprints (current).
- [x] Publish: done 2026-11-17 — Zenodo doi:10.5281/zenodo.24321607 (all versions 10.5281/zenodo.24321606), code at github.com/glasshouse-records/promises-kept-or-not.
- Whether any manager is asked for comment on a draft, and by whom.
- Who the finished dataset is offered to (a co-signer or host organisation).
