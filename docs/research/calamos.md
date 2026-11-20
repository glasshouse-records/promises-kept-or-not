# Calamos (Calamos Advisors LLC) - source research for config/institutions.yaml

Research only, 2026-11-20. Nothing ingested, nothing in data/ or config/ touched. All EDGAR reads via `glasshouse.http.get`
(honest UA); the calamos.com / Wayback probes used curl with the same honest UA.

## 1. Registrants that file N-PX vote tables with operating-company votes, 2024-2026

Names are the EDGAR conformed names (data.sec.gov submissions API, 2026-11-20). Every one filed N-PX on 2024-08-30,
2025-08-27 and 2026-08-28 (Calamos ETF Trust, Antetokounmpo Trust and Aksia Alternative Credit counted below). All
show N-CEN adviser Calamos Advisors LLC (ETF Trust SROI and Antetokounmpo: CGAM is adviser, Calamos Advisors the sub-adviser).

| CIK | Name | Kind | 2024 / 2025 / 2026 N-PX accession (vote table size) |
|---|---|---|---|
| 1079575 | CALAMOS ADVISORS TRUST/IL (one series, Calamos Growth and Income Portfolio S000006427) | open-end (insurance) | 0001438934-24-001493 / -25-001807 / -26-002313 (1.2 MB / 1.0 MB / 1.0 MB) |
| 1579881 | Calamos ETF Trust (9 series 2024, 33 vote-bearing 2025, 45 listed 2026) | open-end ETF | 0001438934-24-001391 / -25-002069 / -26-002281 |
| 1943291 | Calamos Antetokounmpo Sustainable Equities Trust (S000078028) | open-end | 0001438934-24-001584 / -25-001805 / -26-002300 |
| 1171471 | CALAMOS CONVERTIBLE OPPORTUNITIES & INCOME FUND | closed-end | 0001438934-24-001482 / -25-001813 / -26-002290 |
| 1222719 | CALAMOS CONVERTIBLE & HIGH INCOME FUND | closed-end | 0001438934-24-001479 / -25-001792 / -26-002296 |
| 1275214 | CALAMOS STRATEGIC TOTAL RETURN FUND | closed-end | 0001438934-24-001372 / -25-001815 / -26-002268 |
| 1285650 | CALAMOS GLOBAL TOTAL RETURN FUND | closed-end | 0001438934-24-001374 / -25-001774 / -26-002266 |
| 1396277 | Calamos Global Dynamic Income Fund | closed-end | 0001438934-24-001380 / -25-001811 / -26-002277 |
| 1602584 | Calamos Dynamic Convertible & Income Fund | closed-end | 0001438934-24-001486 / -25-001797 / -26-002286 |
| 1717457 | Calamos Long/Short Equity & Dynamic Income Trust | closed-end | 0001438934-24-001491 / -25-001809 / -26-002271 |
| 1937073 | Calamos Aksia Alternative Credit & Income Fund | closed-end (interval-style, sub-advised by Aksia) | table only in 2025 (0001438934-25-001788, 3.7 KB, FRANKLIN-type holdings); 2024 and 2026 filings have no vote table |

Not ingested / left out:
- Calamos Advisors LLC (1316507): its own institutional-manager N-PX (separate accounts) DOES carry a vote table
  (0001438934-24-001386, -25-001784, -26-002327, 0.5-0.8 MB) but it is the adviser's filing, not a fund registrant (same
  call as Dodge & Cox CIK 200217). Recommend not ingesting; the institution `cik` stays 0001316507 (13-F filer).
- Calamos Aksia Private Equity & Alternatives Fund (2047442) and Calamos Aksia Hedged Strategies Fund (2063706): one N-PX
  each (2026-08-28), no vote table.
- Legacy-HTML N-PX before 2024 (2021-2023) are not ingested without --legacy.

## 2. Earliest 2021-2023 SAI (or closed-end equivalent) read, and the voting sentence

