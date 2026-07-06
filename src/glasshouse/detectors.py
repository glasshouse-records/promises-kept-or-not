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
    "own-enforcement": {
        "name": "Own enforcement record",
        "family": "Own conduct",
        "question": "Does a manager that publishes stewardship commitments have its own "
                    "documented enforcement record (resolutions, not allegations)?",
        "reads": "the manager's own enforcement record × its published commitments",
    },
    "commitment-decay": {
        "name": "Commitment decay",
        "family": "Commitment integrity",
        "question": "Did the manager's commitment language on a theme quietly WEAKEN "
                    "across archived policy versions (e.g. 'expect' → 'ask'), or drop out?",
        "reads": "archived policy versions (walk-back timeline) × commitment-strength",
    },
    # Reserved — earned in later loops (kept here so the catalogue is legible):
    # "selective-silence"   — loud where exposure is low, silent where it is high
    # DEFERRED: the HELD-COMPANY claims-vs-enforcement ("backs companies later fined
    #   in a theme it champions") is NOT built — our enforcement data is name-only
    #   (no identifiers → Aldar-class joins), OFAC-dominated, and index managers hold
    #   nearly every fined company (base rate ≈ everyone, so it can't be selective).
    #   It needs identifier-linked, theme-tagged enforcement data (EEOC/EPA + CUSIPs,
    #   or OpenCorporates entity resolution) before it can be precise. Learned cheaply.
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

    def universe(self, conn: sqlite3.Connection, **kw) -> int | None:
        """The count of eligible units this detector examines (the denominator
        for selectivity). Override to enable selectivity; None disables it."""
        return None

    def scorecard(self, conn: sqlite3.Connection, **kw) -> dict:
        """How this detector is validated + what it currently finds. Every
        detector must be able to answer 'why should anyone trust you?'."""
        leads = self.run(conn, **kw)
        sc = {"detector_id": self.id, "technique": self.technique,
              "leads": len(leads), "validation": self.validation}
        sc.update(_selectivity(self, conn, len(leads), **kw))
        return sc

    validation: str = "unvalidated"


def _selectivity(det: Detector, conn: sqlite3.Connection, flagged: int, **kw) -> dict:
    """Shared: of all eligible units, what fraction did the detector flag? A
    high fraction means the pattern is WIDESPREAD (the finding is the industry,
    not a rare few); a low fraction means the detector is picking out a subset."""
    uni = det.universe(conn, **kw)
    if not uni:
        return {}
    frac = round(flagged / uni, 4)
    if frac >= 0.66:
        note = (f"flags {frac:.0%} of the {uni} eligible units — a WIDESPREAD "
                "pattern; the finding is the industry norm, not a rare outlier")
    elif frac <= 0.33:
        note = f"flags a selective {frac:.0%} of the {uni} eligible units"
    else:
        note = f"flags {frac:.0%} of the {uni} eligible units"
    return {"universe": uni, "flagged": flagged, "selectivity": frac,
            "selectivity_note": note}


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
                  "anti-theme proposals; every lead is quarantined until a human "
                  "verifies it before publication.")

    def run(self, conn: sqlite3.Connection, *, min_rate: float = 0.6,
            min_votes: int = 10, matrix: dict | None = None, **kw) -> list[Lead]:
        # Callers with a warm cache (the workbench) pass matrix= for speed;
        # everyone else (tests, CLI) builds fresh from this conn.
        matrix = matrix if matrix is not None else investigate.build_matrix(conn)
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

    def universe(self, conn: sqlite3.Connection, *, min_votes: int = 10,
                 matrix: dict | None = None, **kw) -> int:
        matrix = matrix if matrix is not None else investigate.build_matrix(conn)
        return sum(1 for inst in matrix["institutions"] for c in inst["cells"].values()
                   if c["committed"] and (c["for"] + c["against"]) >= min_votes)


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

    def _committed_cells(self, conn: sqlite3.Connection, matrix: dict | None = None):
        matrix = matrix if matrix is not None else investigate.build_matrix(conn)
        for inst in matrix["institutions"]:
            for theme, c in inst["cells"].items():
                if c["committed"] and c["quote"]:
                    yield inst, theme, c

    def run(self, conn: sqlite3.Connection, *, max_strength: float = 0.5,
            matrix: dict | None = None, **kw) -> list[Lead]:
        leads: list[Lead] = []
        for inst, theme, c in self._committed_cells(conn, matrix):
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

    def universe(self, conn: sqlite3.Connection, *, matrix: dict | None = None, **kw) -> int:
        # Eligible = committed cells whose quote carries enough modal signal to score.
        n = 0
        for _inst, _theme, c in self._committed_cells(conn, matrix):
            _, nh, ns = self.strength(c["quote"])
            if nh + ns >= 2:
                n += 1
        return n

    def scorecard(self, conn: sqlite3.Connection, *, matrix: dict | None = None, **kw) -> dict:
        matrix = matrix if matrix is not None else investigate.build_matrix(conn)
        soft, hard = [], []
        for _inst, _theme, c in self._committed_cells(conn, matrix):
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
        flagged = len(self.run(conn, matrix=matrix, **kw))
        sc = {"detector_id": self.id, "technique": self.technique,
              "leads": flagged, "validation": self.validation,
              "n_soft": len(soft), "n_hard": len(hard),
              "soft_against_rate": sr, "hard_against_rate": hr,
              "discriminates": discriminates, "note": note}
        sc.update(_selectivity(self, conn, flagged, matrix=matrix, **kw))
        return sc


