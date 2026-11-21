# Parnassus Investments (Parnassus Funds, Parnassus Funds II) - research for institutions.yaml

Research only, read 2026-11-21 via glasshouse.http (EDGAR; data.sec.gov submissions, filing indexes, SAI/N-CEN/N-PX documents) and curl with the honest UA (parnassus.com, archive.org). Nothing in data/, config/ or the ledger was touched. Scratch copies of the SAIs live outside the repo.

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

| CIK | Name (data.sec.gov) | Type | N-PX seasons with XML vote tables (ProxyVotingTable.xml) | Notes |
|---|---|---|---|---|
| 747546 | PARNASSUS FUNDS | open-end, series S000000852 Parnassus Fund (now Growth Equity), S000000853 Mid Cap, S000000855 Value Equity, S000079321, S000091873 | 2024-08-21 (0001021408-24-002675, 2,262 rows, 124 issuers), 2025-08-21 (0001021408-25-002660, 2,203 rows), 2026-08-20 (0001193125-26-358191, 2,982 rows) | 2021-2023 N-PX (0001104659-21-096328, -22-082479, -23-084758) are legacy text/HTML |
| 866256 | PARNASSUS FUNDS II (named PARNASSUS INCOME FUNDS until 2025-04-28) | open-end, series S000000856 Core Equity, S000000857 Fixed Income, S000089216 / S000089217 (2025 additions) | 2024-08-21 (0001021408-24-002683, 619 rows), 2025-08-21 (0001021408-25-002658, 1,210 rows), 2026-08-20 (0001193125-26-358189, 1,322 rows) | the task's "Parnassus Income Funds" is this CIK under its old name; it is the same registrant, use one entry |

Not ingested (same convention as dodge_cox / lazard):
- Parnassus Investments, LLC, CIK 948669 (the adviser, 13-F filer): own institutional-manager N-PX (146 rows in 2024-08-21 0001021408-24-002673; also 2025-08-21 0001021408-25-002659, 2026-08-20 0001193125-26-358190). Not a fund registrant.
- CIK 756103 (Parnassus Funds Distributor) and 812235 (Parnassus Investments /TA): no N-PX.
- No N-CEN (747546: 2021-03-08, 2022-03-10, 2023-03-09, 2024-03-06, 2025-02-28, 2026-03-06; 866256: 2021, 2025, 2026 read) lists a sub-adviser (zero subAdviser blocks); the only adviser is Parnassus Investments (LLC).

## 2. Earliest SAI read and the exact quotes

Earliest 2021-2023 SAI (485BPOS, EDGAR filing date from submissions API):
- PARNASSUS FUNDS: 0001193125-21-144778 filed 2021-04-30 (d366417d485bpos.htm). Re-read 2022-04-29 (0001193125-22-133876), 2023-04-28 (0001193125-23-127406), 2024-04-29, 2026-04-30 (0001193125-26-195343).
- PARNASSUS FUNDS II: 0001193125-21-144848 filed 2021-04-30 (d370153d485bpos.htm). Re-read 2022-04-29 (0001193125-22-133934), 2023-04-28 (0001193125-23-127436), 2026-04-30 (0001193125-26-195360).

Quotes, SAI "Proxy Voting" (identical wording in 2021, 2023, 2026; "Annex B" in 2021-2025, "Annex A" in 2026):
> "Proxy voting policies and procedures for the portfolios of the Parnassus Funds are included as Annex B attached to this statement of additional information. Proxy voting expenses incurred by the Adviser on behalf of the Funds and other accounts will be fairly and equitably allocated among the Funds and the other accounts holding the applicable securities."

Prospectus part of the same 485BPOS (2021):
> "The Adviser also votes proxies consistent with its proxy voting policies and procedures, which are stated in the SAI."

Annex B (2021): "ANNEX B PARNASSUS INVESTMENTS PROXY VOTING POLICIES AND PROCEDURES I. Overview Parnassus Investments manages the portfolios of the Parnassus Funds trust and the Parnassus Income Funds trust (collectively, the "Funds") ..." and, section III Policies (2021, 2022, 2023, 2026 unchanged):
> "We do not delegate our proxy voting authority or rely solely on third-party recommendations to vote our shares."
> "Our duty is to vote proxies in the best interests of our clients and Fund shareholders."

ISS is a voting agent / research provider ("we may review information and recommendations from ... our service provider Institutional Shareholder Services"; 2023: "ISS acts as our voting agent ... interprets and applies our Policies to individual proxy items, subject to our review and oversight. We may also utilize Glass Lewis research"). The votes follow Parnassus's own policy: key PARNASSUS for both registrants.

AMG change (2022): Affiliated Managers Group acquired a majority interest in Parnassus Investments, LLC (2022-04-29 SAI still says an auditor was chosen "subject to consummation of the Transaction with AMG"). From the 2022 SAI on, every SAI (2022, 2023, 2026) says:
> "Affiliated Managers Group, Inc., an investment holding company with stakes in a diverse group of boutique investment firms, holds a majority interest in Parnassus Investments, LLC."