Calamos funds are voted by Calamos Advisors under its own policy (Glass Lewis only applies Calamos' custom rules), so no
EXTERNAL series. No N-CEN (2021-2026, spot-read for 1079575, 1171471, 1396277, 1717457, 1579881, 1943291, 1937073) lists a
sub-adviser that votes, except Aksia for 1937073.

| CIK | Document (accession, EDGAR filing date) | Quoted sentence(s) |
|---|---|---|
| 1079575 | 485BPOS 0001104659-21-050134, 2021-04-14 (also -22-045940 2022-04-14, -23-044998 2023-04-13) | "The Portfolio has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight." / "Calamos Advisors has adopted its own Proxy Voting Policies and Procedures (the "Policies")." / "Glass Lewis facilitates the voting of each proxy by applying Calamos' custom proxy voting rules ("proxy voting policy") to the proposal(s)." |
| 1579881 (non-sustainable series) | 485BPOS 0001104659-23-104692, 2023-09-28 (Calamos Convertible Equity Alternative ETF, CVRT) | "The Fund has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight." / "Calamos Advisors has adopted its own Proxy Voting Policies and Procedures (the "Policies")." Same in the 2024-04-22 and 2025-01-17 multi-fund SAIs ("Each Fund has delegated ..."). |
| 1579881 (SROI, Calamos Antetokounmpo Global Sustainable Equities ETF, S000079464) | 485BPOS 0001104659-23-005496, 2023-01-23 (also 0001104659-23-120383, 2023-11-21) | "The Fund has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight and any specific written instructions to the contrary provided to Calamos Advisors by CGAM." / "Calamos Advisors has adopted its own Proxy Voting Policies and Procedures for Sustainable Investment Strategies (the "Policies")." / "Glass Lewis facilitates the voting decision of each proxy in accordance with Calamos Advisors' ESG proxy voting guidelines (the "ESG Custom Voting Policy")." |
| 1943291 | 497 0001104659-23-007604, 2023-01-30 (SAI text; N-1A 2022-08-24; first 485BPOS 2024-04-15) | Same sentences as SROI above (ESG Custom Voting Policy, CGAM instructions). |
| 1171471 | 424B5 0001104659-21-032477, 2021-03-05 (SAI "Proxy Voting Procedures") | "The Fund has delegated proxy voting responsibilities to Calamos, subject to the board of trustees' general oversight." / "Calamos has adopted its own Proxy Voting Policies and Procedures (the "Policies")." |
| 1222719 | 424B5 0001104659-21-032475, 2021-03-05 | same wording |
| 1275214 | 424B5 0001104659-21-061385, 2021-05-05 | same wording ("Board of Trustees'") |
| 1285650 | N-2/A 0001104659-21-025833, 2021-02-19 | same wording |
| 1396277 | N-2 0001104659-21-082034, 2021-06-16 | same wording |
| 1602584 | 424B5 0001104659-21-076112, 2021-06-03 | same wording |
| 1717457 | N-CSR 0001387131-21-012346, 2021-12-29, Item 7 (no prospectus/SAI in 2021-2023 within the filing list; last N-2-family doc is the 497 of 2019-11-26) | "The registrant has delegated authority to vote all proxies relating to the Fund's portfolio securities to the Fund's investment advisor, Calamos Advisors LLC ("Calamos Advisors"). The Calamos Advisors Proxy Voting Policies and Procedures are included as an Exhibit hereto." |
| 1937073 | 424B3 0001104659-23-061942, 2023-05-17 (first effective prospectus; N-2 2022-07-08) | "The Fund has delegated its proxy voting responsibility to the Advisor." and "... to delegate the responsibility for voting proxies ... to the Fund's Advisor and Sub-Advisor ..." / "The sub-advisor to the Fund is Aksia." Joint Advisor/Sub-Advisor voting: policy owner unclear, so UNRESOLVED. |

## 3. Proposed YAML (paste-ready; not applied)

Keys: CALAMOS (Calamos Advisors' own legacy/non-sustainable policy), CALAMOS_SUSTAINABLE (its separate ESG custom policy,
which governs SROI and the Antetokounmpo Trust). `from` is the EDGAR filing date of the earliest SAI-equivalent read.
Closed-end funds are keyed from the earliest 2021 prospectus/N-2 carrying the SAI "Proxy Voting Procedures" text.

```yaml
  calamos:
    display_name: "Calamos (Calamos Advisors LLC)"
    short_name: "Calamos"
    cik: "0001316507"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Calamos Advisors LLC, Naperville IL (CIK 1316507, the 13-F filer and the investment adviser of the Calamos open-end and closed-end funds). Ten US fund registrants that file N-PX vote tables are ingested: Calamos Advisors Trust, Calamos ETF Trust, Calamos Antetokounmpo Sustainable Equities Trust and seven closed-end funds. Every SAI, closed-end SAI or N-CSR Item 7 read (2021-2023) says the fund 'has delegated proxy voting responsibilities to Calamos Advisors' under 'its own Proxy Voting Policies and Procedures', with Glass Lewis applying Calamos' custom rules: the policy is Calamos Advisors' own. Calamos has two custom rule sets, a general one (CALAMOS) and an ESG 'Sustainable Investment Strategies' one (CALAMOS_SUSTAINABLE) that governs the Antetokounmpo funds. aum_usd_tr is not verified."
    npx_ciks:
      # Added 2026-11-20. Not ingested: Calamos Advisors LLC's own institutional-manager N-PX (CIK 1316507, separate accounts, not a fund registrant), Calamos Aksia Private Equity & Alternatives Fund (2047442) and Calamos Aksia Hedged Strategies Fund (2063706) (one N-PX each, no vote table), and the legacy-HTML N-PX before 2024 (not ingested without --legacy).
      - cik: "1079575"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1079575/000110465921050134/tm2111601-1_485bpos.htm"  # 485BPOS (SAI) filed 2021-04-14 (0001104659-21-050134), 'Proxy Voting Procedures': delegated to Calamos Advisors
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Portfolio has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight ... Calamos Advisors has adopted its own Proxy Voting Policies and Procedures' (earliest SAI read 2021-04-14, 0001104659-21-050134; same in 2022-04-14 and 2023-04-13). N-CEN 2021 and 2026 name Calamos Advisors as the only adviser."
        adviser_key_history: [{key: CALAMOS, from: "2021-04-14"}]
        name: "CALAMOS ADVISORS TRUST/IL"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1579881"
        adviser: "Calamos Advisors LLC (the Adviser); Calamos Antetokounmpo Asset Management LLC (CGAM) is the adviser of the SROI ETF only"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1579881/000110465923104692/"  # 485BPOS (SAI) filed 2023-09-28 (0001104659-23-104692); SROI SAI 2023-01-23 (0001104659-23-005496). Replace with the SAI main-document URL when recorded.
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight' (earliest non-sustainable SAI read 2023-09-28, 0001104659-23-104692; 'Each Fund has delegated' in the multi-fund SAIs of 2024-04-22 and 2025-01-17). The SROI ETF (Calamos Antetokounmpo Global Sustainable Equities ETF, S000079464) SAI of 2023-01-23 (0001104659-23-005496) names the separate 'Proxy Voting Policies and Procedures for Sustainable Investment Strategies' ('ESG Custom Voting Policy') and 'any specific written instructions to the contrary provided to Calamos Advisors by CGAM', so SROI is keyed CALAMOS_SUSTAINABLE by series_adviser."
        adviser_key_history: [{key: CALAMOS, from: "2023-09-28"}]
        series_adviser:
          S000079464: [{key: CALAMOS_SUSTAINABLE, from: "2023-01-23"}]   # Calamos Antetokounmpo Global Sustainable Equities ETF (SROI)
        name: "Calamos ETF Trust"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1943291"
        adviser: "Calamos Antetokounmpo Asset Management LLC (CGAM, the Adviser); Calamos Advisors LLC (sub-adviser, votes)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1943291/000110465923007604/a22-23398_7497.htm"  # 497 (prospectus + SAI) filed 2023-01-30 (0001104659-23-007604), 'Proxy Voting Procedures': delegated to Calamos Advisors, ESG Custom Voting Policy
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos Advisors, subject to the board of trustees' general oversight and any specific written instructions to the contrary provided to Calamos Advisors by CGAM ... Calamos Advisors has adopted its own Proxy Voting Policies and Procedures for Sustainable Investment Strategies' (earliest SAI read 2023-01-30, 0001104659-23-007604). The ESG Custom Voting Policy, applied by Glass Lewis, is Calamos Advisors' own; CGAM may instruct otherwise in writing (no instance known)."
        adviser_key_history: [{key: CALAMOS_SUSTAINABLE, from: "2023-01-30"}]
        name: "Calamos Antetokounmpo Sustainable Equities Trust"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      # Closed-end funds: no SAI of their own in the 2021-2023 filing list for 1717457, so the date is the N-CSR (Item 7) of 2021-12-29; the other six carry the SAI 'Proxy Voting Procedures' in a 2021 424B5 / N-2 / N-2/A.
      - cik: "1171471"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1171471/000110465921032477/"  # 424B5 filed 2021-03-05 (0001104659-21-032477), SAI 'Proxy Voting Procedures'
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos, subject to the board of trustees' general oversight ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-03-05, 0001104659-21-032477). N-CEN 2021 and 2026 name Calamos Advisors only."
        adviser_key_history: [{key: CALAMOS, from: "2021-03-05"}]
        name: "CALAMOS CONVERTIBLE OPPORTUNITIES & INCOME FUND"
        validated: "2026-11-20"
      - cik: "1222719"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1222719/000110465921032475/"  # 424B5 filed 2021-03-05 (0001104659-21-032475)
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-03-05, 0001104659-21-032475)."
        adviser_key_history: [{key: CALAMOS, from: "2021-03-05"}]
        name: "CALAMOS CONVERTIBLE & HIGH INCOME FUND"
        validated: "2026-11-20"
      - cik: "1275214"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1275214/000110465921061385/"  # 424B5 filed 2021-05-05 (0001104659-21-061385)
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-05-05, 0001104659-21-061385)."
        adviser_key_history: [{key: CALAMOS, from: "2021-05-05"}]
        name: "CALAMOS STRATEGIC TOTAL RETURN FUND"
        validated: "2026-11-20"
      - cik: "1285650"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1285650/000110465921025833/"  # N-2/A filed 2021-02-19 (0001104659-21-025833)
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-02-19, 0001104659-21-025833)."
        adviser_key_history: [{key: CALAMOS, from: "2021-02-19"}]
        name: "CALAMOS GLOBAL TOTAL RETURN FUND"
        validated: "2026-11-20"
      - cik: "1396277"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1396277/000110465921082034/"  # N-2 filed 2021-06-16 (0001104659-21-082034)
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-06-16, 0001104659-21-082034)."
        adviser_key_history: [{key: CALAMOS, from: "2021-06-16"}]
        name: "Calamos Global Dynamic Income Fund"
        validated: "2026-11-20"
      - cik: "1602584"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1602584/000110465921076112/"  # 424B5 filed 2021-06-03 (0001104659-21-076112)
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting Procedures': 'The Fund has delegated proxy voting responsibilities to Calamos ... Calamos has adopted its own Proxy Voting Policies and Procedures' (earliest read 2021-06-03, 0001104659-21-076112)."
        adviser_key_history: [{key: CALAMOS, from: "2021-06-03"}]
        name: "Calamos Dynamic Convertible & Income Fund"
        validated: "2026-11-20"
      - cik: "1717457"
        adviser: "Calamos Advisors LLC (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1717457/000138713121012346/cpz-ncsr_103121.htm"  # N-CSR filed 2021-12-29 (0001387131-21-012346), Item 7
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR Item 7: 'The registrant has delegated authority to vote all proxies relating to the Fund's portfolio securities to the Fund's investment advisor, Calamos Advisors LLC. The Calamos Advisors Proxy Voting Policies and Procedures are included as an Exhibit hereto.' (earliest read 2021-12-29, 0001387131-21-012346; no prospectus or SAI of the trust is in the 2021-2023 filing list)."
        adviser_key_history: [{key: CALAMOS, from: "2021-12-29"}]
        name: "Calamos Long/Short Equity & Dynamic Income Trust"
        validated: "2026-11-20"
      - cik: "1937073"
        adviser: "Calamos Advisors LLC (the Adviser) and Aksia LLC (Sub-Advisor); both vote"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1937073/000110465923061942/tm2220436d14_424b3.htm"  # 424B3 filed 2023-05-17 (0001104659-23-061942), SAI 'Proxy Voting Policy and Proxy Voting Record'
        adviser_verified: "2026-11-20"
        voting_note: "SAI: 'The Fund has delegated its proxy voting responsibility to the Advisor ... to the Fund's Advisor and Sub-Advisor as a part of the Advisor's and Sub-Advisor's general management of the Fund's portfolio' (0001104659-23-061942, 2023-05-17); the sub-advisor is Aksia. Whose policy governs a given vote is not stated, so UNRESOLVED. Only the 2025 N-PX carries a vote table (3.7 KB)."
        adviser_key_history: [{key: UNRESOLVED, from: "2023-05-17"}]
        name: "Calamos Aksia Alternative Credit & Income Fund"
        validated: "2026-11-20"
    voting_scope_notes:
      - "Keyed from the EDGAR filing date of the earliest SAI-equivalent read per registrant (see each voting_note); earlier meetings stay unlabelled. The Calamos ETF Trust is keyed CALAMOS from the first non-sustainable SAI read (2023-09-28); its 2023-01-23 SAI covers only the SROI sustainable ETF."
      - "CALAMOS_SUSTAINABLE: Calamos Advisors' 'Proxy Voting Policies and Procedures for Sustainable Investment Strategies' (ESG Custom Voting Policy), the Antetokounmpo Trust (from 2023-01-30) and the SROI ETF series (from 2023-01-23). Its full text is in the SAI proxy section; it is not archived separately."
      - "Not ingested: Calamos Advisors LLC's institutional-manager N-PX (CIK 1316507), Calamos Aksia Private Equity & Alternatives Fund (2047442), Calamos Aksia Hedged Strategies Fund (2063706), and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
    commitments:
      # 200 application/pdf (honest client, 2026-11-20, 191,555 bytes; PDF CreationDate 2024-10-23). A DESCRIPTION of both rule sets ('two sets of custom proxy voting rules: ... Sustainable Strategies ... and non-Sustainable Strategies'), so it is keyed CALAMOS and carries a note; Wayback holds captures 2021-03-02, 2024-03-03, 2024-07-14, 2025-07-14, 2026-01-03.
      - label: calamos-description-of-proxy-voting-policies
        url: "https://www.calamos.com/globalassets/media/shared/legalpdfs/descriptionofproxyvotingpoliciesandprocedures.pdf"
        adviser: "Calamos Advisors LLC"
        adviser_key: "CALAMOS"
      # Full general policy as printed in the Calamos Advisors Trust SAI ('PROXY VOTING PROCEDURES ... DISCLOSURE OF PORTFOLIO HOLDINGS'); a stray page number sits mid-sentence ('32 In general'), so strip_page_numbers. Not run through the extractor yet: verify start/end on the 2022 and 2023 editions before enabling.
      - label: calamos-proxy-voting-policy-as-printed-in-sai
        adviser: "Calamos Advisors LLC"
        adviser_key: "CALAMOS"
        sai_appendix:
          cik: "0001079575"
          forms: ["485BPOS"]
          since: "2021-04-01"
          start:
            - "PROXY VOTING PROCEDURES. The Portfolio has delegated proxy voting responsibilities to Calamos Advisors"
          end:
            - "DISCLOSURE OF PORTFOLIO HOLDINGS."
          strip_page_numbers: true
      - label: calamos-sustainable-proxy-voting-policy-as-printed-in-sai
        adviser: "Calamos Advisors LLC"
        adviser_key: "CALAMOS_SUSTAINABLE"
        sai_appendix:
          cik: "0001579881"
          forms: ["485BPOS"]
          since: "2023-01-01"
          start:
            - "Calamos Advisors has adopted its own Proxy Voting Policies and Procedures for Sustainable Investment Strategies"
          end:
            - "DISCLOSURE OF PORTFOLIO HOLDINGS"
          strip_page_numbers: true
```

## 4. Open doubts

- Calamos ETF Trust accession for `adviser_source` is the filing folder, not the main document (main doc for 0001104659-23-104692
  was fetched but its file name was not recorded); fill it in before pasting. Same for the six closed-end folders (the SAI sits in the
  424B5/N-2 main document).
- The sai_appendix start/end markers were read from the text but NOT run through the extractor (no glasshouse commands allowed). The
  ETF Trust end marker "DISCLOSURE OF PORTFOLIO HOLDINGS" was not confirmed (heading case differs: "PROXY VOTING PROCEDURES" with no period in
  the 2023-09-28 SAI). The ETF Trust SAI filing list holds ~35 485BPOS, many single-fund; the SROI-specific rule needs `allow_identical_copies` or a fund filter.
- ETF Trust series launched before 2023-09-28 (S000083148 CEF Income & Arbitrage, S000083476 Nasdaq Equity & Income launched about Aug-Sep 2023)
  have no earlier SAI read; their pre-2023-09-28 meetings stay unlabelled.
- CGAM may give "specific written instructions to the contrary" for SROI and the Antetokounmpo Trust; none known.
- Aksia Alternative Credit: the one N-PX with votes (2025) is a handful of fund/ETF holdings; consider leaving it out of ingest.
- calamos.com has no HTML proxy-voting page (/proxy-voting/ and /legal/proxy-voting/ return 404); the PDF above is the public policy summary.
  The dated full legacy text is an N-CSR exhibit 99.(a)(3)(iii) ("Legacy Policy ... Amended October 9, 2025", e.g.
  https://www.sec.gov/Archives/edgar/data/1396277/000110465925124698/tm2532074d1_ex99-xax3xiii.htm), not read here.