# ── Detector #3: the manager's OWN enforcement record vs its stewardship claim

class OwnRecord(Detector):
    """A manager that publishes stewardship commitments — holding itself out as
    a responsible steward — set against its OWN documented enforcement record.
    The 'rap sheet vs. the marketing' (the DWS-greenwashing shape).

    Precision, non-negotiable: name-join → every lead is quarantined (the record
    often names a subsidiary — verify the corporate relationship); ALLEGATIONS
    (open dockets) are excluded — they are never findings; OFAC name-collisions
    are excluded (the Aldar class); every resolution_type is preserved verbatim
    (a guilty plea is not a DPA is not a civil settlement). It states the
    conjunction of documented facts, never motive."""
    id = "own-record"
    name = "Own enforcement record (stewardship claim vs. own record)"
    technique = "own-enforcement"
    question = ("Does a manager that publishes stewardship commitments have its own "
                "documented enforcement record?")
    validation = ("Small, fast, name-join over the manager's own record (not portfolio "
                  "exposure, so no base-rate blow-up). Allegations and OFAC collisions "
                  "excluded; resolution types preserved; every lead quarantined for the "
                  "subsidiary check. States documented facts, never motive or knowledge.")
    # Legal-weight anchors from METHODOLOGY.md (for footprint prominence only).
    _SEVERITY = {"guilty_plea": 10, "dpa": 7, "npa": 6, "debarment": 6,
                 "civil_settlement": 5, "civil_violation": 4, "board_order": 4,
                 "administrative_action": 3, "expulsion": 2}

    def _stewards(self, conn: sqlite3.Connection) -> set[str]:
        return {r["institution_id"] for r in
                conn.execute("SELECT DISTINCT institution_id FROM commitments")}

    def run(self, conn: sqlite3.Connection, **kw) -> list[Lead]:
        from . import findings
        stewards = self._stewards(conn)
        by_mgr: dict[str, list] = {}
        for o in findings.own_record(conn):          # already OFAC-excluded + quarantined
            if o.resolution_type in ("allegation", "unverified"):
                continue                              # allegations are never findings
            if o.institution_id not in stewards:
                continue                              # no published commitment = no claim side
            by_mgr.setdefault(o.institution_id, []).append(o)
        leads: list[Lead] = []
        for mid, recs in by_mgr.items():
            name = recs[0].institution
            sev = max(self._SEVERITY.get(r.resolution_type, 3) for r in recs)
            types = ", ".join(sorted({r.resolution_type.replace("_", " ") for r in recs}))
            leads.append(Lead(
                detector_id=self.id, technique=self.technique,
                institution_id=mid, institution_name=name, subject="own record",
                headline=(f"{name} publishes stewardship commitments; its own enforcement "
                          f"record includes {len(recs)} resolution(s): {types}"),
                strength=round(sev / 10, 4),
                evidence={"quarantined": True,
                          "note": ("name-join — the record may name a subsidiary; verify the "
                                   "corporate relationship. Allegations and OFAC collisions "
                                   "excluded; resolution types are legally distinct."),
                          "resolutions": [
                              {"agency": r.agency, "resolution_type": r.resolution_type,
                               "primary_ref": r.primary_ref, "action_date": r.action_date,
                               "penalty_usd": r.penalty_usd,
                               "description": (r.description or "")[:200],
                               "source_url": r.source_url} for r in recs]},
                provenance={"technique": self.technique, "join": "name_exact",
                            "excludes": "allegations, OFAC sanction_designation, duplicates"}))
        leads.sort(key=lambda x: -x.strength)
        return leads

    def universe(self, conn: sqlite3.Connection, **kw) -> int:
        return len(self._stewards(conn))


# ── Detector #4: commitment decay (the walk-back, quantified) ───────────────

