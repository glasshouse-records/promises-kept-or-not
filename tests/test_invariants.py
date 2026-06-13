"""Mechanical enforcement of the two Glasshouse invariants that regex/Semgrep
can't catch without false positives (multiline SQL, cross-statement guards).

These scan the actual source: a violation fails CI even if no test exercises
the offending path — the point is to make the project's fatal-mistake classes
impossible to merge, not merely unlikely.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "glasshouse"


def _py_files() -> list[Path]:
    return list(SRC.rglob("*.py"))


def test_no_unfiltered_sum_of_shares_voted():
    """Every SUM(shares_voted) must scope to is_duplicate = 0 within the same
    SQL string literal. N-PX has ~5% as-filed duplicates; an unfiltered sum
    fabricates a false public share count (found inflating up to 6x)."""
    offenders = []
    for path in _py_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                sql = node.value
                if re.search(r"(?i)sum\s*\(\s*[a-z_.]*shares_voted", sql):
                    if "is_duplicate" not in sql:
                        offenders.append(f"{path.name}: {sql[:80]}")
    assert not offenders, (
        "SUM(shares_voted) without is_duplicate filter in same query:\n"
        + "\n".join(offenders))


def test_only_mark_sent_writes_status_sent():
    """The transition to status='sent' may happen in exactly one place —
    outreach.mark_sent — which is the function that enforces the
    human-confirmation gate. Any other writer would let something send
    itself without human approval."""
    # Only the SQL write clause counts; reads (WHERE status='sent') don't.
    write_re = re.compile(r"(?i)\bset\s+status\s*=\s*'sent'")
    writers = []
    for path in _py_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if not write_re.search(node.value):
                continue
            fn = _enclosing_func(tree, node)
            writers.append((path.name, fn))
    # The only legitimate writer is outreach.mark_sent.
    illegitimate = [(f, fn) for (f, fn) in writers
                    if not (f == "outreach.py" and fn == "mark_sent")]
    assert not illegitimate, f"status='sent' written outside mark_sent: {illegitimate}"

    # And mark_sent must actually check the human gate.
    src = (SRC / "outreach.py").read_text()
    mark_sent = src[src.index("def mark_sent"):]
    body = mark_sent[:mark_sent.index("\ndef ", 1)] if "\ndef " in mark_sent[1:] else mark_sent
    assert "human_confirmed" in body and "raise" in body


def _enclosing_func(tree: ast.Module, target: ast.AST) -> str | None:
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for sub in ast.walk(fn):
                if sub is target:
                    return fn.name
    return None
