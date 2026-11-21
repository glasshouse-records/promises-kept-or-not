# Domini Impact Investments (Domini Investment Trust) - research for institutions.yaml

Research only, read 2026-11-21 via glasshouse.http (EDGAR) and curl with the honest UA (domini.com, archive.org). Nothing in data/, config/ or the ledger was touched.

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

| CIK | Name (data.sec.gov) | Type | N-PX seasons | Notes |
|---|---|---|---|---|
| 851680 | DOMINI INVESTMENT TRUST (formerly Domini Social Investment Trust until 2016-11-29) | open-end, 5 series in N-CEN 2021 (4 from 2025) | vote tables (proxyvote.xml): 2024-09-09 0001021408-24-007381 (12,449 vote rows, series S000003423 3,966 / S000014393 2,884 / S000067792 541 / S000069966 5,058), 2025-08-21 0001021408-25-002684 (16,026 rows by tag count, S000003423 + S000014393 + S000067792), 2026-08-11 0001193125-26-344195 (11,590 rows, same three series) | the 2021-2023 N-PX (0001193125-21-251621, -22-223146, -23-214385) are legacy HTML |

Each year a second N-PX under the same CIK is a FUND NOTICE REPORT for series S000003424 (Domini Impact Bond Fund; 2024-09-09 0001021408-24-007382, 2025-08-21 0001021408-25-002683, 2026-08-11 0001193125-26-344194): no vote table, no operating-company votes (bond fund). Series S000069966 (5,058 rows in 2024, none in 2025/2026) leaves the 2025 vote table; its N-CEN entry also disappears in 2025.

Not ingested:
- Domini Impact Investments LLC, CIK 1399069 (the adviser; formerly Domini Social Investments LLC): own institutional-manager N-PX (2024-08-30 0001021408-24-006520, ~302 rows; 2025-08-21 0001021408-25-002682; 2026-08-11 0001193125-26-344193). Not a fund registrant.
- Domini Social Trust 851681, Domini Institutional Trust 1010297, Domini Advisor Trust 1305698: last N-PX 2009. Not relevant to 2024-2026.

## 2. Earliest SAI read and the exact quotes

Earliest SAI (485BPOS) from 2021 on: 0001193125-21-339751 filed 2021-11-24 (d212702d485bpos.htm). Re-read: 2022-11-22 list (0001193125-22-290801), 2023-11-22 0001193125-23-281955 (d489688d485bpos.htm), 2025-11-21 0001193125-25-291191 (d806602d485bpos.htm). One multi-fund SAI for the trust (the TOC shows "11. Appendix B - Proxy Voting Policies and Procedures").

SAI "PROXY VOTING POLICIES" (identical in 2021, 2023, 2025):
> "The Board of Trustees has delegated the responsibility to vote proxies for the Funds to Domini. More details about the Funds' proxy voting guidelines and Domini's proxy voting policies and procedures, including procedures adopted by Domini to address any potential conflicts of interest, are provided in the complete Proxy Voting Policies and Procedures in Appendix B."

Appendix B, INTRODUCTION (identical in 2021, 2023, 2025):
> "These Proxy Voting Guidelines and Procedures have been adopted by the Domini Investment Trust on behalf of each of its series ... The Board of Trustees ("Board") of the Domini Funds delegates the responsibility to vote proxies for the Funds to Domini Impact Investments LLC, the Funds' investment adviser ("Domini" or the "Adviser"), consistent with the Proxy Voting Guidelines and Procedures set forth herein."
> "The Adviser shall seek to vote shares for every holding in a Domini Fund portfolio."

