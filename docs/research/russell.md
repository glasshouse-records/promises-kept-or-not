# Russell Investments: research for a new institution entry

Research only, 2026-11-20. Nothing ingested, no data/ writes, config untouched. EDGAR reads via `glasshouse.http.get` (honest UA); the policy PDF and robots.txt via curl with the same honest UA.

## 1. Registrants that file N-PX vote tables (operating-company votes), 2024-2026

All three are `FUND VOTING REPORT` filings whose `proxyvote.xml` holds real operating-company votes (tens of MB each).

| CIK | Name (data.sec.gov) | N-PX filings 2024-2026 (accession, filed) | Series voted |
|---|---|---|---|
| 351601 | RUSSELL INVESTMENT CO (RIC) | 2024-08-27: 0001021408-24-005072, -005073, -005074 (identical 14-series docs), -005078, -005079 (identical 3-series docs); 2025-08-27: 0001021408-25-003862, -003863; 2026-08-28: 0001193125-26-374592, -374593 | 15 + 3 series (Emerging Markets, Equity Income, Global Equity, Global Infrastructure, Global RE Securities, Intl Developed, Multi-Strategy Income, Multifactor Intl / US Equity, Sustainable Equity, Tax Exempt HY Bond, Tax-Managed US Large Cap, Tax-Managed US Mid & Small, US Small Cap, US Strategic Equity; Multi-Asset Strategy, Tax-Managed Intl Equity, Tax-Managed Real Assets) |
| 824036 | RUSSELL INVESTMENT FUNDS (RIF) | 0001021408-24-004702 (2024-08-27); 0001021408-25-003861 (2025-08-27); 0001193125-26-374555 (2026-08-28) | 4 series: Global Real Estate Securities (S000006866), International Developed Markets (S000006865), U.S. Small Cap Equity (S000006864), U.S. Strategic Equity (S000006863) |
| 2042513 | Russell Investments Exchange Traded Funds | 0001021408-25-003860 (2025-08-27); 0001193125-26-374566 (2026-08-28) | 5 active ETFs: Emerging Markets Equity, Global Equity, International Developed Equity, Global Infrastructure, U.S. Small Cap Equity |

Pre-2024 RIC / RIF N-PX are legacy .txt (0001193125-23-223479, -224005): not XML.

Not ingested (no fund vote tables): Russell Investment Management, LLC (1415227, institutional-manager notice report, 2025 and 2026), and the 15-odd other Russell affiliates that file notice reports (Russell Investments Trust Co 400007, Capital LLC 1843723, Implementation Services 85816, Group Ltd 1692234, Ltd 2054951, Ireland 1021905, Japan 1097249, Management Ltd 1097248, Canada 2054948, Group Ltd 2054945, France 2111170). I did not open each of these; the search showed them as manager filings, not funds. "Russell" index funds of Vanguard/iShares etc. are unrelated.

## 2. Earliest 2021-2023 SAI read and who votes

Finding: RIM (Russell Investment Management, LLC), not the money managers, votes every proxy under its own Proxy Voting Policies and Guidelines. No SAI sentence, for any trust, says a money manager (sub-adviser) votes (regex search for "money manager ... vot/proxy" in the proxy sections of 7 SAIs: nothing). Money managers appear only as "Money Managers" in the service-provider section.

