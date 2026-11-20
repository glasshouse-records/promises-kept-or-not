# Lazard (Lazard Asset Management LLC) - research for institutions.yaml

Research only, read 2026-11-20 via glasshouse.http (EDGAR) and curl with the honest UA (lazardassetmanagement.com). Nothing in data/, config/ or the ledger was touched.

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

| CIK | Name (data.sec.gov) | Type | N-PX seasons with XML vote tables | Notes |
|---|---|---|---|---|
| 874964 | LAZARD FUNDS INC | open-end, 20-30 series | 2024-08-28 (0000930413-24-002506, 33,929 vote rows), 2025-08-19, 2026-08-14 | 2023-12-18 and earlier are legacy |
| 1033669 | LAZARD RETIREMENT SERIES INC | open-end (insurance), 4 series | 2024-08-28 (0000930413-24-002507, 8,818 rows), 2025, 2026 | |
| 1278211 | LAZARD GLOBAL TOTAL RETURN & INCOME FUND INC | closed-end | 2024-08-28 (0000930413-24-002508, 1,104 rows), 2025, 2026 | N-CSR, not a SAI, carries the policy statement |
| 2051630 | Lazard Active ETF Trust | open-end ETF, 4 series in N-PX 2025 (S000091513 Equity Megatrends, S000091514 International Dynamic Equity, S000091515 Japanese Equity, S000091516 Next Gen Technologies), 7 in N-CEN 2026 | 2025-08-19 (0000930413-25-002515, 1,301 rows), 2026-08-14 | no SAI exists in 2021-2023: trust registered 2025 |

Not ingested (same convention as dodge_cox / global_x):
- Lazard Asset Management LLC, CIK 1207017: own INSTITUTIONAL MANAGER VOTING REPORT (separate accounts, 1,680 rows in 2024-08-28 0000930413-24-002518; also 2025, 2026). Not a fund registrant.
- Lazard World Dividend & Income Fund (1323206): last N-PX 2020-08-14, none in 2024-2026.
- Lazard Alternative Strategies Fund LLC (1141766) and Lazard Alternative Emerging Markets 1099 Fund (1525873): last N-PX 2013-2015.
- No N-CEN (FY2020 to FY2025, 6 read per registrant, 1 for the ETF Trust) names a sub-adviser for any Lazard registrant; the only adviser is Lazard Asset Management LLC.

## 2. Earliest SAI read and the exact quotes

