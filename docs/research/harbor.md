# Harbor (Harbor Capital Advisors, Inc.) - source research for config/institutions.yaml

Research only, 2026-11-20. Nothing ingested, nothing in data/ or config/ touched. EDGAR reads via `glasshouse.http.get`
(honest UA); harborcapital.com and Wayback probes with curl and the same honest UA.

## 1. Registrants that file N-PX vote tables with operating-company votes, 2024-2026

Harbor Capital Advisors, Inc. (CIK 1039128, 13-F filer, adviser of all three trusts) delegates voting to sub-advisers for nearly
every series. Each trust files TWO N-PX batches a year; one (08-25/08-28) lists only series with no votes and carries no vote table.

| CIK | Name | N-PX with vote table (2024 / 2025 / 2026), series count |
|---|---|---|
| 793769 | HARBOR FUNDS (formerly HARBOR FUND) | 0001438934-24-001108 (14 series, 21.7 MB) / 0001438934-25-001958 (13, 19.7 MB) / 0001438934-26-001820 (11, 22.0 MB). No-table batches: 0001994489-24-000004, 0001438934-25-001817, 0001438934-26-001626 |
| 1860434 | Harbor ETF Trust | 0001438934-24-001106 (10 series) / 0001438934-25-001972 (24) / 0001438934-26-001867 (25). No-table batches: 0001438934-25-001823 (6), 0001438934-26-001628 (7) |
| 1994489 | Harbor Funds II (Embark Commodity Strategy, Embark Small Cap Equity) | 0001438934-24-001110 / 0001438934-25-001825 / 0001438934-26-001840 (batches 0001994489-24-000003, 0001438934-25-001821, 0001438934-26-001622 hold no table) |

Not ingested / left out:
- Harbor Capital Advisors, Inc. (1039128): N-PX 2024/2025/2026 are notice filings "ALL VOTES BY OTHER PERSONS", no vote table.
- Harbor Advisory Corp /MA/ (1100710), Harbor Investment Advisory LLC (1468792), Harbor Island Capital LLC (1730580), Harbor Group Inc. (1840486):
  institutional-manager N-PX of firms with no evidence of affiliation (name match only). Do not key them HARBOR.
- Harbor Target Retirement funds (stopped before 2024), legacy-HTML N-PX before 2024.

## 2. Earliest 2021-2023 SAI read, and who votes

Funds 485BPOS in the filing list: 2021-02-23 (0001193125-21-052554), 2021-09-01 (-21-263390, -21-262351), 2022-02-23, 2023-02-24.
ETF Trust: N-1A 2021-05-05, first 485BPOS 2021-09-13 (0001193125-21-271678). Funds II: N-1A 2023-10-11, first 485BPOS 2024-01-19 (0001193125-24-011333),
so there is no 2021-2023 SAI for it (trust formed 2023).