### RIC (351601)
- Earliest SAI: 485BPOS 0001193125-21-061230, filed 2021-03-01 (d88551d485bpos.htm). Later checked: 2022-02-28 (-22-058212, not read), 2023-02-28 0001193125-23-053743, 2024-02-28 -24-050406, 2026-02-27 -26-081241.
- Quote (section "PROXY VOTING POLICIES AND PROCEDURES", 2021-03-01): "The Board has delegated to RIM, as RIC's investment adviser, the primary responsibility for monitoring, evaluating and voting proxies solicited by or with respect to issuers of securities in which assets of the Funds may be invested. RIM has established a Proxy Voting and Engagement Committee ("Committee") and has adopted written Proxy Voting and Engagement Policies and Procedures ("P&P") and written proxy voting guidelines ("Guidelines"). ... RIM (whether acting directly or through the Committee) retains final authority with respect to proxy voting".
- Also: "the P&P authorize votes to be cast in accordance with the Guidelines and delegate to the Proxy Administrator responsibility for performing research and making proxy voting recommendations to RIM" and "RIM, through the Committee, constructs the Guidelines". "Matters that are not covered in the Guidelines ... are voted by the Committee."
- Funds of funds: "To the extent that any shares of a Fund are owned directly by any other RIC or RIF fund, those shares will be voted directly by such fund in the same proportion as all other votes received from the other holders of such fund's shares." (2021). The strategy funds of funds vote proportionally and appear not to be in the operating-company N-PX series list.
- 2023-02-28 wording: same, committee renamed "Active Ownership Committee". The 2024+ SAIs add the funds-of-funds sentence at the top ("Each Fund will vote in the same manner and proportion as the votes cast by other shareholders of the Underlying Funds").

### RIF (824036)
- Earliest SAI: 485BPOS 0001193125-21-144533, filed 2021-04-30 (d110096d485bpos.htm). Also read 2023-04-28 0001193125-23-126258, 2026-04-30 -26-196319.
- Quote (2021-04-30): "The Funds invest principally in the Underlying Funds. Each Fund will vote in the same manner and proportion as the votes cast by other shareholders of the Underlying Funds in which the Fund invests. ... The Board has delegated to RIM, as RIF and RIC's investment adviser, the primary responsibility for monitoring, evaluating and voting proxies solicited by or with respect to issuers of securities in which assets of the Funds may be invested." Remainder identical to RIC. Note: this SAI covers the RIF funds-of-funds (LifePoints); the four RIF series that have N-PX votes are the direct equity funds, and the delegation sentence applies to them.

### Russell Investments ETF Trust (2042513)
- No 2021-2023 SAI exists (N-1A filed 2024-11-19, 0001193125-24-261555). Earliest SAI: 485BPOS 0001193125-25-070104, filed 2025-04-01.
- Quote: "RIM, as the Trust's investment adviser, is primarily responsible for monitoring, evaluating and voting proxies solicited by or with respect to issuers of securities in which assets of the Funds may be invested. RIM has established an Active Ownership Committee ("Committee") ... RIM (whether acting directly or through the Committee) retains final authority with respect to proxy voting".

