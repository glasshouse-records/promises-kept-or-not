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


def test_meeting_dates_sort_chronologically_not_lexicographically(tmp_path):
    """Live bug (found in strategic review, 2026-08-25): meeting_date is stored
    as US 'MM/DD/YYYY', so MAX()/ORDER BY sorts LEXICOGRAPHICALLY — '12/31/2024'
    ranks above '06/30/2025'. On the real ledger MAX() returned 12/31/2024 while
    the latest meeting was 2025-06-30. Any 'latest' or date-range query was
    silently wrong; a trustee-facing 'last three years' filter would have been
    too. Fixed by sorting on an ISO expression."""
    from glasshouse import ledger
    from glasshouse.ledger import ISO_MEETING_DATE
    c = ledger.connect(tmp_path / "d.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, "
              "source_url, retrieval_date) VALUES ('A','1','x','N-PX','u','2025-01-01')")
    for md in ("12/31/2024", "06/30/2025", "01/15/2023"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "vote_description, how_voted, is_duplicate) VALUES "
                  "('A','CO','C',?,'p','FOR',0)", (md,))
    c.commit()
    # naive MAX() picks the December date — the bug
    assert c.execute("SELECT MAX(meeting_date) FROM votes").fetchone()[0] == "12/31/2024"
    # the ISO expression picks the true latest
    latest = c.execute(f"SELECT MAX({ISO_MEETING_DATE}) FROM votes").fetchone()[0]
    assert latest == "2025-06-30"
    earliest = c.execute(f"SELECT MIN({ISO_MEETING_DATE}) FROM votes").fetchone()[0]
    assert earliest == "2023-01-15"