Did the voting policy change? The text was rewritten between the 2021-04-30 and 2022-04-29 SAIs (annex retitled "PARNASSUS INVESTMENTS, LLC", entity defined as "Parnassus"; the 2021 "Education and Decisions" procedure is replaced in 2022 by a Proxy Voting Committee; 2023 adds Glass Lewis research, a non-U.S. securities section and "We generally will not disclose our voting intentions"; the 2026 annex no longer mentions the Committee); 2026 renames the second trust "Parnassus Funds II"). Annex similarity 2021 vs 2022 is low (rewrite), 2022 vs 2023 0.89, 2023 vs 2024 0.94, 2024 vs 2026 0.76 (difflib on the first 20k chars). The authority did NOT change: Parnassus still "do[es] not delegate our proxy voting authority" and no AMG entity votes; no sub-adviser in any N-CEN. So the key is PARNASSUS throughout; the policy TEXT changed, which is exactly what the sai_appendix archive records (each edition is a genuine rewrite).

## 3. Proposed YAML (paste under `institutions:`)

```yaml
  parnassus:
    display_name: "Parnassus Investments"
    short_name: "Parnassus"
    cik: "0000948669"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Parnassus Investments, LLC, San Francisco CA (CIK 948669, the 13-F filer and the investment adviser of the Parnassus Funds; Affiliated Managers Group, Inc. holds a majority interest since the 2022 transaction). Two open-end fund registrants that file N-PX vote tables with operating-company votes are ingested: Parnassus Funds (CIK 747546) and Parnassus Funds II (CIK 866256, named Parnassus Income Funds until 2025-04-28). Every SAI says the proxy voting policies are those of Parnassus Investments (Annex B / Annex A) and the policy states 'We do not delegate our proxy voting authority or rely solely on third-party recommendations to vote our shares'; ISS is the voting agent and research provider only. No N-CEN (FY2020 to FY2025) names a sub-adviser. Parnassus Investments, LLC's own institutional-manager N-PX (CIK 948669) is not ingested. aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. Two Parnassus fund registrants file N-PX vote tables with operating-company votes in 2024-2026 (Parnassus Investments, LLC's institutional-manager N-PX, CIK 948669, is not ingested).
      # Every SAI read prints 'Proxy voting policies and procedures for the portfolios of the Parnassus Funds are included as Annex B' and the annex says 'We do not delegate our proxy voting authority'.
      # No N-CEN lists a sub-adviser, so there is no series exception. AMG's majority stake (2022) did not change who votes; the annex was rewritten between the 2021 and 2022 SAIs and keyed PARNASSUS throughout.
      - cik: "747546"
        adviser: "Parnassus Investments, LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/747546/000119312521144778/d366417d485bpos.htm"  # 485BPOS (SAI) filed 2021-04-30 (0001193125-21-144778), 'Proxy Voting': policies in Annex B
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting': 'Proxy voting policies and procedures for the portfolios of the Parnassus Funds are included as Annex B attached to this statement of additional information.' Annex B 'PARNASSUS INVESTMENTS PROXY VOTING POLICIES AND PROCEDURES': 'We do not delegate our proxy voting authority or rely solely on third-party recommendations to vote our shares.' Earliest SAI read 2021-04-30 (0001193125-21-144778); same authority wording in 2022-04-29, 2023-04-28 and 2026-04-30. Affiliated Managers Group holds a majority interest in Parnassus Investments, LLC from 2022; the annex was rewritten (2021 vs 2022 edition) but voting stays with Parnassus. Every Form N-CEN 2021-03 to 2026-03 names Parnassus Investments as the only adviser and no sub-adviser."
        adviser_key_history: [{key: PARNASSUS, from: "2021-04-30"}]
        name: "PARNASSUS FUNDS"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
      - cik: "866256"
        adviser: "Parnassus Investments, LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/866256/000119312521144848/d370153d485bpos.htm"  # 485BPOS (SAI) filed 2021-04-30 (0001193125-21-144848), 'Proxy Voting': policies in Annex B
        adviser_verified: "<date>"
        voting_note: "Named Parnassus Income Funds until 2025-04-28, then Parnassus Funds II. Same SAI wording as Parnassus Funds: 'Proxy voting policies and procedures for the portfolios of the Parnassus Funds are included as Annex B' and the annex's 'We do not delegate our proxy voting authority or rely solely on third-party recommendations to vote our shares.' Earliest SAI read 2021-04-30 (0001193125-21-144848); re-read 2022-04-29, 2023-04-28, 2026-04-30. No sub-adviser in any Form N-CEN."
        adviser_key_history: [{key: PARNASSUS, from: "2021-04-30"}]
        name: "PARNASSUS FUNDS II"
        validated: "<date>"
    voting_scope_notes:
      - "Keyed PARNASSUS per registrant from the EDGAR filing date of the earliest SAI read (2021-04-30 for both); earlier meetings stay unlabelled. Votes follow Parnassus Investments' own proxy voting policies (ISS is voting agent and research only; no sub-adviser in any N-CEN). Affiliated Managers Group's majority stake (2022) did not change who votes."
      - "Not ingested (left out): Parnassus Investments, LLC's institutional-manager N-PX (CIK 948669) and the legacy-text N-PX of 2021-2023 (not ingested without --legacy)."
      - "Policy text: the website page (a JavaScript-rendered page, no policy document link recoverable without a browser; UNRESOLVED, see section 4) and the policy as printed in the SAI annex, whose edition changes (2021, 2022, 2023, 2024, 2026) are genuine rewrites."
    commitments:
      # Annex as printed in the SAI (485BPOS), dated by EDGAR filing date. One label per trust. Start heading varies: 'ANNEX B PARNASSUS INVESTMENTS PROXY ...' (2021), 'ANNEX B PARNASSUS INVESTMENTS, LLC PROXY ...' (2022 to 2025), 'ANNEX A PARNASSUS INVESTMENTS, LLC PROXY ...' (2022-12 single-fund SAI and 2026).
      # Page furniture 'AB-8' / 'AA-11' printed mid-text.
      - label: parnassus-proxy-voting-policy-as-printed-in-sai-funds
        adviser: "Parnassus Investments, LLC"
        adviser_key: "PARNASSUS"
        sai_appendix:
          cik: "0000747546"
          forms: ["485BPOS"]
          since: "2021-04-01"
          start:
            - "ANNEX B PARNASSUS INVESTMENTS PROXY VOTING POLICIES AND PROCEDURES I. Overview"
            - "ANNEX B PARNASSUS INVESTMENTS, LLC PROXY VOTING POLICIES AND PROCEDURES I. Overview"
            - "ANNEX A PARNASSUS INVESTMENTS, LLC PROXY VOTING POLICIES AND PROCEDURES I. Overview"
          end:
            - "PART C OTHER INFORMATION Item 28. Exhibits"
          strip_page_numbers: true
      - label: parnassus-proxy-voting-policy-as-printed-in-sai-funds-ii
        adviser: "Parnassus Investments, LLC"
        adviser_key: "PARNASSUS"
        sai_appendix:
          cik: "0000866256"
          forms: ["485BPOS"]
          since: "2021-04-01"
          start:
            - "ANNEX B PARNASSUS INVESTMENTS PROXY VOTING POLICIES AND PROCEDURES I. Overview"
            - "ANNEX B PARNASSUS INVESTMENTS, LLC PROXY VOTING POLICIES AND PROCEDURES I. Overview"
            - "ANNEX A PARNASSUS INVESTMENTS, LLC PROXY VOTING POLICIES AND PROCEDURES I. Overview"
          end:
            - "PART C OTHER INFORMATION Item 28. Exhibits"
          strip_page_numbers: true
```

