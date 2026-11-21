"""Phase 5 — the event trigger. Daily scan of enforcement sources; every NEW
action against a company is joined, within the same run, to who HOLDS it and
who VOTED at it. Inside the news cycle, not adjacent to it.

Alerts are markdown evidence packs written to data/alerts/ — inputs to the
human-gated outreach queue, never sent anywhere by this module.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date

from . import ledger
from .entities import normalize_name
from .http import DATA_DIR
from .ledger import iso_meeting_date

logger = logging.getLogger(__name__)

ALERTS_DIR = DATA_DIR / "alerts"


def scan(conn: sqlite3.Connection, sources: list[str] | None = None) -> dict:
    """Fetch live enforcement sources, insert what's new, and emit one alert
    pack per newly seen company that the tracked institutions hold or voted at."""
    from .ingest import doj_fcpa, ofac, ungc, worldbank
    fetchers = {"doj_fcpa": doj_fcpa.fetch, "ofac": ofac.fetch,
                "worldbank": worldbank.fetch, "ungc": ungc.fetch}
    names = sources or list(fetchers)

    before = conn.execute("SELECT COALESCE(MAX(id),0) FROM enforcement_actions").fetchone()[0]
    for name in names:
        ledger.insert_enforcement(conn, fetchers[name]())
    new_rows = conn.execute(
        "SELECT * FROM enforcement_actions WHERE id > ? ORDER BY id", (before,)).fetchall()

    conn.create_function("gh_norm", 1, normalize_name)
    n_alerts = 0
    for action in new_rows:
        votes = conn.execute(
            """SELECT COALESCE(i.display_name, f.cik) AS institution, v.issuer_name,
                      v.meeting_date, v.how_voted, v.vote_description
               FROM votes v JOIN filings f ON f.accession = v.accession
               LEFT JOIN institutions i ON i.id = f.institution_id
               WHERE gh_norm(v.issuer_name) = gh_norm(?) AND v.how_voted != '' AND v.is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL}
               ORDER BY {iso} DESC LIMIT 5""".format(iso=iso_meeting_date("v.meeting_date"),
                                                   NON_LEGACY_VOTE_SQL=ledger.NON_LEGACY_VOTE_SQL),
            (action["company_name"],)).fetchall()
        holds = conn.execute(
            """SELECT COALESCE(i.display_name, f.cik) AS institution, h.issuer_name,
                      SUM(h.value_usd) AS value_usd
               FROM holdings h JOIN filings f ON f.accession = h.accession
               LEFT JOIN institutions i ON i.id = f.institution_id
               WHERE gh_norm(h.issuer_name) = gh_norm(?)
               GROUP BY institution""",
            (action["company_name"],)).fetchall()
        if not votes and not holds:
            continue
        n_alerts += 1
        _write_alert(action, votes, holds)
    logger.info("event scan: %d new actions, %d alerts", len(new_rows), n_alerts)
    return {"new_actions": len(new_rows), "alerts": n_alerts}


def news_scan(conn: sqlite3.Connection, timespan: str = "1d") -> int:
    """GDELT pass: news pairing tracked institutions with enforcement terms.
    Output is a trigger file for HUMAN verification against primary sources;
    nothing from this pass enters the evidence ledger."""
    from .ingest.gdelt import news_triggers
    names = [r[0] for r in conn.execute(
        "SELECT display_name FROM institutions WHERE id IN "
        "(SELECT DISTINCT institution_id FROM filings WHERE institution_id IS NOT NULL)")]
    hits = news_triggers(names, timespan=timespan)
    if not hits:
        return 0
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ALERTS_DIR / f"{date.today().isoformat()}_news_triggers.md"
    lines = ["# News triggers (GDELT)", "",
             "NOT CITABLE. Each line is a lead to verify against a primary source",
             "(DOJ/SEC/court records) before any use whatsoever.", ""]
    for h in hits:
        lines.append(f"- [{h['name']}] {h['title']} — {h['domain']} "
                     f"({h['seendate']}) {h['url']}")
    path.write_text("\n".join(lines) + "\n")
    return len(hits)


def _write_alert(action, votes, holds) -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = normalize_name(action["company_name"]).replace(" ", "-")[:50] or "unknown"
    path = ALERTS_DIR / f"{date.today().isoformat()}_{action['id']}_{slug}.md"
    lines = [
        f"# Event alert: {action['company_name']}",
        "",
        f"- **Action:** {action['agency']} | {action['resolution_type']} | "
        f"{action['primary_ref'] or 'NO REF'} | {action['action_date'] or 'date n/a'}",
        f"- **Source:** {action['source_url']} (retrieved {action['retrieval_date']})",
        f"- **Detail:** {(action['description'] or '')[:400]}",
        "",
        "ALL joins below are name-level LEADS — verify entity identity before any use.",
        "",
    ]
    if holds:
        lines.append("## Who holds it (13-F)")
        lines += [f"- {h['institution']}: ${h['value_usd']:,} ({h['issuer_name']})" for h in holds]
        lines.append("")
    if votes:
        lines.append("## Who voted at it (N-PX)")
        lines += [f"- {v['institution']} voted {v['how_voted']} ({v['meeting_date']}): "
                  f"{(v['vote_description'] or '')[:140]}" for v in votes]
    path.write_text("\n".join(lines) + "\n")
