# Pending verification (quarantine)

Findings and records held here are **not publishable** until a human has
verified the primary source. Every exclusion is documented — the discipline
of discarding almost-right findings is the moat.

Run `glasshouse integrity` to list ledger records currently in quarantine
(e.g. enforcement actions with `resolution_type = unverified` or missing
`primary_ref`).

| Date added | Item | Why quarantined | Resolution |
|---|---|---|---|
| 2026-06-11 | All `curated_snapshot` enforcement records (predecessor project, extracted 2026-05-26) | Hand-verified once, but must be re-verified against live primary sources before use in any published claim | open |
| 2026-06-11 | DOJ FCPA records scraped from index pages (a–z) | Index pages give case name + docket only; resolution type and penalty require the underlying case page | open |
| 2026-06-11 | ALL name-equality vote×enforcement joins | Validated false-positive class on first live run: OFAC SDN "ALDAR PROPERTIES" (Sudan-based, SDGT program, Ent_num 33282) normalizes identically to Aldar Properties PJSC (Abu Dhabi-listed developer, a different company). Name joins are leads only; finding-grade requires identifier corroboration (CUSIP/LEI/CIK) or human review | policy — enforced in `findings.flagged_votes` |
| 2026-06-14 | State Street commitment doc (`proxy-voting-engagement-guidelines`) | The configured URL resolves (via Wayback) to a 2-page "Summary of Material Changes," not the full guidelines — too thin to carry theme language, so SSGA produces no contradiction candidates. Need the correct full-policy URL before SSGA say×do findings are possible | open — data acquisition |
| 2026-06-14 | Vanguard commitment versions (6 of 7) | Rotted live URL; every Wayback snapshot since 2022 captured Vanguard's 404 page, ingested as phantom "policy versions" that broke the contradiction engine for Vanguard. Purged via `ingest commitments --purge-errors`; ingestion now rejects error pages. Only the 2022 real policy remains — a current Vanguard policy URL is still needed | partially resolved — guard added, live URL still needed |
