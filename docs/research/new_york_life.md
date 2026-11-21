# New York Life Investments (New York Life Investment Management LLC) - research for institutions.yaml

Research only, read 2026-11-21 via glasshouse.http (EDGAR, data.sec.gov, web.archive.org CDX) and the honest UA for newyorklifeinvestments.com / nylim.com. Nothing in data/, config/ or the ledger was touched. Scratch work was kept in the session scratchpad.

Brand history (for reading the filings): MainStay (to 2024) -> NYLI (Nov 2024 to mid 2026) -> NYLIM (Aug 2026 SAIs and data.sec.gov names). IndexIQ ETF Trust / IndexIQ Active ETF Trust became the "NYLI/NYLIM ETF Trust" and "Active ETF Trust". IndexIQ Advisors LLC (the ETF trusts' adviser) was reorganised into NYLIM (NYLIM's own ADV: effective 2024-09-12); the first ETF SAI that names NYLIM as the Advisor is the 485BPOS of 2024-08-27.

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

Each trust files two N-PX per season: a FUND VOTING REPORT (carries `ProxyVotingTable.xml`) and a FUND NOTICE REPORT (cover page only; its series are the ones with no votes). Row counts are voteRecord rows streamed with `iter_vote_rows`.

| CIK | Name (data.sec.gov, 2026) | Former names | Type | N-PX with vote table (rows) | Notes |
|---|---|---|---|---|---|
| 787441 | NYLIM FUNDS | The MainStay Funds; New York Life Investments Funds | open-end, 9 series with votes | 2024-08-30 0001021408-24-006080 (3,981); 2025-08-27 0001021408-25-003885 (3,895); 2026-08-19 0001193125-26-356868 (3,582) | 2023-08-29 is legacy HTML |
| 1469192 | NYLIM FUNDS TRUST | MainStay Funds Trust | open-end, 31 series with votes | 2024-08-30 0001021408-24-006732 (23,882); 2025-08-27 0001021408-25-003887 (23,893); 2026-08-19 0001193125-26-356870 (23,660) | |
| 887340 | NYLIM VP FUNDS TRUST | MainStay VP Funds Trust | open-end (insurance), 30 series with votes | 2024-08-30 0001021408-24-006295 (25,256); 2025-08-27 0001021408-25-003881 (26,250); 2026-08-19 0001193125-26-356874 (27,166) | |
| 1415995 | NYLIM ETF Trust | IndexIQ ETF Trust; New York Life Investments ETF Trust | open-end ETF, 20 series with votes | 2024-09-03 0001839882-24-027852 (55,116); 2025-08-20 0001839882-25-045836 (37,037); 2026-08-20 0001999371-26-018287 (33,232) | 0001839882-24-027854 is the notice report |
| 1426439 | NYLIM Active ETF Trust | IndexIQ Active ETF Trust | open-end ETF, 4 series with votes | 2024-09-03 0001839882-24-027846 (2,357); 2025-08-20 0001387131-25-000220 (2,345); 2026-08-20 0001999371-26-018283 (2,405) | |
| 1855066 | NYLIM CBRE Global Infrastructure Megatrends Term Fund | MainStay CBRE Global Infrastructure Megatrends (Term) Fund | closed-end | 2024-08-29 0001021408-24-005812 (725); 2025-08-27 0001021408-25-003880 (706); 2026-08-19 0001193125-26-356875 (867) | no series; equity portfolio |

Series with votes (from the vote tables, `voteSeries` = series id) and the 2024/2025/2026 row counts are in the YAML comments of section 3.

