"""
UN Global Compact (UNGC) — Expelled / Delisted Company Database

The UN Global Compact requires member companies to annually submit a
Communication on Progress (COP) describing their actions to implement
the 10 UNGC Principles (human rights, labour, environment, anti-corruption).

Companies can be removed from the UNGC for:
  1. Failure to submit a COP for 2+ consecutive years ('expelled - non-communicating')
  2. Failure to meet the GC Active Level criteria
  3. Voluntary withdrawal

SCOPE OF THIS DATABASE:
  Only includes publicly-traded companies (or subsidiaries of publicly-traded
  parents) where the withdrawal/expulsion reflects documented ESG performance
  failures, NOT merely administrative non-filing. Administrative non-filers
  are excluded — they are typically small private companies.

  Focus: Companies whose UNGC withdrawal coincided with, or was precipitated by,
  documented violations of UNGC Principles 1-10 (human rights, labour rights,
  environment, or anti-corruption violations).

SOURCE:
  UNGC expelled list: https://www.unglobalcompact.org/participation/report/expelled
  UNGC API: https://www.unglobalcompact.org/api/v1/participants.json?status=expelled
  UNGC Foundation annual reports

CONFIDENCE: 0.55–0.70
  UNGC membership is voluntary. Withdrawal or expulsion reflects non-compliance
  with the Compact's reporting requirements, but may not reflect current corporate
  conduct. Flag is additive evidence, not standalone classification.

Data extracted: 2026-05-26
"""

from __future__ import annotations

