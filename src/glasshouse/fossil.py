"""Curated reference: major fossil-fuel companies, keyed by CUSIP.

A SEED, honestly partial. It exists to power the fossil-exposure detector
(a manager's climate commitment vs. the oil & gas in its own portfolio) with
a PRECISE, exact-CUSIP join — no name matching, so no Aldar-class false
positives. The CUSIPs were read from Glasshouse's own 13-F holdings and each
was hand-verified to a real oil & gas / oilfield-services / midstream company.

Provenance: `source_kind = curated_snapshot`. Coverage is major US-listed
oil & gas, oilfield services, and midstream only — it does NOT yet include the
international majors' ADRs (Shell, BP, TotalEnergies), coal producers, or the
full ~1,800-company universe. The full ingest of the Global Oil & Gas Exit
List (gogel.org, with financial identifiers on request) is the documented next
step; until then every result states this partial coverage.
"""

from __future__ import annotations

# cusip → company (hand-verified from our own holdings, 2026-07-07)
FOSSIL_FUEL_CUSIPS: dict[str, str] = {
    # US integrated / E&P / refining
    "30231G102": "Exxon Mobil Corp",
    "166764100": "Chevron Corporation",
    "20825C104": "ConocoPhillips",
    "56585A102": "Marathon Petroleum Corp",
    "718546104": "Phillips 66",
    "91913Y100": "Valero Energy Corp",
    "26875P101": "EOG Resources Inc",
    "25278X109": "Diamondback Energy Inc",
    "25179M103": "Devon Energy Corp",
    "127097103": "Coterra Energy Inc",
    "723787107": "Pioneer Natural Resources Co",
    "42809H107": "Hess Corp",
    "674599105": "Occidental Petroleum Corp",
    "565849106": "Marathon Oil Corp",
    "03743Q108": "APA Corporation (Apache)",
    "03674X106": "Antero Resources Corp",
    "69047Q102": "Ovintiv Inc",
    "165167735": "Expand Energy Corp (Chesapeake)",
    # Oilfield services + midstream
    "806857108": "Schlumberger Ltd",
    "05722G100": "Baker Hughes Company",
    "406216101": "Halliburton Co",
    "969457100": "Williams Companies Inc",
    "49456B101": "Kinder Morgan Inc",
    "682680103": "ONEOK Inc",
    "16411R208": "Cheniere Energy Inc",
    "16411Q101": "Cheniere Energy Partners LP",
    "87612G101": "Targa Resources Corp",
    # International majors (US-listed ADRs / shares)
    "780259305": "Shell plc",
    "055622104": "BP plc",
    "F92124100": "TotalEnergies SE",
    "29446M102": "Equinor ASA",
    "453038408": "Imperial Oil Ltd",
    "136385101": "Canadian Natural Resources Ltd",
    "867224107": "Suncor Energy Inc",
    "15135U109": "Cenovus Energy Inc",
    # Coal producers
    "704551100": "Peabody Energy Corp",
    "03940R107": "Arch Resources Inc",
    "20854L108": "CONSOL Energy Inc",
    "93627C101": "Warrior Met Coal Inc",
    "020764106": "Alpha Metallurgical Resources Inc",
}

# EXCLUDED after review — the false positives this curation prevents (each
# name-collided with a real fossil name but is a different business):
#   565788106 "Marathon Digital Holdings"  — a BITCOIN MINER (vs Marathon Petroleum/Oil)
#   136375102 "Canadian National Railway"  — a RAILROAD (vs Canadian Natural Resources)
#   88262P102 "Texas Pacific Land"         — land/royalty, not a producer (conservative)

# Count is derived from the list so the public-facing string can never drift.
COVERAGE = ("major oil & gas (integrated, E&P, refining), oilfield services, midstream, "
            "international majors' US-listed shares, and coal producers — a curated seed "
            f"of {len(FOSSIL_FUEL_CUSIPS)} companies; the full GOGEL universe (~1,800) is "
            "not yet included")
SOURCE = "curated_snapshot (hand-verified CUSIPs; full GOGEL ingest pending)"
