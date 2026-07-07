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
    "30231G102": "Exxon Mobil Corp",
    "166764100": "Chevron Corporation",
    "20825C104": "ConocoPhillips",
    "969457100": "Williams Companies Inc",
    "56585A102": "Marathon Petroleum Corp",
    "718546104": "Phillips 66",
    "91913Y100": "Valero Energy Corp",
    "806857108": "Schlumberger Ltd",
    "05722G100": "Baker Hughes Company",
    "26875P101": "EOG Resources Inc",
    "49456B101": "Kinder Morgan Inc",
    "682680103": "ONEOK Inc",
    "16411R208": "Cheniere Energy Inc",
    "16411Q101": "Cheniere Energy Partners LP",
    "25278X109": "Diamondback Energy Inc",
    "25179M103": "Devon Energy Corp",
    "406216101": "Halliburton Co",
    "127097103": "Coterra Energy Inc",
    "723787107": "Pioneer Natural Resources Co",
    "42809H107": "Hess Corp",
    "674599105": "Occidental Petroleum Corp",
    "565849106": "Marathon Oil Corp",
}

# EXCLUDED after review — the false positive this curation prevents:
#   565788106 "Marathon Digital Holdings" is a BITCOIN MINER, not oil & gas
#   (name-collision with Marathon Petroleum / Marathon Oil). Never add by name.

COVERAGE = ("major US-listed oil & gas, oilfield services and midstream (curated "
            "seed of 22 companies); international majors' ADRs, coal, and the full "
            "GOGEL universe are not yet included")
SOURCE = "curated_snapshot (hand-verified CUSIPs; full GOGEL ingest pending)"