| CIK | SAI (accession, date) | Quoted sentences |
|---|---|---|
| 793769 | 485BPOS 0001193125-21-052554, 2021-02-23 | "The Board delegates all responsibility for proxy voting with respect to portfolio holdings of the Funds to Harbor Capital Advisors, Inc. ("Harbor Capital")." / "Harbor Capital may further delegate its duties and responsibilities for proxy voting of Fund portfolio holdings to any subadviser (each a "Subadviser") that is retained by Harbor Capital to manage all or any segment of the assets of the Funds." / "Harbor Capital generally delegates proxy voting responsibility to each Subadviser with respect to the portion of the Fund's assets allocated by Harbor Capital to the Subadviser." / "The Harbor Target Retirement Funds are managed directly by Harbor Capital." / "For the proxy voting policy of each Subadviser, please see Appendix A." |
| 793769 | 485BPOS 0001193125-21-262351 / -21-263390, 2021-09-01 (restructured wording) | "For Funds with a discretionary Subadviser, Harbor Capital Advisers, Inc. ("Harbor Capital") delegates proxy voting to the Subadviser." / "Each Subadviser is required to provide to Harbor Capital, upon request, the necessary information regarding its proxy voting record to enable Harbor Capital to prepare the Form N-PX for the Subadvised Products." / "For the proxy voting policy of each discretionary Subadviser, please see Appendix A." |
| 1860434 | 485BPOS 0001193125-21-271678, 2021-09-13 (same text in 0001193125-22-023425, 2022-01-31) | "For Funds with a discretionary Subadviser, Harbor Capital Advisers, Inc. ("Harbor Capital") delegates proxy voting to the Subadviser." / "In each instance where Harbor Capital has retained proxy voting authority, the Multi-Asset Solutions Team ("MAST") will generally administer proxy voting ... in accordance with Harbor Capital's proxy voting guidelines ... Harbor Capital engages a proxy advisory firm (the "Advisory Firm")." The SAI does not say WHICH series are discretionary or retained. |
| 1994489 | 485BPOS 0001193125-24-011333, 2024-01-19 (first; outside 2021-2023) | "For Funds with a discretionary Subadvisor, Harbor Capital delegates proxy voting to the Subadvisor." The SAI names the Embark subadvisors (AQR, CoreCommodity, Neuberger Berman, Quantix, SIMNA, Summerhaven for the Commodity fund; Copeland, Granahan, Hotchkis and Wiley, Punch, Reinhart, Shapiro, Westfield for Small Cap). |

Series classification used below comes from the Forms N-CEN (sub-adviser per series; 2021-01 to 2026-01 read for 793769, 2022-01 to 2026-01 for 1860434,
2025-01 and 2026-01 for 1994489), because the SAI does not map series to delegation. Rule: an EXTERNAL sub-adviser listed in EVERY N-CEN
the series appears in -> EXTERNAL; Harbor Capital itself listed as sub-adviser, no sub-adviser listed, or a change between those -> UNRESOLVED
(do NOT key HARBOR_CAPITAL until the SAI or a Harbor document says which series Harbor retains). `from` = EDGAR date of the earliest SAI read for that
registrant (the rule is inert before a series launched). Because every non-delegated series is UNRESOLVED, the registrant default is UNRESOLVED.

Series (793769, all EXTERNAL; sub-adviser per latest N-CEN): S000000681 Capital Appreciation (Jennison); S000000682 Core Plus (Income Research & Management; was Harbor Bond, PIMCO, until 2022);
S000000685 Disruptive Innovation (was Mid Cap Growth, Wellington; 2023: NZS, Sands, 4BIO, Tekne, Westfield); S000000686 Small Cap Growth (Westfield); S000000687 Large Cap Value (Aristotle);
S000000688 Mid Cap Value (LSV); S000000689 Small Cap Value (EARNEST); S000000690 International (Marathon); S000000691 International Growth (Baillie Gifford, N-CEN to 2024-01);
S000025062 Global Leaders (Sands, N-CEN to 2023-01); S000032104 Convertible Securities (Shenkman, BlueCove from 2026); S000051342 Diversified International All Cap (Marathon);
S000052663 International Small Cap (Cedar Street); S000061981 Core Bond (IR&M); S000064886 International Core (Acadian); S000067063 Mid Cap (EARNEST); S000084021 International Compounders Fund (C WorldWide, N-CEN 2025+).

## 3. Proposed YAML (paste-ready; not applied)

