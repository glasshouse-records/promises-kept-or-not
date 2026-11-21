"""The self-improvement loop — high-level decisions about the tool as a whole.

Reads the balanced index (metrics.py), coverage, the doctor report, and the
queues, then ranks the highest-leverage next moves toward "best dataset
possible." Two tiers, by the operator's standing decision:

  - SAFE, idempotent, tool-only hygiene fixes (dedupe, purge error pages,
    reconcile the review queue) self-apply every cycle — the auto-merge tier.
  - Everything else (coverage runs, code changes, source repairs) is PROPOSED
    with an executor tag (coverage-run / source-medic / code-session / human);
    those flow agent→PR→merge-on-green or wait for a person.

Hard guardrail: the loop NEVER approves a finding, sends outreach, publishes,
or alters data beyond the safe hygiene ops. Tool may self-improve; data and
publication stay human-gated.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from . import metrics
from .http import DATA_DIR
from .ledger import NON_LEGACY_VOTE_SQL

IMPROVE_DIR = DATA_DIR / "improve"

# The auto-apply allowlist: idempotent, tool-level, individually tested. Each
# returns a short result string. NOTHING here decides a finding, sends, or
# fabricates/deletes real data (dedupe marks; purge removes provable error
# pages; review.sync preserves human-decided rows).
def _safe_actions():
    from . import ledger, review
    from .ingest import commitments

    def dedupe(conn):
        v = ledger.dedupe_votes(conn)
        e = ledger.dedupe_enforcement(conn)
        return f"deduped {v:,} vote rows, {e} superseded enforcement rows"

    def purge(conn):
        n = commitments.purge_error_pages(conn)
        return f"purged {n} error-page commitment rows"

    def reconcile(conn):
        r = review.sync(conn)
        return f"review queue: +{r['added']} new, -{r['pruned']} stale, {r['pending']} live"

    return {"dedupe": dedupe, "purge-error-pages": purge, "reconcile-review": reconcile}


def apply_safe(conn: sqlite3.Connection) -> dict:
    """Run the safe hygiene allowlist; snapshot metrics before/after so the
    loop records whether it helped."""
    before = metrics.snapshot(conn)["balanced_index"]
    log = {}
    for name, fn in _safe_actions().items():
        try:
            log[name] = fn(conn)
        except Exception as exc:  # a hygiene op must never break the loop
            log[name] = f"skipped ({exc})"
    after = metrics.snapshot(conn)["balanced_index"]
    return {"ran": log, "index_before": before, "index_after": after,
            "delta": round(after - before, 1)}


def assess(conn: sqlite3.Connection) -> dict:
    """Rank the highest-leverage improvements toward the balanced index."""
    m = metrics.compute(conn)
    comps, raw = m["components"], m["raw"]
    agenda: list[dict] = []

    def item(priority, area, metric, current, target, finding, action, executor, auto_safe):
        agenda.append({"priority": priority, "area": area, "metric": metric,
                       "current": current, "target": target, "finding": finding,
                       "action": action, "executor": executor, "auto_safe": auto_safe})

    # Coverage / completeness — usually the binding constraint right now.
    if comps["coverage"] < 0.9:
        big = _biggest_uncovered(conn)
        finding = (f"Full say+do covers ${raw.get('covered_aum_tr', 0)}T of "
                   f"${raw.get('total_aum_tr', 0)}T tracked AUM. Biggest UNCOVERED: "
                   + (", ".join(f"{n} (${a}T)" for n, a in big) if big else "—") + ".")
        item(1, "coverage", "coverage_aum", comps["coverage"], "0.9",
             finding,
             "Prioritize the biggest uncovered managers: discover their N-PX "
             "trusts (`discover-npx`), ingest votes, and add their policy URLs.",
             "coverage-run", False)
    if comps["completeness"] < 0.6:
        item(2, "completeness", "completeness", comps["completeness"],
             "0.6+",
             f"{raw['with_votes']} institutions have votes but only {raw['full_say_do']} "
             "also have archived policies.",
             "Add commitment-document URLs for vote-covered institutions to "
             "config/institutions.yaml, then `ingest commitments --wayback`.",
             "coverage-run", False)

    # Freshness — if stale, route a refresh (network op, not auto).
    if comps["freshness"] < 0.7:
        item(2, "freshness", "freshness", comps["freshness"], "0.7+",
             f"Live sources last refreshed {raw.get('last_refresh') or 'never'}.",
             "Run `scan-events` / `ingest enforcement` to refresh live sources.",
             "coverage-run", False)

    # Operational health from the doctor report → source-medic agent.
    rp = DATA_DIR / "doctor" / "report.json"
    if rp.exists():
        rpt = json.loads(rp.read_text())
        errs = [c for c in rpt.get("checks", []) if not c["ok"] and c["severity"] == "error"]
        if errs:
            item(1, "sources", "doctor_errors", len(errs), 0,
                 f"{len(errs)} source/integrity errors from the last `doctor` run.",
                 "Dispatch the source-medic agent to repair and open a PR.",
                 "source-medic", False)

    # Hygiene that the safe tier keeps satisfied automatically.
    pending = conn.execute("SELECT COUNT(*) FROM findings WHERE status='pending'").fetchone()[0]
    item(3, "hygiene", "review_reconciled", "auto", "auto",
         f"{pending} candidates pending human review (the gate stays yours).",
         "Safe hygiene (dedupe, purge error pages, reconcile queue) auto-applies "
         "each cycle; review itself is human.", "human", True)

    agenda.sort(key=lambda a: (a["priority"], not a["auto_safe"]))
    return {"balanced_index": m["balanced_index"], "components": comps, "agenda": agenda}


def _biggest_uncovered(conn: sqlite3.Connection, top: int = 3) -> list[tuple[str, float]]:
    """Registered institutions WITHOUT full say+do, ranked by AUM — the
    highest-leverage coverage targets the AUM-weighted index points at."""
    from . import registry
    reg = registry.load()
    full = {r[0] for r in conn.execute(
        "SELECT i.id FROM institutions i WHERE "
        "EXISTS(SELECT 1 FROM filings f JOIN votes v ON v.accession=f.accession "
        f"  WHERE f.institution_id=i.id AND v.is_duplicate=0 AND {NON_LEGACY_VOTE_SQL}) AND "
        "EXISTS(SELECT 1 FROM commitments c WHERE c.institution_id=i.id AND c.superseded=0)").fetchall()}
    uncovered = [(v.get("short_name") or v.get("display_name") or k,
                  float(v.get("aum_usd_tr") or 0))
                 for k, v in reg.items() if k not in full]
    uncovered.sort(key=lambda t: -t[1])
    return [(n, a) for n, a in uncovered if a > 0][:top]


def write_brief(conn: sqlite3.Connection) -> str:
    """Emit a human/agent-readable improvement brief; returns its path."""
    a = assess(conn)
    d = metrics.delta(conn)
    IMPROVE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Glasshouse self-improvement agenda",
        f"\nBalanced index: **{a['balanced_index']}/100**"
        + (f" ({d:+} since last run)" if d is not None else "") + "  ",
        "Components: " + ", ".join(f"{k} {v}" for k, v in a["components"].items()),
        "\n| # | area | finding | action | who | auto |",
        "|--|--|--|--|--|--|",
    ]
    for x in a["agenda"]:
        lines.append(f"| {x['priority']} | {x['area']} | {x['finding']} | {x['action']} "
                     f"| {x['executor']} | {'✓' if x['auto_safe'] else '—'} |")
    lines.append("\n_Tool fixes may self-apply or flow agent→PR; data decisions and "
                 "publication stay human-gated._")
    path = IMPROVE_DIR / "agenda.md"
    path.write_text("\n".join(lines) + "\n")
    (IMPROVE_DIR / "agenda.json").write_text(json.dumps({**a, "ts":
        datetime.now(UTC).isoformat(timespec="seconds")}, indent=2))
    return str(path)