ISS is a research / record-keeping vendor ("Domini relies upon ISS to maintain the following records on its behalf"; Domini may refer to ISS's International SRI guidelines in foreign markets); the matrix ends "*All Items not addressed in this matrix will be referred to Domini for voting instructions".

Sub-advisers: SSGA Funds Management, Inc. (SEC file 801-60103) and Wellington Management Company LLP (801-15908) appear in every N-CEN read (2021-10-14, 2022-10-13, 2023-10-16, 2024-10-15, 2025-10-09, 2026-10-14). By the SAI "Subadviser" section, SSGA FM subadvises the Domini Impact Equity, International Opportunities (S000069966) and Sustainable Solutions (S000067792) Funds (and N-CEN order puts S000003423 with SSGA); Wellington subadvises the Impact International Equity (S000014393) and Impact Bond (S000003424) Funds. The SAI describes the subadviser only as investing "in securities the Adviser has selected and notified the Subadviser are to be included in the Fund's portfolio"; no sentence gives either subadviser proxy-voting authority. The only Wellington proxy text is a portfolio-holdings-disclosure line: ISS "provides proxy voting services for Wellington Management and receives portfolio holdings information ... where Wellington has been assigned voting discretion" (2025; this concerns Wellington's own accounts). Conclusion: Domini's own guidelines govern every series (key DOMINI), NOT the sub-advisers' policies; no EXTERNAL block is needed. The N-PX itself names Domini Impact Investments LLC as the reporting/other included manager.

## 3. Proposed YAML (paste under `institutions:`)

```yaml
  domini:
    display_name: "Domini Impact Investments"
    short_name: "Domini"
    cik: "0001399069"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Domini Impact Investments LLC, New York NY (CIK 1399069, formerly Domini Social Investments LLC, the investment adviser and sponsor of the Domini Funds). One US fund registrant that files N-PX vote tables with operating-company votes is ingested: Domini Investment Trust (CIK 851680, series S000003423 Impact Equity, S000014393 Impact International Equity, S000067792 Sustainable Solutions, S000069966 International Opportunities until 2024; the Impact Bond Fund S000003424 files only notice reports). Every SAI says 'The Board of Trustees has delegated the responsibility to vote proxies for the Funds to Domini' and Appendix B (Domini's Proxy Voting Guidelines and Procedures) says the Board 'delegates the responsibility to vote proxies for the Funds to Domini Impact Investments LLC'. SSGA Funds Management, Inc. (Equity, International Opportunities, Sustainable Solutions) and Wellington Management Company LLP (International Equity, Bond) are sub-advisers in every N-CEN but the SAI gives them no proxy-voting authority, so Domini's own guidelines govern every series. Domini Impact Investments LLC's own institutional-manager N-PX (CIK 1399069) is not ingested. aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. The only Domini fund registrant that files N-PX vote tables with operating-company votes in 2024-2026 is Domini Investment Trust (CIK 851680). Its Bond Fund series S000003424 files notice reports only; Domini Impact Investments LLC's institutional-manager N-PX (CIK 1399069) is not ingested.
      # Every SAI read says 'The Board of Trustees has delegated the responsibility to vote proxies for the Funds to Domini' and Appendix B delegates to 'Domini Impact Investments LLC, the Funds' investment adviser'. SSGA FM and Wellington are sub-advisers in every N-CEN (2021-10 to 2026-10) but the SAI gives them no voting authority, so no series exception: DOMINI for every series.
      - cik: "851680"
        adviser: "Domini Impact Investments LLC (the Adviser); sub-advisers SSGA Funds Management, Inc. and Wellington Management Company LLP do not vote proxies"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/851680/000119312521339751/d212702d485bpos.htm"  # 485BPOS (SAI) filed 2021-11-24 (0001193125-21-339751), 'Proxy Voting Policies': voting delegated to Domini, Appendix B
        adviser_verified: "<date>"
        voting_note: "SAI 'PROXY VOTING POLICIES': 'The Board of Trustees has delegated the responsibility to vote proxies for the Funds to Domini.' Appendix B: 'The Board of Trustees (\"Board\") of the Domini Funds delegates the responsibility to vote proxies for the Funds to Domini Impact Investments LLC, the Funds' investment adviser'. Earliest SAI read 2021-11-24 (0001193125-21-339751); same wording in 2023-11-22 (0001193125-23-281955) and 2025-11-21 (0001193125-25-291191). SSGA Funds Management, Inc. (801-60103) and Wellington Management Company LLP (801-15908) are sub-advisers in every Form N-CEN 2021-10 to 2026-10 but the SAI describes them only as investing in securities the Adviser selects; neither is given proxy-voting authority."
        adviser_key_history: [{key: DOMINI, from: "2021-11-24"}]
        name: "DOMINI INVESTMENT TRUST"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
    voting_scope_notes:
      - "Keyed DOMINI from the EDGAR filing date of the earliest SAI read (2021-11-24, the first 485BPOS from 2021 on); earlier meetings stay unlabelled. Domini's own Proxy Voting Guidelines and Procedures govern every series; SSGA FM and Wellington, sub-advisers in every N-CEN, have no proxy-voting authority in the SAI."
      - "Not ingested (left out): Domini Impact Investments LLC's institutional-manager N-PX (CIK 1399069), the Impact Bond Fund notice reports (no vote table), and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
      - "Policy text: two sources, different documents. The website 'Domini Proxy Voting Guidelines' (a matrix of voting instructions, 'As of November 30, 2025') and Appendix B of the SAI (the guidelines and procedures, ending with the voting matrix). They are archived under separate labels and never mixed."
    commitments:
      # Verified 2026-11-21 (200 application/pdf to the honest client; the alias 30x-redirects to https://domini.com/wp-content/uploads/2025/11/Proxy-Voting-Guidelines-11302025.pdf, 504,601 bytes; first page 'Domini Proxy Voting Guidelines* As of November 30, 2025'). robots.txt allows. Wayback CDX holds NO capture of the alias or of the wp-content PDF (only 2022 captures of the older /proxyvoting page, all 301).
      - label: domini-proxy-voting-guidelines
        url: "https://domini.com/proxyvotingguidelines"
        adviser: "Domini Impact Investments LLC"
        adviser_key: "DOMINI"
      # Appendix B as printed in the SAI (485BPOS), dated by EDGAR filing date. Page furniture 'B-3' / 'B-46' printed mid-text. The 2021 SAI document contains the appendix twice (once per embedded copy); the 2023 and 2025 SAIs once.
      - label: domini-proxy-voting-guidelines-as-printed-in-sai
        adviser: "Domini Impact Investments LLC"
        adviser_key: "DOMINI"
        sai_appendix:
          cik: "0000851680"
          forms: ["485BPOS"]
          since: "2021-11-01"
          start:
            - "Appendix B Proxy Voting Policies and Procedures INTRODUCTION These Proxy Voting Guidelines and Procedures have been adopted by the Domini Investment Trust"
          end:
            - "PART C ITEM 28. EXHIBITS"
          strip_page_numbers: true
```

Markers were checked against the text (tags stripped, whitespace collapsed) of the 485BPOS of 2021-11-24, 2023-11-22 and 2025-11-21: the start string appears right after the Appendix A page "A-6 / A-5" (the TOC line reads "Appendix B - Proxy Voting Policies and Procedures. B-1", which does not match); the end string follows "... will be referred to Domini for voting instructions B-42 / B-46 / B-36".

## 4. Open doubts

- Wayback: no capture of https://domini.com/proxyvotingguidelines or the wp-content PDF. The first fetch by the ingester is the earliest archive; older editions of the website guidelines are unrecoverable except through the SAI label. The 2022-2024 website location is not known (the old https://www.domini.com/proxyvoting page 301s in 2022 Wayback).
- The website label uses the stable alias (redirects to a dated wp-content path). The edition date is on the first page ("As of November 30, 2025").
- Series-to-fund naming for S000067792 (Sustainable Solutions) and S000069966 (International Opportunities, began April 2020, dropped from the vote table in 2025) is inferred from the SAI order and the N-CEN sub-adviser order; it does not affect the key because DOMINI applies to every series.
- The 2022-11-22 SAI (0001193125-22-290801) was not downloaded; 2021, 2023 and 2025 were.
- The sai_appendix strings were checked against fetched text, not run through the ingester. The 2021 SAI document is about 1.47 M characters and repeats the appendix twice, which may make the archive pick two copies; dry-run before merge.
- Domini Investment Trust's N-CEN of 2026-10-14 (0001193125-26-420763) was parsed in aggregate only.
- `<date>` placeholders: set to the commit date.
