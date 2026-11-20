# Artisan Partners (Artisan Partners Limited Partnership) - research for institutions.yaml

Research only, read 2026-11-20 via glasshouse.http (EDGAR) and curl with the honest UA (artisanpartners.com). Nothing in data/, config/ or the ledger was touched.

## 1. Registrants with N-PX vote tables, operating-company votes 2024-2026

| CIK | Name (data.sec.gov) | Type | N-PX seasons with XML vote tables |
|---|---|---|---|
| 935015 | ARTISAN PARTNERS FUNDS INC | open-end, 21 series (see below) | 2024-09-03 (0001999371-24-011266, 12,416 vote rows, filer lists Artisan Partners Limited Partnership), 2025-08-27 (0002000324-25-003267), 2026-08-31 (0002000324-26-004253) |

Series in the 2024 N-PX: S000006493 International, S000006494 International Small-Mid, S000006495 International Value, S000006496 Mid Cap, S000006497 Mid Cap Value, S000006498 Small Cap, S000006537 Value, S000012854 Sustainable Emerging Markets, S000019611 Global Value, S000023270 Global Opportunities, S000028207 Global Equity, S000044335 High Income, S000049420 Developing World, S000056665 Focus, S000058458 Global Discovery, S000067908 Select Equity, S000074472 Floating Rate, S000075101 Emerging Markets Debt Opportunities, S000075102 Global Unconstrained, S000075425 Value Income, S000076279 International Explorer.

There is no closed-end Artisan registrant (the EDGAR name search finds no other Artisan registered fund; the many "Artisan ... Fund LP / Ltd" entities are private funds or unrelated). The adviser Artisan Partners Limited Partnership has no N-PX of its own that was found; the 13F filer on EDGAR is ARTISAN PARTNERS HOLDINGS LP (CIK 1010643, 49 13F-HR, no N-PX); Artisan Partners Asset Management Inc. (1517302) files no N-PX. Artisan Partners UK LLP and the Irish Artisan Partners Global Funds plc are not US registrants.

No Form N-CEN (FY2021 to FY2025, five read, 16 then 21 series) lists a sub-adviser; the only adviser is Artisan Partners Limited Partnership. The SAIs of 2021, 2023 and 2026 contain no sub-adviser or Artisan Partners UK reference.

## 2. Earliest SAI read and exact quotes

The SAI is a stand-alone document (no appendix); the policy is the SAI section "Proxy Voting" (about 10,300 characters, 2021 to 2026).

- Earliest 2021-2023 SAI read: 485BPOS filed 2021-01-28, 0001193125-21-020845 (d43626d485bpos.htm). Also read 0001193125-23-019181 (2023-01-30) and 0001193125-26-027345 (2026-01-28). Other SAI-bearing 485BPOS: 2022-01-28, 2022-02-18, 2022-02-25, 2022-04-27, 2022-05-09, 2024-01-29, 2025-01-28, 2026-11-13.

Quote, 2021-01-28 SAI:
> "The Funds have delegated responsibility for proxy voting to Artisan Partners. Artisan Partners votes proxies solicited by or with respect to the issuers of securities held by the Funds."
> "When making proxy voting decisions, Artisan Partners generally adheres to proxy voting guidelines that set forth Artisan Partners' proxy voting positions on recurring issues and criteria for addressing non-recurring issues."
> "Artisan Partners retains final authority and fiduciary responsibility for the voting of proxies."

("Artisan Partners" is defined on the first page as "Artisan Partners Limited Partnership".) 2023 and 2026 SAIs: same text with the first sentence reading "Artisan Partners Funds has delegated responsibility for proxy voting to Artisan Partners." The primary proxy service provider only executes ("does not have the authority to vote proxies except in accordance with standing or specific instructions"), and the firm's own policy (website PDF) says ISS recommends policies for adoption and "Artisan Partners retains final authority". So votes follow Artisan's own policy: key ARTISAN_PARTNERS.

## 3. Proposed YAML