### Policy documents
- 2026 SAIs (RIC 2026-02-27 and RIF 2026-04-30) print the policy: "Please refer to Appendix B at the end of this SAI for the Guidelines effective March 1, 2026" (RIF: "effective May 1, 2026"). Appendix B starts "PROXY VOTING POLICIES AND GUIDELINES 2026 As adopted by: Russell Investments Capital, LLC ... Russell Investment Management, LLC ...". The RIC filing carries two SAI documents, each repeating Appendix B (identical copies, use `allow_identical_copies`). Appendix B is NOT printed in the 2021-2025 SAIs (checked 2021, 2023, 2024): they only say "The Guidelines are available, without charge, at https://russellinvestments.com".
- Live PDF (200, application/pdf, 371,587 bytes, honest UA, 2026-11-20): https://russellinvestments.com/-/media/files/us/corporate/russell-investments-proxy-voting-guidelines.pdf ("Proxy Voting Policies and Guidelines 2026", adopted by RIM among others). robots.txt (`User-agent: *`) does not disallow /-/media/files/us/. The PDF says "CONFIDENTIAL Copyright (c) 2026 Russell Investments Group, LLC ... may not be reproduced ... without prior written permission", yet it is published: same posture as other archived manager PDFs, but flag to the owner.
- Wayback CDX for the same URL (honest UA): 20220120041845 (200, "Proxy voting guidelines - January 2021", adopted by Russell Investment Management, LLC and Russell Investment Management Ltd), 20221204011309 (200, "January 2022"), 20240418131657 (200, digest MCG3A2...), 20240517204722 (302). I downloaded the first two and read page 1 only; later editions (2023, 2025) are not in the digest list, so they are not yet captured (the 2024 capture's content not read).

## 3. Proposed YAML (paste under `institutions:`, after `proshares`)

Verified facts: key RUSSELL for all three trusts. No series_adviser rules: no SAI names a voting sub-adviser. `from` = EDGAR filing date of earliest SAI read.

```yaml
  russell:
    display_name: "Russell Investments (Russell Investment Management, LLC)"
    short_name: "Russell"
    cik: "0001415227"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Russell Investment Management, LLC (RIM), Seattle WA (CIK 1415227, the investment adviser of the Russell Investment Company, Russell Investment Funds and Russell Investments Exchange Traded Funds, part of Russell Investments Group, LLC; its own N-PX and those of its affiliates are institutional-manager notice reports). Three open-end fund registrants that file N-PX vote tables are ingested: Russell Investment Company (CIK 351601), Russell Investment Funds (CIK 824036) and Russell Investments Exchange Traded Funds (CIK 2042513). The funds are multi-manager, but every SAI read (2021-2026) says the Board delegated proxy voting to RIM, which votes under its own written Proxy Voting Policies and Guidelines (a proxy administrator researches and executes under them; RIM, through its Committee, retains final authority); no SAI says a money manager votes. aum_usd_tr is not verified."
    npx_ciks:
      # Added 2026-11-20. Russell Investment Company, Russell Investment Funds and Russell Investments Exchange Traded Funds are the only Russell registrants that file N-PX vote tables with operating-company votes
      # (RIM 1415227, Russell Investments Trust Co 400007, Capital LLC 1843723 and the other affiliates file institutional-manager notice reports). Every SAI read says 'The Board has delegated to RIM, as [RIC's | RIF and RIC's]
      # investment adviser, the primary responsibility for monitoring, evaluating and voting proxies ... RIM has established a Proxy Voting and Engagement Committee [from 2023: an Active Ownership Committee] and has
      # adopted written Proxy Voting and Engagement Policies and Procedures and written proxy voting guidelines ... RIM (whether acting directly or through the Committee) retains final authority with respect to proxy voting'.
      # The proxy administrator is obliged 'to vote all proxies as set forth in the Guidelines'. Funds of funds vote in proportion to the other holders of the underlying funds. The Russell Investments ETF Trust has no 2021-2023 SAI
      # (first 485BPOS 2025-04-01), so its key starts there. No series_adviser rules: no SAI names a sub-adviser as voter.
      - cik: "351601"
        adviser: "Russell Investment Management, LLC (RIM, the Adviser; the money managers do not vote)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/351601/000119312521061230/d88551d485bpos.htm"  # 485BPOS (SAI) filed 2021-03-01 (0001193125-21-061230), 'Proxy Voting Policies and Procedures': delegated to RIM
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Policies and Procedures': 'The Board has delegated to RIM, as RIC's investment adviser, the primary responsibility for monitoring, evaluating and voting proxies solicited by or with respect to issuers of securities in which assets of the Funds may be invested. RIM has established a Proxy Voting and Engagement Committee ... and has adopted written Proxy Voting and Engagement Policies and Procedures ... and written proxy voting guidelines ... RIM (whether acting directly or through the Committee) retains final authority with respect to proxy voting' (earliest SAI read 2021-03-01, 0001193125-21-061230; same through 2026-02-27, committee renamed Active Ownership Committee by 2023-02-28; the 2026 SAI prints the Guidelines as Appendix B)."
        adviser_key_history: [{key: RUSSELL, from: "2021-03-01"}]
        name: "RUSSELL INVESTMENT CO"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "824036"
        adviser: "Russell Investment Management, LLC (RIM, the Adviser; the money managers do not vote)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/824036/000119312521144533/d110096d485bpos.htm"  # 485BPOS (SAI) filed 2021-04-30 (0001193125-21-144533), 'Proxy Voting Policies and Procedures': delegated to RIM
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Policies and Procedures': 'The Board has delegated to RIM, as RIF and RIC's investment adviser, the primary responsibility for monitoring, evaluating and voting proxies solicited by or with respect to issuers of securities in which assets of the Funds may be invested' (earliest SAI read 2021-04-30, 0001193125-21-144533; same through 2026-04-30). Funds of funds vote in the same proportion as other holders of the underlying funds."
        adviser_key_history: [{key: RUSSELL, from: "2021-04-30"}]
        name: "RUSSELL INVESTMENT FUNDS"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "2042513"
        adviser: "Russell Investment Management, LLC (RIM, the Adviser)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/2042513/000119312525070104/d940284d485bpos.htm"  # 485BPOS (SAI) filed 2025-04-01 (0001193125-25-070104), first SAI of the trust
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Policies and Procedures': 'RIM, as the Trust's investment adviser, is primarily responsible for monitoring, evaluating and voting proxies ... RIM has established an Active Ownership Committee ... RIM ... retains final authority with respect to proxy voting' (earliest SAI 2025-04-01, 0001193125-25-070104; the trust's N-1A was filed 2024-11-19, so there is no 2021-2023 SAI)."
        adviser_key_history: [{key: RUSSELL, from: "2025-04-01"}]
        name: "Russell Investments Exchange Traded Funds"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
    voting_scope_notes:
      - "Keyed RUSSELL, per registrant, from the EDGAR filing date of the earliest SAI read (RIC 2021-03-01, RIF 2021-04-30, ETF trust 2025-04-01); earlier meetings stay unlabelled. The funds are multi-manager, but RIM votes under its own Proxy Voting Policies and Guidelines (a proxy administrator executes under them); no SAI says a money manager votes, so there is no EXTERNAL series rule."
      - "Duplicate filings: the 2024-08-27 RIC N-PX were filed three times (0001021408-24-005072, -005073, -005074, identical 14-series documents) and twice (-005078, -005079, identical 3-series documents); dedupe must run after ingest."
      - "Not ingested (left out): Russell Investment Management LLC (1415227) and its affiliates' institutional-manager notice reports, and the legacy-.txt N-PX before 2024 (not ingested without --legacy)."
      - "Policy text: the Guidelines PDF on russellinvestments.com answers honest clients with 200 and robots.txt does not disallow it; it carries a 'may not be reproduced' copyright legend (decision for the owner). The 2021-2025 SAIs only point to the website; the 2026 SAIs print the Guidelines as Appendix B."
    commitments:
      - label: russell-proxy-voting-policies-and-guidelines
        url: "https://russellinvestments.com/-/media/files/us/corporate/russell-investments-proxy-voting-guidelines.pdf"
        adviser: "Russell Investment Management, LLC"
        adviser_key: "RUSSELL"
        # Wayback captures found (CDX, 200): 2022-01-20 (January 2021 edition), 2022-12-04 (January 2022 edition), 2024-04-18 (content not read). Walked by `ingest commitments --wayback`.
      - label: russell-proxy-voting-guidelines-as-printed-in-sai
        adviser: "Russell Investment Management, LLC"
        adviser_key: "RUSSELL"
        sai_appendix:
          cik: "0000351601"
          forms: ["485BPOS"]
          since: "2026-01-01"
          allow_identical_copies: true
          start: ["PROXY VOTING POLICIES AND GUIDELINES 2026 As adopted by: Russell Investments Capital, LLC"]
          end: []   # TO BE SET at build time: Appendix B's end was not located; run against a fixture before committing
```

If the 2026 SAI label is added, its start marker carries the year ("2026"), so a 2027 edition needs a second marker.

## 4. Open doubts

1. The SAI-appendix `end` marker and the page-footer strip patterns were not tested; build with a fixture before committing.
2. 2022-2025 SAIs of RIC (2022-02-28, 2025-02-28) and RIF (2022, 2024, 2025) were not read; only 2021, 2023, 2024 (RIC) and 2021, 2023, 2026 (RIF) plus RIC 2026. No variation found between those, so the key is uniform.
3. Funds-of-funds vote proportionally to underlying funds, which means those votes appear in the N-PX of the underlying trust only; RIC strategy funds are not in the N-PX series list I saw (3 and 15 series); the 2024 filings' totals were not reconciled with all 29 RIC funds.
4. The 2024-04-18 Wayback capture of the PDF was not read; whether a 2023 or 2025 edition exists on Wayback under a different URL was not checked.
5. Whether all N-PX `proxyvote.xml` rows are operating-company votes (some bond funds might vote few) was not counted per series.
