# John Hancock (John Hancock Investment Management LLC, Manulife): research for config/institutions.yaml

Research only, 2026-11-20. Nothing under `data/` or `config/` was touched; EDGAR was read through `glasshouse.http` (honest User-Agent), and manulifeim.com was probed once with the same honest client. Ready to paste: the YAML block at the end.

## Verdict in five lines

- 14 registrants file N-PX vote tables with operating-company votes in 2024-2026 (6 open-end trusts, 8 closed-end funds).
- Every open-end series is sub-advised (no series in any N-CEN is run directly by John Hancock Investment Management, "JHIM"), so no series is keyed `JOHN_HANCOCK`: the Adviser's own Appendix C policy is a delegation and oversight procedure with no voting guidelines.
- Keys: `EXTERNAL` (unaffiliated subadviser, 49 series + 2 before a 2025 change), `MANULIFE_IM` (Manulife Investment Management affiliates, one shared Global Proxy Voting Policy: 24 series + 2 after the change, plus 6 closed-end funds), `UNRESOLVED` (5 series, 2 more for 2025), unlabelled (30 fund-of-funds series). Two closed-end funds are `EXTERNAL`.
- `MANULIFE_IM` is a new key (Manulife IM (US) LLC is a separate registered adviser under the same Manulife parent; its policy is its own, printed in the SAIs). If the maintainer prefers one group key, rename it `JOHN_HANCOCK` throughout; the evidence is the same.
- The Manulife IM website PDF is blocked to honest clients (403): label filled from Wayback; an SAI-appendix label is proposed but its end markers need a dry run.

## 1. Registrants with operating-company N-PX votes (2024-2026)

N-PX filed August each year (2024-08, 2025-08, 2026-08). "Series with votes" counts distinct `voteSeries` ids across the three years (streamed from the exhibits).

| CIK | EDGAR name | Type | Series with votes | N-PX vote exhibit (2024 / 2025 / 2026) |
|---|---|---|---|---|
| 1331971 | John Hancock Funds II | open-end | 56 | 145 MB / 96 MB / 53 MB |
| 756913 | John Hancock Variable Insurance Trust | open-end (insurance) | 35 | 197 MB / 172 MB / 170 MB |
| 1478482 | John Hancock Exchange-Traded Fund Trust | open-end ETFs | 10 | 37 MB / 38 MB / 42 MB |
| 1329954 | John Hancock Funds III | open-end | 5 | 5.7 / 5.4 / 5.3 MB |
| 743861 | John Hancock Investment Trust II | open-end | 2 | 1.6 / 1.5 / 1.4 MB |
| 45291 | John Hancock Capital Series | open-end | 2 | 0.8 / 0.8 / 0.7 MB |
| 925683 | John Hancock Financial Opportunities Fund | closed-end | n/a (no series) | about 1 MB |
| 1260041 | John Hancock Tax-Advantaged Dividend Income Fund | closed-end | n/a | 0.4 MB |
| 855886 | John Hancock Premium Dividend Fund | closed-end | n/a | 0.3 MB |
| 1176199 / 1189740 / 1215913 | John Hancock Preferred Income Fund / II / III | closed-end | n/a | 35-43 KB each |
| 1496749 | John Hancock Diversified Income Fund (named Hedged Equity & Income Fund until 2025) | closed-end | n/a | 4-7 MB |
| 1396502 | John Hancock Tax-Advantaged Global Shareholder Yield Fund | closed-end | n/a | 1.3 MB (2024 only; no later N-PX) |

Checked and left out: Bond Trust 315554, Sovereign Bond 45288, Strategic Series 792858, Investors Trust 759828, Income Securities Trust 759866, Current Interest 26262, Collateral Trust 1631942, the GA Mortgage / GA Senior Loan / CQS / Marathon funds (no vote-table exhibit); Municipal Securities Trust 857769 and California Tax-Free Income 856671 (votes only on other municipal closed-end funds); Investment Trust III 791271, Series Trust 357238, Tax-Exempt Series Fund 811921, Collateral Investment Trust 1465214 (no N-PX after 2023); institutional-manager N-PX of JHIM 1230788 (206 votes of 2 shares in 2024, 3 in 2025), John Hancock Life Insurance Co (USA) 1073894 (4 votes in 2024) and Manulife Investment Management (US) LLC 1034182 (a 5 MB institutional-account N-PX; a candidate for a separate `manulife_im` institution, not proposed here).

## 2. Earliest 2021-2023 SAI read per open-end registrant, and the wording

All SAIs are 485BPOS read in full (main htm document). The "Proxy Voting" paragraph hashes identically across editions except for printed page numbers, "Trust"/"each Trust" and singular/plural "subadvisor".

| CIK | Earliest SAI | Accession | Later editions read |
|---|---|---|---|
| 1331971 Funds II | 2021-04-26 (Lifestyle SAI) | 0001133228-21-002307 | 11 filings 2021-04 to 2023-12 (several distinct SAIs: Lifestyle, single-fund, Alternative Asset Allocation, Multi-Index) |
| 756913 VIT | 2021-04-23 | 0001133228-21-002276 | 2022-04-22, 2023-04-21 |
| 1478482 ETF Trust | 2021-03-26 (Core Bond ETF, single-fund SAI) | 0001133228-21-001611 | 11 more, 2021-08 to 2023-12 |
| 1329954 Funds III | 2021-07-27 | 0001133228-21-004078 | 2022-07-26, 2023-07-25 |
| 743861 Investment Trust II | 2021-02-24 | 0001133228-21-000883 | 2022-02-24, 2023-02-23 |
| 45291 Capital Series | 2021-02-24 | 0001133228-21-000878 | 2022-02-24, 2023-02-23 |

Exact quote, SAI section "Other Services - Proxy Voting" (Funds II 2021-04-26, same in VIT 2021-04-23; Funds III and Capital Series / Investment Trust II say "each Trust's"; single-fund SAIs such as the ETF Trust 2021-03-26 say "Subadvisory Agreement ... the subadvisor of each of its funds ... The subadvisor has a duty to vote"):

