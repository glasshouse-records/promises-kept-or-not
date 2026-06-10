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
