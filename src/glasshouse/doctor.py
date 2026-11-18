"""`glasshouse doctor` — the system's self-diagnosis, machine-readable.

This is the sensory input of the maintenance loop: deterministic checks
over sources, freshness, and queues, emitted as JSON + a self-contained
task brief an agent (or a human) can act on cold. The doctor only ever
OBSERVES — repairs happen in an agent session whose output is a PR.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

from . import ledger
from .http import DATA_DIR

DOCTOR_DIR = DATA_DIR / "doctor"

# Sources the pipeline expects to be able to refresh, with staleness budgets.
_FRESHNESS_DAYS = {
    "OFAC (SDN)": 14,
    "DOJ (FCPA)": 45,
    "Federal Reserve": 45,
}
# doctor agency name -> `glasshouse ingest enforcement --source` name, so the
# ingest_runs record can be found for it.
_AGENCY_SOURCE = {"OFAC (SDN)": "ofac", "DOJ (FCPA)": "doj_fcpa",
                  "Federal Reserve": "fed"}
# A tracked policy page must be confirmed live at least this often. Capture is
# a daily chore, so a FAILED attempt is reported the same day regardless; this
# budget only catches the chore itself having stopped. 14 days matches the
# tightest source budget above and outlasts a fortnight with the maintainer's
# machine off, without letting a silent gap in the one record that cannot be
# back-filled grow past two weeks.
CAPTURE_BUDGET_DAYS = 14
_KNOWN_BLOCKED = {
    # Documented in METHODOLOGY source-access notes; listed so the report
    # distinguishes "known blocked, awaiting new access path" from new rot.
    "World Bank (debarment)": "API behind Cloudflare challenge (2026-06-11)",
    "UN Global Compact": "participants.json now serves HTML (2026-06-11)",
}


def _today() -> date:
    return date.today()


def _ended_map(institutions: dict | None) -> dict[tuple, dict]:
    """(institution, cik without leading zeros) -> the registrant's `npx_ended` record."""
    if institutions is None:
        from .registry import load
        institutions = load()
    return {(iid, str(r["cik"]).lstrip("0")): r["npx_ended"]
            for iid, inst in institutions.items()
            for r in inst.get("npx_ciks") or [] if r.get("npx_ended")}


def apply_access(doc: dict, ok: bool, detail: str, severity: str) -> tuple[bool, str]:
    """A failed live capture of a label configured `access: {status: blocked}` is
    a documented block (honest client refused; never evaded), reported as info."""
    acc = doc.get("access") or {}
    if not ok and acc.get("status") == "blocked":
        return True, (f"blocked, documented ({acc.get('reason', '')}; checked "
                      f"{acc.get('checked', '')}): {detail}")
    return ok, detail


def missing_vote_seasons(conn: sqlite3.Connection, today: date | None = None,
                         institutions: dict | None = None) -> list[dict]:
    """Fund registrants whose newest N-PX season on file is older than the one
    already due. N-PX covers the 12 months to 30 June and must be filed by
    31 August; from mid-September its absence is a hole in the record, not a
    filer running late. Offline by design: it needs no network to raise the alarm."""
    today = today or _today()
    expected = today.year if (today.month, today.day) >= (9, 15) else today.year - 1
    latest: dict[tuple, int] = {}
    for r in conn.execute(
            "SELECT institution_id, cik, period_of_report FROM filings "
            "WHERE form_type LIKE 'N-PX%' AND report_type NOT LIKE 'LEGACY%' "
            "AND institution_id IS NOT NULL"):
        p = (r[2] or "").strip()
        year = p[:4] if p[:4].isdigit() else p[-4:]
        if year.isdigit():
            key = (r[0], r[1])
            latest[key] = max(latest.get(key, 0), int(year))
    ended = _ended_map(institutions)
    out = []
    for (i, c), y in sorted(latest.items()):
        if y >= expected:
            continue
        g = {"institution": i, "cik": c, "latest_on_file": y, "expected": expected}
        e = ended.get((i, str(c).lstrip("0")))
        # Only seasons AFTER the last period are excused; earlier ones are still holes.
        if e and y >= int(str(e["last_period"])[:4]):
            g["ended"] = e
        out.append(g)
    return out