All three open-end registrants print the same two passages: the SAI section "Proxy Voting" and Appendix B "LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY" (Appendix B is the adviser's own policy, printed in full; edition "Revised As Of March 31, 2020" in 2021, "December 7, 2022" in 2022-2023 SAIs, "April 2024" by 2026).

- LAZARD FUNDS INC: earliest 2021-2023 SAI read 485BPOS filed 2021-04-23, 0000930413-21-000868 (c101228_485bpos-ixbrl.htm). (Preceded only by a 485APOS of 2021-02-26.) Same text re-read in 0000930413-23-001455 (2023-04-28).
- LAZARD RETIREMENT SERIES INC: earliest 485BPOS filed 2021-04-12, 0000930413-21-000764 (c101042_485bpos-ixbrl.htm). Re-read 0000930413-23-001204 (2023-04-07).
- Lazard Active ETF Trust: no 2021-2023 SAI. Earliest SAI is the initial N-1A filed 2025-01-15, 0000930413-25-000091 (c110998_n1a.htm); first 485BPOS 2025-02-21, 0000930413-25-000652. Re-read 2026-04-23 0000930413-26-001180 (policy "Revised: April 2024").

Quote (SAI "Proxy Voting"; Fund/Portfolio/Trust varies by registrant):
> "The Board has delegated to the Investment Manager the authority to vote proxies of companies held in the Fund's portfolio. The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B, which sets forth proxy voting guidelines applicable to specific types of common proxy proposals."

Investment Manager = Lazard Asset Management LLC (cover of every SAI). Appendix B, section B "Responsibility to Vote Proxies":
> "Lazard does not delegate that authority to any other person or entity, but retains complete authority for voting all proxies on behalf of its clients."

and section C.2: ISS and Glass Lewis supply research only; "Portfolio Management ... are responsible for providing the vote recommendation for a given proposal". So votes follow Lazard's own policy, key LAZARD.

Closed-end Lazard Global Total Return & Income Fund: N-CSR filed 2021-03-01, 0000930413-21-000507 (c101014_ncsr.htm), Item 7 (earliest 2021 filing with a policy statement; N-CSR of 2022-03-01 0000930413-22-000405 and 2023-02-27 0000930413-23-000681 exist):
> "The Registrant has delegated voting of proxies in respect of portfolio holdings to Lazard, to vote the Registrant's proxies in accordance with Lazard's proxy voting policy and guidelines (the "Voting Guidelines")"

No SAI/N-2 in 2021-2023, so there is no appendix to archive for it; the Item 7 summary is not the full policy, so the fund gets the website policy label only.

## 3. Proposed YAML (paste under `institutions:` before `proshares:` or at the end)

```yaml
  lazard:
    display_name: "Lazard (Lazard Asset Management LLC)"
    short_name: "Lazard"
    cik: "0001207017"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Lazard Asset Management LLC, New York NY (CIK 1207017, the investment adviser of the Lazard Funds and the 13-F / institutional-manager N-PX filer; a subsidiary of Lazard, Inc.). Four fund registrants that file N-PX vote tables with operating-company votes are ingested: Lazard Funds Inc (CIK 874964), Lazard Retirement Series Inc (1033669), Lazard Global Total Return & Income Fund Inc (1278211, closed-end) and Lazard Active ETF Trust (2051630). Every SAI says 'The Board has delegated to the Investment Manager the authority to vote proxies ... The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B', and Appendix B is Lazard Asset Management LLC's own policy (ISS and Glass Lewis supply research only; Lazard 'retains complete authority for voting all proxies'), so every registrant is keyed LAZARD. The closed-end fund's N-CSR Item 7 says it 'has delegated voting of proxies ... to Lazard, to vote ... in accordance with Lazard's proxy voting policy and guidelines'. No N-CEN (FY2020 to FY2025) names a sub-adviser. Lazard's own institutional-manager N-PX (CIK 1207017, separate accounts) is not ingested. aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. Four Lazard registrants file N-PX vote tables with operating-company votes (Lazard World Dividend & Income Fund 1323206 last filed in 2020; Lazard Alternative Strategies Fund 1141766 and Lazard Alternative Emerging Markets 1099 Fund 1525873 in 2013-2015; Lazard Asset Management LLC's own institutional-manager N-PX, 1207017, is not ingested).
      # Every SAI read prints 'The Board has delegated to the Investment Manager the authority to vote proxies of companies held in the Fund's portfolio. The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B' (Investment Manager = Lazard Asset Management LLC); Appendix B 'LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY'
      # says Lazard 'retains complete authority for voting all proxies on behalf of its clients' and uses ISS / Glass Lewis for research only. No N-CEN (six read per registrant, FY2020 to FY2025; one for the ETF Trust) lists a sub-adviser, so there is no series exception. Each registrant is dated from the EDGAR filing date of the earliest SAI (or N-CSR) read.
      - cik: "874964"
        adviser: "Lazard Asset Management LLC (the Investment Manager); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/874964/000093041321000868/c101228_485bpos-ixbrl.htm"  # 485BPOS (SAI) filed 2021-04-23 (0000930413-21-000868), 'Proxy Voting': delegated to the Investment Manager, Global Proxy Voting Policy in Appendix B
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting': 'The Board has delegated to the Investment Manager the authority to vote proxies of companies held in the Fund's portfolio. The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B' (earliest SAI read 2021-04-23, 0000930413-21-000868; same wording in 2023-04-28). Appendix B is 'LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY' (Revised As Of March 31, 2020; December 7, 2022 from the 2022 SAI). Every Form N-CEN filed 2021-03 to 2026-03 names Lazard Asset Management LLC as the only adviser and no sub-adviser."
        adviser_key_history: [{key: LAZARD, from: "2021-04-23"}]
        name: "LAZARD FUNDS INC"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1033669"
        adviser: "Lazard Asset Management LLC (the Investment Manager); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1033669/000093041321000764/c101042_485bpos-ixbrl.htm"  # 485BPOS (SAI) filed 2021-04-12 (0000930413-21-000764), 'Proxy Voting': delegated to the Investment Manager, Global Proxy Voting Policy in Appendix B
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting': 'The Board has delegated to the Investment Manager the authority to vote proxies of companies held in the Fund's portfolio. The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B' (earliest SAI read 2021-04-12, 0000930413-21-000764; same wording in 2023-04-07). Appendix B is the same Lazard Asset Management LLC Global Proxy Voting Policy. No sub-adviser in any Form N-CEN (2021-03 to 2026-03)."
        adviser_key_history: [{key: LAZARD, from: "2021-04-12"}]
        name: "LAZARD RETIREMENT SERIES INC"
        validated: "<date>"
      - cik: "1278211"
        adviser: "Lazard Asset Management LLC (the Investment Manager); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1278211/000093041321000507/c101014_ncsr.htm"  # N-CSR filed 2021-03-01 (0000930413-21-000507), Item 7: voting delegated to Lazard under Lazard's proxy voting policy and guidelines
        adviser_verified: "<date>"
        voting_note: "Closed-end fund; no SAI or N-2 in 2021-2023. N-CSR Item 7 (earliest 2021 filing read, 2021-03-01, 0000930413-21-000507; also 2022-03-01 and 2023-02-27): 'The Registrant has delegated voting of proxies in respect of portfolio holdings to Lazard, to vote the Registrant's proxies in accordance with Lazard's proxy voting policy and guidelines (the \"Voting Guidelines\")'. No sub-adviser in any Form N-CEN (2021-03 to 2026-03)."
        adviser_key_history: [{key: LAZARD, from: "2021-03-01"}]
        name: "LAZARD GLOBAL TOTAL RETURN & INCOME FUND INC"
        validated: "<date>"
      - cik: "2051630"
        adviser: "Lazard Asset Management LLC (the Investment Manager); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/2051630/000093041325000091/c110998_n1a.htm"  # N-1A (SAI) filed 2025-01-15 (0000930413-25-000091), 'Proxy Voting': delegated to the Investment Manager, Global Proxy Voting Policy in Appendix B
        adviser_verified: "<date>"
        voting_note: "No SAI before 2025 (trust registered 2025). Earliest SAI read: the initial N-1A of 2025-01-15 (0000930413-25-000091), then 485BPOS 2025-02-21 (0000930413-25-000652) and 2026-04-23 (0000930413-26-001180): 'The Board has delegated to the Investment Manager the authority to vote proxies of companies held in the Trust's portfolio. The Investment Manager has adopted a Global Proxy Voting Policy, attached as Appendix B' (Revised As Of November 15, 2023; Revised: April 2024 in the 2026 SAI). Form N-CEN 2026-03-13 names no sub-adviser."
        adviser_key_history: [{key: LAZARD, from: "2025-01-15"}]
        name: "Lazard Active ETF Trust"
        validated: "<date>"
    voting_scope_notes:
      - "Keyed LAZARD per registrant from the EDGAR filing date of the earliest SAI (or, for the closed-end fund, N-CSR) read: Lazard Funds 2021-04-23, Lazard Retirement Series 2021-04-12, Lazard Global Total Return & Income Fund 2021-03-01, Lazard Active ETF Trust 2025-01-15; earlier meetings stay unlabelled. Appendix B of every SAI is Lazard Asset Management LLC's own Global Proxy Voting Policy; ISS and Glass Lewis supply research and Lazard's portfolio managers decide ('retains complete authority')."
      - "Not ingested (left out): Lazard Asset Management LLC's institutional-manager N-PX (CIK 1207017), Lazard World Dividend & Income Fund (1323206; last N-PX 2020), Lazard Alternative Strategies Fund (1141766) and Lazard Alternative Emerging Markets 1099 Fund (1525873), and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
      - "Policy text: two sources, different editions. The website document 'Lazard Proxy Voting Policy and Procedures Overview' (May 2026, a short overview) is NOT the SAI's long Global Proxy Voting Policy; they are archived under separate labels and never mixed. The closed-end fund has only the website label (its N-CSR gives a bullet summary, not the policy)."
    commitments:
      # Verified 2026-11-20 (200 application/pdf to honest client; robots.txt allows; the alias below 30x-redirects to /docs/16376/LazardProxyVotingPolicyAndProceduresOverview.pdf). Wayback holds the alias: 2022-03-20 (200), 2023-05-18 (200).
      - label: lazard-proxy-voting-policy-overview
        url: "https://www.lazardassetmanagement.com/docs/-m0-/16376/LazardProxyVotingPolicyAndProcedures.pdf"
        adviser: "Lazard Asset Management LLC"
        adviser_key: "LAZARD"
      # Appendix B as printed in the SAI (edition revised 2020-03-31, 2022-12-07, 2024-04), dated by EDGAR filing date. One label per trust (three trusts, own CIK). Page numbers 'B-12' / 'B- 12' removed by strip_page_numbers.
      - label: lazard-global-proxy-voting-policy-as-printed-in-sai-funds
        adviser: "Lazard Asset Management LLC"
        adviser_key: "LAZARD"
        sai_appendix:
          cik: "0000874964"
          forms: ["485BPOS"]
          since: "2021-04-01"
          start:
            - "Appendix B LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY A. Introduction"
          end:
            - "THE LAZARD FUNDS, INC. PART C. OTHER INFORMATION"
          strip_page_numbers: true
      - label: lazard-global-proxy-voting-policy-as-printed-in-sai-retirement
        adviser: "Lazard Asset Management LLC"
        adviser_key: "LAZARD"
        sai_appendix:
          cik: "0001033669"
          forms: ["485BPOS"]
          since: "2021-04-01"
          start:
            - "Appendix B LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY A. Introduction"
          end:
            - "LAZARD RETIREMENT SERIES, INC. PART C. OTHER INFORMATION"
          strip_page_numbers: true
      - label: lazard-global-proxy-voting-policy-as-printed-in-sai-etf
        adviser: "Lazard Asset Management LLC"
        adviser_key: "LAZARD"
        sai_appendix:
          cik: "0002051630"
          forms: ["485BPOS"]
          since: "2025-01-01"
          start:
            - "Appendix B LAZARD ASSET MANAGEMENT LLC GLOBAL PROXY VOTING POLICY A. Introduction"
          end:
            - "LAZARD ACTIVE ETF TRUST PART C. OTHER INFORMATION"
            - "PART C OTHER INFORMATION"
          strip_page_numbers: true
```

## 4. Open doubts

- The ETF Trust's end marker differs across editions (2025-02-21 485BPOS has no trust name before "PART C OTHER INFORMATION"; 2026 has "LAZARD ACTIVE ETF TRUST PART C. OTHER INFORMATION"): both are listed; the 2025-01-15 N-1A is form N-1A, not 485BPOS, so the appendix archive starts at the 2025-02-21 485BPOS unless forms adds "N-1A". LAZARD key date uses the N-1A filing (earliest SAI read).
- The sai_appendix start/end strings were checked against the text of 2021 and 2023 SAIs (and the ETF 2025/2026), not run through the ingester (a release build is running). Dry-run with the real archive before merge.
- Lazard Funds N-PX 2024 covers 27 series; series changes were not enumerated since no series exception applies.
- `<date>` placeholders: set to the commit date.
- N-CSR date (2021-03-01) for the closed-end fund is the earliest 2021 filing with Item 7 text, not a SAI; if the maintainer wants SAI-only dating, leave 1278211 UNRESOLVED instead.
