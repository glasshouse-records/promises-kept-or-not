"""The systemic finding: does a published commitment predict anything?

Glasshouse's per-manager detectors answer "what did THIS firm do?". This
module answers the bigger and more defensible question: **across the
industry, does making a public commitment change how a manager votes?**

Why this is the load-bearing claim
----------------------------------
It is safer (a statistical statement about an industry practice, not an
accusation against a named firm), it is bigger (it speaks to the whole
stewardship-promise apparatus), and no paywalled competitor is making it.

Why it is computed PAIRED
-------------------------
The naive comparison — all committed cells vs all uncommitted cells — is
CONFOUNDED, and we proved it on our own data (2026-07-16): it showed
committed managers voting against MORE (82% vs 71%), which looked damning
and was an artifact. The committed group is dominated by managers who vote
against nearly everything, so the "gap" was composition, not behaviour.

The paired design compares each manager **against itself**: its
against-rate on themes it publicly commits to vs. its own against-rate on
themes it never promised anything about. House voting philosophy — the
confound — cancels out. On the real ledger the paired median is ≈ −2%:
the promise makes no measurable difference.

Symmetry is a requirement, not a courtesy
-----------------------------------------
A registrar that can only ever report fault is a prosecutor with a
database. When a manager votes BETTER on the themes it committed to, this
module reports that as plainly as the reverse — which is precisely what
makes the unflattering results hard to dismiss.

Reads a matrix payload (investigate.build_matrix / the cache). No motive,
ever: it reports rates, differences and sample sizes.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Below this, a difference in against-rate is not meaningfully distinguishable
# from noise at our sample sizes; we call it "no difference" rather than
# dressing a rounding error up as a finding.
FLAT = 0.05


@dataclass
class ManagerPair:
    """One manager compared against itself."""
    institution_id: str
    institution_name: str
    committed_rate: float      # against-rate on themes it publicly commits to
    committed_n: int
    baseline_rate: float       # its own rate on themes it never promised
    baseline_n: int

    @property
    def delta(self) -> float:
        """committed − baseline. NEGATIVE means it votes against LESS where it
        made a promise (the promise looks like it mattered)."""
        return round(self.committed_rate - self.baseline_rate, 4)

    @property
    def direction(self) -> str:
        if self.delta <= -FLAT:
            return "better"        # votes for the theme more where it committed
        if self.delta >= FLAT:
            return "worse"
        return "no difference"


def _split(inst: dict) -> tuple[int, int, int, int]:
    """(committed_for, committed_against, baseline_for, baseline_against)."""
    cf = ca = bf = ba = 0
    for c in inst["cells"].values():
        if c["for"] + c["against"] == 0:
            continue
        if c["committed"]:
            cf += c["for"]
            ca += c["against"]
        else:
            bf += c["for"]
            ba += c["against"]
    return cf, ca, bf, ba


def paired_comparison(matrix: dict, *, min_votes: int = 20) -> list[ManagerPair]:
    """Each manager against itself. A manager needs enough votes on BOTH sides
    to be compared at all — no baseline means no comparison, not a guess."""
    out: list[ManagerPair] = []
    for inst in matrix["institutions"]:
        cf, ca, bf, ba = _split(inst)
        if cf + ca < min_votes or bf + ba < min_votes:
            continue
        out.append(ManagerPair(
            institution_id=inst["id"], institution_name=inst["name"],
            committed_rate=round(ca / (cf + ca), 4), committed_n=cf + ca,
            baseline_rate=round(ba / (bf + ba), 4), baseline_n=bf + ba))
    out.sort(key=lambda p: p.delta, reverse=True)
    return out


def industry_summary(matrix: dict, *, min_votes: int = 20) -> dict:
    """The systemic picture: the raw aggregate (labelled as confounded), the
    paired result (the defensible one), and a verdict in registrar voice."""
    tf = ta = uf = ua = 0
    for inst in matrix["institutions"]:
        cf, ca, bf, ba = _split(inst)
        tf += cf
        ta += ca
        uf += bf
        ua += ba
    raw_committed = round(ta / (tf + ta), 4) if (tf + ta) else None
    raw_uncommitted = round(ua / (uf + ua), 4) if (uf + ua) else None

    pairs = paired_comparison(matrix, min_votes=min_votes)
    deltas = [p.delta for p in pairs]
    median = round(statistics.median(deltas), 4) if deltas else None

    if median is None:
        verdict = ("Not enough paired evidence yet to say whether a published "
                   "commitment is associated with how a manager votes.")
    elif abs(median) < FLAT:
        verdict = (
            "Across the managers that can be compared against themselves, a "
            "published commitment shows no measurable association with how the "
            "manager votes: the same firms vote against theme proposals at "
            "close to the same rate whether or not they publicly committed to "
            "that theme.")
    elif median >= FLAT:
        verdict = (
            "Across the managers that can be compared against themselves, "
            "commitment themes are voted against at a higher rate than the "
            "same managers' own uncommitted themes.")
    else:
        verdict = (
            "Across the managers that can be compared against themselves, "
            "commitment themes are voted against at a lower rate than the same "
            "managers' own uncommitted themes.")

    return {
        "generated": matrix.get("generated", ""),
        "raw_committed_rate": raw_committed,
        "raw_uncommitted_rate": raw_uncommitted,
        "raw_votes": tf + ta + uf + ua,
        "raw_caveat": (
            "This raw comparison pools different managers and is CONFOUNDED: the "
            "committed group is dominated by houses that vote against nearly "
            "everything, so a difference here can be composition rather than "
            "behaviour. It is shown for transparency; the paired result below is "
            "the one to rely on."),
        "paired_median_delta": median,
        "n_managers": len(pairs),
        "n_better": sum(1 for p in pairs if p.direction == "better"),
        "n_worse": sum(1 for p in pairs if p.direction == "worse"),
        "n_flat": sum(1 for p in pairs if p.direction == "no difference"),
        "pairs": pairs,
        "verdict": verdict,
        "method": (
            "Each manager is compared against ITSELF: its against-rate on themes "
            "its own archived policy commits to, versus its against-rate on "
            "themes it never committed to. This paired design cancels out house "
            "voting philosophy, the confound that breaks the raw comparison. "
            f"Managers need at least {min_votes} votes on both sides to appear."),
    }


def summary_markdown(s: dict) -> str:
    """Registrar voice: the method, both directions, and the numbers."""
    pct = lambda x: "—" if x is None else f"{x:.1%}"   # noqa: E731
    lines = [
        "# Does a stewardship promise predict anything?", "",
        f"**{s['verdict']}**", "",
        "## How this is measured", "", s["method"], "",
        "## The paired result", "",
        f"Managers compared: **{s['n_managers']}** · votes better than their own "
        f"baseline: **{s['n_better']}** · worse: **{s['n_worse']}** · no measurable "
        f"difference: **{s['n_flat']}** · median difference: "
        f"**{pct(s['paired_median_delta'])}**", "",
        "| Manager | On themes it commits to | On its own other themes | Difference | |",
        "|---|---|---|---|---|",
    ]
    for p in s["pairs"]:
        mark = {"better": "votes for it more", "worse": "votes against it more",
                "no difference": "no measurable difference"}[p.direction]
        lines.append(
            f"| {p.institution_name} | {pct(p.committed_rate)} against "
            f"({p.committed_n:,} votes) | {pct(p.baseline_rate)} against "
            f"({p.baseline_n:,} votes) | {p.delta:+.1%} | {mark} |")
    lines += [
        "", "A negative difference means the manager votes **for** the theme more "
        "often where it made a public commitment.", "",
        "## The raw comparison, and why we do not rely on it", "",
        f"Pooled across managers, commitment themes were voted against "
        f"{pct(s['raw_committed_rate'])} of the time versus "
        f"{pct(s['raw_uncommitted_rate'])} on uncommitted themes "
        f"({s['raw_votes']:,} votes).", "", s["raw_caveat"], "",
        "---", "",
        "*Every figure is recomputable from the public Glasshouse ledger. This "
        "page reports rates and differences in the voting record; it does not "
        "state why any institution voted as it did.*",
    ]
    return "\n".join(lines)