```yaml
  harbor:
    display_name: "Harbor (Harbor Capital Advisors, Inc.)"
    short_name: "Harbor"
    cik: "0001039128"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Harbor Capital Advisors, Inc., Chicago IL (CIK 1039128, the 13-F filer and the investment adviser of Harbor Funds, Harbor ETF Trust and Harbor Funds II; its own institutional-manager N-PX is a notice of 'ALL VOTES BY OTHER PERSONS' with no vote table). Three open-end fund registrants that file N-PX vote tables are ingested. Every SAI read (2021-2024) says that 'For Funds with a discretionary Subadviser, Harbor Capital ... delegates proxy voting to the Subadviser', each of which votes under its own policy (SAI Appendix A), so the sub-advised series are keyed EXTERNAL by series_adviser. The SAI does not say which series Harbor Capital itself votes (it names a 'Multi-Asset Solutions Team' for 'each instance where Harbor Capital has retained proxy voting authority'), so those series and the registrants' default are UNRESOLVED. aum_usd_tr is not verified."
    npx_ciks:
      # Added 2026-11-20. Harbor Funds (793769), Harbor ETF Trust (1860434) and Harbor Funds II (1994489) are the only Harbor Capital registrants that file N-PX vote tables. Each files two N-PX batches a year (the 08-25/08-28 one carries no vote table).
      # Not ingested: Harbor Capital Advisors' own N-PX (1039128, notice 'ALL VOTES BY OTHER PERSONS'); unrelated same-name 13-F filers (Harbor Advisory Corp /MA/ 1100710, Harbor Investment Advisory 1468792, Harbor Island Capital 1730580, Harbor Group 1840486); legacy-HTML N-PX before 2024.
      - cik: "793769"
        adviser: "Harbor Capital Advisors, Inc. (the Adviser); every series in the 2024-2026 N-PX has a discretionary sub-adviser per Form N-CEN"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/793769/000119312521052554/d127232d485bpos.htm"  # 485BPOS (SAI) filed 2021-02-23 (0001193125-21-052554), 'Delegation of Responsibility for Proxy Voting'
        adviser_verified: "2026-11-20"
        voting_note: "SAI: 'Harbor Capital generally delegates proxy voting responsibility to each Subadviser with respect to the portion of the Fund's assets allocated by Harbor Capital to the Subadviser ... For the proxy voting policy of each Subadviser, please see Appendix A' (earliest SAI read 2021-02-23, 0001193125-21-052554); 2021-09-01 onward: 'For Funds with a discretionary Subadviser, Harbor Capital ... delegates proxy voting to the Subadviser' (0001193125-21-262351). Series with an external sub-adviser in every Form N-CEN (2021-01 to 2026-01) are EXTERNAL by series_adviser; the Harbor Target Retirement funds (managed by Harbor Capital, not in the 2024+ N-PX) are not listed."
        adviser_key_history: [{key: UNRESOLVED, from: "2021-02-23"}]
        series_adviser:
          S000000681: [{key: EXTERNAL, from: "2021-02-23"}]   # Capital Appreciation Fund: Jennison
          S000000682: [{key: EXTERNAL, from: "2021-02-23"}]   # Core Plus Fund (Harbor Bond Fund until 2022): PIMCO, then Income Research & Management
          S000000685: [{key: EXTERNAL, from: "2021-02-23"}]   # Disruptive Innovation Fund (Mid Cap Growth Fund until 2022): Wellington, then NZS/Sands/4BIO/Tekne/Westfield
          S000000686: [{key: EXTERNAL, from: "2021-02-23"}]   # Small Cap Growth Fund: Westfield
          S000000687: [{key: EXTERNAL, from: "2021-02-23"}]   # Large Cap Value Fund: Aristotle
          S000000688: [{key: EXTERNAL, from: "2021-02-23"}]   # Mid Cap Value Fund: LSV
          S000000689: [{key: EXTERNAL, from: "2021-02-23"}]   # Small Cap Value Fund: EARNEST
          S000000690: [{key: EXTERNAL, from: "2021-02-23"}]   # International Fund: Marathon
          S000000691: [{key: EXTERNAL, from: "2021-02-23"}]   # International Growth Fund: Baillie Gifford
          S000025062: [{key: EXTERNAL, from: "2021-02-23"}]   # Global Leaders Fund: Sands
          S000032104: [{key: EXTERNAL, from: "2021-02-23"}]   # Convertible Securities Fund: Shenkman, BlueCove from 2026
          S000051342: [{key: EXTERNAL, from: "2021-02-23"}]   # Diversified International All Cap Fund: Marathon
          S000052663: [{key: EXTERNAL, from: "2021-02-23"}]   # International Small Cap Fund: Cedar Street
          S000061981: [{key: EXTERNAL, from: "2021-02-23"}]   # Core Bond Fund: Income Research & Management
          S000064886: [{key: EXTERNAL, from: "2021-02-23"}]   # International Core Fund (Overseas Fund until 2025): Acadian
          S000067063: [{key: EXTERNAL, from: "2021-02-23"}]   # Mid Cap Fund: EARNEST
          S000084021: [{key: EXTERNAL, from: "2021-02-23"}]   # International Compounders Fund: C WorldWide
        name: "HARBOR FUNDS"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1860434"
        adviser: "Harbor Capital Advisors, Inc. (the Adviser); a mix of discretionary sub-advisers and Harbor-run series"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1860434/000119312521271678/d226931d485bpos.htm"  # 485BPOS (SAI) filed 2021-09-13 (0001193125-21-271678), 'Proxy Voting Policy: Delegated Proxy Voting Responsibility'
        adviser_verified: "2026-11-20"
        voting_note: "SAI: 'For Funds with a discretionary Subadviser, Harbor Capital ... delegates proxy voting to the Subadviser' and 'In each instance where Harbor Capital has retained proxy voting authority, the Multi-Asset Solutions Team ('MAST') will generally administer proxy voting' (earliest SAI read 2021-09-13, 0001193125-21-271678; same in 0001193125-22-023425). The SAI does not map series to delegation: series whose every Form N-CEN (2022-01 to 2026-01) names an external sub-adviser are EXTERNAL; series with Harbor Capital as its own sub-adviser, no sub-adviser, or a change between them (Disruptive Innovation ETF, Human Capital Factor ETFs, Multi-Asset Explorer, AlphaEdge ETFs, Active Small Cap ETF) and series with no N-CEN entry (S000080111, S000097720, S000098463, S000101665) stay on the UNRESOLVED registrant default."
        adviser_key_history: [{key: UNRESOLVED, from: "2021-09-13"}]
        series_adviser:
          S000072555: [{key: EXTERNAL, from: "2021-09-13"}]   # Scientific Alpha High-Yield ETF: BlueCove
          S000072556: [{key: EXTERNAL, from: "2021-09-13"}]   # Scientific Alpha Income ETF: BlueCove
          S000075162: [{key: EXTERNAL, from: "2021-09-13"}]   # Long-Term Growers ETF: Jennison
          S000075202: [{key: EXTERNAL, from: "2021-09-13"}]   # Commodity All-Weather Strategy ETF: Quantix
          S000075911: [{key: EXTERNAL, from: "2021-09-13"}]   # Dividend Growth Leaders ETF: Westfield
          S000076438: [{key: EXTERNAL, from: "2021-09-13"}]   # Energy Transition Strategy ETF: Quantix
          S000077093: [{key: EXTERNAL, from: "2021-09-13"}]   # International Compounders ETF: C WorldWide
          S000077996: [{key: EXTERNAL, from: "2021-09-13"}]   # Health Care ETF: Westfield
          S000081567: [{key: EXTERNAL, from: "2021-09-13"}]   # Long-Short Equity ETF: Disciplined Alpha
          S000084690: [{key: EXTERNAL, from: "2021-09-13"}]   # Disciplined Bond ETF: Income Research & Management
          S000088022: [{key: EXTERNAL, from: "2021-09-13"}]   # PanAgora Dynamic Large Cap Core ETF
          S000088918: [{key: EXTERNAL, from: "2021-09-13"}]   # Osmosis Emerging Markets Resource Efficient ETF (N-CEN 2026 only)
          S000088919: [{key: EXTERNAL, from: "2021-09-13"}]   # Osmosis International Resource Efficient ETF (N-CEN 2026 only)
          S000091658: [{key: EXTERNAL, from: "2021-09-13"}]   # Emerging Markets Select ETF: C WorldWide (N-CEN 2026 only)
          S000091659: [{key: EXTERNAL, from: "2021-09-13"}]   # Emerging Markets Equity ETF: EARNEST (N-CEN 2026 only)
          S000091660: [{key: EXTERNAL, from: "2021-09-13"}]   # International Equity ETF: EARNEST (N-CEN 2026 only)
          S000091661: [{key: EXTERNAL, from: "2021-09-13"}]   # Mid Cap Core ETF: EARNEST (N-CEN 2026 only)
          S000091662: [{key: EXTERNAL, from: "2021-09-13"}]   # Mid Cap Value ETF: EARNEST (N-CEN 2026 only)
          S000091663: [{key: EXTERNAL, from: "2021-09-13"}]   # SMID Cap Core ETF: EARNEST (N-CEN 2026 only)
          S000091664: [{key: EXTERNAL, from: "2021-09-13"}]   # SMID Cap Value ETF: EARNEST (N-CEN 2026 only)
          S000091665: [{key: EXTERNAL, from: "2021-09-13"}]   # Transformative Technologies ETF: Jennison (N-CEN 2026 only)
          S000093653: [{key: EXTERNAL, from: "2021-09-13"}]   # Alpha Layering ETF: PanAgora (N-CEN 2026 only)
        name: "Harbor ETF Trust"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
      - cik: "1994489"
        adviser: "Harbor Capital Advisors, Inc. (the Adviser); multi-manager sub-advisors named in the SAI"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/1994489/000119312524011333/d535092d485bpos.htm"  # 485BPOS (SAI) filed 2024-01-19 (0001193125-24-011333), first SAI of the trust (N-1A 2023-10-11)
        adviser_verified: "2026-11-20"
        voting_note: "SAI: 'For Funds with a discretionary Subadvisor, Harbor Capital delegates proxy voting to the Subadvisor' (earliest SAI 2024-01-19, 0001193125-24-011333, outside the 2021-2023 window: the trust was formed 2023-10). The SAI names the Subadvisors of both Embark funds; Form N-CEN 2025-01 lists none and 2026-01 lists them, so the rule is dated from the SAI."
        adviser_key_history: [{key: UNRESOLVED, from: "2024-01-19"}]
        series_adviser:
          S000083502: [{key: EXTERNAL, from: "2024-01-19"}]   # Embark Commodity Strategy Fund: AQR, CoreCommodity, Neuberger Berman, Quantix, Schroder, Summerhaven
          S000083503: [{key: EXTERNAL, from: "2024-01-19"}]   # Embark Small Cap Equity Fund: Copeland, Granahan, Hotchkis and Wiley, Punch, Reinhart, Shapiro, Westfield
        name: "Harbor Funds II"
        validated: "2026-11-20"   # entity name confirmed via data.sec.gov submissions API
    voting_scope_notes:
      - "Keyed per registrant from the EDGAR filing date of the earliest SAI read (Harbor Funds 2021-02-23, Harbor ETF Trust 2021-09-13, Harbor Funds II 2024-01-19); earlier meetings stay unlabelled. Sub-advised series are EXTERNAL (the sub-adviser votes under its own policy, SAI Appendix A); EXTERNAL votes are never paired with a policy document. Series where Harbor Capital itself may vote (listed as its own sub-adviser, or with none, in Form N-CEN) are UNRESOLVED because the SAI describes the retained-authority policy without naming the series."
      - "Policy text: none archived for the EXTERNAL series. Harbor Capital's own policy exists (the SAI section 'Proxy Voting Responsibility Retained by Harbor Capital', MAST/GRC with an Advisory Firm) but no series is keyed HARBOR_CAPITAL yet; see docs/research/harbor.md for the label to add once a series is promoted."
      - "Not ingested (left out): Harbor Capital Advisors' own institutional-manager N-PX (1039128, 'ALL VOTES BY OTHER PERSONS', no vote table), unrelated same-name 13-F filers (1100710, 1468792, 1730580, 1840486), the Harbor Target Retirement funds, and the legacy-HTML N-PX before 2024 (not ingested without --legacy)."
```