def capture_health(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                   today: date | None = None,
                   budget_days: int = CAPTURE_BUDGET_DAYS) -> tuple[bool, str, str]:
    """(ok, detail, severity) for one tracked policy document. Read-only.

    Counting snapshots is not enough: an unchanged policy adds no snapshot, so
    "1 live snapshot on record" was true of a page captured this morning and of
    one whose URL rotted months ago. Two things are an error: the most recent
    attempt failed, or nothing has confirmed the page within the budget (the
    newest of the last successful attempt and the newest live snapshot)."""
    today = today or _today()
    n, newest_row = conn.execute(
        "SELECT COUNT(*), MAX(retrieval_date) FROM commitments WHERE institution_id=? "
        "AND doc_label=? AND wayback_timestamp='' AND superseded=0",
        (institution_id, doc_label)).fetchone()
    last = conn.execute(
        "SELECT attempted_at, outcome, detail, url FROM capture_attempts "
        "WHERE institution_id=? AND doc_label=? ORDER BY id DESC LIMIT 1",
        (institution_id, doc_label)).fetchone()
    last_ok = conn.execute(
        "SELECT MAX(attempted_at) FROM capture_attempts WHERE institution_id=? "
        "AND doc_label=? AND outcome != 'failed'", (institution_id, doc_label)).fetchone()[0]
    confirmed = max((last_ok or "")[:10], newest_row or "")
    if last and last[1] == "failed":
        return (False, f"capture FAILED on {last[0][:10]} ({last[2] or 'no detail'}) for "
                f"{last[3]}; last confirmed live {confirmed or 'never'}. Every uncaptured "
                f"day is a permanent gap: find the document's current official URL and "
                f"update config/institutions.yaml (keep the label).", "error")
    if n == 0:
        return (False, "no live version ever fetched (wayback-only — live URL likely "
                "rotted)", "warn")
    age = (today - date.fromisoformat(confirmed)).days
    if age > budget_days:
        return (False, f"last confirmed live {confirmed} ({age}d ago; budget "
                f"{budget_days}d) — captures have stopped. Run `glasshouse ingest "
                f"commitments`.", "error")
    return (True, f"{n} live snapshot(s) on record; last confirmed live {confirmed} "
            f"({age}d ago; budget {budget_days}d)", "warn")


def sai_needs_review(conn: sqlite3.Connection) -> list[tuple]:
    """(institution, label, detail) for SAI filings whose LATEST read was refused
    as a length outlier: a genuine rewrite would otherwise be skipped unseen."""
    out = []
    for r in conn.execute(
            "SELECT institution_id, doc_label, url, detail, outcome FROM capture_attempts "
            "WHERE id IN (SELECT MAX(id) FROM capture_attempts GROUP BY institution_id, doc_label, url)"
            " AND outcome='needs_review'"):
        out.append((r["institution_id"], r["doc_label"], f"{r['url']}: {r['detail']}"))
    return out


