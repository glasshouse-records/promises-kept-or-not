"""MCP server over the evidence ledger — any AI assistant can query it.

Serves the PUBLISHED snapshot, never the operator's working ledger: the
public surface can only ever show what a human explicitly exported via
`glasshouse export` (publishable rows only — no triage/llm_log/outreach/
signals/match_log, only approved findings). If no snapshot exists yet, the
server refuses to start rather than fall back to the working DB. Read-only
by construction (mode=ro) with a defense-in-depth guard on raw SQL.

    pip install "glasshouse[mcp]"
    glasshouse export            # build the public snapshot first
    python -m glasshouse.mcp_server

Claude Desktop / Claude Code config:
    {"mcpServers": {"glasshouse": {"command": "/path/.venv/bin/python",
                                   "args": ["-m", "glasshouse.mcp_server"]}}}
"""

from __future__ import annotations

import json
import sqlite3

from .http import DATA_DIR
from .publish import OPERATOR_ONLY, newest_snapshot

DISCLAIMER = ("Resolution types are legally distinct (DPA/NPA are not convictions; "
              "dockets are allegations). Quarantined rows are unverified leads, not "
              "findings. Every record carries source_url and retrieval_date — cite them.")


def _snapshot_path():
    snap = newest_snapshot(DATA_DIR / "exports")
    if snap is None:
        raise SystemExit(
            "No published snapshot found. Run `glasshouse export` first — the MCP "
            "server only ever serves published data, never the working ledger.")
    return snap


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{_snapshot_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(cur, cap: int = 200) -> str:
    out = [dict(r) for r in cur.fetchmany(cap)]
    return json.dumps({"disclaimer": DISCLAIMER, "rows": out}, default=str)


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("glasshouse")

    @mcp.tool()
    def query(sql: str) -> str:
        """Run a read-only SQL query against the published Glasshouse snapshot
        (tables: votes, enforcement_actions, commitments, holdings, filings,
        institutions, entities, fund_series, entity_cusips, and approved
        findings). Results capped at 200 rows."""
        low = sql.lower()
        if not low.lstrip().startswith(("select", "with")):
            return json.dumps({"error": "read-only: SELECT/WITH queries only"})
        # Defense in depth: operator tables aren't in the snapshot, but reject
        # references explicitly so the boundary is legible, not incidental.
        import re
        for t in OPERATOR_ONLY:
            if re.search(rf"\b{t}\b", low):
                return json.dumps({"error": f"'{t}' is operator-internal and not "
                                   "part of the public snapshot"})
        with _conn() as conn:
            return _rows(conn.execute(sql))

    @mcp.tool()
    def institutions() -> str:
        """List tracked institutions with vote and policy-version counts."""
        with _conn() as conn:
            return _rows(conn.execute(
                """SELECT i.id, i.display_name, i.cik,
                          (SELECT COUNT(*) FROM votes v JOIN filings f
                           ON f.accession=v.accession WHERE f.institution_id=i.id) AS votes,
                          (SELECT COUNT(*) FROM commitments c
                           WHERE c.institution_id=i.id) AS policy_versions
                   FROM institutions i"""))

    @mcp.tool()
    def contradiction_candidates(theme: str = "") -> str:
        """Quarantined SAY-vs-DO candidates: institution policy language vs its
        AGAINST votes on same-theme proposals. Human review required before use."""
        from .contradictions import find_commitment_vote_contradictions
        with _conn() as conn:
            cands = find_commitment_vote_contradictions(conn, limit_per_theme=10)
        rows = [c.__dict__ for c in cands if not theme or c.theme == theme]
        return json.dumps({"disclaimer": DISCLAIMER, "rows": rows}, default=str)

    mcp.run()


if __name__ == "__main__":
    main()
