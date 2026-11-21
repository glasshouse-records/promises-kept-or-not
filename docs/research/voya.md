# Voya (Voya Investments, LLC / Voya Investment Management) - research for institutions.yaml

Research only, read 2026-11-21 via glasshouse.http (EDGAR data.sec.gov submissions, sec.gov Archives) and curl with the honest UA (voya.com PDF, Wayback CDX). Nothing in data/, config/ or the ledger was touched. N-PX exhibits and SAIs were downloaded to a scratch directory outside the repo and parsed with `iter_vote_rows` / `extract_section` (pure functions); no ingest command was run.

## Verdict in six lines

- 14 registrants file N-PX vote tables with operating-company votes in 2024-2026 (8 open-end trusts/companies, 6 closed-end funds; two of them, Voya Funds Trust and Voya Credit Income Fund, have only nine rows a year). Exact list in section 1.
- Every SAI read (22 filings, 2021 to 2026) says the Board's proxy procedures "delegate to the Adviser [Voya Investments, LLC] the authority to vote proxies", and Appendix B is the Board-approved "Voya Funds" policy that Voya Investments' own Proxy Coordinator / Active Ownership team executes through a proxy advisory firm. Sub-advisers (Voya IM, JPMorgan, T. Rowe Price, Invesco, CBRE, Morgan Stanley, Baron, Columbia, American Century) only give recommendations ("Investment Professionals").
- The same policy contains an escape clause: the Board "may" delegate a fund to its sub-adviser (a "Sub-Adviser-Voted Fund", governed by that sub-adviser's policy). No SAI 2021-2025 names any such fund; the May 2026 edition adds "Appendix A: Sub-Adviser-Voted Funds - None". So no series is EXTERNAL.
- Result: one key, `VOYA`, at registrant level for all 14 registrants; no `series_adviser` exceptions needed; no `EXTERNAL`, no `UNRESOLVED`. Affiliated sub-adviser Voya IM keeps `VOYA` because the same Voya Funds policy governs (not Voya IM's own website policy, see section 4).
- Policy text: one SAI-appendix label (identical text across all trusts; markers verified on 23 filings in 9 trusts). No website label: the only Voya website policy PDF is Voya IM's policy for separate-account clients, a different document.
- Doubts: section 5 (the May 2026 rewrite will trip the 3x length guard, fund-of-funds series, duplicate rows across paired series, two one-issuer registrants).

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

N-PX filed late August each year (2024-08-27/28, 2025-08-25, 2026-08-27). "Series with votes" = distinct `voteSeries` with at least one operating-company issuer.

| CIK | EDGAR name | Type | Series / funds with operating-company votes | N-PX accessions (2024 / 2025 / 2026) |
|---|---|---|---|---|
| 837276 | Voya INVESTORS TRUST | open-end (insurance) | 14: S000005647 VY CBRE Global Real Estate, S000005747 VY CBRE Real Estate, S000005746 VY Invesco Growth and Income, S000005623 VY JPMorgan Emerging Markets Equity, S000005624 VY JPMorgan Small Cap Core Equity, S000005745 VY Morgan Stanley Global Franchise, S000005759 VY T. Rowe Price Capital Appreciation, S000005760 VY T. Rowe Price Equity Income, S000010459 Voya Balanced Income, S000005794 Voya High Yield, S000005752 Voya Large Cap Growth, S000012824 Voya Large Cap Value, S000005758 Voya U.S. Stock Index, S000079415 Voya VACS Index Series S | 0001021408-24-004962 / 0001193125-25-187782 / 0001193125-26-370751 |
| 1039001 | Voya PARTNERS INC | open-end (insurance) | 12: S000010768 VY American Century Small-Mid Cap Value, S000007612 VY Baron Growth, S000007614 VY Columbia Contrarian Core, S000010008 VY Columbia Small Cap Value II, S000007611 VY Invesco Comstock, S000007613 VY Invesco Equity and Income, S000007594 VY JPMorgan Mid Cap Value, S000007608 VY T. Rowe Price Diversified Mid Cap Growth, S000007609 VY T. Rowe Price Growth Equity, S000007598 Voya Global Bond, S000007597 Voya Global Insights, S000009828 Voya International High Dividend Low Volatility | 0001021408-24-005311 / 0001193125-25-187800 / 0001193125-26-369260 |
| 1063946 | Voya EQUITY TRUST | open-end | 12: S000066935 Corporate Leaders 100, S000066938 Global Income & Growth, S000019684 Large Cap Value, S000008383 Large-Cap Growth, S000066936 Mid Cap Research Enhanced Index, S000066937 Small Company, S000008385 MidCap Opportunities, S000034091 Multi-Manager Mid Cap Value, S000075515 Small Cap Growth, S000055625 U.S. High Dividend Low Volatility (2024, 70 rows 2025), S000097620 VACS Series LCC (2026 only), S000080522 VACS Series MCV | 0001021408-24-004955 / 0001193125-25-187783 / 0001193125-26-369267 |
| 895430 | Voya MUTUAL FUNDS | open-end | 7: S000008527 Global High Dividend Low Volatility, S000055623 International High Dividend Low Volatility (2024 only), S000034101 Multi-Manager Emerging Markets Equity, S000030601 Multi-Manager International Equity, S000031148 Multi-Manager International Factors (2024 only), S000008531 Multi-Manager International Small Cap, S000079628 VACS Series EME | 0001021408-24-004969 / 0001193125-25-187797 / 0001193125-26-370753 |
| 916403 | Voya VARIABLE PRODUCTS TRUST | open-end (insurance) | 2: S000008638 MidCap Opportunities, S000008640 SmallCap Opportunities | 0001021408-24-004977 / 0001193125-25-187809 / 0001193125-26-369258 |
| 2664 | Voya VARIABLE FUNDS | open-end (insurance) | 1: S000008703 Voya Growth and Income Portfolio | 0001021408-24-005312 / 0001193125-25-187802 / 0001193125-26-370752 |
| 846799 | Voya BALANCED PORTFOLIO INC | open-end (insurance) | 1: S000008663 (8,988 rows 2024, 279 rows 2025, no 2026 N-PX) | 0001021408-24-005342 / 0001193125-25-187805 / none |
| 1066602 | Voya FUNDS TRUST | open-end | 1: S000029692 Voya Floating Rate Fund, 9 rows (Cumulus Media) in 2024 and 2025 only | 0001021408-24-004949 / 0001193125-25-187762 / cover only |
| 1385632 | Voya Asia Pacific High Dividend Equity Income Fund | closed-end | n/a (no series), about 3,000 rows a year | 0001021408-24-004943 / 0001193125-25-187779 / 0001193125-26-369257 |
| 1332943 | Voya Global Advantage & Premium Opportunity Fund | closed-end | n/a, about 3,300 rows | 0001021408-24-005345 / 0001193125-25-187770 / 0001193125-26-369269 |
| 1285890 | Voya GLOBAL EQUITY DIVIDEND & PREMIUM OPPORTUNITY FUND | closed-end | n/a, about 3,300 rows | 0001021408-24-005344 / 0001193125-25-187771 / 0001193125-26-369270 |
| 1417802 | Voya Infrastructure, Industrials & Materials Fund | closed-end | n/a, about 3,900 rows | 0001021408-24-005346 / 0001193125-25-187804 / 0001193125-26-369268 |
| 1496292 | Voya Emerging Markets High Dividend Equity Fund | closed-end | n/a, about 4,400 rows | 0001021408-24-004975 / 0001193125-25-187803 / 0001193125-26-369259 |
| 1124959 | VOYA CREDIT INCOME FUND | closed-end (interval) | n/a, 9 rows (Cumulus Media) in 2024 and 2025 only | 0001021408-24-004945 / 0001193125-25-187761 / cover only |

Checked and left out:
- Cover-only N-PX in 2024-2026 (no vote table): Voya Variable Insurance Trust 1090682, Voya Strategic Allocation Portfolios 935070, Voya Government Money Market Portfolio 2663, Voya Intermediate Bond Portfolio 2646, Voya Enhanced Securitized Income Fund 1995568 (also Floating Rate's and Credit Income's 2026 N-PX).
- Voya Separate Portfolios Trust 1392116: 2025 vote table has 10 Target Retirement series, issuers only Vanguard funds (no operating-company votes); 2024 and 2026 cover-only. Likewise the 17 Voya Solution / Index Solution series in Voya Partners (2025 only) and Voya Retirement Conservative Portfolio (Investors Trust, 2025): issuers only Vanguard funds (0 non-fund rows tested). No rows to key, so no rule.
- No N-PX after 2022: Voya International High Dividend Equity Income Fund 1395627 (last 2021), Voya Natural Resources Equity Income Fund 1372117 (last 2022), Voya Series Fund 877233 (last 2019).
- Institutional-manager filers: Voya Investment Management LLC 1068837 (separate accounts, 3.6-4.3 MB vote table each year 2024-2026; governed by Voya IM's OWN policy, a different document); Voya Investments LLC 1077479, Voya Investment Management Co 33670, Voya Financial Advisors 1424367 (cover only). Not ingested, same convention as Lazard / Global X.
- Voya Mutual Funds is the EDGAR name of the trust (CIK 895430, found through EDGAR company search, not the cgi-bin name list).

## 2. Earliest 2021-2023 SAI per registrant, and the exact quotes

All are 485BPOS (the main iXBRL document holds the SAI(s) plus Part C). EDGAR full-text path: `https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/<document>`.

| CIK | Earliest SAI read (485BPOS) | Accession | Document | Edition of Appendix B printed | Later editions read |
|---|---|---|---|---|---|
| 895430 Mutual Funds | 2021-02-25 | 0001683863-21-001018 | vmf-20210224.htm | Sept 11, 2020 | 2023-02-24 (May 25, 2022), 2025-07-23 (Feb 5, 2025) |
| 837276 Investors Trust | 2021-04-26 | 0001683863-21-002494 | vit-20210426.htm | Sept 11, 2020 | 2022-04-21 (Jan 27, 2022), 2023-04-24 (Mar 16, 2023), 2024-04-24 (Mar 6, 2024), 2025-04-28 (Feb 5, 2025), 2026-07-14 (May 2026) |
| 1039001 Partners | 2021-04-26 | 0001683863-21-002493 | vpi-20210426.htm | Sept 11, 2020 | 2023-04-26 (Mar 16, 2023) |
| 2664 Variable Funds | 2021-04-27 | 0001683863-21-002637 | voya-20210427.htm | Sept 11, 2020 | 2025-04-28 |
| 916403 Variable Products | 2021-04-27 | 0001683863-21-002630 | voya-20210427.htm | Sept 11, 2020 | 2025-04-28 |
| 846799 Balanced Portfolio | 2021-04-27 | 0001683863-21-002640 | vbpi-20210427.htm | Sept 11, 2020 | 2024-04-25 (Mar 6, 2024) |
| 1066602 Funds Trust | 2021-07-29 | 0001683863-21-004353 | vft-20210729.htm | Sept 11, 2020 | 2023-07-27, 2026-07-29 (May 2026) |
| 1063946 Equity Trust | 2021-09-24 | 0001683863-21-005313 | vet-20210924.htm | Sept 11, 2020 | 2023-09-28, 2025-12-10, 2026-09-25 (May 2026) |

Closed-end funds have no SAI or N-2 in 2021-2023 (the equity funds were launched 2004-2011; the interval fund files 497/486). Their policy statement is the N-CSR Item 7, which reprints the full Voya Funds policy ("PROXY VOTING PROCEDURES and GUIDELINES VOYA FUNDS VOYA INVESTMENTS, LLC Date Last Revised: September 11, 2020"). Earliest 2021 read, all filed 2021-05-06: Asia Pacific HDEI 0001104659-21-062312, Global Advantage 0001104659-21-062320, Global Equity D&P 0001104659-21-062322, Infrastructure 0001104659-21-062314, Emerging Markets HDEI 0001104659-21-062316, Credit Income 0001104659-21-062318 (Asia Pacific, Global Advantage, Credit Income read in full; Global Equity D&P, Infrastructure and Emerging Markets checked for the same heading, date and Sub-Advisor-Voted clause).

Quote 1 (SAI, "Other Services - Proxy Voting"; "Fund" in Mutual Funds / Funds Trust / Equity Trust, "Portfolio" in Investors Trust / Partners / Variable Funds / Variable Products / Balanced Portfolio; identical in all eight 2021 SAIs):

> "The Board has adopted proxy voting procedures and guidelines to govern the voting of proxies relating to each Fund's portfolio securities. The proxy voting procedures and guidelines delegate to the Adviser the authority to vote proxies relating to portfolio securities, and provide a method for responding to potential conflicts of interest. In delegating voting authority to the Adviser, the Board has also approved the Adviser's proxy voting procedures, which require the Adviser to vote proxies in accordance with each Fund's proxy voting procedures and guidelines. An independent proxy voting service has been retained to assist in the voting of Fund proxies through the provision of vote analysis, implementation and recordkeeping and disclosure services."

Adviser = Voya Investments, LLC ("The investment adviser for each Fund is Voya Investments, LLC", Equity Trust SAI 2021-09-24). Sub-advisers: "The Adviser has delegated certain management responsibilities to one or more Sub-Advisers", with no voting delegation.

Quote 2 (Appendix B, Sept 11, 2020 edition, in every 2021-2022 SAI and in the closed-end N-CSRs):

> "The purpose of these Proxy Voting Procedures and Guidelines (the "Procedures", the "Guidelines") is to set forth the Board of Directors/Trustees of the Voya funds' (the "Board") instructions to Voya Investments, LLC (referred to as the "Advisor") for the voting of proxies for each fund the Board serves as Director/Trustee (the "Funds")."

> "The Board, through these instructions, delegates to the Advisor's Proxy Coordinator the responsibility to vote the Funds' proxies in accordance with these Procedures and Guidelines on behalf of the Board."

> "The Funds' sub-advisors and/or portfolio managers are each referred to herein as an "Investment Professional" ... The Board encourages the Funds' Investment Professionals to submit a recommendation to the Proxy Group regarding any proxy-voting-related proposal"

The escape clause, Sept 2020 edition (Mutual Funds, Investors Trust, Partners, Equity Trust, Funds Trust, Variable Funds, N-CSRs):

> "The Board may elect to delegate proxy voting to a sub-advisor of the Funds and also approve the sub-advisor's proxy policies and procedures for implementation on behalf of such Voya fund (a "Sub-Advisor-Voted Fund"). A Sub-Advisor-Voted Fund is not covered under these Procedures and Guidelines, ... However, they are covered by those sub-advisor's proxy policies, provided that the Board has approved them."

March 16, 2023 edition (SAI 2023-2024, "PROXY VOTING POLICY" heading), SAI paragraph: "The Board has approved the Investment Adviser's Proxy Voting Policy ... The Proxy Voting Policy requires the Investment Adviser to vote each Fund's portfolio securities that have voting rights in accordance with the Proxy Voting Policy" and Appendix B: "Pursuant to the Policy, the Adviser's Active Ownership team ("AO Team") is delegated the responsibility to vote the Funds' proxies in accordance with the Proxy Voting Policy on the Funds' behalf." Same escape clause ("Sub-Adviser-Voted Fund", Board "may determine to delegate proxy voting to a sub-adviser of one or more Funds (rather than to the Adviser)"). The 2023 text ("Voya Investment Management" Proxy Group replaced by the AO Team) is the same Voya Investments Board policy.

May 2026 edition (Investors Trust 2026-07-14, Equity Trust 2026-09-25, Funds Trust 2026-07-29): "The Board may determine to delegate full proxy voting authority to a sub-adviser ... A list of Sub-Adviser-Voted Funds is included in Appendix A to this Policy." Appendix A: "Sub-Adviser-Voted Funds None".

Result: sub-advised Voya funds are NOT delegated; Voya Investments votes (via its Proxy Coordinator / AO Team and an independent proxy-advisory firm) under the Board's own Voya Funds guidelines. The Board's delegation to the Adviser is the mechanism; no per-series sub-adviser exception was found in any filing read.

Not read: N-CEN sub-adviser tables (they cannot change the result: the key does not depend on who the sub-adviser is). The 2026 SAI filings 0001193125-26-181732 (2664), -177141 (916403), -402921 (1392116), -070582 (895430) and -181784 (1039001) answer 404 on sec.gov (primary document path from the submissions index) and could not be read; their editions are inferred from sibling trusts (same May 2026 / Feb 2025 text printed by 837276, 1063946, 1066602).

## 3. Proposed YAML (paste under `institutions:`; new entry after `lazard`)

`from` is the EDGAR filing date of the earliest SAI (or N-CSR) read, same convention as Lazard. `<date>` = commit date. No `series_adviser` rules: the registrant default `VOYA` covers every series (fund-of-funds series with only Vanguard-fund issuers carry VOYA too, but they have no operating-company rows).

```yaml
  voya:
    display_name: "Voya (Voya Investments, LLC / Voya Investment Management)"
    short_name: "Voya"
    cik: "0001077479"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Voya Investments, LLC, Scottsdale AZ (CIK 1077479, formerly ING Investments LLC), a subsidiary of Voya Financial, Inc., is the investment adviser of the Voya mutual-fund, variable-insurance and closed-end fund registrants; Voya Investment Management Co. LLC (CIK 33670) and Voya Investment Management LLC (CIK 1068837, which files its own institutional-manager N-PX for separate accounts, not ingested) are affiliated sub-advisers. Fourteen fund registrants that file N-PX vote tables with operating-company votes are ingested: Voya Investors Trust (837276), Voya Partners Inc (1039001), Voya Equity Trust (1063946), Voya Mutual Funds (895430), Voya Variable Products Trust (916403), Voya Variable Funds (2664), Voya Balanced Portfolio Inc (846799), Voya Funds Trust (1066602, one fund, nine rows), and the closed-end Voya Asia Pacific High Dividend Equity Income Fund (1385632), Voya Global Advantage & Premium Opportunity Fund (1332943), Voya Global Equity Dividend & Premium Opportunity Fund (1285890), Voya Infrastructure, Industrials & Materials Fund (1417802), Voya Emerging Markets High Dividend Equity Fund (1496292) and Voya Credit Income Fund (1124959, nine rows). Every SAI read (2021-2026) says the Board's proxy voting procedures 'delegate to the Adviser the authority to vote proxies relating to portfolio securities' and Appendix B is the Board-approved Voya Funds policy ('Voya Funds / Voya Investments, LLC'), executed by the Adviser's Proxy Coordinator (from 2023 the Active Ownership team) through a proxy advisory firm; sub-advisers only recommend. The policy allows the Board to delegate a fund to its sub-adviser ('Sub-Advisor-Voted Fund'), but no SAI names one and the May 2026 edition says 'Appendix A: Sub-Adviser-Voted Funds - None'; so every registrant is keyed VOYA and no series is EXTERNAL. The closed-end funds' N-CSR Item 7 reprints the same policy. aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. Fourteen Voya registrants file N-PX vote tables with operating-company votes (2024-2026). Not ingested: cover-only filers (Voya Variable Insurance Trust 1090682, Strategic Allocation Portfolios 935070, Government Money Market 2663, Intermediate Bond 2646, Enhanced Securitized Income 1995568), Voya Separate Portfolios Trust (1392116; 2025 votes only on Vanguard funds), the retired International HDEI (1395627, last N-PX 2021), Natural Resources Equity Income (1372117, last 2022) and Series Fund (877233, last 2019), and the institutional-manager N-PX of Voya Investment Management LLC (1068837, a different policy).
      # Every SAI read prints 'The proxy voting procedures and guidelines delegate to the Adviser the authority to vote proxies relating to portfolio securities'; Appendix B is Voya Investments, LLC's Board-approved 'VOYA FUNDS' policy (editions Sept 11 2020, Jan 27 2022, May 25 2022, Mar 16 2023, Mar 6 2024, Feb 5 2025, May 2026). Each registrant is dated from the EDGAR filing date of the earliest SAI (or, for the closed-end funds, N-CSR) read.
      - cik: "837276"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/837276/000168386321002494/vit-20210426.htm"  # 485BPOS (SAI) filed 2021-04-26 (0001683863-21-002494), 'Proxy Voting Procedures and Guidelines' + Appendix B
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting Procedures and Guidelines': 'The Board has adopted proxy voting procedures and guidelines to govern the voting of proxies relating to each Portfolio's portfolio securities. The proxy voting procedures and guidelines delegate to the Adviser the authority to vote proxies relating to portfolio securities ... In delegating voting authority to the Adviser, the Board has also approved the Adviser's proxy voting procedures, which require the Adviser to vote proxies in accordance with each Portfolio's proxy voting procedures and guidelines.' Appendix B (VOYA FUNDS, Voya Investments, LLC, Date Last Revised September 11, 2020) delegates 'to the Advisor's Proxy Coordinator the responsibility to vote the Funds' proxies'; sub-advisors are 'Investment Professionals' who may submit a recommendation. Escape clause 'Sub-Advisor-Voted Fund' (Board may delegate to a sub-advisor): no fund named in any SAI 2021-2025; May 2026 edition: 'Appendix A: Sub-Adviser-Voted Funds None'. Earliest SAI read 2021-04-26; same delegation in 2022-04-21, 2023-04-24, 2024-04-24, 2025-04-28 and 2026-07-14."
        adviser_key_history: [{key: VOYA, from: "2021-04-26"}]
        name: "Voya INVESTORS TRUST"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1039001"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1039001/000168386321002493/vpi-20210426.htm"  # 485BPOS (SAI) filed 2021-04-26 (0001683863-21-002493)
        adviser_verified: "<date>"
        voting_note: "Same SAI 'Proxy Voting Procedures and Guidelines' paragraph and Appendix B as Voya Investors Trust (earliest SAI read 2021-04-26, 0001683863-21-002493; same in 2023-04-26): 'delegate to the Adviser the authority to vote proxies relating to portfolio securities'. Includes sub-adviser series (VY American Century, Baron, Columbia, Invesco, JPMorgan, T. Rowe Price) and fund-of-funds Solution / Index Solution series (2025 votes only on Vanguard funds)."
        adviser_key_history: [{key: VOYA, from: "2021-04-26"}]
        name: "Voya PARTNERS INC"
        validated: "<date>"
      - cik: "1063946"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1063946/000168386321005313/vet-20210924.htm"  # 485BPOS (SAI) filed 2021-09-24 (0001683863-21-005313)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph ('each Fund's portfolio securities ... delegate to the Adviser the authority to vote proxies') and Appendix B (September 11, 2020; Mar 16 2023 in 2023-09-28; Feb 5 2025 in 2025-12-10; May 2026 in 2026-09-25). Earliest SAI read 2021-09-24 (0001683863-21-005313). Equity Trust SAI: 'The investment adviser for each Fund is Voya Investments, LLC.'"
        adviser_key_history: [{key: VOYA, from: "2021-09-24"}]
        name: "Voya EQUITY TRUST"
        validated: "<date>"
      - cik: "895430"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/895430/000168386321001018/vmf-20210224.htm"  # 485BPOS (SAI) filed 2021-02-25 (0001683863-21-001018)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph and Appendix B (Sept 11, 2020; May 25, 2022 in 2023-02-24; Feb 5, 2025 in 2025-07-23). Earliest SAI read 2021-02-25 (0001683863-21-001018). Multi-Manager funds (Emerging Markets, International Equity, International Small Cap) are still voted by the Adviser: the SAI delegates 'to the Adviser the authority to vote proxies' and names no Sub-Advisor-Voted Fund."
        adviser_key_history: [{key: VOYA, from: "2021-02-25"}]
        name: "Voya MUTUAL FUNDS"
        validated: "<date>"
      - cik: "916403"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/916403/000168386321002630/voya-20210427.htm"  # 485BPOS (SAI) filed 2021-04-27 (0001683863-21-002630)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph and Appendix B (Sept 11, 2020; Feb 5, 2025 in 2025-04-28). Earliest SAI read 2021-04-27 (0001683863-21-002630)."
        adviser_key_history: [{key: VOYA, from: "2021-04-27"}]
        name: "Voya VARIABLE PRODUCTS TRUST"
        validated: "<date>"
      - cik: "2664"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/2664/000168386321002637/voya-20210427.htm"  # 485BPOS (SAI) filed 2021-04-27 (0001683863-21-002637)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph and Appendix B (Sept 11, 2020; Feb 5, 2025 in 2025-04-28). Earliest SAI read 2021-04-27 (0001683863-21-002637)."
        adviser_key_history: [{key: VOYA, from: "2021-04-27"}]
        name: "Voya VARIABLE FUNDS"
        validated: "<date>"
      - cik: "846799"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/846799/000168386321002640/vbpi-20210427.htm"  # 485BPOS (SAI) filed 2021-04-27 (0001683863-21-002640)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph and Appendix B (Sept 11, 2020; Mar 6, 2024 in 2024-04-25). Earliest SAI read 2021-04-27 (0001683863-21-002640). Last N-PX with votes is 2025-08-25 (279 rows); none in 2026."
        adviser_key_history: [{key: VOYA, from: "2021-04-27"}]
        name: "Voya BALANCED PORTFOLIO INC"
        validated: "<date>"
      - cik: "1066602"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-advisers recommend only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1066602/000168386321004353/vft-20210729.htm"  # 485BPOS (SAI) filed 2021-07-29 (0001683863-21-004353)
        adviser_verified: "<date>"
        voting_note: "Same SAI paragraph and Appendix B (Sept 11, 2020; Mar 16 2023 in 2023-07-27; May 2026 in 2026-07-29). Earliest SAI read 2021-07-29 (0001683863-21-004353). Only Voya Floating Rate Fund (S000029692) has operating-company votes: nine Cumulus Media rows in 2024 and 2025."
        adviser_key_history: [{key: VOYA, from: "2021-07-29"}]
        name: "Voya FUNDS TRUST"
        validated: "<date>"
      - cik: "1385632"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; Voya Investment Management Co. LLC is sub-adviser (recommends only)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1385632/000110465921062312/tm219046d7_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062312), Item 7 reprints the Voya Funds policy
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; no SAI or N-2 in 2021-2023. N-CSR Item 7 (earliest 2021 read, 2021-05-06) reprints 'PROXY VOTING PROCEDURES and GUIDELINES VOYA FUNDS VOYA INVESTMENTS, LLC Date Last Revised: September 11, 2020', in which the Board instructs Voya Investments, LLC (the Advisor) on the voting of proxies for each fund and delegates 'to the Advisor's Proxy Coordinator the responsibility to vote the Funds' proxies'."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "Voya Asia Pacific High Dividend Equity Income Fund"
        validated: "<date>"
      - cik: "1332943"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; Voya Investment Management Co. LLC is sub-adviser (recommends only)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1332943/000110465921062320/tm219046d13_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062320)
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; N-CSR Item 7 of 2021-05-06 reprints the Voya Funds policy (Sept 11, 2020); same wording as 1385632."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "Voya Global Advantage & Premium Opportunity Fund"
        validated: "<date>"
      - cik: "1285890"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; Voya Investment Management Co. LLC is sub-adviser (recommends only)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1285890/000110465921062322/tm219046d14_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062322)
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; N-CSR Item 7 of 2021-05-06 reprints the Voya Funds policy (Sept 11, 2020); same wording as 1385632."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "Voya GLOBAL EQUITY DIVIDEND & PREMIUM OPPORTUNITY FUND"
        validated: "<date>"
      - cik: "1417802"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; Voya Investment Management Co. LLC is sub-adviser (recommends only)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1417802/000110465921062314/tm219046d8_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062314)
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; N-CSR Item 7 of 2021-05-06 reprints the Voya Funds policy (Sept 11, 2020); same wording as 1385632."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "Voya Infrastructure, Industrials & Materials Fund"
        validated: "<date>"
      - cik: "1496292"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; Voya Investment Management Co. LLC is sub-adviser (recommends only)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1496292/000110465921062316/tm219046d10_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062316)
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; N-CSR Item 7 of 2021-05-06 reprints the Voya Funds policy (Sept 11, 2020); same wording as 1385632."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "Voya Emerging Markets High Dividend Equity Fund"
        validated: "<date>"
      - cik: "1124959"
        adviser: "Voya Investments, LLC (the Adviser) votes under the Board's Voya Funds policy; sub-adviser recommends only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1124959/000110465921062318/tm219046d12_ncsr.htm"  # N-CSR filed 2021-05-06 (0001104659-21-062318)
        adviser_verified: "<date>"
        voting_note: "Closed-end interval fund (formerly Voya Senior Income Fund); N-CSR Item 7 of 2021-05-06 reprints the Voya Funds policy (Sept 11, 2020). Only nine operating-company rows (Cumulus Media) in the 2024 and 2025 N-PX."
        adviser_key_history: [{key: VOYA, from: "2021-05-06"}]
        name: "VOYA CREDIT INCOME FUND"
        validated: "<date>"
    voting_scope_notes:
      - "Keyed VOYA per registrant from the EDGAR filing date of the earliest SAI (closed-end funds: N-CSR) read: Voya Mutual Funds 2021-02-25, Investors Trust and Partners 2021-04-26, Variable Products, Variable Funds and Balanced Portfolio 2021-04-27, Funds Trust 2021-07-29, Equity Trust 2021-09-24, the six closed-end funds 2021-05-06; earlier meetings stay unlabelled. The Board's Voya Funds policy is Voya Investments, LLC's to execute whichever sub-adviser manages a series (Voya IM, JPMorgan, T. Rowe Price, Invesco, CBRE, Morgan Stanley, Baron, Columbia, American Century); sub-advisers only recommend. The Board may delegate a fund to its sub-adviser ('Sub-Adviser-Voted Fund') but no SAI names one (May 2026: 'None'), so there is no EXTERNAL series."
      - "Paired series hold the same portfolio and report the same rows (Voya Large Cap Value Fund / Portfolio, Large-Cap Growth Fund / Portfolio, MidCap and SmallCap Opportunities Fund / Portfolio, Multi-Manager Mid Cap Value / VACS Series MCV, U.S. Stock Index Portfolio / VACS Index Series S, Invesco Growth and Income / Equity and Income, Global High Dividend Low Volatility Fund and the Global Advantage and Global Equity D&P closed-end funds); the dedupe pass after ingest must run."
      - "Not ingested (left out): cover-only registrants (1090682, 935070, 2663, 2646, 1995568), Voya Separate Portfolios Trust (1392116, 2025 votes only on Vanguard funds), retired registrants (1395627, 1372117, 877233), Voya Investment Management LLC's institutional-manager N-PX (1068837, Voya IM's own policy for separate accounts), and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
      - "Policy text: the SAI appendix label below is the only archived policy of the Voya Funds. The 'Proxy Voting Policy' PDF on voya.com (Voya Investment Management Co. LLC / Investment Trust Co. / Alternative Asset Management LLC / Voya Investment Management LLC, effective April 10, 2026) covers separate-account clients of the Voya advisers, is NOT the Funds' policy, and is deliberately not attached to any VOYA label."
    commitments:
      # Appendix B as printed in the SAI, dated by EDGAR filing date. Identical text in every trust for the same edition (hash-checked on 9 trusts), so ONE label on the trust with the longest 485BPOS history. Seven editions: Sept 11 2020, Jan 27 2022, May 25 2022, Mar 16 2023, Mar 6 2024, Feb 5 2025, May 2026 (see open doubt 1).
      - label: voya-funds-proxy-voting-policy-as-printed-in-sai
        adviser: "Voya Investments, LLC"
        adviser_key: "VOYA"
        sai_appendix:
          cik: "0000837276"
          forms: ["485BPOS"]
          since: "2021-01-01"
          start:
            - "VOYA FUNDS VOYA INVESTMENTS, LLC Date Last Revised:"
          end:
            - "PART C. OTHER INFORMATION"
            - "STATEMENT OF ADDITIONAL INFORMATION"
          allow_identical_copies: true
```

Optional second label, same shape, `cik: "0000895430"`, `since: "2021-01-01"`: dates the Sept 2020 edition two months earlier (2021-02-25 versus 2021-04-26) and cross-checks the Investors Trust label. Not added by default: it would store the same text twice under a second label.

## 4. Policy label proposal and verification

Website: none for the Funds. Probed 2026-11-21 with the honest UA: `https://individuals.voya.com/document/marketing/voya-im-proxy-voting-policy.pdf` and `https://investments.voya.com/document/marketing/voya-im-proxy-voting-policy.pdf` answer 200 application/pdf (388,857 bytes, same file; Wayback CDX holds one capture, 2026-05-16). Its text is "Proxy Voting Policy, Voya Investment Management Co. LLC, Voya Investment Trust Co., Voya Alternative Asset Management LLC, Voya Investment Management LLC, Effective Date: April 10, 2026", "Covers accounts managed by Voya advisers for which the client has delegated voting authority": the policy for separate accounts, not the Voya Funds. The Funds' SAIs point to `individuals.voya.com/product/mutual-fund/prospectuses-reports` (200 HTML) only for the vote record, not the policy. Hence no website label; the Funds' policy exists only as the SAI appendix and the closed-end N-CSR Item 7.

SAI appendix markers (run through `extract_section(cm.html_to_text(raw), start, end, allow_identical_copies=True)` in a scratch script, not the ingester):
- start: `VOYA FUNDS VOYA INVESTMENTS, LLC Date Last Revised:` (the page heading under "APPENDIX B", unlike the table-of-contents entry; keeps the edition date in the text so each edition hashes as its own version). One copy per SAI in the filing, hence `allow_identical_copies`.
- end: `PART C. OTHER INFORMATION` (last SAI in the filing) or `STATEMENT OF ADDITIONAL INFORMATION` (next SAI's cover); the earliest after the start wins.
- Clean extraction on 23 filings in 9 trusts (a start occurs 1 to 4 times per filing; every copy identical): Mutual Funds 2021-02-25 / 2023-02-24 / 2025-07-23; Investors Trust 2021-04-26, 2022-04-21, 2022-04-25, 2023-04-24, 2024-04-24, 2025-04-28, 2026-04-24, 2026-07-14; Partners 2021-04-26 / 2023-04-26; Variable Funds 2021-04-27 / 2025-04-28; Variable Products 2021-04-27 / 2025-04-28; Balanced 2021-04-27 / 2024-04-25; Funds Trust 2021-07-29 / 2023-07-27 / 2026-07-29; Equity Trust 2021-09-24 / 2023-09-28 / 2025-12-10; Separate Portfolios 2021-07-29 / 2025-09-22.
- Section length and hash per edition (whitespace-free sha256, first 8 hex): Sept 11 2020: 93,625 chars, 83a54ad3 (identical in all 9 trusts); Jan 27 2022: 92,948, 32e8be10; Mar 16 2023: 86,205, 955ab514; Mar 6 2024: 86,319, 93c35491; May 25 2022 (Mutual Funds 2023): 81,330; Feb 5 2025: 83,890, d68c87a8; May 2026: 22,975, f8d00257.
- Filings that yield nothing (no start marker, so recorded nothing): Investors Trust 2024-06-05, 2025-08-15, 2026-04-22 (supplement-type 485BPOS). `strip_page_numbers` is not needed: the 2020 edition ends with a bare page number "24" that stays in the section, harmless and stable.

## 5. Open doubts

1. The May 2026 edition is a rewrite (22,975 chars against about 84,000 before). `OUTLIER_FACTOR = 3` makes `ingest_filings` skip it with `needs_review` (a genuine rewrite would be skipped), and `glasshouse doctor` will report it. A human must decide to record it (it is the policy in force); until then the newest archived edition is Feb 5 2025.
2. Escape clause: the Board "may" delegate to a sub-adviser. Before May 2026 no list existed; I found no SAI naming a Sub-Advisor-Voted Fund and no vote-table sign of one, but absence of a list is not proof for 2021-2025. If the maintainer wants a stricter reading, mark nothing; only Voya Investments' Board minutes could settle it. The N-CEN sub-adviser tables were not read (they do not decide the key).
3. Fund-of-funds series (Solution / Index Solution / Target Retirement / Retirement Conservative, 2025 only, Vanguard issuers): keyed VOYA by the registrant default. Voya's policy has a fund-of-funds section ("the Board will determine the most appropriate method" for underlying-fund votes), so VOYA is the right label, but they carry no operating-company rows. Voya Separate Portfolios Trust is not added at all.
4. Two registrants have only nine rows a year (Voya Funds Trust's Floating Rate Fund and Voya Credit Income Fund, both Cumulus Media 2024-2025). Include or skip at the maintainer's choice; precision is unaffected.
5. Four 2026 SAI accessions (2664, 916403, 1392116, 895430; also 1039001 2026-04-27) return 404 on sec.gov at the path the submissions API gives, so the 2026 editions for those trusts were not read directly; the Investors, Equity and Funds Trust filings carry the same May 2026 text. The ingester logs a fetch warning and continues.
6. Voya Mutual Funds' trust name check: EDGAR carries it as "Voya MUTUAL FUNDS" (CIK 895430). Name strings in the YAML use the `data.sec.gov` capitalisation; `validated` must be set by running the normal validator.
7. The sai_appendix strings were not run through the ingester (a release build may be running); dry-run with the real archive before merge. Re-ingest recommendation after merge (not run): `glasshouse ingest npx --cik <each of the 14 CIKs>` then the usual dedupe, `glasshouse ingest commitments`, `glasshouse engine build`.
8. `from` for Equity Trust (2021-09-24) and Funds Trust (2021-07-29) are the first 485BPOS in 2021-2023; 497 filings in April-June 2021 carry the same SAI and would date them earlier. Judgement call kept to 485BPOS only, as in Lazard and John Hancock.
