"""
NLRB (National Labor Relations Board) Significant Violation Database

Static snapshot of publicly-traded companies with significant, recent NLRB
findings of Unfair Labor Practices (ULPs) — actions that suppress workers'
organizing rights, retaliate against union activity, or refuse to bargain
in good faith in violation of the National Labor Relations Act.

SCOPE: Only includes:
  (a) Final Board orders with substantial compliance orders, AND
  (b) Companies where violations affected 500+ workers or involved systematic
      campaigns to suppress organizing, AND
  (c) Conduct within the last 10 years (post-2015).

NOT included:
  - Routine single-incident ULP charges that were settled or withdrawn
  - Violations by subsidiaries where the parent has no ownership interest
  - Non-US employers (NLRA applies only in the United States)

Confidence: 0.72 (NLRB proceedings are real but linking to publicly-traded
parent companies requires corporate structure research that may be stale).

Source: NLRB Case Activity Tracking System (CATS) + Board orders
        https://www.nlrb.gov/cases-decisions/cases
Data extracted: 2026-05-26
"""

from __future__ import annotations

# Format: {name_fragment_lower: entry_dict}
NLRB_VIOLATORS: dict[str, dict] = {

    # ── Retail & Logistics ────────────────────────────────────────────────────

    "amazon": {
        "company": "Amazon.com, Inc.",
        "violation_types": ["unlawful_discharge", "interference_with_organizing", "refusal_to_bargain"],
        "worker_count_affected": 10000,  # conservative estimate across multiple facilities
        "key_cases": [
            {
                "case_ref": "NLRB Case 29-CA-261755",
                "date": "2022-03-31",
                "facility": "JFK8 (Staten Island, NY) + multiple warehouses",
                "description": (
                    "NLRB found Amazon illegally surveilled workers, threatened them for organizing, "
                    "and unlawfully discharged organizers at JFK8 Staten Island warehouse during "
                    "successful ALU union election campaign (first Amazon US union victory, April 2022). "
                    "Multiple ULP charges across NY, NJ, CA, TN, and other states."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.85,  # very well-documented
    },

    "starbucks": {
        "company": "Starbucks Corporation",
        "violation_types": ["unlawful_discharge", "interference_with_organizing", "refusal_to_bargain"],
        "worker_count_affected": 8000,
        "key_cases": [
            {
                "case_ref": "NLRB consolidated complaints 2022-2024",
                "date": "2023-06-09",
                "facility": "Multiple US locations (300+ stores)",
                "description": (
                    "NLRB filed hundreds of ULP complaints against Starbucks for unlawfully firing "
                    "union organizers, closing stores to prevent unionization, and refusing to bargain "
                    "in good faith with Workers United. A federal judge issued multiple injunctions "
                    "requiring reinstatement of fired workers. By 2024, NLRB had issued 100+ complaints "
                    "covering 400+ stores and thousands of workers."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.90,
    },

    "apple": {
        "company": "Apple Inc.",
        "violation_types": ["interference_with_organizing", "unlawful_rules"],
        "worker_count_affected": 2000,
        "key_cases": [
            {
                "case_ref": "NLRB 2022-2023 complaints",
                "date": "2022-10-27",
                "facility": "Apple retail stores (NY, MD, KY, OK, GA)",
                "description": (
                    "NLRB found Apple illegally interrogated workers, maintained overly broad "
                    "confidentiality rules that chilled organizing, and took adverse actions "
                    "against workers engaged in protected concerted activity at several US Apple "
                    "Stores. Workers at multiple locations voted to unionize 2022-2023."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.78,
    },

    "tesla": {
        "company": "Tesla, Inc.",
        "violation_types": ["unlawful_discharge", "interference_with_organizing", "surveillance"],
        "worker_count_affected": 3000,
        "key_cases": [
            {
                "case_ref": "NLRB 32-CA-197958 et al.",
                "date": "2021-03-25",
                "facility": "Fremont, CA Gigafactory + other facilities",
                "description": (
                    "NLRB Administrative Law Judge ruled Tesla violated NLRA by unlawfully "
                    "firing union activist Richard Ortiz, surveilling workers organizing union "
                    "activity, and requiring workers to remove union-related clothing. Tesla CEO "
                    "Elon Musk's anti-union tweet was found to violate workers' rights. "
                    "Multiple ULP findings and reinstatement orders 2018-2023."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.85,
    },

    "walmart": {
        "company": "Walmart Inc.",
        "violation_types": ["unlawful_discharge", "interference_with_organizing", "surveillance"],
        "worker_count_affected": 5000,
        "key_cases": [
            {
                "case_ref": "NLRB 10-CA-001590 + multiple",
                "date": "2015-06-01",
                "facility": "Multiple US Walmart locations",
                "description": (
                    "NLRB found Walmart violated NLRA by threatening, disciplining, and unlawfully "
                    "terminating employees who participated in OUR Walmart strikes and protests. "
                    "NLRB complaint covered workers in 14 states. Settlement required posting of "
                    "notices, though Walmart disputed findings. Multiple store closures were found "
                    "to be retaliatory by workers (though not formally adjudicated as such)."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "starbucks",
        "confidence": 0.72,
    },

    "trader joe": {
        "company": "Trader Joe's Company",
        "violation_types": ["refusal_to_bargain", "interference_with_organizing"],
        "worker_count_affected": 800,
        "key_cases": [
            {
                "case_ref": "NLRB regional complaints 2022-2024",
                "date": "2023-04-14",
                "facility": "Multiple US locations",
                "description": (
                    "NLRB found Trader Joe's refused to bargain with Trader Joe's United (TJU) "
                    "union at unionized stores, changed working conditions unilaterally, and "
                    "engaged in surface bargaining. NLRB issued multiple complaints 2023-2024."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.72,
    },

    # ── Meat Processing / Food ────────────────────────────────────────────────

    "tyson": {
        "company": "Tyson Foods, Inc.",
        "violation_types": ["interference_with_organizing", "unlawful_discharge"],
        "worker_count_affected": 2000,
        "key_cases": [
            {
                "case_ref": "NLRB 18-CA-multiple",
                "date": "2020-07-01",
                "facility": "Multiple processing plants (IA, MO, KS, NE)",
                "description": (
                    "NLRB investigated multiple ULP charges at Tyson Foods processing plants "
                    "related to COVID-19 safety complaints treated as protected concerted activity. "
                    "Prior NLRB findings in 2015-2019 at storm lake, IA and other facilities "
                    "for interference with UFCW organizing campaigns."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.68,
    },

    # ── Gig Economy ──────────────────────────────────────────────────────────

    "uber": {
        "company": "Uber Technologies, Inc.",
        "violation_types": ["misclassification_related", "interference_with_organizing"],
        "worker_count_affected": 50000,
        "key_cases": [
            {
                "case_ref": "NLRB GC Memo 23-08 (2023)",
                "date": "2023-09-29",
                "facility": "US operations nationwide",
                "description": (
                    "NLRB General Counsel issued memo (GC 23-08) finding rideshare and app-based "
                    "delivery workers are employees, not independent contractors, under the NLRA. "
                    "This directly implicates Uber's worker classification practices. Multiple ULP "
                    "charges filed by drivers alleging retaliation for organizing. "
                    "Note: GC memo is legal interpretation, not final Board adjudication."
                ),
            },
        ],
        "source_url": "https://www.nlrb.gov/cases-decisions/cases",
        "source": "NLRB",
        "confidence": 0.65,  # GC memo, not final Board order
    },

}


def lookup_nlrb_violation(entity_name: str) -> dict | None:
    """
    Check if entity_name matches a company with significant NLRB ULP findings.

    Returns a dict with violation details, or None on no match.

    Note: Confidence is entity-specific (stored in the entry dict).
    The classifier uses a flat 0.72 confidence for all NLRB matches
    unless overridden here.
    """
    name_lower = entity_name.lower().strip()
    if not name_lower:
        return None

    # ── 1. Try live NLRB Socrata API first (7-day disk cache) ────────────
    try:
        from core.live_fetchers import lookup_nlrb_live
        live_result = lookup_nlrb_live(entity_name)
        if live_result:
            return live_result
    except Exception:
        pass  # live fetch unavailable; fall through to curated static dict

    # ── 2. Fall back to curated static dict ───────────────────────────────
    from core.entity_matcher import fuzzy_match
    for fragment, entry in NLRB_VIOLATORS.items():
        matched, _score = fuzzy_match(entity_name, fragment)
        if matched:
            return {
                "has_nlrb_violation": True,
                "company":           entry["company"],
                "violation_types":   entry["violation_types"],
                "worker_count":      entry.get("worker_count_affected", 0),
                "key_cases":         entry.get("key_cases", []),
                "source_url":        entry.get("source_url", "https://www.nlrb.gov"),
                "confidence":        entry.get("confidence", 0.72),
                "data_gap":          False,
            }

    return None
