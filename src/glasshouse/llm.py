"""The LLM tier: single-shot, logged, ADVISORY-ONLY calls.

Architecture rule this module enforces: model output never becomes ledger
fact. It lands in the `triage` table as a recommendation with a rationale,
the full raw output is logged in `llm_log` (model id + prompt hash), and
the human gate stays exactly where it was. Determinism in the spine,
model calls at decision points, agents only in the maintenance bay.

Requires `pip install "glasshouse[llm]"` and ANTHROPIC_API_KEY. Without
either, callers get a clear NotConfigured error — nothing degrades
silently.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import UTC, datetime

DEFAULT_MODEL = "claude-fable-5"


class NotConfigured(RuntimeError):
    pass


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise NotConfigured(
            "ANTHROPIC_API_KEY not set. The LLM tier is optional and advisory; "
            "install with `pip install 'glasshouse[llm]'` and export the key.")
    try:
        import anthropic
    except ImportError as exc:
        raise NotConfigured(
            "anthropic SDK not installed — pip install 'glasshouse[llm]'") from exc
    return anthropic.Anthropic()


def call(conn: sqlite3.Connection, *, purpose: str, input_key: str,
         system: str, user: str, model: str = DEFAULT_MODEL,
         max_tokens: int = 500) -> str:
    """One logged completion. Returns the raw text output verbatim."""
    client = _client()
    prompt_sha = hashlib.sha256((system + "\x00" + user).encode()).hexdigest()[:16]
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    conn.execute(
        "INSERT INTO llm_log (ts, model, purpose, prompt_sha, input_key, output) "
        "VALUES (?,?,?,?,?,?)",
        (datetime.now(UTC).isoformat(timespec="seconds"),
         model, purpose, prompt_sha, input_key, text))
    conn.commit()
    return text
