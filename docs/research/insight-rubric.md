# What counts as an impactful insight (roadmap 3b)

Written 2026-11-28. The rubric the screens (3b-b) score against and the trial (3b-c)
tests. Everything a screen produces is a **lead**: it goes through the
investigative-journalist, `desk verify`, and the owner before any use. Footprints,
never intent: we say what was written and what was voted, not why.

## Who acts on a finding, and what they need

| Reader | Acts on | Needs from us |
|---|---|---|
| Journalist | a story with a named manager, a date and a number | one sentence that is true, a primary-source citation per fact |
| Advocacy group / shareholder campaigner | pressure on a manager before next proxy season | the specific ballots, the manager's own words |
| Pension trustee / asset owner | mandate reviews, questions to their manager | their manager compared with peers on the same ballots |
| Regulator (fund names, marketing) | a fund whose label and votes diverge | fund-level votes, the fund's name/strategy, dates |
| Researcher | a replicable measure | the query, the coverage limits, the dataset version |

## What makes a finding matter (score each 0–3, the total ranks candidates)

1. **Broken or weakened promise:** the manager's own published words point one way and its votes point the other, or the words were changed and the votes moved with them. Strongest when both are dated, especially by the managers' own document metadata.
2. **Size:** the number of ballots, the share of the manager's record, and where holdings are on file the money behind the votes. A 2-point move over 3,000 ballots beats a 40-point move over 12.
3. **Same-ballot control:** the gap holds when managers are compared on the same proposals (`peers`), not just on different ballots. Without this, a finding scores 0 here and cannot rank in the top tier.
4. **Persistence:** it holds across at least two seasons, or it is a dated change between them.
5. **Clarity:** it can be said in one plain sentence without caveats that change its meaning.

**Disqualifiers (the candidate is dropped, not down-ranked):**
- it rests on a name-level join;
- it mixes engine (proposal-level) rates with the older line-level layer;
- it compares an institution's votes with a policy belonging to a different adviser;
- it crosses the 2022-23 legacy rows without saying so;
- the rate rests on fewer than 30 ballots.

## Screens to build (3b-b), each one a script over the engine

| ID | Screen | Engine tools | What a hit looks like |
|---|---|---|---|
| S1 | Walk-back | `policy_diff` + `proposals` / `peers` by year | sentence removed or softened in theme T at date D; support on T falls after D on the same ballots, faster than at peers |
| S2 | Say vs do | `say_vs_do` | policy "generally supports" X; support for X while that version was in force is far below the stated stance |
| S3 | Peer outlier | `peers` | on ≥ 3-manager ballots in theme T, the manager sits far from the peer median, with large n |
| S4 | Unexplained shift | `proposals` by year, `policy_versions` | support on T moves sharply year to year with no policy version change in between (needs the most care: report only, no inference) |
| S5 | ESG-labelled funds | `fund_votes`, fund names | funds whose names claim ESG or sustainability vote on E&S proposals like, or less favourably than, the same manager's unlabelled funds |
| S6 | Internal split | `fund_votes` | funds of one manager and one adviser voting opposite ways on the same item (pass-through and split voting are the benign explanations to rule out) |

## Data gaps that limit what we can claim

- **Vote outcomes (passed or failed, margin) are not in the ledger.** They come from 8-K Item 5.07, which is not ingested, so "this manager's votes decided the outcome" cannot be claimed yet. A candidate data source; it would need its own source module and coverage note.
- **Shares outstanding are not in the ledger**, so we cannot compute a manager's share of the vote.
- **Holdings (13-F) cover only some managers.** Money-weighted size is used where they are on file, and the screen says when they are not.