Optional label, only when a series is promoted from UNRESOLVED to a new key `HARBOR_CAPITAL` (add that key together with it):

```yaml
    commitments:
      # 200 application/pdf (honest client, 2026-11-20, 2,374,759 bytes). Page 1 of 2 is Harbor's 'Proxy Voting Policy' (delegation to Subadvisers; 'In certain instances where Harbor Capital has retained proxy voting authority, the Governance, Risk & Compliance Team ... will generally administer proxy voting'), but the file is a Microsoft 'Print To PDF' IMAGE with no text layer (pdftotext returns 142 characters), so it cannot be text-hashed. Wayback holds the PDF (2021-10-21, 2024-06-16) and the page https://www.harborcapital.com/proxy-voting/ (from 2021-10-16).
      - label: harbor-proxy-voting-policy
        url: "https://assets.harborcapital.com/docs/HF_Proxy_Guidelines.pdf"
        adviser: "Harbor Capital Advisors, Inc."
        adviser_key: "HARBOR_CAPITAL"
      # The retained-authority section as printed in the Harbor ETF Trust SAI (verified present in 0001193125-22-023425 only; the Funds 2021-02-23 SAI words it differently: 'The Board delegates all responsibility for proxy voting ... to Harbor Capital'). Not extractor-tested.
      - label: harbor-capital-retained-voting-as-printed-in-sai
        adviser: "Harbor Capital Advisors, Inc."
        adviser_key: "HARBOR_CAPITAL"
        sai_appendix:
          cik: "0001860434"
          forms: ["485BPOS"]
          since: "2021-09-01"
          allow_identical_copies: true
          start:
            - "PROXY VOTING RESPONSIBILITY RETAINED BY HARBOR CAPITAL In each instance where Harbor Capital has retained proxy voting authority"
          end:
            - "Recordkeeping Where Harbor Capital retains proxy voting responsibilities"
          strip_page_numbers: true
```

