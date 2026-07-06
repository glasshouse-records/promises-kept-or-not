"""The detector framework — the spine of the "big tool".

Every accountability pattern Glasshouse can find is a DETECTOR: one named
tool that asks a single sharp question of the primary record and emits cited
LEADS. Detectors are pluggable — the say-vs-do engine, commitment-strength,
selective silence, claims-vs-enforcement each become one — but they all share
this shape, land in the same review → newsroom → publish pipeline, and each
carries a self-describing SCORECARD (the tool held accountable for its own
method).

Two rules hold for every detector, forever:
  • FOOTPRINTS, NOT VERDICTS. A lead states cited acts, dates, amounts, votes
    — never motive. "Committed to X, voted against 79% of X proposals" is the
    strongest possible claim *and* the safest. Intent is for humans/courts.
  • LEADS ONLY. Detectors read the ledger and write nothing to it. Promotion
    to a finding stays a human decision (review.py → firststone.py).

TECHNIQUES is the seed of an open taxonomy of accountability-evasion patterns
(a "MITRE ATT&CK for corporate accountability"): each technique is a stable id
a detector cites, so leads are comparable and the catalogue is citable.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from . import investigate

# ── the taxonomy: accountability-evasion techniques ─────────────────────────
# Stable ids so detectors, leads, and (later) the backtest scorecards all speak
# the same language. Grows one entry per detector we earn from a real case.
TECHNIQUES: dict[str, dict] = {
    "say-vs-do": {
        "name": "Broken promise",
        "family": "Commitment integrity",
        "question": "Does the manager vote against the very theme its own policy commits to?",
        "reads": "archived policy commitments × N-PX proxy votes",
    },
    "soft-commitment": {
        "name": "Soft commitment",
        "family": "Commitment integrity",
        "question": "Is the stated commitment itself hedged — weak-modal, discretionary "
                    "language rather than a hard pledge?",
        "reads": "archived policy commitment text (Loughran-McDonald strong/weak modal basis)",
    },
    # Reserved — earned in later loops (kept here so the catalogue is legible):
    # "commitment-decay"    — commitment language quietly weakening across versions
    # "selective-silence"   — loud where exposure is low, silent where it is high
    # "claims-vs-enforcement" — champions a theme, backs companies later fined in it
}


@dataclass
class Lead:
    """One cited, quarantined signal from a detector. Self-describing: a reader
    can trace every element to a primary source without this code."""
    detector_id: str
    technique: str
    institution_id: str
    institution_name: str
    subject: str                 # what the lead is about (e.g. the theme)
    headline: str                # plain, cited, footprints-not-intent
    strength: float              # 0..1 — how pronounced the footprint is (NOT a probability of guilt)
    evidence: dict = field(default_factory=dict)     # the cited specifics
    provenance: dict = field(default_factory=dict)   # how it was derived


class Detector:
    """Base: a named question over the ledger. Subclasses implement run()."""
    id: str = ""
    name: str = ""
    technique: str = ""
    question: str = ""

    def run(self, conn: sqlite3.Connection, **kw) -> list[Lead]:  # pragma: no cover
        raise NotImplementedError

    def scorecard(self, conn: sqlite3.Connection, **kw) -> dict:
        """How this detector is validated + what it currently finds. Every
        detector must be able to answer 'why should anyone trust you?'."""
        leads = self.run(conn, **kw)
        return {"detector_id": self.id, "technique": self.technique,
                "leads": len(leads), "validation": self.validation}

    validation: str = "unvalidated"


# ── Detector #1: the preserved say-vs-do "intentions" engine ────────────────

class BrokenPromise(Detector):
    """The flagship, migrated whole from the say-vs-do engine. For each theme a
    manager's archived policy *commits* to, it reports how often the manager's
    funds voted AGAINST shareholder proposals advancing that theme — with the
    verbatim commitment and the largest cited votes.

    This is 'big banks promise climate protection, then vote against it' —
    stated as cited fact, which is exactly why it holds up."""
    id = "broken-promise"
    name = "Broken promise (say vs. do)"
    technique = "say-vs-do"
    question = ("Where a manager's own policy commits to a theme, how often do "
                "its funds vote against shareholder proposals advancing it?")
    validation = ("Validated by construction, not by prediction: SAY (a verbatim, "
                  "dated policy sentence) and DO (the de-duplicated N-PX voting "
                  "record) are both primary sources. Polarity guards exclude "
                  "anti-theme proposals; every lead is a quarantined candidate a "
                  "human confirms before publication.")

    def run(self, conn: sqlite3.Connection, *, min_rate: float = 0.6,
            min_votes: int = 10) -> list[Lead]:
        matrix = investigate.build_matrix(conn)
        leads: list[Lead] = []
        for inst in matrix["institutions"]:
            for theme, c in inst["cells"].items():
                n = c["for"] + c["against"]
                if not (c["committed"] and n >= min_votes and c["rate"] >= min_rate):
                    continue
                label = theme.replace("-", " ")
                pct = round(c["rate"] * 100)
                votes = [{"issuer_name": e["issuer_name"], "meeting_date": e["meeting_date"],
                          "vote_description": e["vote_description"], "shares_voted": e["shares_voted"],
                          "accession": e["accession"], "source_url": e.get("source_url", "")}
                         for e in c["examples"][:6]]
                leads.append(Lead(
                    detector_id=self.id, technique=self.technique,
                    institution_id=inst["id"], institution_name=inst["name"],
                    subject=theme,
                    headline=(f"{inst['name']} policy commits to {label}; its funds voted "
                              f"against {pct}% of {label} proposals on record "
                              f"({c['against']} of {n})"),
                    strength=round(c["rate"], 4),
                    evidence={"commitment_quote": c["quote"], "doc_label": c["doc_label"],
                              "doc_version": c["doc_version"], "doc_url": c["doc_url"],
                              "votes_for": c["for"], "votes_against": c["against"],
                              "against_rate": c["rate"], "votes": votes,
                              "low_confidence": c.get("low_confidence", False)},
                    provenance={"technique": self.technique,
                                "min_rate": min_rate, "min_votes": min_votes,
                                "source": "investigate.build_matrix"}))
        leads.sort(key=lambda x: (-x.strength, -x.evidence["votes_against"]))
        return leads


# ── Detector #2: commitment strength (how hedged is the promise itself) ─────

# Strong vs weak language, grounded in the Loughran-McDonald strong/weak modal
# categories (the standard financial-text dictionaries, sraf.nd.edu) plus
# explicit commitment verbs. This is our operationalization, not L-M verbatim.
_HARD_RE = re.compile(
    r"\b(?:will|shall|must|commit\w*|requir\w*|ensur\w*|guarantee\w*|pledg\w*|"
    r"mandat\w*|always|expect\w*)\b", re.IGNORECASE)
_SOFT_RE = re.compile(
    r"\b(?:may|might|could|would|encourag\w*|consider\w*|seek\w*|aim\w*|aspir\w*|"
    r"endeavou?r\w*|striv\w*|intend\w*|believ\w*|generally|typically|possibl\w*|"
    r"perhaps|where\s+appropriate|as\s+appropriate|to\s+the\s+extent|help\w*)\b",
    re.IGNORECASE)


class CommitmentStrength(Detector):
    """Scores how HARD vs SOFT a commitment's own wording is. A pledge stuffed
    with weak-modal / discretionary language ("we may consider… we generally
    encourage… where appropriate") is a soft commitment — less binding than it
    looks. This does NOT accuse; it flags that the words themselves are hedged.

    It is self-validating: the scorecard checks, on our own record, whether
    softer commitments actually go with worse voting follow-through (a higher
    against-rate). No external labels required."""
    id = "soft-commitment"
    name = "Soft commitment (hedged promise)"
    technique = "soft-commitment"
    question = ("Is the manager's stated commitment itself hedged — weak-modal, "
                "discretionary language rather than a hard pledge?")
    validation = ("Descriptive, not predictive: flags commitments whose OWN wording "
                  "is hedged (weak-modal / discretionary), read from the manager's "
                  "text (Loughran-McDonald strong/weak modal basis). Whether softness "
                  "predicts voting follow-through is tested live in the scorecard — and "
                  "reported honestly whether or not it holds. Asserts nothing about intent.")

    @staticmethod
    def strength(text: str) -> tuple[float, int, int]:
        """(strength 0..1, n_hard, n_soft). 1 = all hard language, 0 = all
        hedged. Neutral 0.5 when the sentence carries neither."""
        hard = len(_HARD_RE.findall(text or ""))
        soft = len(_SOFT_RE.findall(text or ""))
        if hard + soft == 0:
            return 0.5, 0, 0
        return round(hard / (hard + soft), 4), hard, soft

    def _committed_cells(self, conn: sqlite3.Connection):
        matrix = investigate.build_matrix(conn)
        for inst in matrix["institutions"]:
            for theme, c in inst["cells"].items():
                if c["committed"] and c["quote"]:
                    yield inst, theme, c

    def run(self, conn: sqlite3.Connection, *, max_strength: float = 0.5, **kw) -> list[Lead]:
        leads: list[Lead] = []
        for inst, theme, c in self._committed_cells(conn):
            s, nh, ns = self.strength(c["quote"])
            # Require enough modal signal to judge — a lone stray word is noise,
            # not a hedged promise (learned on the first real run, 2026-07-06).
            if s > max_strength or (nh + ns) < 2 or ns < 2:
                continue
            label = theme.replace("-", " ")
            leads.append(Lead(
                detector_id=self.id, technique=self.technique,
                institution_id=inst["id"], institution_name=inst["name"], subject=theme,
                headline=(f"{inst['name']}'s stated {label} commitment is hedged: its "
                          f"wording leans on weak-modal / discretionary language "
                          f"({ns} hedged vs {nh} firm terms)"),
                strength=round(1 - s, 4),   # strength of the FOOTPRINT = how soft it is
                evidence={"commitment_quote": c["quote"], "doc_label": c["doc_label"],
                          "doc_version": c["doc_version"], "doc_url": c["doc_url"],
                          "strength": s, "n_hard": nh, "n_soft": ns,
                          "against_rate": c["rate"], "n_votes": c["for"] + c["against"]},
                provenance={"technique": self.technique, "max_strength": max_strength,
                            "basis": "Loughran-McDonald strong/weak modal categories"}))
        leads.sort(key=lambda x: -x.strength)
        return leads

    def scorecard(self, conn: sqlite3.Connection, **kw) -> dict:
        soft, hard = [], []
        for _inst, _theme, c in self._committed_cells(conn):
            n = c["for"] + c["against"]
            if n == 0:
                continue
            s, _, _ = self.strength(c["quote"])
            (soft if s <= 0.5 else hard).append(c["rate"])
        med = lambda xs: round(sorted(xs)[len(xs) // 2], 4) if xs else None  # noqa: E731
        sr, hr = med(soft), med(hard)
        # Honest verdict: does softness actually discriminate? Needs both a real
        # sample AND a real gap AND unsaturated rates (if everyone is ~100%
        # against, softness can't predict anything).
        discriminates = bool(
            len(soft) >= 3 and len(hard) >= 3 and sr is not None and hr is not None
            and sr - hr >= 0.1 and min(sr, hr) < 0.9)
        if discriminates:
            note = (f"softer commitments go with a higher against-rate "
                    f"({sr:.0%} vs {hr:.0%}) — the signal predicts follow-through here")
        elif sr is not None and hr is not None and min(sr, hr) >= 0.9:
            note = (f"no predictive power on this record: against-rates are saturated "
                    f"(soft {sr:.0%}, hard {hr:.0%}) — committed managers vote against "
                    "at near-uniform rates, so wording can't discriminate. Ships as a "
                    "descriptive lead only.")
        else:
            note = (f"predictive self-validation not established (soft {sr}, hard {hr}, "
                    f"n_soft={len(soft)}, n_hard={len(hard)}). Descriptive lead only.")
        return {"detector_id": self.id, "technique": self.technique,
                "leads": len(self.run(conn, **kw)), "validation": self.validation,
                "n_soft": len(soft), "n_hard": len(hard),
                "soft_against_rate": sr, "hard_against_rate": hr,
                "discriminates": discriminates, "note": note}


# ── registry ────────────────────────────────────────────────────────────────

_DETECTORS: list[Detector] = [BrokenPromise(), CommitmentStrength()]


def registry() -> dict[str, Detector]:
    """All registered detectors, by id. Adding a detector is one line here."""
    return {d.id: d for d in _DETECTORS}


def run_all(conn: sqlite3.Connection, **kw) -> dict[str, list[Lead]]:
    """Run every detector; return leads grouped by detector id. Reads only."""
    return {d.id: d.run(conn, **kw) for d in _DETECTORS}


def scorecards(conn: sqlite3.Connection, **kw) -> list[dict]:
    """Every detector's self-describing scorecard — the catalogue of what the
    tool can find and why each finding can be trusted."""
    return [d.scorecard(conn, **kw) for d in _DETECTORS]
