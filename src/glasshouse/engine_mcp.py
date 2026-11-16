"""MCP server for the evidence engine — the operator's local investigator.

Unlike `mcp_server.py` (which serves only the PUBLISHED snapshot to the world),
this exposes the working engine index to an agent running on the operator's own
machine. It is read-only by construction: the engine opens both databases with
mode=ro, and the one writing tool, `file_draft`, writes only under data/desk/.

    python -m glasshouse.engine_mcp

Nothing here publishes or sends. A filed draft is an unverified lead until
`verify_draft` passes AND a person reviews it.
"""

from __future__ import annotations

import json
import re

from . import desk, engine


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("glasshouse-engine")
    eng = engine.Engine()
    for name in engine.TOOLS:
        mcp.tool(name=name)(getattr(eng, name))

    @mcp.tool()
    def file_draft(draft_json: str) -> str:
        """File a draft (the JSON format in desk.py) and get its verification
        report back. Re-file under the same slug to fix what failed."""
        draft = json.loads(draft_json)
        slug = re.sub(r"[^a-z0-9-]+", "-", str(draft.get("slug", "")).lower()).strip("-")
        if not slug:
            return json.dumps({"error": "draft needs a slug"})
        draft["slug"] = slug
        desk.DESK_DIR.mkdir(parents=True, exist_ok=True)
        path = desk.DESK_DIR / f"{slug}.json"
        path.write_text(json.dumps(draft, indent=1, ensure_ascii=False))
        return json.dumps(desk.verify_file(path), ensure_ascii=False)

    mcp.run()


if __name__ == "__main__":
    main()
