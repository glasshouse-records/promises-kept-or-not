"""MCP server over the evidence ledger — any AI assistant can query it.

Read-only by construction: the SQLite connection is opened in query-only
mode, and free-form SQL is capped. Run with:

    pip install "glasshouse[mcp]"
    python -m glasshouse.mcp_server

Claude Desktop / Claude Code config:
    {"mcpServers": {"glasshouse": {"command": "/path/.venv/bin/python",
                                   "args": ["-m", "glasshouse.mcp_server"]}}}
"""

from __future__ import annotations

import json
import sqlite3

from .ledger import DB_PATH

DISCLAIMER = ("Resolution types are legally distinct (DPA/NPA are not convictions; "
              "dockets are allegations). Quarantined rows are unverified leads, not "
              "findings. Every record carries source_url and retrieval_date — cite them.")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
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
        """Run a read-only SQL query against the Glasshouse evidence ledger
        (tables: votes, enforcement_actions, commitments, holdings, filings,
        institutions, entities, match_log). Results capped at 200 rows."""
        if not sql.lstrip().lower().startswith(("select", "with")):
            return json.dumps({"error": "read-only: SELECT/WITH queries only"})
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