def diagnose(conn: sqlite3.Connection) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, severity: str = "warn") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail,
                       "severity": "info" if ok else severity})

    today = _today()

    # A restored ledger holds the bundle's rows with their ORIGINAL retrieval
    # dates; none of them is evidence that this machine fetched anything.
    restored = conn.execute(
        "SELECT source FROM ingest_runs WHERE source LIKE 'restore:%' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    if restored:
        _, version, mhash = (restored[0].split(":") + ["", ""])[:3]
        check("ledger:restored", True,
              f"this ledger is a restore of bundle {version} (manifest {mhash}) and "
              f"NOT a live ingest; its rows keep the retrieval dates they had when the "
              f"bundle was made. Source freshness is reported as 'restored, not live' "
              f"until a live ingest runs.")

    stale_dupes = ledger.duplicate_flags_stale(conn)
    check("votes:duplicate-flags", not stale_dupes,
          stale_dupes or "duplicate flags cover every vote", "error")

    # 0. The votes themselves: every rate is computed from them.
    for g in missing_vote_seasons(conn, today):
        if g.get("ended"):
            e = g["ended"]
            check(f"votes:{g['institution']}/{g['cik']}", True,
                  f"no N-PX expected after {e['last_period']}: {e.get('reason', '')} "
                  f"(source {e.get('source', '')}; checked {e.get('checked', '')})")
            continue
        check(f"votes:{g['institution']}/{g['cik']}", False,
              f"N-PX season {g['expected']} was due 31 Aug and is not on file (latest: "
              f"{g['latest_on_file']}). Run `glasshouse ingest npx --institution "
              f"{g['institution']}`, then `dedupe` and `engine build`.", "error")

    # 1. Live-source freshness: newest retrieval per agency.
    for agency, budget in _FRESHNESS_DAYS.items():
        # Prefer the last SUCCESSFUL run (a run that found nothing new is still
        # a successful look); fall back to the newest row when none are recorded.
        row = conn.execute(
            "SELECT MAX(substr(run_at,1,10)) FROM ingest_runs "
            "WHERE source = ? AND ok = 1", (_AGENCY_SOURCE.get(agency, agency),)).fetchone()
        last = row[0]
        if not last and restored:
            check(f"source:{agency}", True,
                  "restored, not live: no live ingest has run on this ledger")
            continue
        if not last:
            row = conn.execute(
                "SELECT MAX(retrieval_date) FROM enforcement_actions "
                "WHERE agency = ? AND source_kind='live'", (agency,)).fetchone()
            last = row[0]
        if not last:
            check(f"source:{agency}", False, "no live rows ever ingested", "error")
            continue
        age = (today - date.fromisoformat(last)).days
        check(f"source:{agency}", age <= budget,
              f"last successful ingest {last} ({age}d ago; budget {budget}d)",
              "error" if age > 2 * budget else "warn")

    # 2. Known-blocked sources (so the agent doesn't rediscover them).
    for agency, why in _KNOWN_BLOCKED.items():
        check(f"blocked:{agency}", False, f"KNOWN BLOCKED — {why}; needs a new "
              f"sanctioned access path (bulk file or official API; no browser "
              f"impersonation)", "warn")

    # 3. Commitments: is every tracked policy page actually being captured?
    from .registry import load
    blocked_labels: list[str] = []
    for inst_id, inst in load().items():
        for doc in inst.get("commitments", []):
            if restored and not conn.execute(
                    "SELECT 1 FROM capture_attempts WHERE institution_id=? AND doc_label=? "
                    "LIMIT 1", (inst_id, doc["label"])).fetchone():
                check(f"commitment-live:{inst_id}/{doc['label']}", True,
                      "restored, not live: no capture has run on this ledger")
                continue
            ok, detail, severity = capture_health(conn, inst_id, doc["label"], today)
            was_ok = ok
            ok, detail = apply_access(doc, ok, detail, severity)
            if ok and not was_ok:
                blocked_labels.append(f"{inst_id}/{doc['label']}")
            check(f"commitment-live:{inst_id}/{doc['label']}", ok, detail, severity)

    if blocked_labels:
        check("commitment-access:blocked", True,
              f"{len(blocked_labels)} label(s) failing live capture are documented "
              f"blocked: {', '.join(blocked_labels)}")

    for inst_id, label, detail in sai_needs_review(conn):
        check(f"sai-outlier:{inst_id}/{label}", False,
              f"SAI section refused as a length outlier, needs a human look: {detail}", "warn")

    # 4. Ledger integrity (hard failures only; quarantine is healthy).
    from .ledger import integrity_check
    problems = integrity_check(conn)
    for k, rows in problems.items():
        if k != "quarantined":
            check(f"integrity:{k}", not rows, f"{len(rows)} offending rows",
                  "error")

    # 5. Queues a human should know about.
    pending = conn.execute(
        "SELECT COUNT(*) FROM findings WHERE status='pending'").fetchone()[0]
    check("queue:review", pending < 50,
          f"{pending} candidates pending human review")
    silent = conn.execute(
        "SELECT COUNT(*) FROM outreach WHERE status='sent' AND response_date=''").fetchone()[0]
    check("queue:non-response", True, f"{silent} sent items awaiting response")

    failures = [c for c in checks if not c["ok"] and c["severity"] == "error"]
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "healthy": not failures,
        "n_errors": len(failures),
        "n_warnings": sum(1 for c in checks if not c["ok"] and c["severity"] == "warn"),
        "checks": checks,
    }


def emit(conn: sqlite3.Connection) -> tuple[str, str | None]:
    """Write report.json always; write a self-contained agent task brief when
    something needs repair. Returns (report_path, task_path | None)."""
    report = diagnose(conn)
    DOCTOR_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCTOR_DIR / "report.json"
    report_path.write_text(json.dumps(report, indent=1))

    broken = [c for c in report["checks"] if not c["ok"] and c["severity"] in ("error", "warn")]
    if not broken:
        return str(report_path), None

    lines = [
        "# Glasshouse repair task (auto-generated by `glasshouse doctor`)",
        "",
        f"Generated {report['ts']}. You are working in the glasshouse repo.",
        "Diagnose and fix what you can of the following. Ground rules:",
        "",
        "- Fix the INGESTER, never hand-edit ledger data.",
        "- Free public sources only; never impersonate a browser to evade CDN rules.",
        "- Every fix needs a passing test (`pytest`) and, where the source is",
        "  reachable, a live smoke check.",
        "- Output is a branch + commit (or PR), never a push to main.",
        "- If a source is genuinely gone, document it in METHODOLOGY.md",
        "  source-access notes instead of forcing it.",
        "",
        "## Failing checks",
        "",
    ]
    for c in broken:
        lines.append(f"- [{c['severity'].upper()}] {c['name']}: {c['detail']}")
    lines += [
        "",
        "## Where things live",
        "- ingesters: src/glasshouse/ingest/*.py (one module per source)",
        "- ledger invariants: src/glasshouse/ledger.py (integrity_check)",
        "- methodology/source notes: METHODOLOGY.md",
        "- run a single source: `.venv/bin/glasshouse ingest enforcement --source <name>`",
    ]
    task_path = DOCTOR_DIR / "task.md"
    task_path.write_text("\n".join(lines) + "\n")
    return str(report_path), str(task_path)
