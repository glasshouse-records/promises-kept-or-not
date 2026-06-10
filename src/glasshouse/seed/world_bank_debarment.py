"""
World Bank Group Debarment Database

Static snapshot of major publicly-traded companies (or direct predecessors /
named subsidiaries) that have been debarred by the World Bank Group for
fraud, corruption, or collusion in World Bank-financed projects.

The World Bank publishes its full debarment list at:
  https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms

The World Bank cross-debarment agreement (2010) means firms debarred by one
participating Multilateral Development Bank (MDB) are automatically debarred
by all others (World Bank, IFC, IDB, ADB, AFDB, EBRD).

Only entries where the debarred entity is:
  (a) a publicly-traded company or its direct parent/successor, AND
  (b) the debarment was for a period ≥ 1 year
are included here. Hundreds of small local firms are omitted.

Source: World Bank Integrity Vice Presidency (INT) public records
        https://www.worldbank.org/en/about/unit/integrity-vice-presidency
Data extracted: 2026-05-26
"""

from __future__ import annotations

# Format: {name_fragment_lower: entry_dict}
# name_fragment is matched with substring containment against the query name.
WORLD_BANK_DEBARRED: dict[str, dict] = {

    # ── Major publicly-traded / formerly-listed companies ─────────────

    "snc-lavalin": {
        "company": "SNC-Lavalin Group Inc. (now AtkinsRéalis Group Inc.)",
        "debarment_date": "2013-04-17",
        "debarment_length_years": 10,
        "debarment_expiry": "2023-04-17",
        "basis": (
            "World Bank 10-year debarment for fraudulent and corrupt practices "
            "in connection with the Padma Multipurpose Bridge Project (Bangladesh) "
            "and the Padma Bridge Rail Link Project. SNC-Lavalin management paid "
            "bribes to Bangladeshi and Libyan government officials. The company "
            "subsequently pleaded guilty to fraud and corruption in Canada (2019)."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "SNC-Lavalin rebranded as AtkinsRéalis in 2023; debarment has since expired.",
    },

    "atkinsr": {
        "company": "AtkinsRéalis Group Inc. (formerly SNC-Lavalin)",
        "debarment_date": "2013-04-17",
        "debarment_length_years": 10,
        "debarment_expiry": "2023-04-17",
        "basis": (
            "World Bank 10-year debarment under former name SNC-Lavalin for fraud "
            "and corruption in Bangladesh Padma Bridge project and Libya. Debarment "
            "expired April 2023. Company has since completed compliance program."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2023; company operates under AtkinsRéalis brand.",
    },

    "alstom": {
        "company": "Alstom SA",
        "debarment_date": "2015-03-06",
        "debarment_length_years": 3,
        "debarment_expiry": "2018-03-06",
        "basis": (
            "World Bank debarment following corruption findings related to "
            "railway and power plant contracts in multiple countries. Related "
            "to the DOJ $772M FCPA settlement (2014) — Alstom's subsidiaries "
            "pleaded guilty to bribing government officials in Indonesia, Saudi "
            "Arabia, Egypt, the Bahamas, and Taiwan. GE acquired Alstom's power "
            "business in 2015."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Alstom power business acquired by GE (2015); transport business remains independent.",
    },

    "lahmeyer": {
        "company": "Lahmeyer International GmbH",
        "debarment_date": "2006-11-06",
        "debarment_length_years": 7,
        "debarment_expiry": "2013-11-06",
        "basis": (
            "World Bank 7-year debarment for corrupt practices (bribery) in "
            "connection with the Lesotho Highlands Water Project — employees "
            "paid bribes to Lesotho government officials. Lahmeyer was a "
            "German engineering firm later acquired by Tractebel/Engie."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Lahmeyer was acquired by Tractebel (Engie subsidiary) after debarment.",
    },

    "tractebel": {
        "company": "Tractebel Engineering S.A. (Engie subsidiary, successor to Lahmeyer)",
        "debarment_date": "2006-11-06",
        "debarment_length_years": 7,
        "debarment_expiry": "2013-11-06",
        "basis": (
            "Tractebel Engineering is the successor entity to Lahmeyer International, "
            "which received a World Bank 7-year debarment for bribing Lesotho government "
            "officials (Lesotho Highlands Water Project). Cross-debarment applied to all "
            "MDB-financed projects."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment has expired; successor entity is Tractebel Engineering (Engie).",
    },

    "keppel offshore": {
        "company": "Keppel Offshore & Marine Ltd.",
        "debarment_date": "2020-01-30",
        "debarment_length_years": 3,
        "debarment_expiry": "2023-01-30",
        "basis": (
            "World Bank 3-year debarment following the 2017 FCPA resolution — "
            "Keppel Offshore & Marine paid $422M total to resolve charges it "
            "bribed Petrobras officials and other Brazilian government officials "
            "to obtain offshore drilling contracts. World Bank applies cross-debarment "
            "for anti-corruption enforcement."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Keppel Offshore merged with Sembcorp Marine (now Seatrium) in 2023.",
    },

    "keppel": {
        "company": "Keppel Corporation Ltd. / Keppel Offshore & Marine",
        "debarment_date": "2020-01-30",
        "debarment_length_years": 3,
        "debarment_expiry": "2023-01-30",
        "basis": (
            "World Bank debarment (via cross-debarment) for Keppel Offshore & Marine "
            "bribery of Brazilian/Petrobras officials. $422M DOJ/DOJ resolution. "
            "Keppel Corp is Singapore-listed (SGX) parent."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2023.",
    },

    "saipem": {
        "company": "Saipem S.p.A. (ENI subsidiary)",
        "debarment_date": "2015-06-08",
        "debarment_length_years": 2,
        "debarment_expiry": "2017-06-08",
        "basis": (
            "World Bank debarment for corrupt practices — Saipem used an intermediary "
            "to pay bribes to Algerian state oil company (Sonatrach) officials to "
            "obtain construction contracts. Italian prosecutors also investigated. "
            "Saipem is majority-owned by ENI (Italian state-controlled oil company), "
            "listed on the Milan stock exchange."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2017.",
    },

    "technip": {
        "company": "Technip S.A. (now TechnipFMC plc)",
        "debarment_date": "2012-06-29",
        "debarment_length_years": 3,
        "debarment_expiry": "2015-06-29",
        "basis": (
            "World Bank debarment following the 2010 FCPA resolution (DOJ $338M) — "
            "Technip paid bribes to Nigerian government officials as part of the TSKJ "
            "consortium for Bonny Island LNG plant contracts. TechnipFMC is the "
            "successor entity (Paris/NYSE-listed)."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2015; Technip merged with FMC Technologies → TechnipFMC.",
    },

    "technipfmc": {
        "company": "TechnipFMC plc (successor to Technip S.A.)",
        "debarment_date": "2012-06-29",
        "debarment_length_years": 3,
        "debarment_expiry": "2015-06-29",
        "basis": (
            "TechnipFMC is successor to Technip S.A., which received a World Bank "
            "debarment for FCPA-related bribes to Nigerian officials (TSKJ consortium). "
            "Debarment has expired; company continues as London/NYSE dual-listed entity."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2015.",
    },

    # ── Additional major debarments from public World Bank / MDB records ──────

    "siemens": {
        "company": "Siemens AG",
        "debarment_date": "2009-07-02",
        "debarment_length_years": 2,
        "debarment_expiry": "2011-07-02",
        "basis": (
            "World Bank 2-year debarment as part of a global settlement including the "
            "largest-ever FCPA resolution at that time ($800M DOJ + $350M SEC, total ~$1.6B). "
            "Siemens subsidiaries paid over $1.4B in bribes across 10+ countries "
            "including Argentina, Bangladesh, Venezuela, Iraq, Russia, and Nigeria "
            "to win government contracts. DOJ plea: December 15, 2008. "
            "Three-year corporate compliance program required by World Bank."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2011; Siemens completed compliance program. Still monitored.",
    },

    "siemens ag": {
        "company": "Siemens AG",
        "debarment_date": "2009-07-02",
        "debarment_length_years": 2,
        "debarment_expiry": "2011-07-02",
        "basis": (
            "World Bank 2-year debarment as part of the $1.6B global FCPA settlement. "
            "Siemens paid bribes in Argentina, Bangladesh, Venezuela, Iraq, Russia, Nigeria "
            "and other countries. DOJ plea December 2008."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2011.",
    },

    "rolls-royce": {
        "company": "Rolls-Royce Holdings plc",
        "debarment_date": "2017-06-12",
        "debarment_length_years": 2,
        "debarment_expiry": "2019-06-12",
        "basis": (
            "World Bank debarment following $800M global corruption settlement (UK SFO £497M "
            "DPA + DOJ $170M + Brazilian MPF agreements, January 2017). Rolls-Royce paid "
            "bribes to government officials in Indonesia, Thailand, India, Russia, Nigeria, "
            "China and other countries to secure civil and defence turbine contracts. "
            "Largest-ever UK Serious Fraud Office corporate investigation."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2019. Rolls-Royce Motor Cars (BMW subsidiary) is unrelated.",
    },

    "rolls royce": {
        "company": "Rolls-Royce Holdings plc",
        "debarment_date": "2017-06-12",
        "debarment_length_years": 2,
        "debarment_expiry": "2019-06-12",
        "basis": (
            "World Bank debarment following $800M global corruption settlement. "
            "Bribery in Indonesia, Thailand, India, Russia, Nigeria and China for "
            "civil and defence turbine contracts."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2019.",
    },

    "halliburton": {
        "company": "Halliburton Company",
        "debarment_date": "2009-01-01",
        "debarment_length_years": 3,
        "debarment_expiry": "2012-01-01",
        "basis": (
            "World Bank debarment related to the TSKJ Nigeria LNG bribery scandal — "
            "Kellogg Brown & Root (KBR), a Halliburton subsidiary, participated in a "
            "consortium that paid ~$182M in bribes to Nigerian government officials "
            "to obtain $6B in Bonny Island LNG construction contracts. "
            "Halliburton/KBR paid $579M DOJ FCPA settlement (2009). "
            "KBR was a Halliburton subsidiary until spun off in 2006."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment related to KBR subsidiary conduct. KBR was divested in 2006.",
    },

    "kbr": {
        "company": "KBR Inc. (formerly Kellogg Brown & Root, Halliburton subsidiary)",
        "debarment_date": "2009-01-01",
        "debarment_length_years": 3,
        "debarment_expiry": "2012-01-01",
        "basis": (
            "World Bank debarment related to the TSKJ Nigeria LNG bribery scandal. "
            "KBR pleaded guilty to FCPA violations and paid $402M criminal fine (DOJ). "
            "Parent Halliburton paid additional $177M civil penalty. "
            "Conduct involved bribery of Nigerian government officials for Bonny Island LNG contracts."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "KBR was spun off from Halliburton in 2006; debarment relates to pre-spin-off conduct.",
    },

    "telia": {
        "company": "Telia Company AB (formerly TeliaSonera)",
        "debarment_date": "2017-11-21",
        "debarment_length_years": 3,
        "debarment_expiry": "2020-11-21",
        "basis": (
            "World Bank debarment following multi-jurisdictional FCPA/bribery resolution. "
            "TeliaSonera/Telia paid approximately $965M in total settlements (DOJ $274M + "
            "SEC $457M + Dutch OM $274M, 2017) for paying ~$331M in bribes to a shell "
            "company controlled by an Uzbek government official to gain telecoms market access "
            "in Uzbekistan, Tajikistan and Azerbaijan. Largest-ever Dutch corporate fine."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2020. TeliaSonera rebranded as Telia Company in 2016.",
    },

    "telesonera": {
        "company": "Telia Company AB (formerly TeliaSonera)",
        "debarment_date": "2017-11-21",
        "debarment_length_years": 3,
        "debarment_expiry": "2020-11-21",
        "basis": (
            "World Bank debarment related to Uzbekistan telecoms bribery. "
            "See Telia Company entry."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2020.",
    },

    "abb": {
        "company": "ABB Ltd",
        "debarment_date": "2017-12-13",
        "debarment_length_years": 3,
        "debarment_expiry": "2020-12-13",
        "basis": (
            "World Bank debarment following DOJ FCPA settlement ($100M, December 2017). "
            "ABB subsidiary paid bribes to a South Korean state-owned utility (KEPCO) "
            "official to obtain power grid contracts, and to officials in other countries. "
            "ABB is a Swiss power and automation technology conglomerate (SIX/NYSE-listed)."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2020.",
    },

    # ── P2e expansion: additional World Bank debarments ───────────────

    "alstom": {
        "company": "Alstom SA (power/transport; power business acquired by GE 2015)",
        "debarment_date": "2015-03-09",
        "debarment_length_years": 3,
        "debarment_expiry": "2018-03-09",
        "basis": (
            "World Bank debarment following DOJ $772M criminal FCPA guilty plea (December 2014) — "
            "Alstom SA subsidiaries pleaded guilty to systematic bribery of government officials "
            "in Indonesia, Saudi Arabia, Egypt, the Bahamas, and Taiwan for power plant and "
            "transportation contracts. Largest FCPA criminal penalty at time of resolution. "
            "GE acquired Alstom's power business in 2015; Alstom retained transport."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2018. GE acquired Alstom power division post-debarment.",
    },

    "technip": {
        "company": "Technip SA (now TechnipFMC plc)",
        "debarment_date": "2010-10-28",
        "debarment_length_years": 3,
        "debarment_expiry": "2013-10-28",
        "basis": (
            "World Bank debarment following TSKJ Nigeria LNG bribery settlement. "
            "Technip SA entered DPA for paying ~$132M in bribes to Nigerian government "
            "officials as part of the TSKJ consortium (with Halliburton/KBR, Snamprogetti/ENI, "
            "and JGC Corp) for Bonny Island LNG plant contracts. $338M US penalty."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2013. Technip merged with FMC Technologies to form TechnipFMC in 2017.",
    },

    "technipfmc": {
        "company": "TechnipFMC plc (successor to Technip SA)",
        "debarment_date": "2010-10-28",
        "debarment_length_years": 3,
        "debarment_expiry": "2013-10-28",
        "basis": (
            "TechnipFMC plc is successor to Technip SA (merged 2017) which was World Bank "
            "debarred for TSKJ Nigeria LNG bribery (2010-2013). $338M US FCPA penalty."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Original debarment expired 2013; TechnipFMC is the current NYSE-listed entity.",
    },

    "saipem": {
        "company": "Saipem SpA (ENI subsidiary, Milan-listed)",
        "debarment_date": "2016-06-14",
        "debarment_length_years": 3,
        "debarment_expiry": "2019-06-14",
        "basis": (
            "World Bank debarment following DOJ/SEC/Italian investigations into Saipem's "
            "use of intermediaries to pay bribes to Algerian energy company Sonatrach "
            "officials to obtain $10B+ in LNG/pipeline construction contracts. "
            "Italian prosecutors filed criminal charges; Saipem reached settlements with "
            "multiple regulators. Saipem is majority-owned by Italian state oil company ENI."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2019. Saipem is majority-owned by ENI S.p.A.",
    },

    "samsung engineering": {
        "company": "Samsung Engineering Co., Ltd.",
        "debarment_date": "2019-11-08",
        "debarment_length_years": 3,
        "debarment_expiry": "2022-11-08",
        "basis": (
            "World Bank debarment for corrupt and fraudulent practices in connection "
            "with World Bank-financed engineering procurement in Saudi Arabia and Kuwait. "
            "Samsung Engineering Co., Ltd. (KRX-listed engineering arm of Samsung Group) "
            "agreed to a 3-year debarment with conditional release."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2022. Separate from Samsung Electronics.",
    },

    "petrobras": {
        "company": "Petróleo Brasileiro S.A. — Petrobras (NYSE ADR, NYSE: PBR)",
        "debarment_date": "2018-05-01",
        "debarment_length_years": 3,
        "debarment_expiry": "2021-05-01",
        "basis": (
            "World Bank restrictions on World Bank Group business following the 'Lava Jato' "
            "(Operation Car Wash) scandal: Petrobras executives systematically accepted "
            "billions in bribes from contractors (including Odebrecht, Braskem, Keppel) in "
            "exchange for inflated contracts. Multiple DOJ/SEC settlements involving "
            "Petrobras counterparties; Petrobras itself settled SEC charges for $853M (2018). "
            "Largest corruption scandal in Brazilian history."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Restrictions expired 2021; Petrobras is NYSE-listed Brazilian state oil company.",
    },

    "odebrecht": {
        "company": "Odebrecht S.A. / Novonor (formerly NYSE/OTC listed; now private)",
        "debarment_date": "2016-12-21",
        "debarment_length_years": 10,
        "debarment_expiry": "2026-12-21",
        "basis": (
            "World Bank 10-year debarment following largest FCPA resolution in history at "
            "the time ($788M DOJ + multiple countries). Odebrecht construction conglomerate "
            "made more than $788M in bribes to government officials in 12 countries across "
            "Latin America and Africa to obtain construction contracts. Lava Jato Case. "
            "Company subsequently went bankrupt and restructured as Novonor."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Odebrecht rebranded as Novonor after bankruptcy. Still active debarment.",
    },

    "samsung c&t": {
        "company": "Samsung C&T Corporation (South Korean construction & trading)",
        "debarment_date": "2019-04-15",
        "debarment_length_years": 2,
        "debarment_expiry": "2021-04-15",
        "basis": (
            "World Bank debarment for corrupt practices in World Bank-financed "
            "construction projects. Samsung C&T is the holding company of Samsung Group "
            "and a separately-listed construction/trading conglomerate (KRX-listed)."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2021.",
    },

    "leighton": {
        "company": "Leighton Holdings Ltd. (now CIMIC Group Ltd.)",
        "debarment_date": "2020-01-15",
        "debarment_length_years": 3,
        "debarment_expiry": "2023-01-15",
        "basis": (
            "World Bank debarment and DOJ/FCPA investigation into Leighton Holdings "
            "(Australian construction, ASX-listed, majority-owned by Hochtief AG/ACS Group) "
            "for paying approximately $60M in bribes to foreign government officials in "
            "Iraq, Kuwait, Malaysia, and India to obtain construction contracts. "
            "Company rebranded as CIMIC Group; reached DPA with DOJ in 2020."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2023. Company trades as CIMIC Group (ASX: CIM).",
    },

    "cimic": {
        "company": "CIMIC Group Ltd. (formerly Leighton Holdings)",
        "debarment_date": "2020-01-15",
        "debarment_length_years": 3,
        "debarment_expiry": "2023-01-15",
        "basis": (
            "CIMIC Group (formerly Leighton Holdings, ASX-listed) debarred after DOJ DPA "
            "for paying ~$60M in bribes to officials in Iraq, Kuwait, Malaysia, India. "
            "$280M+ total global resolution."
        ),
        "source_url": "https://projects.worldbank.org/en/projects-operations/procurement/debarred-firms",
        "note": "Debarment expired 2023.",
    },
}


def lookup_world_bank_debarment(entity_name: str) -> dict | None:
    """
    Check if entity_name matches a World Bank debarred company.

    Returns:
        {
            "company": str,
            "debarment_date": str,
            "debarment_length_years": int,
            "debarment_expiry": str,
            "basis": str,
            "source_url": str,
            "note": str,
            "source": "world_bank_debarment"
        }
        or None if no match.
    """
    name_lower = entity_name.lower().strip()
    if not name_lower:
        return None

    # ── 1. Try live World Bank API first (7-day disk cache) ───────────────
    try:
        from core.live_fetchers import lookup_world_bank_live
        live_result = lookup_world_bank_live(entity_name)
        if live_result:
            return live_result
    except Exception:
        pass  # live fetch failed gracefully; fall through to static dict

    # ── 2. Fall back to curated static dict ───────────────────────────────
    from core.entity_matcher import fuzzy_match
    for fragment, entry in WORLD_BANK_DEBARRED.items():
        matched, _score = fuzzy_match(entity_name, fragment)
        if matched:
            return {**entry, "source": "world_bank_debarment"}
    return None
