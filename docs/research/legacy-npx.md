# Adding the 2022–23 voting year (legacy N-PX)

**Problem.** Votes from July 2022 to June 2023 were filed in August 2023, before the SEC's structured N-PX rule. They are free-form HTML/text documents, not XML. The ledger holds 80,938 such lines from 9 filings, parsed by `ingest/npx_legacy.py` (ISS/Broadridge table format) and tagged `vote_source='legacy_html'`. The release excludes them because they were never validated. A false vote is fatal, so these lines ship only when they are shown to be right.

**What is different from XML N-PX:**
- **No series ID on a line.** Legacy documents group votes under a "Fund Name:" heading instead. Registrant-level adviser keys still apply. Series-keyed registrants (Vanguard, BlackRock, Natixis, Virtus, the shared trusts) need fund name → series ID, or their legacy lines stay unlabelled.
- **No share counts** in most formats.
- **Several layouts.** ISS/Broadridge tables, Glass Lewis/Proxy Edge text, and manager-specific layouts.

## Approaches considered

1. **Extend the single parser, then sample-check by hand.** This is cheap, but a sample of a few hundred rows cannot show that 3 million rows are right. Rejected as the only check.
2. **Two independent parsers that must agree (chosen).** The existing parser works on the table structure. A second parser works on the plain text of the same document, with different code and different assumptions. A line ships only if both produce it with the same fields: issuer, CUSIP, meeting date, proposal, proposed by, management recommendation, and vote. Disagreement drops the line, and the disagreement rate per filing is reported. This fits the constraints: no budget, a solo maintainer, reproducible, and precision over recall. It also measures its own error rate instead of assuming it.
3. **Buy a cleaned history** (for example sec-api.io). Rejected: it isn't free, and its provenance is someone else's.

## Plan

1. **Survey.** Read every configured registrant's N-PX filed 2023-07-01 to 2024-06-30. Cache the documents under `data/legacy_cache/` and count the format markers per document (`scratchpad legacy_survey.py`). Then decide which layouts are worth a parser, by vote volume.
2. **Second parser.** Write an independent text-line parser for the ISS layout first, test-first, with property tests. Then write the agreement check: row multisets per document and field-by-field comparison.
3. **Period filter.** Legacy ingest takes only the filings for the period ending 2023-06-30. `list_filings` otherwise reaches back to 2003.
4. **Fund name → series.** Use the series names in the 2023 N-CEN data sets and EDGAR series and class data, with an exact match after normalisation. If there is no exact single match, the line stays unlabelled.
5. **Release gate.** Ship `legacy_html` lines only where both parsers agree and the filing's agreement rate is at least 99.5%. Ship nothing from a filing below that rate. Report per-filing rates in COVERAGE.json and the DATASHEET.

## Findings so far (2026-11-21)

- **JPMorgan's 2023 filings use Broadridge's "ProxyEdge" fixed-width text**, not the ISS HTML tables the existing parser reads. That parser gets 0 rows from them. Two independent ProxyEdge parsers are being written to one contract: `legacy_pe_blocks` slices by column offsets, and `legacy_pe_lines` is a line-regex state machine.
- **ProxyEdge reports "For/Against Management", not the management recommendation.** Storing an inferred recommendation would be a derived fact. The decision is pending.
- **The filing's SGML header (`.hdr.sgml`) lists each series ID with its name.** So fund heading → series ID can come from the filing itself.
- **One filing can carry another registrant's funds.** JP Morgan Mutual Fund Investment Trust's 2023 N-PX document is the same 35 MB report as the ETF Trust's. Rule: a fund section is kept only if its name maps to a series in the filing's own header. Otherwise the same votes would be counted under two registrants.
- **The documents are large** (up to 35 MB of text), so the cache under `data/legacy_cache/` is gzip-compressed and keeps one copy per document.
- **ISS text: two parsers agree on 4,827,995 rows over every cached 2023 ISS document** (2026-11-21), with 21 rows that differ; every document is under the 0.5% gate (worst 0.29%). Three format quirks found by the disagreements, each now a regression test in both parsers:
  - Invesco frames fund headings as `=Name====`, with no space.
  - Northern Funds continue a heading ending in `-` on an unframed line (the subadviser's name).
  - Frequency recommendations wrap inside their column (`Three` / `Years`). In the real documents, all 7,267 bare number words continue with "Year(s)" on the next line, so an uncompleted stub is dropped.
