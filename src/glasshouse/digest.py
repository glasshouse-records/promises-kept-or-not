"""Weekly digest renderer. Produces the email body as a file in the outbox;
a human pastes it into Buttondown (or any sender) when publication begins.
Nothing here sends anything, ever.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import diff
from .http import DATA_DIR

DIGEST_DIR = DATA_DIR / "outbox"


def render(conn: sqlite3.Connection) -> str:
    """Render the digest from current deltas + review state and return the
    file path. Does not record a run — `glasshouse diff --record` owns that."""
    d = diff.compute(conn)
    from .review import stats as review_stats
    rs = review_stats(conn)

    lines = [
        f"# Glasshouse digest — {date.today().isoformat()}",
        "",
        "What changed in the public record this period. Every item traces to a",
        "primary source; resolution types are legally distinct (DPA/NPA are not",
        "convictions; dockets are allegations).",
        "",
        f"## Deltas since {d.since or 'ledger creation'}",
        f"- {d.new_votes:,} new proxy-vote records",
        f"- {d.new_enforcement:,} new enforcement actions",
        f"- {d.new_commitment_versions:,} new policy versions archived",
        "",
    ]
    if d.enforcement_samples:
        lines.append("## New on the enforcement record")
        for s in d.enforcement_samples:
            lines.append(f"- {s['agency']}: {s['company_name']} "
                         f"({s['resolution_type']}, {s['primary_ref'] or 'no ref'})")
        lines.append("")
    if d.commitment_samples:
        lines.append("## Policy documents that changed")
        for s in d.commitment_samples:
            lines.append(f"- {s['institution_id']}/{s['doc_label']} "
                         f"@ {s['wayback_timestamp'] or s['retrieval_date']}")
        lines.append("")
    lines += [
        "## Review pipeline",
        f"- approved findings: {rs.get('approved', 0)}",
        f"- rejected after review: {rs.get('rejected', 0)} (every exclusion documented)",
        f"- pending human review: {rs.get('pending', 0)}",
        "",
        "_Reply to this digest with corrections — discarding almost-right",
        "findings is the discipline this project is built on._",
    ]
    body = "\n".join(lines) + "\n"
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGEST_DIR / f"digest_{date.today().isoformat()}.md"
    path.write_text(body)
    return str(path)