Markers were checked against the text (HTML tags stripped, whitespace collapsed) of the SAIs 747546: 2021-04-30, 2022-04-29, 2022-12-28 (single-fund SAI, Annex A), 2023-04-28, 2024-04-29, 2026-04-30; 866256: 2021-04-30, 2023-04-28, 2026-04-30 (two copies in the multi-SAI 2026 document). Every start string matched exactly once per SAI (twice in the 2026 Funds II document) and every end string follows the annex ("... AB-8 PART C OTHER INFORMATION Item 28. Exhibits").

## 4. Open doubts

- Website label: https://www.parnassus.com/sustainability/stewardship/proxy-voting returns 200 text/html to the honest client but is a JavaScript shell (26 KB, no policy link, no PDF in the cdn.parnassus.com PDF sitemap). robots.txt does not disallow it. Wayback holds captures of that page (2024-09-11, 2025-02-10, 2026-01-18, 2026-04-08; none before). The page URL changed (https://www.parnassus.com/about-us/proxy-voting also returns 200 but is the same shell; /proxy-voting is 404). No policy-document URL was verified, so no website label is proposed; the SAI label is the archive. A copy of an older policy exists on a third-party host (ISS: vds.issgovernance.com/repo/2309/policies/Parnassus%20Proxy%20Voting%20Policies%20and%20Procedures%2007202020.pdf, dated 2020-07-20, 200 application/pdf); it is not the publisher's own site, so it is a lead, not a label.
- The 2022-12-28 485BPOS (0001193125-22-312878) is a single-fund SAI with a different Annex A heading; it is covered by the third start string.
- The sai_appendix strings were checked against fetched text, not run through the ingester (no ingest was allowed). Dry-run with the real archive before merge.
- Annex similarity figures use difflib on the first 20,000 characters and are indicative only.
- `<date>` placeholders: set to the commit date. Series S000079321 and S000091873 names (Parnassus Growth Equity / Parnassus Mid Cap Growth?) were not confirmed; they do not affect the key because no series exception applies.
