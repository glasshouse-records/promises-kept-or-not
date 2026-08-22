"""Case files — the forensic synthesis on top of the detector library.

One detector produces a footprint. A CASE is what a human publisher actually
needs before signing anything: every independent footprint that converges on
one manager × theme, each cited, each labelled by the evidentiary weight it
can carry.

Corroboration is the whole point. A single 79%-against rate is a lead. The
same manager, on the same theme, ALSO quietly weakening its own commitment
language, ALSO voting worse at the companies where it holds the biggest
stake — that is three independent footprints from three different record
types, and it is what turns a lead into a case a person can stand behind.

The honesty that keeps this safe:
  • Footprints are CLASSED, never blended into an invented composite "guilt
    score". Each detector declares its own class (strong / supporting /
    descriptive). We count them; we do not average them into a number that
    would imply a probability of wrongdoing.
  • Manager-scoped footprints (the firm's own rap sheet, its internal vote
    splits) are CONTEXT about the manager — they never corroborate a
    theme-specific claim.
  • A case requires at least one STRONG footprint. Descriptive and supporting
    signals cannot, alone, make a case.
  • Every footprint keeps its citation. Nothing here asserts motive.

Cases are still LEADS. Publication remains a human act (review.py /
firststone.py). This module only reads.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import detectors


@dataclass
class Case:
    """All independent footprints converging on one manager × theme."""
    institution_id: str
    institution_name: str
    subject: str                                   # the theme
    footprints: list[detectors.Lead] = field(default_factory=list)       # theme-scoped
    manager_context: list[detectors.Lead] = field(default_factory=list)  # manager-scoped

    def _n(self, cls: str) -> int:
        return sum(1 for f in self.footprints
                   if detectors.registry()[f.detector_id].evidence_class == cls)

    @property
    def n_strong(self) -> int:
        return self._n("strong")

    @property
    def n_supporting(self) -> int:
        return self._n("supporting")

    @property
    def n_descriptive(self) -> int:
        return self._n("descriptive")

    @property
    def rank_key(self) -> tuple:
        # Independent STRONG corroboration first; then breadth; then the single
        # most pronounced footprint. Never a blended "score".
        return (self.n_strong, len(self.footprints),
                max((f.strength for f in self.footprints), default=0.0))


def build_cases(conn: sqlite3.Connection, **kw) -> list[Case]:
    """Group every detector's leads into manager × theme cases, ranked by
    independent strong corroboration. Reads only.

    A case needs at least one STRONG footprint — a descriptive or supporting
    signal cannot make a case on its own."""
    reg = detectors.registry()
    theme_leads: dict[tuple[str, str], list[detectors.Lead]] = {}
    mgr_leads: dict[str, list[detectors.Lead]] = {}

    for det_id, leads in detectors.run_all(conn, **kw).items():
        scope = reg[det_id].scope
        if reg[det_id].polarity == "favourable":
            continue          # exculpatory: shown via favourable_for(), never as corroboration
        for ld in leads:
            if scope == "manager":
                # keyed by name: vote-divergence carries no institution_id
                mgr_leads.setdefault(ld.institution_name, []).append(ld)
            else:
                theme_leads.setdefault((ld.institution_id, ld.subject), []).append(ld)

    cases: list[Case] = []
    for (iid, theme), fps in theme_leads.items():
        case = Case(institution_id=iid, institution_name=fps[0].institution_name,
                    subject=theme, footprints=fps,
                    manager_context=mgr_leads.get(fps[0].institution_name, []))
        if case.n_strong == 0:
            continue          # descriptive/supporting alone is not a case
        cases.append(case)
    cases.sort(key=lambda c: c.rank_key, reverse=True)
    return cases


def favourable_for(conn: sqlite3.Connection, institution_id: str, subject: str,
                   **kw) -> list[detectors.Lead]:
    """What the record shows in the institution's FAVOUR on this same claim.

    A case file that cannot show exculpatory evidence is a case for the
    prosecution. These leads are deliberately kept out of the corroboration
    count (good behaviour must not make a case look stronger) and surfaced
    separately, so the reader weighs both."""
    out: list[detectors.Lead] = []
    reg = detectors.registry()
    for det_id, leads in detectors.run_all(conn, **kw).items():
        if reg[det_id].polarity != "favourable":
            continue
        out += [ld for ld in leads
                if ld.institution_id == institution_id and ld.subject == subject]
    return out


def case_markdown(case: Case, favourable: list[detectors.Lead] | None = None) -> str:
    """A cited case file, in registrar voice: what converges, how strong each
    footprint is, and where every claim traces to. Never motive."""
    reg = detectors.registry()
    label = case.subject.replace("-", " ")
    lines = [f"# {case.institution_name} — {label}", "",
             f"**{case.n_strong} strong** · {case.n_supporting} supporting · "
             f"{case.n_descriptive} descriptive footprint(s) converge here.", "",
             "> Each footprint below is an independently derived, cited observation "
             "from the public record. They are **leads**, not findings: a human must "
             "verify every primary source before publication. Nothing here states "
             "why an institution acted — only what the record shows it did.", "",
             "## Converging footprints", ""]
    for f in sorted(case.footprints, key=lambda x: -x.strength):
        d = reg[f.detector_id]
        lines.append(f"### {d.name} — _{d.evidence_class}_")
        lines.append(f"{f.headline}")
        lines.append(f"- *asks:* {d.question}")
        lines.append(f"- *why this weight:* {d.validation}")
        ev = f.evidence
        if ev.get("doc_url"):
            lines.append(f"- *policy source:* {ev['doc_url']}")
        for v in (ev.get("votes") or [])[:3]:
            src = f" ({v['source_url']})" if v.get("source_url") else ""
            lines.append(f"- *cited vote:* AGAINST “{v['vote_description'][:70]}” at "
                         f"{v['issuer_name']} — N-PX `{v['accession']}`{src}")
        if ev.get("filing_accession"):
            lines.append(f"- *13-F filing:* `{ev['filing_accession']}` "
                         f"(retrieved {ev.get('filing_retrieved', '')})")
        for ch in (ev.get("softenings") or [])[:2]:
            lines.append(f"- *language softened* {ch['from_version']}→{ch['to_version']}: "
                         f"“{ch['from'][:60]}…” → “{ch['to'][:60]}…”")
        if ev.get("shrink"):
            s = ev["shrink"]
            lines.append(f"- *binding commitments fell* {s['from_n']} → {s['to_n']} "
                         f"(versions {s['from_version']}→{s['to_version']})")
        lines.append("")
    if favourable:
        lines += ["## What the record shows in their favour", "",
                  "_Exculpatory findings on this same claim. They are deliberately NOT "
                  "counted as corroboration above — good behaviour must not make a case "
                  "look stronger — but a file that hid them would be a case for the "
                  "prosecution, not a record._", ""]
        for f in favourable:
            lines.append(f"- **{reg[f.detector_id].name}:** {f.headline}")
        lines.append("")
    if case.manager_context:
        lines += ["## Manager-level context", "",
                  "_About the firm, not corroboration of the claim above._", ""]
        for f in case.manager_context:
            lines.append(f"- **{reg[f.detector_id].name}:** {f.headline}")
        lines.append("")
    lines += ["---", "",
              "*Every figure is recomputable from the public Glasshouse ledger. "
              "Footprint classes: **strong** = an active choice or documented act; "
              "**supporting** = a weaker class (holdings carry an index alibi); "
              "**descriptive** = discriminating power unproven on this record.*"]
    return "\n".join(lines)