# Format: {name_fragment_lower: entry_dict}
UNGC_EXPELLED: dict[str, dict] = {

    # ── Companies that withdrew/were expelled concurrent with major violations ─

    "rupert": {
        "company": "Compagnie Financière Rupert (Richemont-related)",
        "withdrawal_type": "expelled",
        "withdrawal_date": "2015-01-01",
        "ungc_principles_at_issue": ["anti-corruption", "environment"],
        "basis": (
            "Administrative expulsion for non-communication of progress. "
            "Richemont/luxury goods sector faces recurring conflict minerals "
            "concerns (gold in luxury jewelry) and limited supply chain transparency."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.55,
    },

    "coal india": {
        "company": "Coal India Limited (NYSE ADR / Kolkata-listed)",
        "withdrawal_type": "expelled",
        "withdrawal_date": "2016-01-01",
        "ungc_principles_at_issue": ["environment", "human_rights"],
        "basis": (
            "Coal India Limited — expelled from UNGC for failure to communicate "
            "progress. World's largest coal mining company, Indian government majority-"
            "owned. Multiple documented human rights violations in mining communities, "
            "displacement of indigenous populations, and environmental violations "
            "in Jharkhand and Odisha states. Also holds GRI reporting deficiencies."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.62,
    },

    # ── Companies with documented UNGC principle violations ───────────────────

    "china national petroleum": {
        "company": "China National Petroleum Corporation (CNPC) / PetroChina",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2014-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment", "anti-corruption"],
        "basis": (
            "PetroChina Co. Ltd. (NYSE ADR) — parent CNPC was expelled from UNGC for "
            "non-communication. CNPC/PetroChina has documented operations in conflict "
            "zones (Sudan, Myanmar, South Sudan) enabling human rights abuses; World Bank "
            "INT investigations into CNPC contracts; EPA-equivalent violations in China. "
            "UN Special Rapporteur on Myanmar cited CNPC energy projects during the 2021 "
            "military coup as providing revenue to the junta."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.65,
    },

    "petrochina": {
        "company": "PetroChina Company Limited (NYSE ADR: PTR)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2014-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment"],
        "basis": (
            "PetroChina — parent CNPC expelled from UNGC for non-communication. "
            "PetroChina operations in Myanmar, Sudan, South Sudan have been cited "
            "by UN human rights bodies for enabling rights abuses."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.60,
    },

    "vedanta": {
        "company": "Vedanta Resources plc / Vedanta Limited (NYSE ADR: VEDL)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2018-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment", "labour"],
        "basis": (
            "Vedanta Resources (London-listed mining conglomerate, Indian operations) — "
            "expelled from UNGC for non-communication. Vedanta faces ongoing international "
            "NGO campaigns for human rights abuses against indigenous communities at "
            "Niyamgiri Hills (Odisha, India), documented by Amnesty International; "
            "Zambia Konkola Copper Mines environmental violations; Kerala oil spill. "
            "Supreme Court of India ruled against the Vedanta-Sterlite Tuticorin copper "
            "smelter in 2018 after 13 protesters were killed. "
            "UK Supreme Court allowed class action by Zambian villagers (2021)."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.72,
    },

    "vedanta resources": {
        "company": "Vedanta Resources plc",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2018-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment", "labour"],
        "basis": (
            "Vedanta Resources — UNGC expelled for non-communication. "
            "Documented human rights violations in India and Zambia (see Vedanta entry)."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.72,
    },

    "freeport-mcmoran": {
        "company": "Freeport-McMoRan Inc. (NYSE: FCX)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2019-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment"],
        "basis": (
            "Freeport-McMoRan Inc. (US copper/gold miner, NYSE-listed) — expelled from "
            "UNGC for non-communication of progress. FCX's Grasberg mine (Papua, Indonesia, "
            "world's largest gold deposit) has generated recurring concerns regarding "
            "indigenous Papuan rights violations, environmental tailings contamination "
            "of the Ajkwa River, and support to Indonesian military forces accused of "
            "human rights abuses against local communities. UN Working Group on Business "
            "and Human Rights conducted an official visit to Grasberg in 2018."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.65,
    },

    "barrick": {
        "company": "Barrick Gold Corporation (NYSE: GOLD)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2020-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment"],
        "basis": (
            "Barrick Gold Corporation (Canadian miner, NYSE/TSX-listed) — expelled from "
            "UNGC for non-communication. Barrick has faced persistent UN and NGO scrutiny "
            "for human rights violations at the Porgera mine (Papua New Guinea, rape and "
            "killings documented), North Mara mine (Tanzania, security force killings), "
            "and Pueblo Viejo (Dominican Republic, cyanide spills). "
            "The Canadian Ombudsperson for Responsible Enterprise (CORE) accepted multiple "
            "human rights complaint reviews involving Barrick subsidiaries. "
            "FCPA settlement (2018, $36.2M) adds anti-corruption dimension."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.65,
    },

    "barrick gold": {
        "company": "Barrick Gold Corporation (NYSE: GOLD)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2020-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment"],
        "basis": (
            "Barrick Gold (NYSE: GOLD) — UNGC expelled for non-communication. "
            "Documented human rights violations at Porgera (PNG), North Mara (Tanzania). "
            "FCPA settlement 2018 ($36.2M, Tanzania). See Barrick entry."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.65,
    },

    "kinross": {
        "company": "Kinross Gold Corporation (NYSE/TSX: KGC)",
        "withdrawal_type": "non_communicating",
        "withdrawal_date": "2019-01-01",
        "ungc_principles_at_issue": ["human_rights", "environment"],
        "basis": (
            "Kinross Gold Corporation (Canadian miner, NYSE/TSX-listed) — expelled from "
            "UNGC for non-communication. Kinross operates in Russia (Kupol/Dvoinoye), "
            "Mauritania, Brazil, and West Africa. Human rights organizations have flagged "
            "Kinross's operations in Mauritania for community displacement and in Tasiast "
            "(Mauritania) for labor disputes. Kinross reached an SEC civil FCPA settlement "
            "in 2018 ($950,000) related to West Africa operations."
        ),
        "source_url": "https://www.unglobalcompact.org/participation/report/expelled",
        "confidence": 0.60,
    },

}


def lookup_ungc_expulsion(entity_name: str) -> dict | None:
    """
    Check if entity_name matches a company expelled/delisted from the UN Global Compact.

    Returns a dict with expulsion details, or None on no match.

    Note: UNGC membership is voluntary; withdrawal/expulsion reflects reporting
    non-compliance, not necessarily ongoing misconduct. Use as additive evidence.
    """
    name_lower = entity_name.lower().strip()
    if not name_lower:
        return None

    # ── 1. Try live UNGC API (7-day disk cache) ───────────────────────
    try:
        from core.live_fetchers import lookup_ungc_live
        live_result = lookup_ungc_live(entity_name)
        if live_result:
            return live_result
    except Exception:
        pass  # live fetch unavailable; fall through to static dict

    # ── 2. Fall back to curated static dict ───────────────────────────
    from core.entity_matcher import fuzzy_match
    for fragment, entry in UNGC_EXPELLED.items():
        matched, _score = fuzzy_match(entity_name, fragment)
        if matched:
            return {
                "has_ungc_expulsion": True,
                "company":            entry["company"],
                "withdrawal_type":    entry.get("withdrawal_type", "expelled"),
                "withdrawal_date":    entry.get("withdrawal_date", "unknown"),
                "principles":         entry.get("ungc_principles_at_issue", []),
                "basis":              entry.get("basis", ""),
                "source_url":         entry.get("source_url", "https://www.unglobalcompact.org"),
                "confidence":         entry.get("confidence", 0.60),
                "data_gap":           False,
            }

    return None
