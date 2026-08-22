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

import math
import statistics
from dataclasses import dataclass

# Below this, a difference in against-rate is not meaningfully distinguishable
# from noise at our sample sizes; we call it "no difference" rather than
# dressing a rounding error up as a finding.
FLAT = 0.05


@dataclass
class ManagerPair:
    """One manager compared against itself, with theme mix controlled."""
    institution_id: str
    institution_name: str
    committed_rate: float      # against-rate on themes it publicly commits to
    committed_n: int
    baseline_rate: float       # its own rate on themes it never promised
    baseline_n: int
    expected_delta: float = 0.0   # what THEME MIX alone predicts (the placebo)

    @property
    def delta(self) -> float:
        """committed − baseline. NEGATIVE means it votes against LESS where it
        made a promise. Raw: still contains theme mix."""
        return round(self.committed_rate - self.baseline_rate, 4)

    @property
    def residual(self) -> float:
        """The part of the difference theme mix does NOT explain. This is the
        only quantity that can carry a direction label: a manager's committed
        and baseline baskets are different mixes of themes, and themes have
        very different industry-wide rates, so the raw delta is mostly
        composition (verified by placebo, 2026-07-16)."""
        return round(self.delta - self.expected_delta, 4)

    @property
    def significant(self) -> bool:
        """Is the residual larger than sampling noise? Normal approximation on
        the difference of two proportions. Without this, a bounded rate near
        1.0 makes a manager structurally unable to be labelled in one
        direction while remaining eligible for the other."""
        p1, n1 = self.committed_rate, self.committed_n
        p2, n2 = self.baseline_rate, self.baseline_n
        if n1 < 1 or n2 < 1:
            return False
        se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        if se == 0:
            se = math.sqrt(0.25 / n1 + 0.25 / n2)   # degenerate rate: conservative
        return abs(self.residual) / se >= 1.96

    @property
    def direction(self) -> str:
        if not self.significant:
            return "no difference"
        if self.residual <= -FLAT:
            return "better"        # votes for the theme more than mix predicts
        if self.residual >= FLAT:
            return "worse"
        return "no difference"


def theme_industry_rates(matrix: dict) -> dict[str, float]:
    """Industry-wide against-rate per theme, over every manager. The benchmark
    the placebo is built from."""
    agg: dict[str, list[int]] = {}
    for inst in matrix["institutions"]:
        for th, c in inst["cells"].items():
            n = c["for"] + c["against"]
            if not n:
                continue
            a = agg.setdefault(th, [0, 0])
            a[0] += c["for"]
            a[1] += c["against"]
    return {th: (a[1] / (a[0] + a[1])) for th, a in agg.items() if a[0] + a[1]}


def _expected_rate(inst: dict, committed: bool, industry: dict[str, float]) -> float | None:
    """What this manager's basket would score if it voted exactly at each
    theme's industry rate — i.e. the rate its THEME MIX alone predicts."""
    num = den = 0.0
    for th, c in inst["cells"].items():
        n = c["for"] + c["against"]
        if not n or bool(c["committed"]) is not committed or th not in industry:
            continue
        num += n * industry[th]
        den += n
    return (num / den) if den else None


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
    industry = theme_industry_rates(matrix)
    out: list[ManagerPair] = []
    for inst in matrix["institutions"]:
        cf, ca, bf, ba = _split(inst)
        if cf + ca < min_votes or bf + ba < min_votes:
            continue
        exp_c = _expected_rate(inst, True, industry)
        exp_b = _expected_rate(inst, False, industry)
        out.append(ManagerPair(
            institution_id=inst["id"], institution_name=inst["name"],
            committed_rate=round(ca / (cf + ca), 4), committed_n=cf + ca,
            baseline_rate=round(ba / (bf + ba), 4), baseline_n=bf + ba,
            expected_delta=(round(exp_c - exp_b, 4)
                            if exp_c is not None and exp_b is not None else 0.0)))
    out.sort(key=lambda p: p.residual, reverse=True)
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
    residuals = [p.residual for p in pairs]
    median_res = round(statistics.median(residuals), 4) if residuals else None

    if median_res is None:
        verdict = ("Not enough paired evidence yet to say whether a published "
                   "commitment is associated with how a manager votes.")
    elif abs(median_res) < FLAT:
        verdict = (
            "Across the managers that can be compared against themselves, a "
            "published commitment shows no measurable association with how the "
            "manager votes: the same firms vote against theme proposals at "
            "close to the same rate whether or not they publicly committed to "
            "that theme.")
    elif median_res >= FLAT:
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
            "behaviour. It is shown for transparency only; the paired, "
            "theme-mix-controlled result above is the one to rely on. Note also "
            "that it covers every manager, while the paired table covers only "
            "those with enough votes on both sides."),
        "paired_median_delta": median,
        "paired_median_residual": median_res,
        "n_managers": len(pairs),
        "n_better": sum(1 for p in pairs if p.direction == "better"),
        "n_worse": sum(1 for p in pairs if p.direction == "worse"),
        "n_flat": sum(1 for p in pairs if p.direction == "no difference"),
        "pairs": pairs,
        "verdict": verdict,
        "method": (
            "Each manager is compared against ITSELF: its against-rate on themes "
            "its own archived policy commits to, versus its against-rate on "
            "themes it never committed to. That pairing cancels house voting "
            "philosophy — one confound. It does not cancel THEME MIX: the two "
            "baskets contain different themes, and themes have very different "
            "industry-wide rates, so most of the raw difference is composition. "
            "Each manager's difference is therefore compared against what its "
            "own theme mix alone predicts, and only the RESIDUAL — the part mix "
            "does not explain, and only when it exceeds sampling noise — can "
            f"carry a direction. Managers need at least {min_votes} votes on "
            "both sides to appear."),
    }


def summary_markdown(s: dict) -> str:
    """Registrar voice: the method, both directions, and the numbers."""
    pct = lambda x: "—" if x is None else f"{x:.1%}"   # noqa: E731
    lines = [
        "# Does a stewardship promise predict anything?", "",
        f"**{s['verdict']}**", "",
        "## How this is measured", "", s["method"], "",
        "## The paired result", "",
        f"Managers compared: **{s['n_managers']}** · better than their theme mix "
        f"predicts: **{s['n_better']}** · worse: **{s['n_worse']}** · no measurable "
        f"difference: **{s['n_flat']}** · median residual: "
        f"**{pct(s['paired_median_residual'])}**", "",
        "| Manager | On themes it commits to | On its own other themes | Raw diff. | "
        "Predicted by theme mix | Residual | |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in s["pairs"]:
        mark = {"better": "votes for it more than mix predicts",
                "worse": "votes against it more than mix predicts",
                "no difference": "no measurable difference"}[p.direction]
        lines.append(
            f"| {p.institution_name} | {pct(p.committed_rate)} against "
            f"({p.committed_n:,} votes) | {pct(p.baseline_rate)} against "
            f"({p.baseline_n:,} votes) | {p.delta:+.1%} | {p.expected_delta:+.1%} | "
            f"{p.residual:+.1%} | {mark} |")
    lines += [
        "", "A negative **residual** means the manager votes *for* the theme more "
        "often than its own theme mix predicts. The raw difference is shown for "
        "transparency, but it is mostly composition: only the residual, and only "
        "when it exceeds sampling noise, carries a label.", "",
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
