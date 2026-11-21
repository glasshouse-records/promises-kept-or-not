# Coverage sweep list (2026-11-21)

Source: SEC Form N-CEN data sets 2025q4–2026q3 (latest N-CEN per registrant), `scripts/ncen_coverage.py`.
Assets = monthly average net assets of funds that are not money-market, fund-of-funds, target-date, or named as bond/income funds (a rough equity filter).
Covered = registrant CIK appears in config/institutions.yaml npx_ciks. At the time of writing: $10.6T of $17.8T equity-like assets (60%).

Some registrants below were deliberately left out (sub-advised, bond-only, no N-PX votes): check the institution's notes and ROADMAP before adding.

| assets $B | CIK | registrant | N-CEN family |
|--:|--:|---|---|
| 486 | 736054 | VANGUARD STAR FUNDS | The Vanguard Group, Inc. |
| 277 | 923202 | VANGUARD TAX-MANAGED FUNDS | The Vanguard Group, Inc. |
| 269 | 734383 | VANGUARD SPECIALIZED FUNDS | The Vanguard Group, Inc. |
| 234 | 24238 | Fidelity Contrafund | Fidelity Group of Funds |
| 189 | 933691 | JNL Series Trust | JNL Fund Complex |
| 175 | 754510 | Fidelity Securities Fund | Fidelity Group of Funds |
| 169 | 1209466 | Invesco Exchange-Traded Fund Trust | INVESCOETF |
| 158 | 744822 | Fidelity Investment Trust | Fidelity Group of Funds |
| 154 | 763852 | JPMorgan Trust II | JPMorgan Funds |
| 118 | 707823 | Fidelity Mt Vernon Street Trust | Fidelity Group of Funds |
| 118 | 105563 | VANGUARD WELLINGTON FUND | The Vanguard Group, Inc. |
| 112 | 1004655 | VANGUARD WHITEHALL FUNDS | The Vanguard Group, Inc. |
| 110 | 1567101 | BRIDGE BUILDER TRUST | BRIDGE BUILDER TRUST |
| 100 | 1027263 | EQ ADVISORS TRUST | EQFUNDS |
| 97 | 320351 | Fidelity Select Portfolios | Fidelity Group of Funds |
| 97 | 1485894 | J.P. Morgan Exchange-Traded Fund Trust | JPMorgan Funds |
| 95 | 106444 | VANGUARD FIXED INCOME SECURITIES FUNDS | The Vanguard Group, Inc. |
| 91 | 915092 | Master Investment Portfolio | BlackRock-advised Funds |
| 84 | 107606 | VANGUARD WINDSOR FUNDS | The Vanguard Group, Inc. |
| 82 | 906352 | First Eagle Funds | First Eagle Funds |
| 79 | 1724826 | Six Circles Trust | Six Circles Funds |
| 74 | 752177 | VANGUARD CHESTER FUNDS | The Vanguard Group, Inc. |
| 59 | 889519 | VANGUARD VALLEY FORGE FUNDS | The Vanguard Group, Inc. |
| 55 | 1557156 | Goldman Sachs Trust II | Goldman Sachs Fund Complex |
| 54 | 893818 | BlackRock Funds III | BlackRock-advised Funds |
| 52 | 914036 | LINCOLN VARIABLE INSURANCE PRODUCTS TRUST | LINCOLNTRS |
| 50 | 80257 | T. ROWE PRICE GROWTH STOCK FUND, INC. | TROWEPRICE |
| 50 | 872323 | HARRIS ASSOCIATES INVESTMENT TRUST | Oakmark Funds |
| 46 | 35348 | Fidelity Hastings Street Trust | Fidelity Group of Funds |
| 45 | 932471 | VANGUARD HORIZON FUNDS | The Vanguard Group, Inc. |
| 43 | 1112996 | AIM Counselor Series Trust (Invesco Counselor Series Trust) | INVESCOFDS |
| 43 | 1424958 | Direxion Shares ETF Trust | Direxion Shares ETF Trust |
| 43 | 1738078 | BlackRock Funds V | BlackRock-advised Funds |
| 41 | 1012968 | T. Rowe Price Equity Funds, Inc. | TROWEPRICE |
| 41 | 793769 | HARBOR FUNDS | Harbor Capital Advisors, Inc. |
| 38 | 719608 | NEW ECONOMY FUND | Capital Group Fund Group |
| 38 | 909994 | Old Westbury Funds Inc | Bessemer Investment Management LLC |
| 37 | 61397 | Fidelity Magellan Fund | Fidelity Group of Funds |
| 37 | 1616668 | Pacer Funds Trust | Pacer Advisors, Inc. |
| 36 | 1413032 | Columbia Funds Variable Series Trust II | Columbia Funds Complex |
| 36 | 892538 | SUNAMERICA SERIES TRUST | SUNAMERICA |
| 35 | 844779 | BlackRock Funds | BlackRock-Advised Funds |
| 35 | 1126087 | Brighthouse Funds Trust I | Brighthouse Investment Advisers, LLC |
| 35 | 725781 | AIM Sector Funds (Invesco Sector Funds) | INVESCOFDS |
| 34 | 35341 | Fidelity Devonshire Trust | Fidelity Group of Funds |
| 34 | 710826 | Brighthouse Funds Trust II | Brighthouse Investment Advisers, LLC |
| 33 | 105377 | AIM Equity Funds (Invesco Equity Funds) | INVESCOFDS |
| 32 | 857490 | VANGUARD VARIABLE INSURANCE FUNDS | The Vanguard Group, Inc. |
| 31 | 883622 | IVY FUNDS | Nomura Funds (formerly, Macquarie Funds) |
| 31 | 1735964 | Cliffwater Corporate Lending Fund | Cliffwater |
| 31 | 1593547 | Advisors' Inner Circle Fund III | GQG PARTNERS LLC |
| 31 | 939934 | SEI INSTITUTIONAL INVESTMENTS TRUST | SEI Funds |
| 30 | 813900 | PACIFIC SELECT FUND | Pacific Life Fund Advisors LLC |
| 30 | 927845 | T. ROWE PRICE VALUE FUND, INC. | TROWEPRICE |
| 29 | 719423 | VALIC Co I | VALIC Company |
| 29 | 353905 | Nationwide Variable Insurance Trust | Nationwide Mutual Funds |
| 29 | 945908 | Fidelity Covington Trust | Fidelity Group of Funds |
| 28 | 805650 | Franklin Managed Trust | Franklin Templeton Group of Funds |
| 28 | 887147 | T. ROWE PRICE MID-CAP GROWTH FUND, INC. | TROWEPRICE |
| 27 | 356476 | EMPOWER FUNDS, INC. | Empower Capital Management, LLC |
| 27 | 794105 | VANGUARD BOND INDEX FUNDS | The Vanguard Group, Inc. |
| 27 | 810893 | PIMCO FUNDS | PIMCOFUNDS |
| 27 | 275309 | Fidelity Capital Trust | Fidelity Group of Funds |
| 26 | 52848 | VANGUARD WORLD FUND | The Vanguard Group, Inc. |
| 25 | 816153 | THORNBURG INVESTMENT TRUST | THORNBURG |
| 24 | 356494 | Variable Insurance Products Fund | Fidelity Group of Funds |
| 24 | 880859 | AIM International Mutual Funds (Invesco International Mutual Funds) | INVESCOFDS |
| 24 | 894024 | T. ROWE PRICE DIVIDEND GROWTH FUND, INC. | TROWEPRICE |
| 24 | 823620 | AMERICAN HIGH INCOME TRUST | Capital Group Fund Group |
| 23 | 742212 | NORTHWESTERN MUTUAL SERIES FUND INC | Mason Street Advisors, LLC |
| 23 | 825063 | Franklin Mutual Series Funds | Franklin Templeton Group of Funds |
| 23 | 772129 | GMO TRUST | GMO Registered Funds |
| 23 | 1415726 | Innovator ETFs Trust | Innovator Capital Management, LLC |
| 23 | 803747 | JP Morgan Mutual Fund Investment Trust | JPMorgan Funds |
| 21 | 34066 | VANGUARD EXPLORER FUND | The Vanguard Group, Inc. |
| 20 | 1303459 | Fidelity Central Investment Portfolios LLC | Fidelity Group of Funds |
| 19 | 315700 | Fidelity Advisor Series VII | Fidelity Group of Funds |
| 19 | 778207 | TRANSAMERICA SERIES TRUST | TRANSAMERICA |
| 19 | 1462712 | T. ROWE PRICE U.S. LARGE-CAP CORE FUND, INC. | TROWEPRICE |
| 19 | 810902 | BARON INVESTMENT FUNDS TRUST (f/k/a BARON ASSET FUND) | BARONFUNDS |
| 19 | 814507 | BlackRock Equity Dividend Fund | BlackRock-advised Funds |
| 17 | 1217673 | BARON SELECT FUNDS | BARONFUNDS |
| 17 | 834237 | BlackRock Global Allocation Fund, Inc. | BlackRock-advised Funds |
| 16 | 1450011 | PIMCO ETF Trust | PIMCOFUNDS |
| 16 | 1156906 | CAUSEWAY CAPITAL MANAGEMENT TRUST | CAUSEWAY CAPITAL MANAGEMENT TRUST                                                      |
| 16 | 1655589 | Franklin Templeton ETF Trust | Franklin Templeton Group of Funds |
| 16 | 1293967 | PRIMECAP Odyssey Funds | PRIMECAP Management Company |
| 16 | 1447247 | Partners Group Private Equity Fund, LLC | Partners Group Registered Funds |
| 16 | 1444822 | AQR Funds | AQR Funds |
| 16 | 1548609 | Brown Advisory Funds | Brown Advisory LLC |
| 16 | 80248 | T. ROWE PRICE NEW HORIZONS FUND, INC. | TROWEPRICE |
| 15 | 1414040 | ALPS ETF Trust | ALPS Advised Funds |
| 15 | 1048702 | Nationwide Mutual Funds | Nationwide Mutual Funds |
| 15 | 1012678 | T. ROWE PRICE MID-CAP VALUE FUND, INC. | TROWEPRICE |
| 15 | 1503123 | DBX ETF Trust | XTRACKERS |
| 15 | 1131013 | GuideStone Funds | GuideStone Capital Management, LLC |
| 15 | 313850 | VANGUARD TRUSTEES' EQUITY FUND | The Vanguard Group, Inc. |
| 15 | 1491978 | FlexShares Trust | Northern Trust Investments, Inc. |
| 14 | 1018170 | HARDING LOEVNER FUNDS INC | Harding Loevner LP |
| 14 | 1011008 | State Street Navigator Securities Lending Trust | State Street Investment Management Funds |
| 14 | 1120543 | Baillie Gifford Funds | Baillie Gifford Funds |
| 13 | 1089951 | AMG Funds | AMGFUNDSGR |
| 13 | 896435 | AIM Variable Insurance Funds (Invesco Variable Insurance Funds) | INVESCOFDS |
| 12 | 826473 | VANGUARD FENWAY FUNDS | The Vanguard Group, Inc. |
| 12 | 1516523 | Advisers Investment Trust | State Farm Investment Management Corp. |
| 12 | 1032423 | Diamond Hill Funds | Diamond Hill Funds |
| 12 | 1002624 | T. ROWE PRICE HEALTH SCIENCES FUND, INC. | TROWEPRICE |
| 12 | 872625 | FRANKLIN STRATEGIC SERIES | Franklin Templeton Group of Funds |
| 12 | 809821 | Delaware Group Equity Funds V | Nomura Funds (formerly, Macquarie Funds) |
| 12 | 1378872 | Invesco Exchange-Traded Fund Trust II | INVESCOETF |
| 12 | 822632 | WILLIAM BLAIR FUNDS | William Blair Investment Management, LLC |
| 12 | 1037897 | JP Morgan Fleming Mutual Fund Group Inc | JPMorgan Funds |
| 12 | 1848758 | NEOS ETF Trust | NEOS Investment Management, LLC |
| 11 | 1995745 | Venerable Variable Insurance Trust | Venerable Investment Advisers, LLC |
| 11 | 1579982 | ARK ETF Trust | ARKETFTRUS |
| 11 | 837274 | Franklin Templeton Variable Insurance Products Trust | Franklin Templeton Group of Funds |
| 11 | 1761055 | BlackRock ETF Trust | BlackRock-advised Funds |
| 11 | 806633 | WASATCH FUNDS TRUST | Wasatch Funds |
| 11 | 1015965 | Voya VARIABLE PORTFOLIOS INC | Voya mutual funds |
| 11 | 795259 | MoA Funds Corp | MUTUAL OF AMERICA CAPITAL MANAGEMENT LLC |
| 11 | 897111 | Carillon Series Trust | Carillon Tower Advisers, Inc. |
| 11 | 1486048 | T. ROWE PRICE REAL ASSETS FUND, INC. | TROWEPRICE |
| 11 | 867297 | Virtus Investment Trust | Virtus Funds |
| 11 | 916053 | MASSMUTUAL SELECT FUNDS | MASSMUTUAL FUNDS |
| 11 | 819930 | T. ROWE PRICE SCIENCE & TECHNOLOGY FUND, INC. | TROWEPRICE |
| 10 | 1659326 | JPMorgan Trust IV | JPMorgan Funds |
| 10 | 1105446 | Calvert Responsible Index Series, Inc. | Calvert |
| 10 | 1091439 | ALLIANZ VARIABLE INSURANCE PRODUCTS TRUST |  ALLIANZ FUNDS |
| 10 | 834798 | T. ROWE PRICE SMALL-CAP VALUE FUND, INC. | TROWEPRICE |
| 10 | 1689873 | GraniteShares ETF Trust | GraniteShares ETF Trust |
| 9 | 1467631 | ACAP STRATEGIC FUND | Silverbay Capital Management LLC |
| 9 | 1047712 | UNDISCOVERED MANAGERS FUNDS | JPMorgan Funds |
| 9 | 355916 | BlackRock Variable Series Funds, Inc. | BlackRock-advised Funds |
| 9 | 1038469 | T. ROWE PRICE INTEGRATED EQUITY FUNDS, INC. | TROWEPRICE |
| 9 | 88525 | Guggenheim Funds Trust | Guggenheim |
| 9 | 1097077 | BlackRock Large Cap Series Funds, Inc. | BlackRock-Advised Funds |
| 9 | 1547576 | Krane Shares Trust | Krane Funds Advisors, LLC                                                              |
| 9 | 805664 | TEMPLETON GROWTH FUND INC | Franklin Templeton Group of Funds |
| 8 | 1479360 | PIMCO Equity Series | PIMCOFUNDS |
| 8 | 1870117 | Capital Group Fixed Income ETF Trust | Capital Group Fund Group |
| 8 | 75170 | T. ROWE PRICE SMALL-CAP STOCK FUND, INC. | TROWEPRICE |
| 8 | 1041917 | COHEN & STEERS REAL ESTATE SECURITIES FUND INC | COHENSTEER |
| 8 | 702340 | Penn Series Funds Inc | Penn Mutual Asset Management, LLC |
| 8 | 934563 | HC Capital Trust | HC Capital Solutions an operating division of Hirtle Callaghan & Co., LLC |
| 8 | 923084 | T. ROWE PRICE SPECTRUM FUNDS II, INC. | TROWEPRICE |
| 8 | 205323 | Fidelity Commonwealth Trust | Fidelity Group of Funds |
| 8 | 1023391 | FMI Funds Inc | Fiduciary Management, Inc. |
| 8 | 1096903 | COHEN & STEERS INSTITUTIONAL REALTY SHARES INC | COHENSTEER |
| 8 | 1738074 | BlackRock Funds IV | BlackRock-advised Funds |
| 8 | 356682 | Calvert Social Investment Fund | Calvert |
| 8 | 874505 | COHEN & STEERS REALTY SHARES INC | COHENSTEER |
| 7 | 1872555 | Catholic Responsible Investments Funds | Christian Brothers Investment Services, Inc. |
| 7 | 809707 | Franklin Investors Securities Trust | Franklin Templeton Group of Funds |
| 7 | 1355064 | Mutual Fund Series Trust | Mutual Fund Series Trust |
| 7 | 1688680 | Brinker Capital Destinations Trust | Brinker Capital Investments, LLC |
| 7 | 225030 | AFL CIO Housing Investment Trust | AFL CIO Housing Investment Trust |
| 7 | 1406305 | Gateway Trust | Natixis Loomis Sayles Funds |
| 7 | 202032 | AIM Growth Series (Invesco Growth Series) | INVESCOFDS |
| 7 | 711080 | Touchstone Strategic Trust | Touchstone Funds |
| 7 | 1320615 | Mercer Funds | MERCERGLIN |
| 7 | 1842754 | Cliffwater Enhanced Lending Fund | Cliffwater |
| 7 | 1475712 | Global Opportunities Portfolio | EatonVance |
| 7 | 1070222 | NEW COVENANT FUNDS | SEI Funds Complex |
| 7 | 1657201 | Invesco Exchange-Traded Self-Indexed Fund Trust | INVESCOETF |
| 7 | 865177 | Putnam Sustainable Leaders Fund | Putnam Family of Funds |
| 6 | 1359057 | Manager Directed Portfolios | Hood River Capital Management LLC |
| 6 | 766285 | AMANA MUTUAL FUNDS TRUST | SATURNA CAPITAL CORPORATION |
| 6 | 720318 | Variable Insurance Products Fund IV | Fidelity Group of Funds |
| 6 | 1002667 | Tax-Managed Growth Portfolio | EatonVance |
| 6 | 1830437 | Perpetual Americas Funds Trust | Perpetual Americas Funds Trust |
| 6 | 875610 | Delaware Group Global & International Funds | Nomura Funds (formerly, Macquarie Funds) |
| 6 | 1227523 | Optimum Fund Trust | Nomura Funds (formerly, Macquarie Funds) |
| 6 | 1609212 | AMG Pantheon Master Fund, LLC | AMG Fund Complex |
| 6 | 709364 | ROYCE FUND | ROYCEFUNDS |
| 6 | 76721 | IMPAX FUNDS SERIES TRUST I | Impax Funds |
| 6 | 1609211 | AMG Pantheon Fund, LLC | AMG Fund Complex |
| 6 | 933188 | Senior Debt Portfolio | EatonVance |
| 6 | 835597 | SEI INSTITUTIONAL INTERNATIONAL TRUST | SEI Funds |
| 6 | 1810747 | Simplify Exchange Traded Funds | Simplify Asset Management Inc. |
| 6 | 890540 | Advisors' Inner Circle Fund II | Vontobel Asset Management, Inc. |
| 6 | 1016073 | Driehaus Mutual Funds | Driehaus Capital Management LLC |
| 6 | 1272950 | RBC Funds Trust | RBC Global Asset Management (US) Inc. |
| 6 | 357298 | PERMANENT PORTFOLIO FAMILY OF FUNDS | Pacific Heights Asset Management, LLC |
| 6 | 810016 | Ivy Variable Insurance Portfolios | Nomura Funds (formerly, Macquarie Funds) |
| 6 | 1388485 | FundVantage Trust | Polen Advised Funds for FundVantage Trust and Polen Credit Opportunities Fund |
| 5 | 1643174 | Horizon Funds | Horizon Funds |
| 5 | 28540 | Fidelity Oxford Street Trust | Fidelity Group of Funds |
| 5 | 911415 | ALGER INSTITUTIONAL FUNDS | Alger Family of Funds |
| 5 | 875186 | MORGAN STANLEY PATHWAY FUNDS | MORGAN STANLEY PATHWAY FUNDS |
| 5 | 225930 | Templeton Funds | Franklin Templeton Group of Funds |
| 5 | 918294 | T. ROWE PRICE EQUITY SERIES, INC. | TROWEPRICE |
| 5 | 1789470 | StepStone Private Markets | StepStone Group Private Wealth LLC |
| 5 | 896975 | Tweedy, Browne Fund Inc. | Tweedy, Browne Company LLC |
| 5 | 1614370 | Smead Funds Trust | Smead Capital Management, Inc. |
| 5 | 1806095 | Datum One Series Trust | Brandes Investment Partners LP |
| 5 | 737800 | LORD ABBETT MUNICIPAL INCOME FUND INC | LORDABBETT |
| 5 | 923184 | Matthews International Funds | Matthews International Capital Management, LLC |
| 5 | 1116914 | Eaton Vance Floating Rate Portfolio/MA | EatonVance |
| 5 | 1169187 | T. ROWE PRICE INSTITUTIONAL INCOME FUNDS, INC. | TROWEPRICE |
| 5 | 826732 | CALAMOS INVESTMENT TRUST/IL | Calamos Family of Funds |