> "Based on the terms of the current Subadvisory Agreements, the Trust's proxy voting policies and procedures (the "Trust Procedures") delegate to the subadvisors of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures. A subadvisor has a duty to vote or not vote such proxies in the best interests of the fund it subadvises and its shareholders, and to avoid the influence of conflicts of interest. In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor. Complete descriptions of the Trust Procedures and the proxy voting procedures of the Advisor and the subadvisors are set forth in Appendix C to this SAI."

Appendix C (same SAI): "In general, Advisers defer proxy voting decisions to the sub-advisers managing the Funds. It is the policy of the Trusts to delegate the responsibility for voting proxies relating to portfolio securities held by a Fund to the Fund's respective Adviser or, if the Fund's Adviser has delegated portfolio management responsibilities to one or more investment sub-adviser(s), to the fund's sub-adviser(s), subject to the Board's continued oversight. The sub-adviser for each Fund shall vote all proxies relating to securities held by each Fund ... and ... shall use proxy voting policies and procedures adopted by each sub-adviser".

Fund-of-funds rule (Appendix C, "Voting Proxies of Underlying Funds of a Fund of Funds"): where the fund of funds is not the sole shareholder it "will vote proxies relating to shares of the Underlying Fund in the same proportion as the vote of all other holders"; where it is the sole shareholder the Adviser votes under its Proxy Voting Procedures or by proportional (mirror) instruction.

Appendix C of the 2021-04 SAIs prints "John Hancock Funds Proxy Voting Policies and Procedures (Updated December 10, 2019)", the Advisers' own "Proxy Voting Policies and Procedures (Updated December 1, 2019)" (a delegation and oversight procedure), and, for Manulife-sub-advised series, "Manulife Investment Management Global Proxy Voting Policy and Procedures, March 2020" (April 2021 edition in the SAIs of 2022-2023), which "applies to each of the Manulife IM advisory affiliates listed in Appendix A", including Manulife Investment Management (US) LLC and Manulife Investment Management (North America) Limited.

Closed-end funds (no SAI accompanies the annual report): the voting statement is the exhibit to Item 7 of the N-CSR, "See attached exhibit 'Proxy Voting Policies and Procedures'". Earliest 2021 read per fund:

| CIK | N-CSR | Accession | Exhibit prints | Sentence that decides who votes |
|---|---|---|---|---|
| 925683 | 2021-02-19 | 0001683863-21-000814 | Manulife IM Global Proxy Voting Policy (External) | "Where Manulife IM is granted and accepts responsibility for voting proxies for client accounts, it will seek to ensure proxies are received and voted in the best interests of the client" |
| 1260041 | 2021-12-17 | 0001683863-21-007333 | Manulife Asset Management "Proxy Voting Policy" (ISS) | "Where MAM is granted and accepts responsibility for voting proxies for client accounts, it will take reasonable steps to seek to ensure proxies are received and voted in the best interest of the client"; from 2022-12-23 the Manulife IM Global Policy |
| 855886 | 2021-12-17 | 0001683863-21-007336 | same as 1260041 | same |
| 1176199 / 1189740 / 1215913 | 2021-10-04 | 0001683863-21-005933 / -005934 / -005935 | "5E: Proxy Voting Policies and Procedures for the Adviser" | "The Advisers generally retain one or more sub-advisers to manage the assets of the Funds, including voting proxies with respect to a Fund's portfolio securities" and "the Advisers delegate proxy voting decisions to the sub-advisers managing the funds" |
| 1496749 | 2021-02-19 | 0001683863-21-000798 | Wellington Management Global Proxy Policy and Procedures | Wellington's own policy (sole sub-adviser per N-CEN) |
| 1396502 | 2021-12-17 | 0001683863-21-007334 | Epoch Investment Partners Proxy Voting and Class Action Monitoring Policy | "Epoch maintains proxy voting authority for Client accounts, unless otherwise instructed by the client." |

## 3. Series by key (open-end trusts, series with 2024-2026 votes)

| Registrant | EXTERNAL | MANULIFE_IM | UNRESOLVED | EXTERNAL then MANULIFE_IM | Unlabelled |
|---|---|---|---|---|---|
| Funds II (56) | 18 | 7 | 1 | 0 | 30 |
| Variable Insurance Trust (35) | 18 | 11 | 4 | 2 | 0 |
| ETF Trust (10) | 6 | 4 | 0 | 0 | 0 |
| Funds III (5) | 5 | 0 | 0 | 0 | 0 |
| Investment Trust II (2) | 0 | 2 | 0 | 0 | 0 |
| Capital Series (2) | 2 | 0 | 0 | 0 | 0 |
| Total (110) | 49 | 24 | 5 | 2 | 30 |

Closed-end: MANULIFE_IM 6 (Financial Opportunities, Tax-Advantaged Dividend from 2021-12-17, Premium Dividend, Preferred Income I/II/III), EXTERNAL 2 (Diversified Income, Global Shareholder Yield).

## 4. Open doubts (for the maintainer)