Not recommended / not ingested (same convention as lazard, dodge_cox, global_x):
- NYLIM MacKay Muni Income Opportunities Fund (CIK 1995668, closed-end): vote tables 2 / 23 / 23 rows, all trustee elections of other registered funds (e.g. BlackRock Municipal Income Trust). No operating-company vote; left out.
- NYLIM MacKay DefinedTerm Muni Opportunities Fund (1518557): every N-PX 2023-2026 is a FUND NOTICE REPORT (no table).
- New York Life Investment Management LLC (CIK 1133639; the institution CIK for the entry): own INSTITUTIONAL MANAGER COMBINATION REPORT with a vote table (separate accounts; 2024-08-29 0001085146-24-004428, 2025-08-25 0001085146-25-005477, 2026-08-11 0001085146-26-000583). Also IndexIQ Advisors LLC (1415996, 2024-08-29 0001085146-24-004427, combination report). Not fund registrants; not ingested (as Lazard's 1207017).
- MainStay Capital Management LLC /ADV (1127612): notice reports only. Eclipse Funds Inc (868307, formerly MainStay Institutional Funds; last N-PX 2012), IndexIQ Trust (1427789, last 2019), NYLIM Institutional Funds (1135510, 2004).
- Fund-of-funds series (Conservative/Moderate/Growth/Equity Allocation and the ETF Allocation funds, 1-4 rows in 2024 and 2026, 34-47 in 2025, up to 116 in the VP allocation portfolios): the issuers voted are registered funds (the SAI says the Manager "may vote in accordance with its predetermined or custom voting guidelines" for affiliated underlying funds). They are keyed NYLIM because the SAI says the Manager retained voting authority; whether to count them at all is an ingest-time decision (see doubts).

## 2. Who votes, and under whose policy

The MainStay trusts print one rule plus a fund-by-fund list in the SAI section "PROXY VOTING POLICIES AND PROCEDURES". Earliest 2021-2023 SAI read per registrant (EDGAR filing date of the 485BPOS):

| CIK | Earliest SAI read | Re-read |
|---|---|---|
| 787441 | 0001741773-21-000187 (2021-02-24, c485bpos.htm) | 0001741773-22-000394 (2022-02-25), -23-000227 (2023-02-23), and 2024-2026 editions |
| 1469192 | 0001741773-21-000186 (2021-02-24) | 18 further 485BPOS 2021-03-29 .. 2023-08-28 and 2024-2026 |
| 887340 | 0001741773-21-000834 (2021-04-23) | 0001741773-22-001139 (2022-04-19), -23-001013 (2023-04-14), 2024-2026 |
| 1415995 | 0001104659-21-003095 (2021-01-12, one-fund SAI, "the Board has delegated ... to the Advisor"); first multi-fund SAI 0001104659-21-111027 (2021-08-30) | 2022-02-28, 2022-08-29, 2023-08-28 (0001104659-23-095581), 2024-08-27 (0001999371-24-010693), 2025, 2026 |
| 1426439 | 0001104659-21-082629 (2021-06-17); multi-fund 0001104659-21-111017 (2021-08-30) | Winslow SAI part in 0001104659-23-095604 (2023-08-28); CBRE in 0001104659-23-050257 (2023-04-26) |
| 1855066 | N-2 0001104659-21-051250 (2021-04-16; the SAI is part B of the N-2) | |

### 2.1 The Manager rule (identical in 787441, 1469192, 887340 and in the closed-end N-2s)

> "The Board has adopted Proxy Voting Policies and Procedures for the Funds that delegate all responsibility for voting proxies received relating to the Funds' portfolio securities to New York Life Investments, subject to the oversight of the Board. The Manager has adopted its own Proxy Voting Policies and Procedures in order to assure that proxies voted on behalf of the Funds are voted in the best interests of the Funds and their shareholders. Where a Fund has retained the services of a Subadvisor to provide day-to-day portfolio management for the Fund, the Manager may delegate proxy voting authority to the Subadvisor; provided that, as specified in the Manager's Proxy Voting Policies and Procedures, the Subadvisor either (1) follows the Manager's Proxy Voting Policy and the Funds' Procedures; or (2) has demonstrated that its proxy voting policies and procedures are consistent with the Manager's Proxy Voting Policies and Procedures or are otherwise implemented in the best interests of the Manager's clients and appear to comply with governing regulations."  (0001741773-21-000187; "Portfolios" in 887340)

So the Manager's policy is the default, and the SAI then lists, per fund, who it actually delegated to (2.2). The Manager's own guidelines: "The Manager has selected ISS to assist it in researching and voting proxies ... The Manager has adopted ISS's Sustainability proxy voting guidelines with respect to recurring issues" (2021; "Benchmark" guidelines in the 2026 SAIs). The funds the Manager keeps itself:

> "The Manager has retained voting authority for the MainStay Balanced Fund (portion), MainStay Conservative Allocation Fund, MainStay Conservative ETF Allocation Fund, MainStay Defensive ETF Allocation Fund, MainStay Equity Allocation Fund, MainStay Equity ETF Allocation Fund, MainStay Growth Allocation Fund, MainStay Growth ETF Allocation Fund, MainStay Moderate Allocation Fund and MainStay Moderate ETF Allocation Fund."  (0001741773-21-000187 and -000186; ESG Multi-Asset Allocation added from 0001741773-21-002934 (2021-09-30); "NYLI S&P 500 Index Fund" added from 0001741773-24-003668 (2024-08-28); VP: "the MainStay VP Asset Allocation Portfolios and a portion of the MainStay VP Balanced Portfolio", 0001741773-21-000834, plus "NYLI VP Hedge Multi-Strategy Portfolio, the NYLI VP S&P 500 Index Portfolio" from 0001741773-24-004633 (2024-12-18))

### 2.2 Delegations named in the SAIs (all quoted: "The Manager has delegated proxy[-]voting authority to the Fund[s]' Subadvisor[s], X.")

Affiliate flag = Form N-CEN `isSubAdviserAffiliated` (read for every N-CEN 2021-2026).

| Sub-adviser | N-CEN affiliated | Policy printed in SAI | Series (2024-2026 votes) | First SAI that names the series |
|---|---|---|---|---|
| MacKay Shields LLC | Y | full policy in 2021-22 SAIs ("1. Introduction MacKay Shields LLC ... has adopted these Proxy Voting Policy and Procedures"); 2,094-char summary from 2022-08-29 ("MacKay Shields has adopted Proxy-Voting Policies and Procedures designed to make sure ... ISS") | the MacKay series and Income Builder fixed-income portion | 2021-02-24 (787441, 1469192), 2021-04-23 (887340) |
| NYL Investors LLC | Y | summary + website PDF | Floating Rate; Balanced (fixed-income portion) | same dates |
| Candriam (Belgium / Luxembourg to 2022) | Y | summary (own proprietary policy, ISS executes) | EM Equity (+ Debt, no votes) | same dates |
| IndexIQ Advisors LLC | Y | "IndexIQ Advisors exercises its proxy voting rights ..." | S&P 500 Index Fund / VP, VP Hedge Multi-Strategy | 1469192 2022-08-29, 887340 2023-04-14 |
| Ausbil Investment Management | affiliate by SAI ("an indirect majority-owned subsidiary of New York Life") | summary | NYLI International Small-Mid Cap Equity ETF | 0001999371-26-009522 (2026-04-30) |
| Epoch Investment Partners | N (the 2026 SAI says "TD Epoch") | summary | Epoch funds, Income Builder equity portion | 2021-02-24 / 2021-04-23 |
| Winslow Capital Management | N | summary | Winslow funds, VP Winslow, Winslow ETFs | 2021-02-24 (787441); 2021-04-23 (VP); Active ETF 2023-08-28 |
| Wellington Management | N | summary | WMC funds, VP Wellington, Balanced equity portion | 1469192 2021-03-29 (0001741773-21-000725); 787441 2022-02-25; VP 2021-04-23 |
| CBRE Clarion / CBRE Investment Management | N | summary | CBRE funds, VP CBRE, Active ETF CBRE Real Assets, closed-end | 2021-02-24 / 2021-04-23 / N-2 2021-04-16 / ETF 2023-04-26 |
| Cushing (Asset Management LP) | N | summary | Cushing MLP Premier | 2021-02-24 unnamed ("the Fund's Subadvisor"); named from 2022-08-29 |
| Fiera Capital; PineStone | N | summary | Fiera SMID Growth; PineStone Global/International/US | 2023-04-19; 2023-06-15 (VP International: 2024-04-19) |
| Janus Henderson, FIAM, American Century (T. Rowe Price before), Newton (Mellon before), Brown Advisory + SBH, Dimensional (from 2024-12-18), Schroders (from 2024-12-18), MFS, Newton Technology Growth | N | summary (VP SAI only) | VP portfolios | 2021-04-23 unless noted; Dimensional / Schroders / MFS / Newton Tech Growth 2024-12-18 |

The three Epoch, Winslow and Wellington answers contradict the premise that they are affiliates: N-CEN flags all three N and the SAI calls Epoch "TD Epoch". They are therefore EXTERNAL, not own-policy keys. (If the maintainer prefers to archive their printed summaries, a key per firm works the same way as MANULIFE_IM; the summaries are not policy documents and are not proposed.)

Two further statements matter:
- S&P 500 Index Fund / VP: MacKay Shields until about 2022 (VP 2023), then IndexIQ Advisors, then the Manager: "NYLI S&P 500 Index Fund" is in the retained list from the 2024-08-28 SAI (VP from 2024-12-18), and the Form N-CEN of 2025 lists no sub-adviser.
- ETF trusts: "The Board has delegated responsibility for decisions regarding proxy voting for securities held by each Fund to the Advisor. The Advisor will vote such proxies in accordance with its proxy policies and procedures" (IndexIQ ETF Trust; Advisor = IndexIQ Advisors LLC until the 2023-08-28 SAI, New York Life Investment Management LLC from the 2024-08-27 SAI). Active ETF Trust: "The Advisor has delegated proxy-voting authority to each Fund's Subadvisor" with Appendix A summaries (MacKay Shields, NYL Investors, Winslow Capital, CBRE, Ausbil).
- Closed-end CBRE fund, N-2 2021-04-16: "Subadvisor Proxy Voting Guidelines. The Manager has delegated proxy-voting authority to the Fund's Subadvisor, CBRE Clarion."

### 2.3 Gaps in the SAI text (why some series are UNRESOLVED)

- NYLI WMC Value Fund (S000006906, 787441) and NYLI WMC Small Companies Fund (S000036715, 1469192) are never named in any SAI: the Wellington heading in every edition lists "WMC Enduring Capital, WMC Growth, WMC International Research Equity and WMC Growth Funds" (the repeated "WMC Growth" is evidently a typo; the 2026-08-24 edition drops the last one). N-CEN says Wellington, but the SAI does not say who votes, so UNRESOLVED.
- Income Builder (S000006900, VP S000009444) and Balanced (S000036714, VP S000009437) are split: Epoch / Wellington equity portion, MacKay / NYL Investors fixed-income portion, Manager-retained portion. One series, several voters, not separable in the vote table: UNRESOLVED.

## 3. Proposed YAML (paste under `institutions:`)

`<date>` placeholders are the commit date. `until` is the day before the next window starts (global_x convention). Windows at every SAI-derived boundary: `from` = EDGAR filing date of the first SAI naming the series under that voter. All N-CEN reads were used only to identify and classify the sub-adviser, never for a date.

```yaml
  new_york_life:
    display_name: "New York Life Investments (New York Life Investment Management LLC) and its subadvisers"
    short_name: "New York Life Investments"
    cik: "0001133639"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "New York Life Investment Management LLC (NYLIM, 'New York Life Investments'), New York NY (CIK 1133639, a New York Life Insurance Company subsidiary; also the 13-F filer and an institutional-manager N-PX filer for separate accounts, not ingested). It manages the MainStay (now NYLI / NYLIM) mutual funds, the MainStay VP insurance trust, the IndexIQ ETFs (IndexIQ Advisors LLC, merged into NYLIM 2024-09-12) and the closed-end CBRE fund. Six registrants that file N-PX vote tables with operating-company votes are ingested: NYLIM Funds (CIK 787441, formerly The MainStay Funds), NYLIM Funds Trust (1469192), NYLIM VP Funds Trust (887340), NYLIM ETF Trust (1415995, formerly IndexIQ ETF Trust), NYLIM Active ETF Trust (1426439, formerly IndexIQ Active ETF Trust) and NYLIM CBRE Global Infrastructure Megatrends Term Fund (1855066). Every open-end SAI says the Board delegated all proxy voting to the Manager, which 'has adopted its own Proxy Voting Policies and Procedures' and 'may delegate proxy voting authority to the Subadvisor'; the SAI then names, fund by fund, the subadvisers it delegated to (affiliates MacKay Shields, NYL Investors, Candriam, IndexIQ Advisors and Ausbil vote under their OWN policies: MACKAY_SHIELDS, NYL_INVESTORS, CANDRIAM, INDEXIQ, AUSBIL; unaffiliated Epoch, Winslow, Wellington, CBRE, Cushing, Fiera, PineStone, Janus Henderson, FIAM, American Century, Newton, Brown Advisory, Segall Bryant & Hamill, Dimensional, Schroders and MFS: EXTERNAL) and the funds the Manager kept (NYLIM). aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. Six registrants (see notes). Not ingested: NYLIM MacKay Muni Income Opportunities Fund (1995668; votes are other registered funds' trustee elections), NYLIM MacKay DefinedTerm Muni Opportunities Fund (1518557; notice reports only), NYLIM's own institutional-manager N-PX (1133639) and IndexIQ Advisors LLC (1415996), MainStay Capital Management (1127612, notice), Eclipse Funds (868307), IndexIQ Trust (1427789), and the legacy-HTML N-PX before 2024.
      # Series with no rule below have no operating-company votes in the 2024-2026 vote tables (or are listed under 'no rule'). Vote rows 2024 / 2025 / 2026 in the comments.
      - cik: "787441"
        adviser: "New York Life Investment Management LLC (the Manager); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/787441/000174177321000187/c485bpos.htm"  # 485BPOS (SAI) filed 2021-02-24 (0001741773-21-000187), 'PROXY VOTING POLICIES AND PROCEDURES'
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting Policies and Procedures': 'The Board has adopted Proxy Voting Policies and Procedures for the Funds that delegate all responsibility for voting proxies ... to New York Life Investments ... The Manager has adopted its own Proxy Voting Policies and Procedures ... the Manager may delegate proxy voting authority to the Subadvisor'; then per fund 'The Manager has delegated proxy-voting authority to the Fund's Subadvisor, X' (MacKay Shields, NYL Investors, Epoch, Winslow Capital, Wellington from 2022-02-25) and 'The Manager has retained voting authority for the MainStay Balanced Fund (portion), ...Allocation Funds' (earliest SAI read 2021-02-24, 0001741773-21-000187; same structure through the SAI of 2026-02-26). No registrant-wide key: each series is keyed by the voter the SAI names for it (earliest naming SAI date). WMC Value is never named: UNRESOLVED."
        series_adviser:
          S000006894: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay Strategic Bond Fund (21 / 23 / -)
          S000006896: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay High Yield Corporate Bond Fund (56 / 88 / 65)
          S000006898: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay Tax Free Bond Fund (6 / 12 / 3)
          S000006899: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay Convertible Fund (24 / 15 / 24)
          S000006900: [{key: UNRESOLVED, from: "2021-02-24"}]   # Income Builder Fund: Epoch equity portion + MacKay fixed-income portion (two voters in one series) (1,876 / 1,866 / 1,751)
          S000006902: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay International Equity Fund (78 / - / -)
          S000006903: [{key: EXTERNAL, from: "2022-02-25"}]   # WMC Enduring Capital Fund: Wellington (417 / 398 / 342)
          S000006905: [{key: EXTERNAL, from: "2021-02-24"}]   # Winslow Large Cap Growth Fund: Winslow Capital (616 / 599 / 580)
          S000006906: [{key: UNRESOLVED, from: "2021-02-24"}]   # WMC Value Fund: never named in the SAI proxy section; N-CEN says Wellington (887 / 894 / 817)
        name: "NYLIM FUNDS"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1469192"
        adviser: "New York Life Investment Management LLC (the Manager); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1469192/000174177321000186/c485bpos.htm"  # 485BPOS (SAI) filed 2021-02-24 (0001741773-21-000186)
        adviser_verified: "<date>"
        voting_note: "Same SAI wording as the sibling trust (earliest SAI read 2021-02-24, 0001741773-21-000186; Wellington first named 2021-03-29, 0001741773-21-000725; Cushing named 2022-08-29, before that 'the Fund's Subadvisor'; Fiera 2023-04-19, 0001104659-23-046991; PineStone 2023-06-15, 0001104659-23-071532). S&P 500 Index Fund: MacKay Shields until the 2022-03-29 SAI, IndexIQ Advisors from 2022-08-29 (0001741773-22-002923) to the 2024-05-01 SAI, Manager-retained from 2024-08-28 (0001741773-24-003668); the gaps between SAIs are UNRESOLVED. Balanced (three voters) and WMC Small Companies (not named) UNRESOLVED."
        series_adviser:
          S000026784: [{key: EXTERNAL, from: "2021-02-24"}]   # Epoch U.S. Equity Yield Fund (1,500 / 1,367 / 1,402)
          S000026786: [{key: EXTERNAL, from: "2021-02-24"}]   # Epoch Global Equity Yield Fund (1,866 / 1,856 / 1,741)
          S000028227: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay High Yield Muni Bond Fund (52 / 90 / 111)
          S000028522: [{key: EXTERNAL, from: "2021-02-24"}]   # Epoch International Choice Fund (698 / 689 / 716)
          S000028525: [{key: MACKAY_SHIELDS, from: "2021-02-24", until: "2022-03-29"}, {key: UNRESOLVED, from: "2022-03-30", until: "2022-08-28"}, {key: INDEXIQ, from: "2022-08-29", until: "2024-05-01"}, {key: UNRESOLVED, from: "2024-05-02", until: "2024-08-27"}, {key: NYLIM, from: "2024-08-28"}]   # S&P 500 Index Fund (7,016 / 6,694 / 6,593)
          S000028529: [{key: NYL_INVESTORS, from: "2021-02-24"}]   # Floating Rate Fund (10 / 10 / 14)
          S000028532: [{key: NYLIM, from: "2021-02-24"}]   # Conservative Allocation Fund (fund of funds; Manager retained) (1 / - / 4)
          S000028533: [{key: NYLIM, from: "2021-02-24"}]   # Moderate Allocation Fund (1 / - / 4)
          S000028534: [{key: NYLIM, from: "2021-02-24"}]   # Growth Allocation Fund (1 / - / 4)
          S000028535: [{key: NYLIM, from: "2021-02-24"}]   # Equity Allocation Fund (1 / - / 4)
          S000028537: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay Total Return Bond Fund (10 / 10 / 14)
          S000028542: [{key: EXTERNAL, from: "2021-03-29"}]   # WMC International Research Equity Fund: Wellington (3,083 / 3,188 / 3,584)
          S000036714: [{key: UNRESOLVED, from: "2021-02-24"}]   # Balanced Fund: Wellington equity + NYL Investors fixed income + Manager portion (887 / 894 / 817)
          S000036715: [{key: UNRESOLVED, from: "2021-02-24"}]   # WMC Small Companies Fund: not named in the SAI proxy section (1,007 / 1,140 / 1,057)
          S000036992: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay New York Muni Fund (11 / 26 / 32)
          S000039301: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay Short Duration High Income Fund (37 / 69 / 14)
          S000039358: [{key: EXTERNAL, from: "2021-03-29"}]   # WMC Growth Fund: Wellington (838 / 648 / 640)
          S000039903: [{key: MACKAY_SHIELDS, from: "2021-02-24"}]   # MacKay California Muni Fund (- / 5 / 5)
          S000045768: [{key: EXTERNAL, from: "2021-02-24"}]   # Cushing MLP Premier Fund: Cushing, named only from 2022-08-29; N-CEN 2021-02-10 already lists it unaffiliated (212 / 252 / 214)
          S000054257: [{key: EXTERNAL, from: "2021-02-24"}]   # Epoch Capital Growth Fund (1,549 / 1,566 / 1,522)
          S000059215: [{key: CANDRIAM, from: "2021-02-24"}]   # Candriam Emerging Markets Equity Fund (1,568 / 1,817 / 1,748)
          S000067318: [{key: EXTERNAL, from: "2021-02-24"}]   # CBRE Global Infrastructure Fund: CBRE Clarion (803 / 669 / 735)
          S000067319: [{key: EXTERNAL, from: "2021-02-24"}]   # CBRE Real Estate Fund (467 / 514 / 469)
          S000068835: [{key: NYLIM, from: "2021-02-24"}]   # Conservative ETF Allocation Fund (- / 47 / 4)
          S000068837: [{key: NYLIM, from: "2021-02-24"}]   # Equity ETF Allocation Fund (- / 34 / 4)
          S000068838: [{key: NYLIM, from: "2021-02-24"}]   # Moderate ETF Allocation Fund (- / 47 / 4)
          S000068839: [{key: NYLIM, from: "2021-02-24"}]   # Growth ETF Allocation Fund (- / 47 / 4)
          S000073437: [{key: NYLIM, from: "2021-09-30", until: "2024-02-25"}, {key: UNRESOLVED, from: "2024-02-26"}]   # ESG Multi-Asset Allocation Fund (named as retained 2021-09-30 to the 2023-08-28 SAI; not in 2024-02-26) (72 / - / -)
          S000080473: [{key: EXTERNAL, from: "2023-04-19"}]   # Fiera SMID Growth Fund (627 / 685 / 756)
          S000081082: [{key: EXTERNAL, from: "2023-06-15"}]   # PineStone Global Equity Fund (530 / 502 / 430)
          S000081083: [{key: EXTERNAL, from: "2023-06-15"}]   # PineStone International Equity Fund (658 / 648 / 640)
          S000081084: [{key: EXTERNAL, from: "2023-06-15"}]   # PineStone U.S. Equity Fund (377 / 379 / 374)
        name: "NYLIM FUNDS TRUST"
        validated: "<date>"
      - cik: "887340"
        adviser: "New York Life Investment Management LLC (the Manager); subadvisers vote per portfolio"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/887340/000174177321000834/c485bpos.htm"  # 485BPOS (SAI) filed 2021-04-23 (0001741773-21-000834)
        adviser_verified: "<date>"
        voting_note: "Same SAI structure ('Portfolios'; earliest SAI read 2021-04-23, 0001741773-21-000834; re-read 2022-04-19, 2023-04-14 and 2024-2026): the Manager delegates to the named Subadvisors and 'has retained voting authority for the MainStay VP Asset Allocation Portfolios and a portion of the MainStay VP Balanced Portfolio'. S&P 500 Index Portfolio: MacKay Shields until the 2022-04-19 SAI, IndexIQ Advisors 2023-04-14 to 2024-04-19, Manager-retained from 2024-12-18 (0001741773-24-004633); gaps UNRESOLVED. Hedge Multi-Strategy: IndexIQ Advisors 2023-04-14 (first named) to 2024-04-19, Manager from 2024-12-18."
        series_adviser:
          S000009425: [{key: EXTERNAL, from: "2021-04-23"}]   # Wellington Growth Portfolio (838 / 648 / 640)
          S000009427: [{key: MACKAY_SHIELDS, from: "2021-04-23"}]   # MacKay Convertible Portfolio (24 / 15 / 24)
          S000009429: [{key: EXTERNAL, from: "2021-04-23"}]   # Epoch U.S. Equity Yield Portfolio (1,500 / 1,367 / 1,402)
          S000009430: [{key: EXTERNAL, from: "2021-04-23"}]   # Winslow Large Cap Growth Portfolio (616 / 599 / 580)
          S000009432: [{key: EXTERNAL, from: "2021-04-23"}]   # Mid Cap portfolio: Wellington Mid Cap (SAIs to 2024-04-19), Schroders (named 2024-12-18): both unaffiliated (1,482 / 761 / 735)
          S000009436: [{key: EXTERNAL, from: "2021-04-23"}]   # Dimensional U.S. Equity Portfolio: Wellington U.S. Equity before, Dimensional named 2024-12-18 (1,066 / 1,295 / 1,591)
          S000009437: [{key: UNRESOLVED, from: "2021-04-23"}]   # Balanced Portfolio: Wellington + NYL Investors + Manager portion (887 / 894 / 817)
          S000009438: [{key: NYL_INVESTORS, from: "2021-04-23"}]   # Floating Rate Portfolio (10 / 10 / 14)
          S000009439: [{key: NYLIM, from: "2021-04-23"}]   # Conservative Allocation Portfolio (- / - / 112)
          S000009440: [{key: NYLIM, from: "2021-04-23"}]   # Equity Allocation Portfolio (- / - / 84)
          S000009441: [{key: NYLIM, from: "2021-04-23"}]   # Moderate Allocation Portfolio (- / - / 112)
          S000009442: [{key: NYLIM, from: "2021-04-23"}]   # Growth Allocation Portfolio (- / - / 116)
          S000009443: [{key: MACKAY_SHIELDS, from: "2021-04-23", until: "2022-04-19"}, {key: UNRESOLVED, from: "2022-04-20", until: "2023-04-13"}, {key: INDEXIQ, from: "2023-04-14", until: "2024-04-19"}, {key: UNRESOLVED, from: "2024-04-20", until: "2024-12-17"}, {key: NYLIM, from: "2024-12-18"}]   # S&P 500 Index Portfolio (7,016 / 6,694 / 6,593)
          S000009444: [{key: UNRESOLVED, from: "2021-04-23"}]   # Income Builder Portfolio: Epoch equity + MacKay fixed income (1,876 / 1,856 / 1,741)
          S000009448: [{key: MACKAY_SHIELDS, from: "2021-04-23"}]   # MacKay High Yield Corporate Bond Portfolio (46 / 59 / 41)
          S000009449: [{key: EXTERNAL, from: "2024-04-19"}]   # PineStone International Equity Portfolio: first named 2024-04-19 (691 / 600 / 599)
          S000031904: [{key: MACKAY_SHIELDS, from: "2021-04-23"}]   # MacKay Strategic Bond Portfolio (- / - / 4)
          S000033925: [{key: CANDRIAM, from: "2021-04-23"}]   # Candriam Emerging Markets Equity Portfolio (1,568 / 1,817 / 1,748)
          S000033926: [{key: EXTERNAL, from: "2021-04-23"}]   # Small Cap Growth Portfolio: Brown Advisory + Segall Bryant & Hamill (1,176 / 1,195 / 1,009)
          S000033927: [{key: EXTERNAL, from: "2021-04-23"}]   # Natural Resources Portfolio: Mellon, then Newton (611 / 514 / 653)
          S000033928: [{key: EXTERNAL, from: "2021-04-23"}]   # Janus Henderson Balanced Portfolio (977 / 1,017 / 975)
          S000033929: [{key: EXTERNAL, from: "2021-04-23"}]   # Fidelity Institutional AM Utilities Portfolio: FIAM (407 / 426 / 421)
          S000033930: [{key: EXTERNAL, from: "2021-04-23"}]   # American Century Equity Portfolio (T. Rowe Price Equity Income before 2022-04-19) (1,558 / 1,395 / 1,371)
          S000033931: [{key: EXTERNAL, from: "2021-04-23"}]   # PIMCO Real Return Portfolio (- / - / 4)
          S000049057: [{key: EXTERNAL, from: "2021-04-23"}]   # CBRE Global Infrastructure Portfolio (803 / 669 / 735)
          S000053035: [{key: EXTERNAL, from: "2021-04-23"}]   # Wellington Small Cap Portfolio (2,104 / 2,187 / 2,175)
          S000063068: [{key: INDEXIQ, from: "2023-04-14", until: "2024-04-19"}, {key: UNRESOLVED, from: "2024-04-20", until: "2024-12-17"}, {key: NYLIM, from: "2024-12-18"}]   # Hedge Multi-Strategy Portfolio (- / 108 / 10)
          S000089397: [{key: EXTERNAL, from: "2024-12-18"}]   # MFS Investors Trust Portfolio (- / 692 / 1,000)
          S000089398: [{key: EXTERNAL, from: "2024-12-18"}]   # MFS Research Portfolio (- / 1,133 / 1,442)
          S000089399: [{key: EXTERNAL, from: "2024-12-18"}]   # Newton Technology Growth Portfolio (- / 299 / 418)
        name: "NYLIM VP FUNDS TRUST"
        validated: "<date>"
      - cik: "1415995"
        adviser: "IndexIQ Advisors LLC, then New York Life Investment Management LLC (the Advisor); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1415995/000110465921111027/tm2123983-5_485bpos.htm"  # 485BPOS (SAI) filed 2021-08-30 (0001104659-21-111027), 'PROXY VOTING POLICIES'
        adviser_verified: "<date>"
        voting_note: "SAI 'PROXY VOTING POLICIES': 'the Board has delegated responsibility for decisions regarding proxy voting for securities held by each Fund to the Advisor. The Advisor will vote such proxies in accordance with its proxy policies and procedures, a summary of which is included in Appendix A' (one-fund SAI 2021-01-12, 0001104659-21-003095; multi-fund SAI 2021-08-30; same through 2023-08-28, 0001104659-23-095581). Advisor = IndexIQ Advisors LLC until the 2023-08-28 SAI; from the SAI of 2024-08-27 (0001999371-24-010693) the Advisor is New York Life Investment Management LLC (IndexIQ Advisors was reorganised into NYLIM, effective 2024-09-12 per NYLIM's ADV). Every Form N-CEN 2021-2026 lists no sub-adviser for any series."
        adviser_key_history: [{key: INDEXIQ, from: "2021-08-30", until: "2024-08-26"}, {key: NYLIM, from: "2024-08-27"}]
        # Series with votes (rows 2024 / 2025 / 2026): S000023661 Hedge Multi-Strategy Tracker, S000025928 IQ Real Return, S000025931 Merger Arbitrage, S000025932 IQ Global Resources, S000032652 CBRE NextGen Real Estate, S000050195 FTSE International Equity Currency Neutral (13,105 / 13,168 / 12,963), S000054231 Candriam International Equity, S000054232 Candriam U.S. Large Cap Equity, S000057680/57681 IQ U.S. Large/Small Cap, S000062011 500 International, S000070449 Healthy Hearts, S000071178 Engender Equality, S000073838 Clean Oceans, S000073839 Cleaner Transport, S000074744/74745/74746 R&D Leaders, S000077598 Candriam U.S. Mid Cap Equity. Advisor-voted: no series rule. Index-tracking ESG funds vote under the ISS SRI guidelines, the others under Sustainability guidelines (one policy summary).
        name: "NYLIM ETF Trust"
        validated: "<date>"
      - cik: "1426439"
        adviser: "IndexIQ Advisors LLC, then New York Life Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1426439/000110465923095604/tm2319108d1_485bpos.htm"  # 485BPOS (SAI) filed 2023-08-28 (0001104659-23-095604)
        adviser_verified: "<date>"
        voting_note: "SAI 'PROXY VOTING POLICIES': 'The Board has delegated responsibility for decisions regarding proxy voting for securities held by each series of the Trust to the Advisor. Where a Fund has retained the services of a Subadvisor ... the Advisor may delegate proxy-voting authority to the Subadvisor ... The Advisor has delegated proxy-voting authority to each Fund's Subadvisor' (earliest SAI read 2021-06-17, 0001104659-21-082629). Named: Winslow Capital (0001104659-23-095604, 2023-08-28; 'The Advisor has delegated proxy-voting authority to the Fund's Subadvisor, Winslow Capital'), CBRE (0001104659-23-050257, 2023-04-26), Ausbil (0001999371-26-009522, 2026-04-30)."
        series_adviser:
          S000075560: [{key: EXTERNAL, from: "2023-08-28"}]   # Winslow Large Cap Growth ETF (616 / 599 / 495)
          S000075561: [{key: EXTERNAL, from: "2023-08-28"}]   # Winslow Focused Large Cap Growth ETF (374 / 419 / 394)
          S000079855: [{key: EXTERNAL, from: "2023-04-26"}]   # CBRE Real Assets ETF (1,367 / 1,327 / 1,467)
          S000101653: [{key: AUSBIL, from: "2026-04-30"}]   # International Small-Mid Cap Equity ETF (- / - / 49)
        name: "NYLIM Active ETF Trust"
        validated: "<date>"
      - cik: "1855066"
        adviser: "New York Life Investment Management LLC (the Manager); CBRE Investment Management (subadviser, delegated)"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1855066/000110465921051250/tm2112316d1_n2.htm"  # N-2 filed 2021-04-16 (0001104659-21-051250), 'Subadvisor Proxy Voting Guidelines'
        adviser_verified: "<date>"
        voting_note: "N-2 SAI: 'Subadvisor Proxy Voting Guidelines. The Manager has delegated proxy-voting authority to the Fund's Subadvisor, CBRE Clarion.' (earliest 2021 filing, 2021-04-16; N-2/A 2021-09-07, 2021-09-27, 2021-10-26). Unaffiliated (N-CEN 2022-2026)."
        adviser_key_history: [{key: EXTERNAL, from: "2021-04-16"}]
        name: "NYLIM CBRE Global Infrastructure Megatrends Term Fund"
        validated: "<date>"
    voting_scope_notes:
      - "Keyed per series from the EDGAR filing date of the first SAI that names the series under that voter; earlier meetings stay unlabelled. The Manager's rule is a default: 'the Manager may delegate proxy voting authority to the Subadvisor'; the SAI's fund-by-fund lists say who it did delegate to. Sub-adviser identity and the affiliation flag come from Form N-CEN; dates never do."
      - "Affiliates voting under their own policy: MacKay Shields, NYL Investors, Candriam, IndexIQ Advisors, Ausbil. EXTERNAL (unaffiliated, no archived policy): Epoch ('TD Epoch'), Winslow, Wellington, CBRE, Cushing, Fiera, PineStone, Janus Henderson, FIAM, American Century, Newton, Brown Advisory, Segall Bryant & Hamill, Dimensional, Schroders, MFS, T. Rowe Price, Mellon, PIMCO, Markston."
      - "UNRESOLVED: series with more than one voter in one vote table (Income Builder, Balanced), series the SAI never names (WMC Value, WMC Small Companies) and the gaps between SAIs when the voter changes (S&P 500 Index Fund / Portfolio, Hedge Multi-Strategy, ESG Multi-Asset)."
      - "Not ingested (left out): NYLIM MacKay Muni Income Opportunities Fund (1995668, votes are trustee elections of other registered funds), NYLIM MacKay DefinedTerm Muni Opportunities Fund (1518557, notice reports only), NYLIM's own institutional-manager N-PX (1133639) and IndexIQ Advisors LLC (1415996), and the legacy-HTML N-PX before 2024 (not ingested without --legacy). The fund-of-funds allocation series vote underlying registered funds; the Manager retained them (NYLIM) but they are not operating-company votes."
      - "Policy text: newyorklifeinvestments.com redirects to nylim.com and answers honest clients (robots.txt allows everything except /assets/noindex). Four policies are archived: NYLIM's own PDF (website label plus the SAI's 'Manager's Proxy Voting Guidelines', which are different documents and never mixed), NYL Investors' PDF, IndexIQ Advisors' PDF (now 404; Wayback only) and the MacKay Shields summary printed in the SAI. Candriam, Ausbil and the unaffiliated advisers' summaries are printed in the SAI but not proposed as labels."
    commitments:
      # NYLIM's own policy (website). 200 application/pdf, 10 pages, ModDate 2026-04-02, last-modified 2026-07-07; the www.newyorklifeinvestments.com URL redirects to nylim.com. Wayback holds this URL: 2021-05-12 (200), 2022-05-12, 2023-03-14, 2023-12-16, 2024-09-20, 2024-10-09, 2025-08-16; the nylim.com host 2026-03-08 and 2026-08-20. The 2021-05-12 capture reads 'NEW YORK LIFE INVESTMENT MANAGEMENT LLC PROXY VOTING POLICY AND PROCEDURES ... ("New York Life Investments") (the "Adviser")'.
      - label: nylim-proxy-voting-policy-and-procedures
        url: "https://www.newyorklifeinvestments.com/assets/documents/proxies/nylim-proxy-voting-procedures.pdf"
        adviser: "New York Life Investment Management LLC"
        adviser_key: "NYLIM"
        former_urls:
          - "https://www.nylim.com/assets/documents/proxies/nylim-proxy-voting-procedures.pdf"
      # NYL Investors LLC (fixed-income affiliate). 200 application/pdf, 12 pages, ModDate 2026-02-03. Wayback: newyorklifeinvestments.com host 2023-12-16 (200, 11 pages, ModDate 2023-02-14), nylim.com host 2026-03-14, 2026-08-20.
      - label: nyl-investors-proxy-voting-policy-and-procedures
        url: "https://www.newyorklifeinvestments.com/assets/documents/proxies/nyl-investors-proxy-voting-policy-and-procedures.pdf"
        adviser: "NYL Investors LLC"
        adviser_key: "NYL_INVESTORS"
        former_urls:
          - "https://www.nylim.com/assets/documents/proxies/nyl-investors-proxy-voting-policy-and-procedures.pdf"
      # IndexIQ Advisors LLC. The canonical URL now answers 404 (definitive: the adviser was merged into NYLIM 2024-09-12); Wayback 200 capture 2021-05-12 (10 pages, ModDate 2021-03-15, 'IndexIQ Advisors LLC Proxy Voting Policy and Procedures ... It is IndexIQ's policy that where proxy voting authority has been delegated to the Adviser by clients').
      - label: indexiq-proxy-voting-policy-and-procedures
        url: "https://www.newyorklifeinvestments.com/assets/documents/proxies/indexiq-proxy-voting-procedures.pdf"
        adviser: "IndexIQ Advisors LLC"
        adviser_key: "INDEXIQ"
      # The Manager's own text as printed in the SAI: from 'PROXY VOTING POLICIES AND PROCEDURES It is the policy of the ...' to the start of the subadviser summaries. One label per trust (Funds / Portfolios wording). The list of funds the Manager retained is removed (it changes every year), and standalone 3-digit page numbers printed inside the text. Verified on 7 SAIs of 787441, 34 of 1469192 and 7 of 887340 (start unique, end found in every full SAI; the three 2021-03-22 / 2021-03-29 prospectus filings without the section return nothing).
      - label: nylim-proxy-voting-policy-as-printed-in-sai-funds
        adviser: "New York Life Investment Management LLC"
        adviser_key: "NYLIM"
        sai_appendix:
          cik: "0000787441"
          forms: ["485BPOS"]
          since: "2021-01-01"
          start:
            - "PROXY VOTING POLICIES AND PROCEDURES It is the policy of the"
          end:
            - "Subadvisor Proxy Voting Guidelines."
          strip_patterns:
            - 'The Manager has retained voting authority for [^.]*\.'
            - '(?<=[A-Za-z.,"”’)]) \d{3}(?= [A-Za-z“"''])'
      - label: nylim-proxy-voting-policy-as-printed-in-sai-trust
        adviser: "New York Life Investment Management LLC"
        adviser_key: "NYLIM"
        sai_appendix:
          cik: "0001469192"
          forms: ["485BPOS"]
          since: "2021-01-01"
          start:
            - "PROXY VOTING POLICIES AND PROCEDURES It is the policy of the"
          end:
            - "Subadvisor Proxy Voting Guidelines."
          strip_patterns:
            - 'The Manager has retained voting authority for [^.]*\.'
            - '(?<=[A-Za-z.,"”’)]) \d{3}(?= [A-Za-z“"''])'
      - label: nylim-proxy-voting-policy-as-printed-in-sai-vp
        adviser: "New York Life Investment Management LLC"
        adviser_key: "NYLIM"
        sai_appendix:
          cik: "0000887340"
          forms: ["485BPOS"]
          since: "2021-01-01"
          start:
            - "PROXY VOTING POLICIES AND PROCEDURES It is the policy of the"
          end:
            - "Subadvisor Proxy Voting Guidelines."
          strip_patterns:
            - 'The Manager has retained voting authority for [^.]*\.'
            - '(?<=[A-Za-z.,"”’)]) \d{3}(?= [A-Za-z“"''])'
      # MacKay Shields summary (2,094 characters, identical text in 33 SAIs of 1469192 from 2022-08-29 and in 787441 from 2023-02-23). The long 2021-22 text ('1. Introduction MacKay Shields LLC ...') is a different edition and is not captured by this label.
      - label: mackay-shields-proxy-voting-summary-as-printed-in-sai-trust
        adviser: "MacKay Shields LLC"
        adviser_key: "MACKAY_SHIELDS"
        sai_appendix:
          cik: "0001469192"
          forms: ["485BPOS"]
          since: "2022-08-01"
          start:
            - "MacKay Shields has adopted Proxy-Voting Policies and Procedures designed to make sure that where clients have delegated proxy-voting authority to MacKay Shields"
          end:
            - "MainStay Balanced (fixed-income portion)"
            - "NYLI Balanced (fixed-income portion)"
            - "NYLIM Balanced (fixed-income portion)"
          strip_patterns:
            - '(?<=[A-Za-z.,"”’)]) \d{3}(?= [A-Za-z“"''])'
      - label: mackay-shields-proxy-voting-summary-as-printed-in-sai-funds
        adviser: "MacKay Shields LLC"
        adviser_key: "MACKAY_SHIELDS"
        sai_appendix:
          cik: "0000787441"
          forms: ["485BPOS"]
          since: "2023-01-01"
          start:
            - "MacKay Shields has adopted Proxy-Voting Policies and Procedures designed to make sure that where clients have delegated proxy-voting authority to MacKay Shields"
          end:
            - "MainStay Balanced (fixed-income portion)"
            - "NYLI Balanced (fixed-income portion)"
            - "NYLIM Balanced (fixed-income portion)"
          strip_patterns:
            - '(?<=[A-Za-z.,"”’)]) \d{3}(?= [A-Za-z“"''])'
```

Label markers were checked with `extract_section` (read-only) on the cached SAI texts: NYLIM labels return text for every full SAI (start occurs once, end found; 2021-03-22 prospectus filings return None as expected); MacKay summary returns the same 2,094-char text (hash f949990b, 58c0bba1 in the 2023-04-19 / 2024-05-01 sibling SAIs, which differ by a few words) in 1469192 from 2022-08-29 and 787441 from 2023-02-23.

## 4. Open doubts

- The sai_appendix markers were verified with `extract_section` on EDGAR texts fetched via glasshouse.http, not run through the ingester (no ingest commands allowed). Dry-run before merge. The `strip_patterns` regexes use YAML single quotes (a doubled `''` is a literal `'`); check they survive the YAML parser.
- INDEXIQ has no SAI label: the ETF-trust Appendix A text changes by SAI (2023-08-28 version extracts at 3,422 chars, but the 2024-2026 versions are inline in the SAI body and the end marker overshoots to 130,000+ characters), so only the Wayback PDF (2021-05-12) is proposed. Ausbil and Candriam summaries exist in the SAIs but have no label.
- Epoch, Winslow and Wellington are classed unaffiliated (N-CEN flag N, "TD Epoch") although the brief expected Epoch / Winslow / Candriam / MacKay as affiliates. Candriam and MacKay are affiliates (N-CEN Y); Epoch and Winslow are not. EXTERNAL carries no policy text, so their summaries printed in the SAI are not archived.
- ETF trust change of voter (IndexIQ Advisors to NYLIM) is dated by the first SAI naming NYLIM (2024-08-27), while NYLIM's ADV dates the merger 2024-09-12: about two weeks of meetings may be mislabelled NYLIM.
- Cushing is keyed EXTERNAL from 2021-02-24 although the SAI names it only from 2022-08-29 (before: 'the Fund's Subadvisor'); the N-CEN of 2021-02-10 names Cushing Asset Management LP, unaffiliated. If the maintainer wants SAI-only evidence, start at 2022-08-29.
- Wellington is first named for the 1469192 funds on 2021-03-29 and for 787441 on 2022-02-25 (the 2021-03-22 filings carry no proxy section); WMC funds in 787441 before 2022-02-25 are unlabelled. All of these predate the earliest ingestable N-PX (2024).
- Between the last SAI naming IndexIQ (2024-05-01 / 2024-04-19) and the first SAI listing the Manager (2024-08-28 / 2024-12-18) the S&P 500 Index and Hedge Multi-Strategy series are UNRESOLVED; this window overlaps N-PX 2024 meetings (Jul 2023 to Jun 2024 meetings are mostly before it).
- Series name drift in the vote-table comments (MainStay to NYLI to NYLIM) is cosmetic; the S-ids are the keys. S000006902 (MacKay International Equity, 78 rows in 2024 only) and S000073437 (ESG Multi-Asset, 72 rows) are discontinued.
- Fund-of-funds allocation series: whether to ingest at all is a coverage decision; if ingested, their votes are on registered funds, not companies.
- `<date>` placeholders: set to the commit date. The data.sec.gov entity names read in Nov 2026 are the new NYLIM names ("NYLIM FUNDS" etc.); use them for `name:` as the validation step does.