```yaml
  artisan_partners:
    display_name: "Artisan Partners (Artisan Partners Limited Partnership)"
    short_name: "Artisan Partners"
    cik: "0001010643"
    country: "USA"
    type: "asset_manager"
    aum_usd_tr: 0.0
    notes: "Artisan Partners Limited Partnership, Milwaukee WI, the investment adviser of the Artisan Partners Funds (the operating partnership of Artisan Partners Asset Management Inc., CIK 1517302; CIK 1010643, Artisan Partners Holdings LP, is the 13-F filer used as the institution CIK; the adviser entity itself has no CIK of its own that was found). One US fund registrant files N-PX vote tables: Artisan Partners Funds Inc (CIK 935015, 21 series). Every SAI says 'The Funds [Artisan Partners Funds] have [has] delegated responsibility for proxy voting to Artisan Partners. Artisan Partners votes proxies ... When making proxy voting decisions, Artisan Partners generally adheres to proxy voting guidelines that set forth Artisan Partners' proxy voting positions', with a proxy service provider (ISS) in a research and administrative role only; no Form N-CEN (FY2021 to FY2025) names a sub-adviser. aum_usd_tr is not verified."
    npx_ciks:
      # Added <date>. The only Artisan US fund registrant that files N-PX vote tables is Artisan Partners Funds Inc (CIK 935015; the open-end series list is in the 2024-2026 N-PX). Every SAI read (2021-01-28, 2023-01-30, 2026-01-28) prints, in the section 'Proxy Voting', 'The Funds have delegated responsibility for proxy voting to Artisan Partners. Artisan Partners votes proxies solicited by or
      # with respect to the issuers of securities held by the Funds' (2023 and 2026: 'Artisan Partners Funds has delegated ...'); 'Artisan Partners' is Artisan Partners Limited Partnership. No N-CEN (five read, FY2021 to FY2025) lists a sub-adviser, so there is no series exception. ARTISAN_PARTNERS is dated from the EDGAR filing date of the earliest SAI read.
      - cik: "935015"
        adviser: "Artisan Partners Limited Partnership (the Adviser); no sub-adviser"
        adviser_source: "https://www.sec.gov/Archives/edgar/data/935015/000119312521020845/d43626d485bpos.htm"  # 485BPOS (SAI) filed 2021-01-28 (0001193125-21-020845), 'Proxy Voting': the Funds delegated voting to Artisan Partners, which votes under its guidelines
        adviser_verified: "<date>"
        voting_note: "SAI 'Proxy Voting': 'The Funds have delegated responsibility for proxy voting to Artisan Partners. Artisan Partners votes proxies solicited by or with respect to the issuers of securities held by the Funds' (earliest SAI read 2021-01-28, 0001193125-21-020845; 2023-01-30 and 2026-01-28 read 'Artisan Partners Funds has delegated ...'). 'Artisan Partners generally adheres to proxy voting guidelines that set forth Artisan Partners' proxy voting positions'; the proxy service provider only executes under Artisan Partners' instructions and 'Artisan Partners retains final authority'. Every Form N-CEN (2021-12 to 2025-12) names Artisan Partners Limited Partnership as the only adviser and no sub-adviser."
        adviser_key_history: [{key: ARTISAN_PARTNERS, from: "2021-01-28"}]
        name: "ARTISAN PARTNERS FUNDS INC"
        validated: "<date>"   # entity name confirmed via data.sec.gov submissions API
    voting_scope_notes:
      - "Keyed ARTISAN_PARTNERS from the EDGAR filing date of the earliest SAI read (485BPOS 2021-01-28, 0001193125-21-020845); earlier meetings stay unlabelled. No SAI or N-CEN names a sub-adviser, so every series carries the registrant key."
      - "Not ingested (left out): Artisan Partners Limited Partnership has no institutional-manager N-PX found, Artisan Partners Asset Management Inc. (1517302) and Holdings LP (1010643) file none, the Irish Artisan Partners Global Funds plc is not a US registrant, and the legacy-HTML N-PX before 2024 are not ingested without --legacy."
      - "Policy text: the Artisan Partners Proxy Voting Policy PDF on artisanpartners.com (28 pages, 200 application/pdf to honest clients 2026-11-20; robots.txt does not disallow it for this UA; Wayback captures 2015-09 to 2026-04) and the section 'Proxy Voting' as printed in the Artisan Partners Funds SAI. The website policy (an adviser-wide policy with Appendix A guidelines; ISS named) and the SAI section (a ten-thousand-character summary naming no vendor in 2021) are different documents and are archived under separate labels."
    commitments:
      # Verified 2026-11-20 (200, application/pdf, honest client). Applies to Artisan Partners Limited Partnership and Artisan Partners UK LLP; PDF metadata dates are 2026-11-02/03, so an edition date is printed inside it. Wayback: 2015-09-05, 2017-03-18, 2023-05-06, 2023-11-29, 2024-02-05, 2025-04-01, 2026-04-03.
      - label: artisan-partners-proxy-voting-policy
        url: "https://www.artisanpartners.com/content/dam/documents/legal/proxy-voting/Proxy-Voting-Policy.pdf"
        adviser: "Artisan Partners Limited Partnership"
        adviser_key: "ARTISAN_PARTNERS"
      # The SAI 'Proxy Voting' section (no appendix), dated by EDGAR filing date. Two spellings of the first sentence ('The Funds have' to 2022, 'Artisan Partners Funds has' from 2023): both starts listed. The table of contents also contains 'Proxy Voting 51', so the start strings include the first sentence.
      - label: artisan-partners-proxy-voting-as-printed-in-sai
        adviser: "Artisan Partners Limited Partnership"
        adviser_key: "ARTISAN_PARTNERS"
        sai_appendix:
          cik: "0000935015"
          forms: ["485BPOS"]
          since: "2021-01-01"
          allow_identical_copies: true
          start:
            - "Proxy Voting The Funds have delegated responsibility for proxy voting to Artisan Partners."
            - "Proxy Voting Artisan Partners Funds has delegated responsibility for proxy voting to Artisan Partners."
          end:
            - "Disclosure of Portfolio Holdings The board of directors has"
          strip_page_numbers: true
```

## 4. Open doubts

- The 2022 SAIs (2022-01-28 to 2022-05-09) were not text-read: the wording change from "The Funds have" to "Artisan Partners Funds has" happened somewhere between 2021-01-28 and 2023-01-30; a third spelling ("The Funds has") is not excluded. Read one 2022 SAI before activating the sai_appendix start strings. Page-number stripping ("Statement of Additional Information - Artisan Partners Funds | 51" mid-sentence in 2021) is unverified against the ingester's `strip_patterns`; likely needs `strip_patterns` for that running footer. Not run through the ingester (release build in progress).
- Institution CIK: no CIK found for Artisan Partners Limited Partnership; 1010643 (Artisan Partners Holdings LP) is the 13F filer. Maintainer may prefer 1517302 (the public parent).
- Series-level adviser: Artisan's autonomous investment teams "each take their own approach to the proxy voting process" (Sustainable Investing Policy), but the SAI and policy say Artisan Partners votes; no series exception made.
- The website policy URL has no previous-edition archive in the repo; Wayback captures exist (listed above).
- `<date>` placeholders: set to the commit date.