1. Key name: `MANULIFE_IM` (affiliate with its own printed policy, the PGIM precedent) versus a single `JOHN_HANCOCK` group key. No series qualifies for `JOHN_HANCOCK` as "its own policy governs": the JHIM procedure has no guidelines.
2. 30 Funds II fund-of-funds series left unlabelled: their 2025-2026 issuers are only registered funds (Vanguard trusts, John Hancock ETF Trust), found by a name regex. Re-check against the ledger (operating-company rows for those series would need a rule). Their 2024 votes were not tested because the 2024 file holds only 22 series; the issuer test used 2025 and 2026.
3. Transition series (VIT High Yield Trust S000008240, Small Cap Value Trust S000008313): the FY2024 N-CEN (period 2024-12-31) names Western Asset / Wellington, the FY2025 N-CEN (period 2025-12-31) names Manulife IM (US) alone; 2025 is therefore UNRESOLVED. The Funds II twins (High Yield Fund, Small Cap Value Fund) show only the old subadviser in their last N-CEN read and have votes only to 2025, so they stay EXTERNAL; confirm against the 2026 N-CEN when it exists.
4. Preferred Income Funds I-III: keyed MANULIFE_IM on the chain of delegation (Adviser exhibit says sub-advisers vote; N-CEN names Manulife IM (US) alone), but their N-CSR never prints the Manulife policy. Downgrade to UNRESOLVED if the maintainer wants a printed policy for every labelled series.
5. Tax-Advantaged Dividend Income Fund: N-CEN of 2021-01-08 lists Wells Capital Management beside Manulife; the boundary date (2021-12-17, first N-CSR printing only Manulife's policy) is a judgement, and all of it precedes the ledger's earliest votes (2023-07).
6. VIT Lifestyle Growth Portfolio (S000032006) shows 64 votes, all Bank of Cyprus Holdings, no fund issuers: keyed MANULIFE_IM, but an odd profile worth a look in the ledger.
7. The SAI-appendix label's `end` markers were verified on only 4 of the 5 SAIs read; run it dry before enabling (the SAIs print only the subadvisers' policies for their own series, and the heading after the Manulife policy differs).
8. Funds II N-PX 2024 has far fewer series with votes (22) than 2025-2026 (42): the Multi-Index and Lifetime portfolios first vote in 2025. Not an ingest fault as far as seen.
9. John Hancock Investment Trust II (743861) is the EDGAR name of the trust that holds the Regional Bank and Financial Industries funds; there is no separate "John Hancock Investment Trust" with a 2024+ N-PX.

## 5. Recommended commands (not run; a release build is reading the ledger)

After the YAML is merged: `glasshouse ingest npx --cik 1331971` (and each CIK above, plus `--reingest` if rows already exist), then the usual dedupe, `glasshouse ingest commitments`, `glasshouse engine build`. Live smoke check done for this research: all fourteen CIKs return N-PX filings from data.sec.gov submissions; the exhibits were streamed, not ingested. The Manulife IM website PDF answers 403 to honest clients (HEAD, 2026-11-20); Wayback CDX holds eight captures.

## 6. Proposed YAML (paste under `institutions:`; new entry after `proshares`)