## 4. Open doubts

- The EXTERNAL rules rest on Form N-CEN sub-adviser lists, not on an SAI series list (the SAI never maps series to delegation). A series
  could still be Harbor-voted despite an external N-CEN sub-adviser; the SAI says delegation is "generally" to each Subadviser. N-CEN is annual
  (FY ends Oct 31, filed January) so mid-year sub-adviser changes are not dated.
- Harbor Funds 2021-02-23 SAI is conditional ("may further delegate", "generally delegates"); the unconditional "delegates proxy voting to the Subadviser"
  starts with the 2021-09-01 SAIs. The proposal dates EXTERNAL from 2021-02-23; for stricter precision use UNRESOLVED until 2021-08-31 and EXTERNAL from 2021-09-01.
- Series S000080111, S000097720, S000098463, S000101665 (Harbor ETF Trust) appear in N-PX but in no N-CEN read: left on the UNRESOLVED default.
  Active Small Cap ETF (S000086592: Harbor plus Byron Place in the 2025 N-CEN, Byron Place alone in 2026) is UNRESOLVED.
- Harbor Funds N-PX vote tables are 20+ MB each year; the 08-25/08-28 batches have no tables (expect zero-vote runs, not failures).
- Two 485BPOS were filed 2021-09-01 for CIK 793769 (0001193125-21-262351 and -21-263390, same content, 4.1 MB); the Funds' filing list also
  has single-fund 497 supplements that are not SAIs.