class CommitmentDecay(Detector):
    """Where a manager's commitment language on a theme quietly WEAKENED across
    archived policy versions — a firm term softened ('expect' → 'ask',
    'will' → 'may', 'require' → 'encourage') or a commitment dropped out
    entirely. Reuses the walk-back timeline (whose diff guards already prevent
    extraction-artifact false removals) and the commitment-strength measure to
    judge the DIRECTION of each change.

    Footprints only: it states that dated version A carried firmer language than
    dated version B, quoting both — never why. It reports softenings/removals,
    not rewordings that keep or raise strength."""
    id = "commitment-decay"
    name = "Commitment decay (language weakened over time)"
    technique = "commitment-decay"
    question = ("Did the manager's commitment language on a theme quietly weaken across "
                "archived policy versions, or drop out?")
    validation = ("Descriptive and verbatim-cited: compares the commitment-strength of "
                  "matched sentences between consecutive archived versions (same walk-back "
                  "timeline used on the public site). A change counts only when strength "
                  "DROPS or a commitment is removed; both versions are linked. States "
                  "dated facts, never motive.")

    def _timelines(self, conn: sqlite3.Connection, timelines: dict | None = None):
        if timelines is not None:
            return list(timelines.get("institutions", {}).values())
        from . import timeline
        return [timeline.institution_timeline(conn, r["id"])
                for r in conn.execute("SELECT id FROM institutions ORDER BY id")]

    def _decay(self, data: dict) -> tuple[list[dict], dict | None]:
        """Two honest signals: (1) SOFTENINGS — a tracked sentence whose
        commitment-strength dropped (expect→ask); (2) net SHRINKAGE — the count
        of binding commitment sentences for the theme fell within one document
        lineage (first vs last version that carries any). Raw removals are NOT
        counted, because a reworded commitment shows up as removed+added and
        would overstate abandonment."""
        strength = CommitmentStrength.strength
        softenings = []
        for ev in data["events"]:
            for old, new in ev["revised"]:
                if strength(new)[0] < strength(old)[0]:
                    softenings.append({"from": old, "to": new,
                                       "from_version": ev["from"]["version"],
                                       "to_version": ev["to"]["version"],
                                       "from_url": ev["from"]["url"], "to_url": ev["to"]["url"]})
        by_doc: dict[str, list] = {}
        for p in data.get("presence", []):
            by_doc.setdefault(p["doc_label"], []).append(p)   # already version-ordered per lineage
        shrink = None
        for pres in by_doc.values():
            if len(pres) >= 2 and pres[-1]["n"] < pres[0]["n"]:
                drop = pres[0]["n"] - pres[-1]["n"]
                if shrink is None or drop > shrink["drop"]:
                    shrink = {"drop": drop, "from_n": pres[0]["n"], "to_n": pres[-1]["n"],
                              "from_version": pres[0]["version"], "to_version": pres[-1]["version"],
                              "from_url": pres[0]["url"], "to_url": pres[-1]["url"],
                              "from_sample": pres[0]["sample"]}
        return softenings, shrink

    def run(self, conn: sqlite3.Connection, *, timelines: dict | None = None, **kw) -> list[Lead]:
        leads: list[Lead] = []
        for tl in self._timelines(conn, timelines):
            for theme, data in tl["themes"].items():
                softenings, shrink = self._decay(data)
                if not softenings and not shrink:
                    continue
                label = theme.replace("-", " ")
                bits = []
                if shrink:
                    bits.append(f"binding commitments fell from {shrink['from_n']} to "
                                f"{shrink['to_n']} (versions {shrink['from_version']}→"
                                f"{shrink['to_version']})")
                if softenings:
                    bits.append(f"{len(softenings)} firm term(s) softened")
                mag = (shrink["drop"] if shrink else 0) + len(softenings)
                leads.append(Lead(
                    detector_id=self.id, technique=self.technique,
                    institution_id=tl["institution_id"], institution_name=tl["name"],
                    subject=theme,
                    headline=(f"{tl['name']}'s {label} commitment language weakened across "
                              f"archived versions — {'; '.join(bits)}"),
                    strength=round(min(1.0, mag / 4), 4),
                    evidence={"softenings": softenings, "shrink": shrink},
                    provenance={"technique": self.technique,
                                "source": "walk-back timeline × commitment-strength"}))
        leads.sort(key=lambda x: -x.strength)
        return leads

    def universe(self, conn: sqlite3.Connection, *, timelines: dict | None = None, **kw) -> int:
        # (manager, theme) pairs that changed at all — the honest denominator for
        # "when the language changed, how often did it weaken?"
        n = 0
        for tl in self._timelines(conn, timelines):
            for data in tl["themes"].values():
                if data["events"]:
                    n += 1
        return n


# ── registry ────────────────────────────────────────────────────────────────

_DETECTORS: list[Detector] = [BrokenPromise(), CommitmentStrength(), OwnRecord(),
                              CommitmentDecay()]


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