```yaml
  john_hancock:
    display_name: "John Hancock (John Hancock Investment Management LLC, Manulife) and its subadvisers"
    short_name: "John Hancock"
    cik: "0001230788"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "John Hancock Investment Management LLC, Boston MA (CIK 1230788, formerly John Hancock Advisers LLC), a Manulife Financial subsidiary, is the investment adviser of the John Hancock mutual-fund, ETF, variable-insurance and closed-end fund trusts; John Hancock Variable Trust Advisers LLC (1320616) co-advises the variable trusts. Both file 13F-NT notices only (13-F holdings are not ingested here). Every John Hancock open-end series is SUB-ADVISED (no series in the N-CEN reads is managed by the Adviser directly): each trust's procedures delegate voting to the series' subadviser, which votes under its OWN policy (Manulife Investment Management (US) LLC / (North America) Limited, which share one Global Proxy Voting Policy, key MANULIFE_IM; or an unaffiliated subadviser: Wellington, T. Rowe Price, Dimensional, Boston Partners, Jennison, State Street and others, key EXTERNAL). The Adviser's own policy (Appendix C, 'John Hancock Funds Proxy Voting Policies and Procedures') is a delegation-and-oversight procedure plus a mirror/proportional-vote rule for funds of funds voting underlying-fund shares; it contains no voting guidelines, so no series is keyed JOHN_HANCOCK. Fourteen registrants that file N-PX vote tables with operating-company votes are ingested (six open-end trusts, eight closed-end funds). aum_usd_tr is not verified."
    npx_ciks:
      # Added 2026-11-20. Fourteen John Hancock registrants file N-PX vote tables with operating-company votes (2024-2026; the first with votes filed 2024-08). Six open-end trusts: Funds II (1331971), Variable Insurance Trust (756913),
      # Funds III (1329954), Investment Trust II (743861, the EDGAR name of the trust holding the Regional Bank and Financial Industries funds), Capital Series (45291), Exchange-Traded Fund Trust (1478482); eight closed-end funds.
      # Every SAI read (wording identical in every 2021-2023 edition) says the Trust's procedures delegate voting to each fund's subadvisor under the subadvisor's own policy; there is NO registrant default, so each series carries a rule (`series_adviser`),
      # read from the trust's Form N-CEN Item C.3 sub-adviser table (every N-CEN filed 2021-2026). `from` is the filing date of the first N-CEN read for the series. Only series with N-PX votes (2024-2026) carry a rule.
      - cik: "1331971"
        adviser: "John Hancock Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1331971/000113322821002307/jhfii-html3592_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-04-26 (0001133228-21-002307)."
        series_adviser:
          # S000023552: Alternative Asset Allocation Fund: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          S000003311: [{key: EXTERNAL, from: "2021-11-12"}]   # Blue Chip Growth Fund: T. Rowe Price Associates
          S000003312: [{key: EXTERNAL, from: "2021-11-12"}]   # Capital Appreciation Fund: Jennison Associates
          S000030799: [{key: EXTERNAL, from: "2021-11-12"}]   # Capital Appreciation Value Fund: T. Rowe Price Associates
          S000003313: [{key: EXTERNAL, from: "2021-11-12"}]   # Core Bond Fund: Wells Capital Management
          S000027304: [{key: MANULIFE_IM, from: "2021-11-12"}]   # Emerging Markets Debt Fund: Manulife Investment Management (US)
          S000017260: [{key: EXTERNAL, from: "2021-11-12"}]   # Emerging Markets Fund: Dimensional Fund Advisors
          S000003317: [{key: EXTERNAL, from: "2021-11-12"}]   # Equity Income Fund: T. Rowe Price Associates
          S000020234: [{key: EXTERNAL, from: "2021-11-12"}]   # Floating Rate Income Fund: BCSF Advisors
          S000032685: [{key: MANULIFE_IM, from: "2021-10-13"}]   # Fundamental All Cap Core Fund: Manulife Investment Management (US)
          S000037602: [{key: MANULIFE_IM, from: "2021-11-12"}]   # Fundamental Global Franchise Fund: Manulife Investment Management (US)
          S000040959: [{key: MANULIFE_IM, from: "2021-11-12"}]   # Global Equity Fund: Manulife Investment Management (US)
          S000034046: [{key: EXTERNAL, from: "2021-11-12"}]   # Health Sciences Fund: T. Rowe Price Associates
          S000003320: [{key: EXTERNAL, from: "2021-11-12"}]   # High Yield Fund: Western Asset Management Company
          S000009779: [{key: EXTERNAL, from: "2021-11-12"}]   # International Small Company Fund: Dimensional Fund Advisors
          S000055170: [{key: MANULIFE_IM, from: "2021-11-12"}]   # International Strategic Equity Allocation Fund: Manulife Investment Management (US)
          S000024677: [{key: EXTERNAL, from: "2021-11-12"}]   # Mid Value Fund: T. Rowe Price Associates
          S000035066: [{key: EXTERNAL, from: "2021-10-13"}]   # Multi-Asset Absolute Return Fund: Nordea Investment Management North America
          # S000042847: Multi-Index 2010 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042848: Multi-Index 2015 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042849: Multi-Index 2020 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042850: Multi-Index 2025 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042851: Multi-Index 2030 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042852: Multi-Index 2035 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042853: Multi-Index 2040 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042854: Multi-Index 2045 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000042855: Multi-Index 2050 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000044503: Multi-Index 2055 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000053255: Multi-Index 2060 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000069423: Multi-Index 2065 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000043433: Multi-Index Lifestyle Aggressive Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000043434: Multi-Index Lifestyle Balanced Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000043435: Multi-Index Lifestyle Conservative Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000043436: Multi-Index Lifestyle Growth Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000043437: Multi-Index Lifestyle Moderate Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013654: Multimanager 2025 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013655: Multimanager 2030 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013656: Multimanager 2035 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013657: Multimanager 2040 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013658: Multimanager 2045 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000013659: Multimanager 2050 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000044502: Multimanager 2055 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000053254: Multimanager 2060 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000069425: Multimanager 2065 Lifetime Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000003335: Multimanager Lifestyle Aggressive Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          # S000003337: Multimanager Lifestyle Balanced Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          S000003339: [{key: UNRESOLVED, from: "2021-03-10"}]   # Multimanager Lifestyle Growth Portfolio: fund of funds with operating-company AND underlying-fund votes in one series (two voting regimes); Manulife Investment Management (US)
          # S000003342: Multimanager Lifestyle Moderate Portfolio: no rule (fund of funds; N-PX issuers are only registered funds, voted by the Trust's underlying-fund procedure, not a sub-adviser policy)
          S000003360: [{key: EXTERNAL, from: "2021-11-12"}]   # New Opportunities Fund: GW & K Investment Management
          S000003319: [{key: EXTERNAL, from: "2021-11-12"}]   # Opportunistic Fixed Income Fund: Wellington Management Company
          S000003356: [{key: EXTERNAL, from: "2021-11-12"}]   # Real Estate Securities Fund: Wellington Management Company
          S000009815: [{key: EXTERNAL, from: "2021-11-12"}]   # Science & Technology Fund: Allianz Global Investors U.S. + T. Rowe Price Associates
          S000003363: [{key: EXTERNAL, from: "2021-11-12"}]   # Small Cap Growth Fund: Redwood Investments
          S000009819: [{key: EXTERNAL, from: "2021-11-12"}]   # Small Cap Value Fund: Wellington Management Company
          S000009820: [{key: MANULIFE_IM, from: "2021-11-12"}]   # Strategic Income Opportunities Fund: Manulife Investment Management (US)
          S000055171: [{key: MANULIFE_IM, from: "2021-11-12"}]   # U.S. Sector Rotation Fund: Manulife Investment Management (US)
        name: "JOHN HANCOCK FUNDS II"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "756913"
        adviser: "John Hancock Investment Management LLC / John Hancock Variable Trust Advisers LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/756913/000113322821002276/jhvit-html3521_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-04-23 (0001133228-21-002276)."
        series_adviser:
          S000008219: [{key: MANULIFE_IM, from: "2021-03-10"}]   # 500 Index Trust: Manulife Investment Management (North America)
          S000008217: [{key: EXTERNAL, from: "2021-03-10"}]   # Blue Chip Growth Trust: T. Rowe Price Associates
          S000008220: [{key: EXTERNAL, from: "2021-03-10"}]   # Capital Appreciation Trust: Jennison Associates
          S000021933: [{key: EXTERNAL, from: "2021-03-10"}]   # Capital Appreciation Value Trust: T. Rowe Price Associates
          S000008222: [{key: EXTERNAL, from: "2021-03-10"}]   # Core Bond Trust: Wells Capital Management
          S000008302: [{key: EXTERNAL, from: "2021-03-10"}]   # Disciplined Value International Trust: Boston Partners Global Investors
          S000017255: [{key: EXTERNAL, from: "2021-03-10"}]   # Emerging Markets Value Trust: Dimensional Fund Advisors
          S000008228: [{key: EXTERNAL, from: "2021-03-10"}]   # Equity Income Trust: T. Rowe Price Associates
          S000008229: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Financial Industries Trust: Manulife Investment Management (US)
          S000008296: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Fundamental All Cap Core Trust: Manulife Investment Management (US)
          S000008321: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Fundamental Large Cap Value Trust: Manulife Investment Management (US)
          S000008231: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Global Trust: Manulife Investment Management (US)
          S000008239: [{key: EXTERNAL, from: "2021-03-10"}]   # Health Sciences Trust: T. Rowe Price Associates
          S000008240: [{key: EXTERNAL, from: "2021-03-10", until: "2024-12-31"}, {key: UNRESOLVED, from: "2025-01-01", until: "2025-12-31"}, {key: MANULIFE_IM, from: "2026-01-01"}]   # High Yield Trust: Western Asset Management Company until the FY2024 N-CEN, Manulife IM (US) from the FY2025 N-CEN (filed 2026-03-11); change date inside 2025 not established
          S000008297: [{key: EXTERNAL, from: "2021-03-10"}]   # International Equity Index Trust: SSgA Funds Management
          S000008301: [{key: EXTERNAL, from: "2021-03-10"}]   # International Small Company Trust: Dimensional Fund Advisors
          S000032006: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Lifestyle Growth Portfolio: Manulife Investment Management (US)
          S000008279: [{key: UNRESOLVED, from: "2021-03-10"}]   # Managed Volatility Balanced Portfolio: fund of funds with operating-company AND underlying-fund votes in one series (two voting regimes); Manulife Investment Management (US)
          S000008281: [{key: UNRESOLVED, from: "2021-03-10"}]   # Managed Volatility Conservative Portfolio: fund of funds with operating-company AND underlying-fund votes in one series (two voting regimes); Manulife Investment Management (US)
          S000008278: [{key: UNRESOLVED, from: "2021-03-10"}]   # Managed Volatility Growth Portfolio: fund of funds with operating-company AND underlying-fund votes in one series (two voting regimes); Manulife Investment Management (US)
          S000008280: [{key: UNRESOLVED, from: "2021-03-10"}]   # Managed Volatility Moderate Portfolio: fund of funds with operating-company AND underlying-fund votes in one series (two voting regimes); Manulife Investment Management (US)
          S000008285: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Mid Cap Index Trust: Manulife Investment Management (North America)
          S000008286: [{key: EXTERNAL, from: "2021-03-10"}]   # Mid Cap Stock Trust: Wellington Management Company
          S000008289: [{key: EXTERNAL, from: "2021-03-10"}]   # Mid Value Trust: T. Rowe Price Associates
          S000008233: [{key: EXTERNAL, from: "2021-03-10"}]   # Opportunistic Fixed Income Trust: Wellington Management Company
          S000008338: [{key: EXTERNAL, from: "2021-03-10"}]   # Real Estate Securities Trust: Wellington Management Company
          S000008340: [{key: EXTERNAL, from: "2021-03-10"}]   # Science & Technology Trust: Allianz Global Investors U.S. + T. Rowe Price Associates
          S000008311: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Small Cap Index Trust: Manulife Investment Management (North America)
          S000008312: [{key: EXTERNAL, from: "2021-03-10"}]   # Small Cap Opportunities Trust: Dimensional Fund Advisors + GW & K Investment Management
          S000008343: [{key: EXTERNAL, from: "2021-03-10"}]   # Small Cap Stock Trust: Wellington Management Company
          S000008313: [{key: EXTERNAL, from: "2021-03-10", until: "2024-12-31"}, {key: UNRESOLVED, from: "2025-01-01", until: "2025-12-31"}, {key: MANULIFE_IM, from: "2026-01-01"}]   # Small Cap Value Trust: Wellington Management Company until the FY2024 N-CEN, Manulife IM (US) from the FY2025 N-CEN (filed 2026-03-11); change date inside 2025 not established
          S000008316: [{key: EXTERNAL, from: "2021-03-10"}]   # Small Company Value Trust: T. Rowe Price Associates
          S000036499: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Strategic Equity Allocation Trust: Manulife Investment Management (US)
          S000008320: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Strategic Income Opportunities Trust: Manulife Investment Management (US)
          S000008325: [{key: MANULIFE_IM, from: "2021-03-10"}]   # Total Stock Market Index Trust: Manulife Investment Management (North America)
        name: "JOHN HANCOCK VARIABLE INSURANCE TRUST"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1329954"
        adviser: "John Hancock Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1329954/000113322821004078/jhfiii-html3883_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-07-27 (0001133228-21-004078)."
        series_adviser:
          S000023715: [{key: EXTERNAL, from: "2021-06-07"}]   # John Hancock Disciplined Value Fund: Boston Partners Global Investors
          S000028882: [{key: EXTERNAL, from: "2021-06-07"}]   # John Hancock Disciplined Value Mid Cap Fund: Boston Partners Global Investors
          S000015906: [{key: EXTERNAL, from: "2021-06-07"}]   # John Hancock Global Shareholder Yield Fund: Epoch Investment Partners
          S000001412: [{key: EXTERNAL, from: "2021-06-07"}]   # John Hancock International Growth Fund: Wellington Management Company
          S000035055: [{key: EXTERNAL, from: "2021-06-07"}]   # John Hancock U.S. Quality Growth Fund: Wellington Management Company
        name: "JOHN HANCOCK FUNDS III"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "743861"
        adviser: "John Hancock Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/743861/000113322821000883/jhitii-html3345_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-02-24 (0001133228-21-000883)."
        series_adviser:
          S000000634: [{key: MANULIFE_IM, from: "2021-01-08"}]   # Financial Industries Fund: Manulife Investment Management (US)
          S000000635: [{key: MANULIFE_IM, from: "2021-01-08"}]   # Regional Bank Fund: Manulife Investment Management (US)
        name: "JOHN HANCOCK INVESTMENT TRUST II"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "45291"
        adviser: "John Hancock Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/45291/000113322821000878/jhcs-html3347_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-02-24 (0001133228-21-000878)."
        series_adviser:
          S000000617: [{key: EXTERNAL, from: "2021-01-08"}]   # Classic Value Fund: Pzena Investment Management
          S000000620: [{key: EXTERNAL, from: "2021-01-08"}]   # U.S. Global Leaders Growth Fund: Sustainable Growth Advisers
        name: "JOHN HANCOCK CAPITAL SERIES"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1478482"
        adviser: "John Hancock Investment Management LLC (the Advisor); subadvisers vote per series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1478482/000113322821001611/jhcbetf-html3453_485bpos.htm"
        adviser_verified: "2026-11-20"
        voting_note: "SAI 'Proxy Voting': 'Based on the terms of the current Subadvisory Agreement[s], the Trust[s]' proxy voting policies and procedures (the \"Trust Procedures\") delegate to the subadvisor[s] of each of its funds the responsibility to vote all proxies relating to securities held by that fund in accordance with the subadvisor's proxy voting policies and procedures ... In the event that the Advisor assumes day-to-day management responsibilities for the fund, the Trust's Procedures delegate proxy voting responsibilities to the Advisor' (Appendix C prints the Advisers' own procedures, which say 'Advisers defer proxy voting decisions to the sub-advisers managing the Funds', and each subadvisor's policy). So no registrant-wide key: each series is keyed by its voting subadviser read from the trust's Form N-CEN Item C.3 tables (filed 2021-2026): MANULIFE_IM when every subadviser named is a Manulife Investment Management entity (one Global Proxy Voting Policy covers them all), EXTERNAL for any unaffiliated subadviser, UNRESOLVED for a fund of funds with both operating-company and underlying-fund votes or a sub-adviser change inside the window; a fund of funds whose only N-PX issuers are registered funds is left unlabelled (the Trust's underlying-fund procedure applies, not a sub-adviser policy). Earliest SAI read 2021-03-26 (0001133228-21-001611)."
        series_adviser:
          S000083349: [{key: EXTERNAL, from: "2024-07-09"}]   # John Hancock Disciplined Value International Select ETF: Boston Partners Global Investors
          S000082342: [{key: MANULIFE_IM, from: "2024-07-09"}]   # John Hancock Fundamental All Cap Core ETF: Manulife Investment Management (US)
          S000079041: [{key: MANULIFE_IM, from: "2023-07-03"}]   # John Hancock International High Dividend ETF: Manulife Investment Management (US)
          S000055737: [{key: EXTERNAL, from: "2021-07-01"}]   # John Hancock Multifactor Developed International ETF: Dimensional Fund Advisors
          S000063017: [{key: EXTERNAL, from: "2021-07-01"}]   # John Hancock Multifactor Emerging Markets ETF: Dimensional Fund Advisors
          S000050077: [{key: EXTERNAL, from: "2021-07-01"}]   # John Hancock Multifactor Large Cap ETF: Dimensional Fund Advisors
          S000050079: [{key: EXTERNAL, from: "2021-07-01"}]   # John Hancock Multifactor Mid Cap ETF: Dimensional Fund Advisors
          S000059464: [{key: EXTERNAL, from: "2021-07-01"}]   # John Hancock Multifactor Small Cap ETF: Dimensional Fund Advisors
          S000074603: [{key: MANULIFE_IM, from: "2022-06-29"}]   # John Hancock Preferred Income ETF: Manulife Investment Management (US)
          S000077441: [{key: MANULIFE_IM, from: "2023-07-03"}]   # John Hancock U.S. High Dividend ETF: Manulife Investment Management (US)
        name: "JOHN HANCOCK EXCHANGE-TRADED FUND TRUST"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "925683"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/925683/000168386321000814/f7997d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-02-19 (0001683863-21-000814), Item 7 exhibit EX-99.(C)(1) 'Manulife Investment Management Global Proxy Voting Policy and Procedures (External)'. Item 7 of the fund's N-CSR points to an exhibit that prints the Manulife Investment Management Global Proxy Voting Policy and Procedures, which 'applies to each of the Manulife IM advisory affiliates listed in Appendix A' (Manulife Investment Management (US) LLC, the fund's sub-adviser per Form N-CEN, is listed). Closed-end fund: no SAI is filed with the annual report, so the N-CSR exhibit is the voting statement."
        adviser_key_history: [{key: MANULIFE_IM, from: "2021-02-19"}]
        name: "JOHN HANCOCK FINANCIAL OPPORTUNITIES FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1260041"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1260041/000168386321007333/f9314d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-12-17 (0001683863-21-007333), Item 7 exhibit EX-99.(C)(1) 'Proxy Voting Policy' of Manulife Asset Management (the former name): 'Where MAM is granted and accepts responsibility for voting proxies for client accounts ...' (ISS recommendations adopted); from the N-CSR of 2022-12-23 the exhibit is the Manulife IM Global Proxy Voting Policy. Form N-CEN of 2021-01-08 lists Manulife IM (US) AND Wells Capital Management (unaffiliated) as sub-advisers; from the N-CEN of 2022-01-05 Manulife IM (US) alone. EXTERNAL until the day before the first N-CSR that prints only the Manulife policy."
        adviser_key_history: [{key: EXTERNAL, from: "2021-01-08", until: "2021-12-16"}, {key: MANULIFE_IM, from: "2021-12-17"}]
        name: "JOHN HANCOCK TAX-ADVANTAGED DIVIDEND INCOME FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "855886"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/855886/000168386321007336/f9315d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-12-17 (0001683863-21-007336), Item 7 exhibit EX-99.(C)(1) 'Proxy Voting Policy' of Manulife Asset Management (the former name; ISS recommendations adopted); from the N-CSR of 2022-12-23 the Manulife IM Global Proxy Voting Policy. Form N-CEN (2021-2026): Manulife IM (US) LLC sole sub-adviser."
        adviser_key_history: [{key: MANULIFE_IM, from: "2021-12-17"}]
        name: "JOHN HANCOCK PREMIUM DIVIDEND FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1176199"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1176199/000168386321005933/f9255d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-10-04 (0001683863-21-005933), Item 7 exhibit EX-99.(C)(1) '5E: Proxy Voting Policies and Procedures for the Adviser': 'The Advisers generally retain one or more sub-advisers to manage the assets of the Funds, including voting proxies with respect to a Fund's portfolio securities' and 'the Advisers delegate proxy voting decisions to the sub-advisers managing the funds'. The exhibits of 2021-2024 print this adviser policy only, never the sub-adviser's; Form N-CEN (2021-2026) names Manulife Investment Management (US) LLC as the sole sub-adviser, so the vote is the sub-adviser's, keyed MANULIFE_IM on the chain of delegation (its policy text is not printed in this fund's N-CSR; same entity as the funds that do print it)."
        adviser_key_history: [{key: MANULIFE_IM, from: "2021-10-04"}]
        name: "JOHN HANCOCK PREFERRED INCOME FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1189740"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1189740/000168386321005934/f9256d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-10-04 (0001683863-21-005934), Item 7 exhibit EX-99.(C)(1) '5E: Proxy Voting Policies and Procedures for the Adviser': 'The Advisers generally retain one or more sub-advisers to manage the assets of the Funds, including voting proxies with respect to a Fund's portfolio securities' and 'the Advisers delegate proxy voting decisions to the sub-advisers managing the funds'. The exhibits of 2021-2024 print this adviser policy only, never the sub-adviser's; Form N-CEN (2021-2026) names Manulife Investment Management (US) LLC as the sole sub-adviser, so the vote is the sub-adviser's, keyed MANULIFE_IM on the chain of delegation (its policy text is not printed in this fund's N-CSR; same entity as the funds that do print it)."
        adviser_key_history: [{key: MANULIFE_IM, from: "2021-10-04"}]
        name: "JOHN HANCOCK PREFERRED INCOME FUND II"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1215913"
        adviser: "John Hancock Investment Management LLC (the Adviser); Manulife Investment Management (US) LLC (affiliated sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1215913/000168386321005935/f9257d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-10-04 (0001683863-21-005935), Item 7 exhibit EX-99.(C)(1) '5E: Proxy Voting Policies and Procedures for the Adviser': 'The Advisers generally retain one or more sub-advisers to manage the assets of the Funds, including voting proxies with respect to a Fund's portfolio securities' and 'the Advisers delegate proxy voting decisions to the sub-advisers managing the funds'. The exhibits of 2021-2024 print this adviser policy only, never the sub-adviser's; Form N-CEN (2021-2026) names Manulife Investment Management (US) LLC as the sole sub-adviser, so the vote is the sub-adviser's, keyed MANULIFE_IM on the chain of delegation (its policy text is not printed in this fund's N-CSR; same entity as the funds that do print it)."
        adviser_key_history: [{key: MANULIFE_IM, from: "2021-10-04"}]
        name: "JOHN HANCOCK PREFERRED INCOME FUND III"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1496749"
        adviser: "John Hancock Investment Management LLC (the Adviser); Wellington Management Company LLP (sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1496749/000168386321000798/f8031d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-02-19 (0001683863-21-000798), Item 7 exhibit EX-99.(C)(1) 'WELLINGTON MANAGEMENT GLOBAL PROXY POLICY AND PROCEDURES' (Wellington's own policy; later editions: the 2023 Global Proxy Voting Guidelines). Form N-CEN (2021-2026): Wellington is the sole sub-adviser. The registrant was named John Hancock Hedged Equity & Income Fund until 2025 (same CIK, same sub-adviser)."
        adviser_key_history: [{key: EXTERNAL, from: "2021-02-19"}]
        name: "JOHN HANCOCK DIVERSIFIED INCOME FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1396502"
        adviser: "John Hancock Investment Management LLC (the Adviser); Epoch Investment Partners, Inc. (sub-adviser) votes"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1396502/000168386321007334/f10471d5.htm"
        adviser_verified: "2026-11-20"
        voting_note: "N-CSR filed 2021-12-17 (0001683863-21-007334), Item 7 exhibit EX-99.(C)(1) Epoch Investment Partners Compliance Manual 'Proxy Voting and Class Action Monitoring Policy': 'Epoch maintains proxy voting authority for Client accounts, unless otherwise instructed by the client.' Form N-CEN: Epoch (with Wells Capital Management until the 2022-01-05 read), both unaffiliated. Only one N-PX with votes (filed 2024-08-05); no later N-PX."
        adviser_key_history: [{key: EXTERNAL, from: "2021-12-17"}]
        name: "JOHN HANCOCK TAX-ADVANTAGED GLOBAL SHAREHOLDER YIELD FUND"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
    voting_scope_notes:
      - "Keyed per SERIES for the six open-end trusts, never per registrant: the SAIs say the Trust's procedures 'delegate to the subadvisors of each of its funds the responsibility to vote all proxies' under 'the subadvisor's proxy voting policies and procedures', and the voting subadviser per series is read from Form N-CEN Item C.3 (every read 2021-2026). MANULIFE_IM = every subadviser named is a Manulife Investment Management entity (US) LLC / (North America) Limited / Asset Management (North America) Limited (the former name); EXTERNAL = any unaffiliated subadviser named in any read; UNRESOLVED = fund of funds with both operating-company and underlying-fund votes (Multimanager Lifestyle Growth, the four Managed Volatility Portfolios of the Variable Insurance Trust) or an EXTERNAL to MANULIFE_IM change inside a year (High Yield Trust, Small Cap Value Trust: Western Asset / Wellington until the FY2024 N-CEN, Manulife IM (US) at the FY2025 N-CEN, so the change date is somewhere in 2025). The N-PX does not split a series' sleeves; a series with several subadvisers is EXTERNAL if any is unaffiliated (Small Cap Opportunities Trust: Dimensional and GW&K until 2026)."
      - "Unlabelled on purpose: 30 John Hancock Funds II fund-of-funds series (the Multimanager Lifestyle/Lifetime and Multi-Index Lifetime/Lifestyle Portfolios, Alternative Asset Allocation) whose N-PX issuers in 2025-2026 are only registered funds (Vanguard trusts, John Hancock Exchange Traded Fund Trust). Those votes follow the Trust's 'Voting Proxies of Underlying Funds of a Fund of Funds' procedure (proportional/mirror voting, or the Adviser under its own procedures), not a sub-adviser's guidelines, so pairing them with the Manulife IM policy would be false. The heuristic 'issuer is a registered fund' was a name regex over 2025-2026 N-PX: re-check against the ledger before relying on it."
      - "Closed-end funds are keyed per registrant (one fund each, no series): Financial Opportunities, Tax-Advantaged Dividend Income and Premium Dividend (Manulife IM (US): their N-CSR Item 7 exhibit prints Manulife's policy), the three Preferred Income Funds (Manulife IM (US) per N-CEN; the exhibit is the Adviser's delegation procedure, so the key rests on the chain of delegation, flagged in voting_note), Diversified Income (Wellington) and Tax-Advantaged Global Shareholder Yield (Epoch; only the 2024 N-PX exists)."
      - "Not ingested (left out): the Municipal Securities Trust (857769) and California Tax-Free Income Fund (856671) (their N-PX votes are only on other municipal closed-end funds, no operating company); John Hancock Investors Trust (759828), Income Securities Trust (759866), Bond Trust (315554), Sovereign Bond Fund (45288), Strategic Series (792858), Municipal Securities Trust (857769), California Tax-Free Income Fund (856671), Current Interest (26262), Collateral Trust (1631942), the GA Mortgage / GA Senior Loan / CQS / Marathon private-credit funds (no vote-table exhibit or none with operating-company votes); Investment Trust III (791271), Series Trust (357238), Tax-Exempt Series Fund (811921) and Collateral Investment Trust (1465214) (no N-PX since 2023 or earlier); the institutional-manager N-PX of John Hancock Investment Management LLC (1230788: 206 votes of 2 shares each in 2024, 3 votes in 2025, no exhibit in 2026) and John Hancock Life Insurance Co (USA) (1073894: 4 operating-company votes in 2024, a stub in 2025) and Manulife Investment Management (US) LLC (1034182, a 5 MB institutional-account N-PX under its own policy, a candidate for a separate MANULIFE_IM institution); and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
      - "Policy text: the Manulife Investment Management Global Proxy Voting Policy and Procedures PDF on manulifeim.com answers honest clients with 403 (HEAD, 2026-11-20): not evaded, so the label is filled from the Wayback index (eight captures 2021-09-17 to 2026-07-21, five distinct digests; the 2023-05-07 capture is a 301). Under a separate label, the policy as printed in Appendix C of the John Hancock Variable Insurance Trust SAI (March 2020 edition in the SAIs of 2021, April 2021 edition in 2022-2023, a re-typeset April 2021 edition in the 2023-11 Funds II SAI). The SAI route is partial: each SAI prints only the subadvisers' policies for its own series, and the heading after the Manulife policy differs by SAI (next subadviser's policy)."
    commitments:
      # The Manulife IM Global Proxy Voting Policy PDF; manulifeim.com answers 403 to honest clients (Akamai-style error page, 2026-11-20), so this label is filled by the Wayback walk (id_ endpoint) and a live fetch is logged as a failed attempt.
      # Wayback captures: 2021-09-17, 2021-12-14, 2023-06-07, 2024-07-04 (digest SY52VCHB...), 2025-08-27, 2026-01-14, 2026-07-21 (three further digests). It is a PDF, so no `body` bound is needed.
      - label: manulife-im-global-proxy-voting-policy-and-procedures
        url: "https://www.manulifeim.com/content/dam/mim-institutional/global/documents/policies/Manulife-IM-Global-Proxy-Voting-Policy-and-Procedures.pdf"
        adviser: "Manulife Investment Management (US) LLC and its advisory affiliates"
        adviser_key: "MANULIFE_IM"
        access: {status: blocked, reason: "manulifeim.com answers honest clients with 403; documented in METHODOLOGY, never evaded", checked: "2026-11-20"}
      # The same policy as printed in Appendix C of the John Hancock Variable Insurance Trust SAI, dated by EDGAR filing date. Separate label from the website PDF. VERIFY ENDS BEFORE USE: starts matched exactly once in the five SAIs read
      # (Funds II 2021-04-26 / 2022-11-21 / 2023-11-17, Variable Insurance Trust 2021-04-23 / 2023-04-21); the policy is followed by 'PART C OTHER INFORMATION' (Lifestyle SAI of 2021), the Nordea engagement policy (Funds II 2022-11, 2023-11) or the Allspring policy (VIT 2023-04);
      # VIT 2021-04 and the 2022 VIT SAI were not checked. The multi-SAI 485BPOS prints Appendix C once per SAI, so allow_identical_copies is set; a dry run must confirm one edition per filing.
      - label: manulife-im-global-proxy-voting-policy-as-printed-in-sai
        adviser: "Manulife Investment Management (US) LLC and its advisory affiliates"
        adviser_key: "MANULIFE_IM"
        sai_appendix:
          cik: "0000756913"
          forms: ["485BPOS"]
          since: "2021-01-01"
          allow_identical_copies: true
          start:
            - "MANULIFE INVESTMENT MANAGEMENT GLOBAL PROXY VOTING POLICY AND PROCEDURES March 2020 Executive Summary"
            - "MANULIFE INVESTMENT MANAGEMENT GLOBAL PROXY VOTING POLICY AND PROCEDURES April 2021 Executive summary"
            - "Manulife Investment Management global proxy voting policy and procedures Executive summary"
          end:
            - "PART C OTHER INFORMATION"
            - "NORDEA ASSET MANAGEMENT ENGAGEMENT POLICY"
            - "ALLSPRING GLOBAL INVESTMENTS, LLC PROXY VOTING POLICIES AND PROCEDURES"
          strip_page_numbers: true
```
