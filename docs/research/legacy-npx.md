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
- **Closed-end funds have no series.** Exception to the rule above: if the header lists no series at all and the filing's agreed rows carry exactly one fund heading, the rows map to an empty `vote_series` (as the XML-era rows of the same funds). Recorded in `legacy_parse.series_fallback` with series id `""`.
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

## ISS HTML contract amendment 7 (2026-11-27): Ticker and Security ID on one line

Fidelity-style ISS HTML (17 filings, e.g. 0000035315-23-000529, 0000024238-23-000039) prints
both labels in ONE line of the meeting-header cell:
`TICKER:&#xa0;&#xa0;3660&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;SECURITY ID:&#xa0;&#xa0;88557W101`.
Both parsers read the ticker as everything after `TICKER:` (`3660 SECURITY ID: 88557W101`) and
no security id, so 1,028,013 shipped lines carry an empty cusip (no false value: the
security-id validation rejected nothing it was given; the id was simply never read).
7a. In a meeting-header cell line, the labels `Ticker:` and `Security ID:` (any case) may both
    occur; a label's value is the text after it up to the start of the other label on the same
    line, or to the end of the line, whitespace (including no-break spaces) collapsed and
    stripped. Either order. A label occurring twice in one line rejects that meeting (counted).
7b. Nothing else changes: values are still validated downstream (a valid CUSIP/CINS -> cusip,
    a valid ISIN -> isin, else '').

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

### Registrant Voted amendment R1 (2026-11-27)

From the first run on the real document (2,166 "Meeting Date:" lines have no issuer above):
1. A `Meeting Date:` line NOT directly below a `Security ID:` line starts a new meeting of
   the SAME issuer_name, security_id and ticker as the previous meeting of the current fund
   (another meeting of that company, e.g. Constellation Brands 19-Jul-22 then 09-Nov-22, or
   a meeting continuing after a page break). With no previous meeting in the current fund
   it is dropped (counted). A page-break header (same fund heading + column header) between
   them does not matter.
2. A proposal_id is followed by ONE or more spaces (the page has ` 10 Shareholder ...`).
3. A line of digits only (a page number) is ignored and counted, never drops a meeting.
4. Vote: `Voted - X` becomes X only when X is For, Against, Abstain, Withhold, Withheld,
   1 Year, 2 Years or 3 Years; every other vote string stays verbatim (`Voted - Split`).
5. Proposal lines under a fund heading with no meeting yet are dropped (counted).

### Registrant Voted amendment R2 (2026-11-27)

From the first comparison of the two parsers (1.9% disagreement; list in
data/research/regvoted_disagreements.txt):
1. fund_heading is the nearest non-empty line above the column header that does NOT start
   with `Sub-Adviser:` (Global X Emerging Markets ETF prints a centred
   `Sub-Adviser: Mirae Asset Global Investments` line between its name and the header;
   222 such lines). The sub-adviser line is ignored.
2. `Ticker:` may follow the security id with no space (`Security ID: J6384J101Ticker: 3993`):
   security_id is the text between `Security ID:` and `Ticker:`, stripped.
3. Any other difference must be resolved from the contract text, never by copying the
   other parser's output; a case the contract does not decide drops the meeting.

### Registrant Voted amendment R3 (2026-11-27)

After R2 the parsers still differ on about 130 meetings, all cases the contract left open:
1. Right-hand columns are read from the END of the proposal block's column line with closed
   lists, at least one space between fields (columns are often squeezed:
   `Management   For Voted - For`):
   vote = one of `Voted - For|Against|Abstain|Withhold|Withheld|Split|1 Year|2 Years|3 Years`,
   `Voted -Abstain`, `Voted -- For`, `Voted`, `Take No Action`, `Non-Voting` (longest match);
   rec = one of `For`, `Against`, `Abstain`, `Withhold`, `None`, `N/A`, `1 Year`, `2 Years`,
   `3 Years`; proponent = one of `Management`, `Shareholder`, `N/A`. Header offsets are not
   used for these three fields. A column line that does not end in vote + rec + proponent in
   that order is not a column line (rule 5 applies). Text before them is proposal text.
