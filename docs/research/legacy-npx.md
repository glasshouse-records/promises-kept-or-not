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
- **After the format check was relaxed to the column header alone** (State Street omits the banner) and a fourth quirk was fixed (a heading frame that opens on one line and closes on the next), **the two ISS parsers agree on 10,410,212 rows over every cached document with the ISS column header, with 460 disagreements**. Two filings fail the gate and are rejected whole: 0001081400-23-000482 and 0001193125-23-221493.
- **The remaining 2023 layouts have no validated parser yet:**
  - ISS HTML tables, "Proposal No | Proposal | Proposed By | Management Recommendation | Vote Cast": Franklin, American Century, Capital Group, Dimensional and others.
  - Federated's flat table.
  - Fidelity's tables: the old `npx_legacy.py` reads these (1.1M rows), but it has no second parser yet.
- **ISS HTML tables** ("Proposal No | Proposal | Proposed By | Management/Dissident Recommendation | Vote Cast"): two independent parsers (`legacy_isshtml_dom` uses html.parser; `legacy_isshtml_lines` uses a regex tokenizer) agree on **all 2,273,214 rows over 61 cached documents, with 0 disagreements**. Four random rows were checked against the raw HTML and matched.
  - Contract amendment 1 accepts upper-case FOR/AGAINST/ABSTAIN/WITHHOLD.
  - Lower-case values, bare digits, "Unknown", "Againt", "Took No Action" and "Non-Voting" are dropped.
  - Fidelity's HTML prefixes fund names with "VOTE SUMMARY REPORT", so those sections stay unmapped (dropped). Fidelity is read by the older `npx_legacy` parser, which has no second parser yet.

## ProxyEdge contract amendment PE-I (2026-11-27): capital I printed as lower-case i

JPMorgan Exchange-Traded Fund Trust's 2022-23 N-PX (0001438934-23-000406, 10,991
meetings) prints EVERY capital letter I as a lower-case i, in the SEC's own copy
(`iSiN:`, `UNiTED`, `MSCi`, `DiRECTORS`); both ProxyEdge parsers read 0 rows. The
layout is otherwise standard ProxyEdge, with Word/HTML style fragments between
sections. Amendment, applied by each parser's own builder without reading the other:

1. Block labels and column-header words are recognised with the letter i standing for
   I (compare after replacing i by I in the label word only; `iSiN:` = `ISIN:`). No
   other label tolerance is added.
2. Identifiers (Security/CUSIP, ISIN, Ticker) are upper-cased before validation; the
   existing check-digit rules then apply unchanged.
3. Every free-text field (fund heading, issuer, proposal text, proposal type, vote,
   for/against-management) is kept exactly as printed. Nothing is "un-mangled".
   Vote and type vocabularies keep their existing matching rules (amendment 1).
4. Word/HTML style fragment lines (containing `mso-`, `font-family`, `&quot;`,
   `height:` or `justify;`) are never fund headings, issuers or proposal text.
5. Everything else, including the per-filing 0.5% agreement gate, is unchanged.

## Contract: "Registrant Voted" text layout (2026-11-27)

Global X Funds' 2022-23 N-PX (0001135428-23-000255, `glx-npx.htm`) prints, inside
`<pre>` blocks of an HTML file, per fund:

    <centred fund name>
     Proposal                                  Proposed by Mgt. Position Registrant Voted
    ABBVIE INC.
     Security ID: 00287Y109  Ticker: ABBV
     Meeting Date: 05-May-23           Meeting Type: Annual
     1  Elect Robert J. Alpern                 Management     For          Voted - For
     8  Shareholder Proposal Regarding Report on Political
          Expenditures and Values Congruency   Shareholder    Against      Voted - Against

Two parsers (`legacy_regvoted_blocks`: splits the document into fund sections and meeting
blocks, then slices columns by the column header's character offsets; `legacy_regvoted_lines`:
a line-by-line regex state machine) each expose `parse(text: str) -> list[dict]` with exactly
the 14 keys of `legacy_issueno.KEYS`, and `parse_stats(text) -> Counter` of drops. Rules:

1. Text: HTML tags removed, entities unescaped, lines kept. Only text inside the fund
   sections counts; the leading "Non-Voting Funds" list yields nothing.
2. fund_heading: the non-empty line immediately above a column-header line
   (`Proposal  Proposed by  Mgt. Position  Registrant Voted`, any spacing), stripped. The
   header repeats after page breaks; a repeat with the SAME heading continues the current
   fund (and the current meeting, if proposal lines follow before a new issuer); a
   different heading starts a new fund.
3. issuer_name: the line directly above ` Security ID:`, stripped, as printed.
   security_id: the token after `Security ID:` ('' if none); ticker: the token after
   `Ticker:` ('' if none). Both as printed (validation is downstream).
4. meeting_date from `Meeting Date: DD-Mon-YY` -> `MM/DD/20YY`; an unreadable date drops the
   meeting. meeting_type: text after `Meeting Type:`, stripped. country '', meeting_status ''.
5. Proposal line: optional leading space, proposal_id token (`1`, `1.1`, `1A`, `1.A`), two or
   more spaces, text. Unnumbered indented lines continue the open proposal's text (joined
   with one space). The three right-hand columns (proponent, rec, vote) are read from the
   ONE line of the proposal block that carries them; a block with none, or with them on two
   lines, is dropped (counted).
6. proponent as printed (`Management`, `Shareholder`, other); rec as printed
   (`For`, `Against`, `Abstain`, `Withhold`, `1 Year`, `N/A`, ...); for_against ''.
   vote as printed after stripping a leading `Voted - ` only when exactly that
   (`Voted - For` -> `For`); `Take No Action` -> `Take No Action`; anything else
   (`Non-Voting`, `Voted - Split`, `Voted -Abstain`, `Voted -- For`, bare `Voted`) is kept
   verbatim so the downstream vocabulary drops it.
7. Proxy contests: a meeting in which any proposal_id occurs twice (a second card printed
   after the first, numbering restarting) is dropped whole and counted; so is any meeting
   whose meeting_type contains "contest" (any case).
8. Nothing is guessed: a line that fits no rule inside a meeting drops that meeting
   (counted), never a silent skip.

Downstream (wrapper `legacy_regvoted`, mirroring `legacy_issueno_html`): multiset agreement
over all 14 keys, `legacy_pe.guarded`, the 0.5% per-filing gate; vote vocabulary For ->
FOR, Against -> AGAINST, Abstain -> ABSTAIN, Withheld/Withhold -> WITHHOLD, 1 Year / 2 Years /
3 Years -> 1 YEAR / 2 YEARS / 3 YEARS, Take No Action -> TNA, else dropped; proponent
Management -> ISSUER, Shareholder -> SECURITY HOLDER, else dropped; security id: a valid
CUSIP/CINS -> cusip, a valid ISIN -> isin, else ''; fund -> series only through the SGML
header and reviewed aliases; legacy_format 'regvoted', report types LEGACY_REGVOTED(_REJECTED);
quarantined (not in PROMOTED_LEGACY_FORMATS) until review and a hand sample.
GQG's HTML-table rendering of the same columns is a later variant, not covered here.
