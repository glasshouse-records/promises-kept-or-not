"""
SEC Major Enforcement Database (Non-FCPA)

Static snapshot of significant SEC enforcement actions against publicly-traded
companies for accounting fraud, securities fraud, and major disclosure violations.

Excludes FCPA cases (those are in the FCPATrackerClient database in classifier.py).
Focuses on:
  - Accounting/earnings fraud (fraudulent financial statements)
  - Securities fraud / material misrepresentation
  - Options backdating
  - Revenue recognition manipulation

Only includes resolved actions with significant civil penalties or criminal
referrals — not routine enforcement or small disclosure violations.

Source: SEC Litigation Releases (LR-xxxxx) + DOJ press releases
        https://www.sec.gov/litigation/litreleases.shtml
Data extracted: 2026-05-26

NOTE ON ACCURACY: Some of the largest 2000s-era cases (Enron, WorldCom,
Tyco, Adelphia) involved companies that subsequently went bankrupt; penalties
were largely uncollectable. However they are documented as evidence of
SEC enforcement against the entity that the fund may have held.

NLP INTEGRATION: For live SEC release fetching and auto-classification, see
data/sec_nlp_classifier.py. The NLP classifier can fetch recent SEC Litigation
Releases from https://www.sec.gov/litigation/litreleases.shtml and classify
them into SCI categories without requiring an API key. Usage:
    python -m data.sec_nlp_classifier --url https://www.sec.gov/litigation/releases/...
    python -m data.sec_nlp_classifier --file new_releases.jsonl --out classified.jsonl
"""

from __future__ import annotations