2. Unnumbered lines that carry no columns and come after `Meeting Date:` but before the
   meeting's first proposal (e.g. `Please Note That the Company Notice ...`) are ignored and
   counted; they never become proposal text or a proposal.
3. Blank lines may separate the issuer line from ` Security ID:`; "directly above" means the
   nearest non-blank line.
4. proposal_id also takes three-part forms (`3.1.1`). Ids like `O.1` / `S.1` stay outside the
   contract (meeting dropped).

### Registrant Voted amendment R4 (2026-11-27)

After R3 the parsers differ on 0.17%, but both glue page-break notes onto the previous
proposal (AIA GROUP LTD 18-May-23 proposal 12 got "... 19 Apr 2023: Please Note That This is
A Revision ... Thank You Non-Voting" appended; its vote was right, its text was not):
1. A proposal is CLOSED once its column line has been read. Unnumbered lines that follow a
   closed proposal (before the next proposal id, issuer, `Meeting Date:` or fund section)
   are notes: ignored and counted, never proposal text, never a proposal.
2. proposal_text: the proposal's text pieces joined with single spaces, internal runs of
   whitespace collapsed to one space, stripped.

### Registrant Voted amendment R5 (2026-11-27)

Review found that R1 + R4 together can give one company's votes to the previous one: an
issuer line followed by a missing or malformed Security ID line (`BETA CORP` then a bare
`Meeting Date:`) is read as an R4 note, and the bare date then inherits ALPHA's identity. Both
parsers agree, so the gate cannot see it. R1.1 is narrowed:
1. A `Meeting Date:` line not directly below a `Security ID:` line (nearest non-blank line)
   inherits the previous meeting's identity ONLY when the nearest non-blank line above it is
   (a) a column line (R3.1) that closed a proposal of that previous meeting, or (b) the
   column header line of a repeated page header. In the real document 2,001 such lines follow
   a column line and 160 a page header; 5 follow a `... Thank You  Non-Voting  Non-Voting`
   note, which is not an R3.1 column line (no proponent), so those meetings are dropped
   (with R5.3 chains: 101 rows in blocks; the gate keeps only rows both parsers read).
2. Otherwise the meeting it starts is dropped whole (counted), whatever follows.
3. A dropped meeting leaves no identity to inherit: a later bare `Meeting Date:` with no new
   ` Security ID:` meeting in between is dropped too (counted).
4. Matching stays as printed: `Security ID:` exactly (a ` Security Id:` line is not one).

## Contract: "Registrant Voted" HTML-table layout (2026-11-27)

The same columns as the text layout above, printed as HTML tables by SEI for The Advisors'
Inner Circle Fund III (CIK 1593547; GQG and other advisers' series), one N-PX per fund
(17 cached filings, 0001135428-23-000144 ... -000235, e.g. `democracy-npx2023.htm`):

    <tr><td colspan=3><b>Democracy International Fund</b></td>...</tr>
    <tr><td colspan=2><b>Proposal</b></td><td></td><td><b>Proposed by</b></td><td><b>Mgt. Position</b></td><td><b>Registrant Voted</b></td></tr>
    <tr><td colspan=2><b>ABB LTD.</b></td>...</tr>
    <tr><td colspan=2><i>Security ID: H0010V101</i></td><td><i>Ticker: ABBN</i></td>...</tr>
    <tr><td colspan=2>Meeting Date: 07-Sep-22</td><td colspan=2>Meeting Type: Extraordinary Shareholders</td>...</tr>
    <tr><td>1</td><td colspan=2>Approve Spin-Off of Accelleron Industries AG</td><td>Management</td><td>For</td><td>Voted - For</td></tr>

Two parsers, written independently from this contract (`legacy_regvoted_html_cells`: an
html.parser tokenizer building rows of cells; `legacy_regvoted_html_rows`: regex over
`<tr>`/`<td>` markup), each expose `parse(text) -> list[dict]` with exactly the 14 keys of
`legacy_issueno.KEYS`, the same value forms as the text layout (so the text wrapper's
`translate` applies unchanged), and `parse_stats(text) -> Counter` of drops. Rules:

H1. Rows and cells. Only `<tr>` rows of `<table>`s count. A cell's value: tags removed,
    entities unescaped (once), `&nbsp;`/U+00A0 as a space, whitespace runs collapsed to one
    space, stripped. A row's VALUES are its non-empty cell values in order; a row with none
    is ignored. Cell positions and colspans are NOT used (they vary between filings and
    within one: the same proposal row has 5 or 6 cells).
H2. Column header row: values exactly `Proposal`, `Proposed by`, `Mgt. Position`,
    `Registrant Voted`. fund_heading = the values of the nearest preceding non-ignored row
    when it has exactly ONE value, joined as printed; otherwise the document is rejected
    (nothing parsed). The header repeats after page breaks: the same heading continues the
    current fund (and meeting), a different one starts a new fund.
H3. Issuer row: a row with exactly one value, immediately followed (next non-ignored row)
    by a Security ID row. issuer_name = that value. Security ID row: first value starts with
    `Security ID:` (exact case). security_id = text after `Security ID:` up to `Ticker:` (or
    the end of the value), stripped; ticker = text after `Ticker:`, found in the same value
    or in the row's second value, stripped; '' if absent. As printed (two SEDOLs
    `B44DPG3 BD5CMH2` stay as printed; validation is downstream).
H4. Meeting Date row: first value starts with `Meeting Date:` (exact; `Meeting for ADR
    Holders` or `Meeting of Board ...` are NOT meeting rows). meeting_date `DD-Mon-YY` ->
    `MM/DD/20YY`; unreadable drops the meeting. meeting_type = text after `Meeting Type:`
    in the same or the second value, stripped, '' if absent. country '', meeting_status ''.
    A Meeting Date row that does not directly follow a Security ID row continues the
    previous meeting's issuer/security_id/ticker ONLY if the row before it closed a
    proposal (H6) of that previous meeting, or is a repeated column header (H2); otherwise
    the meeting is dropped, and a dropped meeting leaves no identity for a later bare
    Meeting Date (text amendments R1 and R5).
H5. Column values (closed lists, read from the END of a row's values): vote = one of
    `Voted - For|Against|Abstain|Withheld|Withhold|Split|1 Year|One Year|2 Years|3 Years|
    Three Years`, `Did Not Vote`, `Do Not Vote`, `Take No Action`, `Non-Voting`; rec = one
    of `For`, `Against`, `Abstain`, `Withhold`, `None`, `N/A`, `1 Year`, `One Year`,
    `2 Years`, `3 Years`, `Three Years`, `Undetermined`, `Non-Voting`; proponent = one of
    `Management`, `Issuer`, `Shareholder`, `N/A`, `Non-Voting`. A row whose last three
    values are vote, rec, proponent from these lists (in that order from the end) is a
    COLUMN row; anything else is not (a row ending in e.g. `Sharehold` or `W` is not a
    column row).
H6. Proposals. Inside a meeting (after its Meeting Date row), rows are read in order:
    (a) a row whose first value is a proposal id (`1`, `12`, `1.1`, `1a`, `1.A`, `2.a`,
        `3.1.1`; letters any case; optional trailing `.` removed) AND has a second value
        that is not a column value starts a new proposal with that id; the id is not text.
    (b) any other row continues the OPEN proposal (one started and not yet closed); with
        no open proposal it starts a new proposal with proposal_id ''.
    The values between the id (if any) and the column values are text pieces. A column
    row CLOSES the proposal: proponent, rec, vote are its last three values. A proposal
    not closed when the next proposal, issuer, Meeting Date, column header or the end of
    the table starts is dropped (counted). proposal_text = text pieces joined with one
    space, whitespace collapsed, stripped; empty text drops the proposal.
H7. Values as printed: proponent, rec as printed; vote: `Voted - X` -> X (`Voted - One
    Year` -> `One Year`), `Voted – For` (en dash) is not in the list (not a column row);
    `Did Not Vote`, `Do Not Vote`, `Take No Action`, `Non-Voting` kept verbatim
    (downstream drops them). for_against ''.
H8. Proxy contests: a meeting is dropped whole (counted) if its meeting_type contains
    `contest` (any case), or a non-empty proposal_id occurs twice in it, or any of its
    proposal texts contains `Dissident` or `Management Nominee` (any case), or two of its
    proposals have identical text (unnumbered filings cannot show a repeated id).
H9. Nothing is guessed: a row inside a meeting that fits no rule (e.g. a column row with
    no open proposal and no text) drops that meeting (counted).

Downstream: a wrapper `legacy_regvoted_html` (legacy_format 'regvoted_html', report types
LEGACY_REGVOTED_HTML(_REJECTED)) uses the text wrapper's `translate` plus: proponent
`Issuer` -> Management; vote/rec `One Year` -> `1 Year`, `Three Years` -> `3 Years`; `Did
Not Vote`, `Do Not Vote`, `Undetermined`, `None`, `N/A` dropped as in the text layout.
Quarantined until review and a hand sample.

### Registrant Voted HTML amendment HR1-HR5 (2026-11-27)

From the first run of both parsers (they agree exactly on 7 of the 8 files they read; 9 of
17 files gave nothing because the contract only read `<tr>` rows):
HR1. Row stream. The document is read as ONE stream of rows in document order: every `<tr>`
     of every table (as H1), AND every `<div>` or `<p>` element that is NOT inside a table
     and contains no `<div>`, `<p>` or `<table>` of its own, as a row with ONE value (its
     text per H1; empty -> ignored). 0001135428-23-000144 prints issuer, `Security ID:`,
     `Ticker:`, `Meeting Date:` and `Meeting Type:` as such divs between tables, and
     0001135428-23-000166 prints the fund heading as a `<p>` above each table.
HR2. Table boundaries are not breaks: a proposal or meeting continues across `</table>`
     ... `<table>` (H6's "end of the table" is replaced by "end of the document").
HR3. A one-value row exactly `Ticker: X` directly after the Security ID row sets ticker; a
     one-value row exactly `Meeting Type: X` directly after the Meeting Date row sets
     meeting_type. They are part of those rows, not proposals.
HR4. Page furniture is ignored (counted) wherever it occurs: a one-value row matching
     `Page | N`, `Page N`, or digits only. It never becomes or continues a proposal.
HR5. An empty Security ID (`Security ID:` with nothing after it) gives security_id '' and
     the meeting is KEPT (as the text layout: '' if none); validation is downstream.

### Registrant Voted HTML amendments HR6-HR8 (2026-11-27)

Review found a blind spot both parsers share (so the agreement gate cannot see it): a
proposal split by a page break had its head dropped at the repeated column header, and its
tail then started a new unnumbered proposal (H6b) that took the vote ("A Director: Brian M.
Levitt" | Withheld, TORONTO-DOMINION in 0001135428-23-000235; 162 such rows over 7 filings).
HR6. When a repeated column header (H2) arrives while a proposal is OPEN, that proposal is
     dropped (counted) AND every following row up to and including the next column row
     (H5) is skipped (counted). A new issuer, Meeting Date or proposal-id row ends the skip
     early (that row is read normally).
HR7. A row inside a meeting whose LAST value starts with `Voted` but which is not a column
     row (H5), e.g. an unlisted rec such as `Two Years`, drops the whole meeting (counted).
HR8. A proposal whose text (first text piece) starts with an id-like token the H6(a) pattern
     does not accept drops the whole meeting (counted): a token ending in `.` or `)` that is
     a Roman numeral (I-XXX), one or two letters, or letters/digits containing a digit
     (`O1.`, `S4.`, `1)`, `1a)`, `E.23`, `I.`); or digits and dots glued to a letter
     (`12.14Approve`, `4.113Re-election`, `9.c9`). Section labels (`AGM`, `EGM`) glued onto
     such proposals go with them.