SEC_FRAUD_CASES: dict[str, list[dict]] = {

    # ── Major Accounting Fraud ─────────────────────────────────────────

    "enron": [
        {
            "date": "2003-07-08",
            "penalty_usd": 0,   # company bankrupt, penalty largely uncollected
            "description": (
                "Enron Corporation — SEC charged Enron Corp. and multiple executives "
                "with massive accounting fraud. Enron used special purpose entities "
                "and mark-to-market accounting to conceal debt and inflate earnings; "
                "the $63B collapse was the largest US bankruptcy at the time. "
                "Company bankrupt (2001); executives Ken Lay (deceased), Jeff Skilling "
                "criminally convicted. SEC obtained $164M in disgorgement from "
                "Enron's insurers and executives."
            ),
            "sec_ref": "SEC LR-18174",
            "fraud_type": "accounting_fraud",
        },
    ],

    "worldcom": [
        {
            "date": "2003-05-19",
            "penalty_usd": 750_000_000,
            "description": (
                "WorldCom Inc. (later MCI) — SEC charged $11B accounting fraud, "
                "the largest ever at time of discovery. WorldCom improperly capitalized "
                "line costs as capital expenses to inflate earnings. $750M settlement "
                "(largest SEC penalty at time). Company filed for bankruptcy (2002); "
                "CEO Bernard Ebbers criminally convicted."
            ),
            "sec_ref": "SEC LR-18234",
            "fraud_type": "accounting_fraud",
        },
    ],

    "mci": [
        {
            "date": "2003-05-19",
            "penalty_usd": 750_000_000,
            "description": (
                "MCI Inc. (formerly WorldCom) — SEC $11B accounting fraud settlement, "
                "$750M penalty. MCI/WorldCom improperly capitalized $11B in costs to "
                "inflate reported earnings. Later acquired by Verizon (2006)."
            ),
            "sec_ref": "SEC LR-18234",
            "fraud_type": "accounting_fraud",
        },
    ],

    "tyco international": [
        {
            "date": "2006-04-17",
            "penalty_usd": 50_000_000,
            "description": (
                "Tyco International Ltd. — SEC civil fraud charges for systematic "
                "looting of company assets by CEO Dennis Kozlowski and CFO Mark Swartz "
                "($400M+ stolen), plus financial statement fraud. $50M SEC civil penalty "
                "against the company. Kozlowski and Swartz criminally convicted. "
                "NOTE: Tyco also had a separate 2012 FCPA settlement ($26M)."
            ),
            "sec_ref": "SEC LR-19651",
            "fraud_type": "accounting_fraud",
        },
    ],

    "adelphia communications": [
        {
            "date": "2005-11-14",
            "penalty_usd": 715_000_000,
            "description": (
                "Adelphia Communications Corporation — SEC $715M settlement for "
                "securities fraud by the Rigas family founders who used the company "
                "as a personal bank, hiding $2.3B in off-balance sheet debt. "
                "Adelphia went bankrupt; founders John and Timothy Rigas convicted."
            ),
            "sec_ref": "SEC LR-19390",
            "fraud_type": "accounting_fraud",
        },
    ],

    "healthsouth": [
        {
            "date": "2006-04-14",
            "penalty_usd": 100_000_000,
            "description": (
                "HealthSouth Corporation (hospital operator) — SEC settlement for "
                "$2.7B accounting fraud; CEO Richard Scrushy and CFOs inflated "
                "earnings over 6 years to meet Wall Street targets. $100M SEC penalty. "
                "Company survived and later became Encompass Health."
            ),
            "sec_ref": "SEC LR-19618",
            "fraud_type": "accounting_fraud",
        },
    ],

    "encompass health": [
        {
            "date": "2006-04-14",
            "penalty_usd": 100_000_000,
            "description": (
                "Encompass Health Corp. (formerly HealthSouth) — predecessor HealthSouth "
                "settled SEC accounting fraud charges for $100M (2006). $2.7B in "
                "fabricated earnings over 6 years."
            ),
            "sec_ref": "SEC LR-19618",
            "fraud_type": "accounting_fraud",
        },
    ],

    "xerox": [
        {
            "date": "2002-04-11",
            "penalty_usd": 10_000_000,
            "description": (
                "Xerox Corporation — SEC civil fraud settlement; Xerox improperly "
                "accelerated $3B in equipment lease revenues (revenue recognition fraud) "
                "to inflate earnings over 4 years. $10M civil penalty; multiple "
                "executives also settled personally. Xerox restated 4 years of financials."
            ),
            "sec_ref": "SEC LR-17435",
            "fraud_type": "accounting_fraud",
        },
    ],

    "aig": [
        {
            "date": "2006-02-09",
            "penalty_usd": 1_640_000_000,
            "description": (
                "American International Group (AIG) — SEC/DOJ settlement for "
                "accounting fraud and bid-rigging in connection with finite reinsurance "
                "and improper accounting for $500M Gen Re finite reinsurance transaction "
                "that falsely inflated AIG's reserves. $1.64B settlement (DOJ $800M + "
                "SEC $700M + NY AG $143M). CEO Hank Greenberg separately settled."
            ),
            "sec_ref": "SEC LR-19590",
            "fraud_type": "accounting_fraud",
        },
    ],

    "american international group": [
        {
            "date": "2006-02-09",
            "penalty_usd": 1_640_000_000,
            "description": (
                "AIG — $1.64B settlement for finite reinsurance accounting fraud and "
                "bid-rigging. SEC charged fraudulent inflation of loss reserves via "
                "sham transactions with Gen Re."
            ),
            "sec_ref": "SEC LR-19590",
            "fraud_type": "accounting_fraud",
        },
    ],

    "bristol-myers squibb": [
        {
            "date": "2004-08-04",
            "penalty_usd": 150_000_000,
            "description": (
                "Bristol-Myers Squibb Company — SEC charged channel-stuffing fraud; "
                "BMS paid $150M settlement for fraudulently inflating pharmaceutical "
                "revenues through excess inventory pushed to wholesalers ('channel "
                "stuffing'), which enabled executives to meet Wall Street earnings "
                "targets. Separate from BMS's 2015 FCPA settlement ($14.75M). "
                "NOTE: BMS has two separate enforcement actions — this (2004 SEC "
                "accounting fraud) and 2015 FCPA."
            ),
            "sec_ref": "SEC LR-18755",
            "fraud_type": "accounting_fraud",
        },
    ],

    "qwest communications": [
        {
            "date": "2005-03-15",
            "penalty_usd": 250_000_000,
            "description": (
                "Qwest Communications International Inc. (telecom, later acquired "
                "by CenturyLink → Lumen Technologies) — SEC $250M settlement for "
                "$3.8B accounting fraud; Qwest improperly recognized revenue from "
                "IRU (indefeasible right of use) fiber optic capacity swaps as "
                "sales rather than leases."
            ),
            "sec_ref": "SEC LR-19039",
            "fraud_type": "accounting_fraud",
        },
    ],

    "lumen technologies": [
        {
            "date": "2005-03-15",
            "penalty_usd": 250_000_000,
            "description": (
                "Lumen Technologies (formerly CenturyLink, successor to Qwest via "
                "merger) — Qwest Communications settled SEC fraud charges for $250M "
                "for $3.8B IRU revenue recognition fraud."
            ),
            "sec_ref": "SEC LR-19039",
            "fraud_type": "accounting_fraud",
        },
    ],

    "centurylink": [
        {
            "date": "2005-03-15",
            "penalty_usd": 250_000_000,
            "description": (
                "CenturyLink (now Lumen Technologies, successor to Qwest) — "
                "predecessor Qwest's $250M SEC settlement for revenue recognition fraud."
            ),
            "sec_ref": "SEC LR-19039",
            "fraud_type": "accounting_fraud",
        },
    ],

    "computer associates": [
        {
            "date": "2004-09-22",
            "penalty_usd": 225_000_000,
            "description": (
                "Computer Associates International Inc. (now CA Technologies / "
                "Broadcom) — SEC $225M settlement + DOJ DPA for 'premature revenue "
                "recognition' fraud; CA backdated software contracts to inflate "
                "revenues over multiple years. CEO Sanjay Kumar convicted."
            ),
            "sec_ref": "SEC LR-18776",
            "fraud_type": "accounting_fraud",
        },
    ],

    "broadcom": [
        {
            "date": "2004-09-22",
            "penalty_usd": 225_000_000,
            "description": (
                "Broadcom (now owns CA Technologies, successor to Computer Associates) — "
                "predecessor CA International settled SEC accounting fraud charges for "
                "$225M (2004) for premature revenue recognition. CA later acquired "
                "by Broadcom in 2018."
            ),
            "sec_ref": "SEC LR-18776",
            "fraud_type": "accounting_fraud",
        },
    ],

    # ── Options Backdating ────────────────────────────────────────────

    "comverse technology": [
        {
            "date": "2010-08-10",
            "penalty_usd": 54_500_000,
            "description": (
                "Comverse Technology Inc. — SEC $54.5M settlement for options "
                "backdating; executives systematically backdated stock option grants "
                "to take advantage of lower prices without disclosing the practice, "
                "resulting in understated compensation expenses. Founder Jacob 'Kobi' "
                "Alexander charged criminally, fled to Namibia."
            ),
            "sec_ref": "SEC LR-21609",
            "fraud_type": "options_backdating",
        },
    ],

    "unitedhealth group": [
        {
            "date": "2008-12-22",
            "penalty_usd": 895_000_000,
            "description": (
                "UnitedHealth Group Inc. — SEC $895M settlement for stock options "
                "backdating (largest options backdating settlement). Former CEO "
                "William McGuire had options worth hundreds of millions backdated "
                "to lower-price dates, improperly understating compensation expenses. "
                "McGuire personally returned $600M+ in compensation."
            ),
            "sec_ref": "SEC LR-20847",
            "fraud_type": "options_backdating",
        },
    ],

    "unitedhealth": [
        {
            "date": "2008-12-22",
            "penalty_usd": 895_000_000,
            "description": (
                "UnitedHealth Group — $895M options backdating settlement (largest). "
                "Former CEO McGuire's options systematically backdated over multiple years."
            ),
            "sec_ref": "SEC LR-20847",
            "fraud_type": "options_backdating",
        },
    ],

    # ── Recent / Post-2015 Major Enforcement ─────────────────────────

    "kraft heinz": [
        {
            "date": "2021-07-01",
            "penalty_usd": 62_000_000,
            "description": (
                "The Kraft Heinz Company (NASDAQ-listed food company) settled SEC "
                "charges for an accounting fraud scheme involving employee misconduct "
                "in the procurement division — employees fabricated and manipulated "
                "cost accounting entries to reduce reported costs and meet internal "
                "targets, inflating pre-tax income by approximately $208M over "
                "5 years. $62M SEC civil penalty."
            ),
            "sec_ref": "SEC LR-25126",
            "fraud_type": "accounting_fraud",
        },
    ],

    "under armour": [
        {
            "date": "2021-05-03",
            "penalty_usd": 9_000_000,
            "description": (
                "Under Armour, Inc. — SEC $9M settlement for misleading investors "
                "about its revenue growth; Under Armour pulled forward future-quarter "
                "revenue into earlier periods ('pull-forward') to meet analyst "
                "expectations without disclosing the practice. DOJ also investigated."
            ),
            "sec_ref": "SEC LR-25070",
            "fraud_type": "accounting_fraud",
        },
    ],

    "ge": [
        {
            "date": "2020-12-09",
            "penalty_usd": 200_000_000,
            "description": (
                "General Electric Company (GE) — SEC $200M settlement for misleading "
                "investors about the financial performance of GE Power and Baker Hughes "
                "businesses; GE failed to disclose critical information about insurance "
                "reserves and revenue from its insurance run-off operations, creating "
                "a misleading picture of earnings quality."
            ),
            "sec_ref": "SEC LR-24985",
            "fraud_type": "accounting_fraud",
        },
    ],

    "general electric": [
        {
            "date": "2020-12-09",
            "penalty_usd": 200_000_000,
            "description": (
                "General Electric (GE) settled SEC charges for $200M for misleading "
                "investors about GE Power and insurance reserve adequacy. GE previously "
                "also had a 2004 SEC settlement ($50M) and 2010 FCPA NPA ($23.4M)."
            ),
            "sec_ref": "SEC LR-24985",
            "fraud_type": "accounting_fraud",
        },
    ],

    "ge aerospace": [
        {
            "date": "2020-12-09",
            "penalty_usd": 200_000_000,
            "description": (
                "GE Aerospace (successor to General Electric's power/aviation businesses "
                "after corporate reorganization) — GE's $200M SEC settlement for "
                "misleading investors about earnings quality (2020) + FCPA NPA (2010)."
            ),
            "sec_ref": "SEC LR-24985",
            "fraud_type": "accounting_fraud",
        },
    ],

    "hertz": [
        {
            "date": "2019-06-10",
            "penalty_usd": 16_000_000,
            "description": (
                "Hertz Global Holdings — SEC $16M settlement for accounting fraud; "
                "Hertz's corporate accounting team made improper manual entries that "
                "overstated pre-tax income by $235M across multiple years. "
                "Subsequent audit committee investigation led to financial restatements."
            ),
            "sec_ref": "SEC LR-24498",
            "fraud_type": "accounting_fraud",
        },
    ],

    "valeant pharmaceuticals": [
        {
            "date": "2020-01-21",
            "penalty_usd": 45_000_000,
            "description": (
                "Valeant Pharmaceuticals International Inc. (now Bausch Health "
                "Companies Inc.) — SEC $45M settlement for channel stuffing fraud; "
                "Valeant fraudulently inflated pharmaceutical revenues by booking "
                "fictitious sales to a distribution company (Philidor Rx Services), "
                "which it secretly controlled."
            ),
            "sec_ref": "SEC LR-24991",
            "fraud_type": "accounting_fraud",
        },
    ],

    "bausch health": [
        {
            "date": "2020-01-21",
            "penalty_usd": 45_000_000,
            "description": (
                "Bausch Health Companies (formerly Valeant Pharmaceuticals) — "
                "$45M SEC settlement for channel stuffing revenue fraud via secret "
                "control of distributor Philidor Rx Services."
            ),
            "sec_ref": "SEC LR-24991",
            "fraud_type": "accounting_fraud",
        },
    ],

    "luckin coffee": [
        {
            "date": "2020-12-16",
            "penalty_usd": 180_000_000,
            "description": (
                "Luckin Coffee Inc. (Chinese coffee chain, formerly NASDAQ-listed, "
                "now delisted) — SEC $180M settlement for fabricating approximately "
                "CN¥2.2B ($310M USD) in revenues from Q2 2019 through Q1 2020 by "
                "recording fictitious sales transactions."
            ),
            "sec_ref": "SEC LR-24991",
            "fraud_type": "accounting_fraud",
        },
    ],

    # ── Post-2015 Financial Industry Fraud ───────────────────────────

    "wells fargo": [
        {
            "date": "2020-02-21",
            "penalty_usd": 3_000_000_000,
            "description": (
                "Wells Fargo & Company — DOJ/SEC $3B settlement for decades-long "
                "widespread fraud in which employees created millions of unauthorized "
                "accounts, credit cards, and insurance policies in customers' names "
                "without consent to meet internal sales goals. Criminal information "
                "filed (no admission of guilt); largest consumer fraud settlement in "
                "US banking history at the time."
            ),
            "sec_ref": "DOJ 20-157 + SEC Rel. 34-88242",
            "fraud_type": "consumer_fraud",
        },
    ],

    "deutsche bank": [
        {
            "date": "2021-01-08",
            "penalty_usd": 130_000_000,
            "description": (
                "Deutsche Bank AG (German bank, NYSE ADR) — SEC $130M settlement "
                "for FCPA violations and wire fraud; Deutsche Bank paid bribes to "
                "government officials in Abu Dhabi, Saudi Arabia, and Italy, and "
                "engaged in commodities price manipulation. Separate from the 2015 "
                "LIBOR settlement ($2.5B)."
            ),
            "sec_ref": "DOJ 21-013",
            "fraud_type": "accounting_fraud",
        },
    ],

    "goldman sachs": [
        {
            "date": "2020-10-22",
            "penalty_usd": 2_900_000_000,
            "description": (
                "Goldman Sachs Group Inc. — DOJ/SEC $2.9B 1MDB settlement for FCPA "
                "violations and breach of fiduciary duties; Goldman misappropriated "
                "sovereign wealth fund assets and concealed FCPA violations. Largest "
                "FCPA fine against a US financial institution. Concurrent SEC "
                "enforcement on internal controls failures."
            ),
            "sec_ref": "DOJ 20-1049",
            "fraud_type": "securities_fraud",
        },
    ],

    "citigroup": [
        {
            "date": "2020-09-17",
            "penalty_usd": 400_000_000,
            "description": (
                "Citigroup Inc. (NYSE) — OCC/Fed $400M consent order for risk management "
                "and data governance failures; SEC separately brought charges in 2012 "
                "for CDO-related securities fraud ($285M, later reduced to $95M on appeal). "
                "Major institutional counterparty in 2008 financial crisis losses."
            ),
            "sec_ref": "SEC Rel. 34-66234",
            "fraud_type": "securities_fraud",
        },
    ],

    "citi": [
        {
            "date": "2020-09-17",
            "penalty_usd": 400_000_000,
            "description": (
                "Citigroup (Citi) — $400M OCC consent order for risk management failures "
                "+ 2012 SEC CDO fraud charges. Major financial crisis misconduct exposure."
            ),
            "sec_ref": "SEC Rel. 34-66234",
            "fraud_type": "securities_fraud",
        },
    ],

    "bank of america": [
        {
            "date": "2014-08-21",
            "penalty_usd": 16_650_000_000,
            "description": (
                "Bank of America Corporation (NYSE) — DOJ $16.65B settlement for "
                "fraudulent mortgage-backed securities sales prior to and during the "
                "2008 financial crisis; BofA and its Countrywide and Merrill Lynch "
                "subsidiaries knowingly sold MBS with misrepresented underlying loan "
                "quality. Largest DOJ financial industry settlement at the time."
            ),
            "sec_ref": "DOJ Civil Settlement 2014",
            "fraud_type": "securities_fraud",
        },
    ],

    "jpmorgan": [
        {
            "date": "2013-11-19",
            "penalty_usd": 13_000_000_000,
            "description": (
                "JPMorgan Chase & Co. (NYSE) — DOJ $13B settlement for fraudulent "
                "mortgage-backed securities sales; JPMorgan and subsidiaries Bear "
                "Stearns and WaMu sold billions in MBS with known defects, "
                "misrepresenting loan quality to investors. Largest DOJ financial "
                "industry settlement at the time. Note: Separate from FCPA violations."
            ),
            "sec_ref": "DOJ Civil Settlement 2013",
            "fraud_type": "securities_fraud",
        },
    ],

    "jpmorgan chase": [
        {
            "date": "2013-11-19",
            "penalty_usd": 13_000_000_000,
            "description": (
                "JPMorgan Chase — $13B DOJ settlement for fraudulent MBS sales "
                "(Bear Stearns + WaMu included). Largest DOJ financial settlement. "
                "Also: FCPA DPA 2016 ($264M) for 'Sons and Daughters' hiring scheme."
            ),
            "sec_ref": "DOJ Civil Settlement 2013",
            "fraud_type": "securities_fraud",
        },
    ],

    "theranos": [
        {
            "date": "2018-03-14",
            "penalty_usd": 500_000,
            "description": (
                "Theranos Inc. (private, but large institutional/PE exposure via secondary "
                "trading) — SEC $500K settlement against founder Elizabeth Holmes for "
                "deceiving investors about blood-testing technology capabilities. "
                "Holmes separately convicted criminally (4 counts wire fraud, 2022). "
                "DOJ separately charged former President Ramesh Balwani. "
                "Note: Theranos was privately held; flag applies to any fund with "
                "secondary market exposure."
            ),
            "sec_ref": "SEC Rel. 34-82896",
            "fraud_type": "securities_fraud",
        },
    ],

    "nikola": [
        {
            "date": "2021-12-21",
            "penalty_usd": 125_000_000,
            "description": (
                "Nikola Corporation (electric truck maker, NASDAQ) — SEC $125M "
                "settlement for misleading investors about its truck technology, "
                "production capabilities, and business partnerships. Founder Trevor "
                "Milton separately convicted criminally (2022) for securities and "
                "wire fraud. A prominent SPAC-era fraud case."
            ),
            "sec_ref": "SEC Rel. 34-93699",
            "fraud_type": "securities_fraud",
        },
    ],

    "lordstown motors": [
        {
            "date": "2023-07-25",
            "penalty_usd": 25_000_000,
            "description": (
                "Lordstown Motors Corp (NASDAQ electric truck startup) — SEC $25M "
                "settlement for misleading investors about Endurance truck orders; "
                "the company falsely claimed to have firm purchase orders from fleet "
                "customers to boost its credibility and stock price post-SPAC merger."
            ),
            "sec_ref": "SEC Rel. 34-97983",
            "fraud_type": "securities_fraud",
        },
    ],

    "archegos": [
        {
            "date": "2022-03-31",
            "penalty_usd": 0,
            "description": (
                "Archegos Capital Management (family office, not publicly traded) — "
                "SEC/DOJ charged founder Bill Hwang with securities fraud and RICO "
                "for manipulating prices of over $100B in total return swaps on "
                "ViacomCBS, Discovery, Baidu, etc. Hwang convicted 2024. "
                "Counter-parties (Credit Suisse, Nomura, Morgan Stanley) suffered "
                "$10B+ in losses. Flag applies to CS, Nomura, Morgan Stanley exposure."
            ),
            "sec_ref": "SEC LR-25303",
            "fraud_type": "market_manipulation",
        },
    ],

    # ── Ponzi Schemes / Securities Fraud ─────────────────────────────

    "madoff": [
        {
            "date": "2008-12-11",
            "penalty_usd": 17_000_000_000,  # SEC estimated losses
            "description": (
                "Bernie Madoff Investment Securities LLC — SEC/DOJ largest Ponzi "
                "scheme in history: $17B+ in actual investor losses ($65B stated). "
                "NOTE: Madoff's firm was privately held; any publicly-traded fund "
                "that had direct exposure to BMIS would be flagged here. "
                "Included for reference when analyzing financial sector holdings."
            ),
            "sec_ref": "DOJ/SEC 2008-2009",
            "fraud_type": "ponzi_scheme",
        },
    ],
}


def lookup_sec_enforcement(entity_name: str) -> dict | None:
    """
    Check if entity_name matches a known major SEC enforcement action.

    Returns:
        {
            "has_sec_action": True,
            "cases": [...],
            "total_penalty_usd": int,
            "source": "SEC Enforcement (non-FCPA)",
            "source_url": "https://www.sec.gov/litigation/litreleases.shtml"
        }
        or None if no match.
    """
    name_lower = entity_name.lower().strip()
    if not name_lower:
        return None
    from core.entity_matcher import fuzzy_match

    matched: list[dict] = []
    for fragment, cases in SEC_FRAUD_CASES.items():
        is_match, _score = fuzzy_match(entity_name, fragment)
        if is_match:
            matched.extend(cases)

    if not matched:
        return None

    seen = set()
    unique = []
    for c in matched:
        ref = c.get("sec_ref", c.get("description", "")[:40])
        if ref not in seen:
            seen.add(ref)
            unique.append(c)

    return {
        "has_sec_action": True,
        "cases": unique,
        "total_penalty_usd": sum(c.get("penalty_usd", 0) for c in unique),
        "source": "SEC Enforcement (non-FCPA) / Litigation Releases",
        "source_url": "https://www.sec.gov/litigation/litreleases.shtml",
    }
