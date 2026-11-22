"""Unpromoted legacy votes (vote_source 'legacy_html', or a legacy_format outside
ledger.PROMOTED_LEGACY_FORMATS) must be invisible to every
analysis, site, metric, newsroom, MCP and triage read of the votes table.

(a) behavioural: a seeded ledger with one XML vote and one unpromoted-format vote;
(b) static: every SQL string in src/ reading FROM/JOIN votes carries the predicate
    unless it is on the explicit allowlist below."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from glasshouse import findings, ledger, metrics, newsroom, site

SRC = Path(__file__).resolve().parent.parent / "src" / "glasshouse"


def _seed(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('A','1','x','N-PX','u','2026-01-01')")
    for how, fmt in (("FOR", None), ("AGAINST", "future_fmt")):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
                  "how_voted, shares_voted, vote_source, legacy_format, is_duplicate) "
                  "VALUES ('A','Acme','C1','06/30/2025','Climate report',?,100,?,?,0)",
                  (how, "xml" if fmt is None else "legacy_text", fmt))
    c.commit()
    return c


def test_helper_alias_and_constant_agree():
    assert ledger.non_legacy_vote_sql() == ledger.NON_LEGACY_VOTE_SQL
    assert ledger.non_legacy_vote_sql("v") == (
        "IFNULL(v.vote_source,'') != 'legacy_html' AND "
        "(v.legacy_format IS NULL OR v.legacy_format IN ('proxyedge','iss_text','iss_html'))")


def test_promoted_formats_constant():
    assert ledger.PROMOTED_LEGACY_FORMATS == ("proxyedge", "iss_text", "iss_html")


def _count(c):
    return c.execute(f"SELECT COUNT(*) FROM votes WHERE {ledger.NON_LEGACY_VOTE_SQL}").fetchone()[0]


def test_unpromoted_stay_out_promoted_get_in(tmp_path):
    c = _seed(tmp_path)  # one XML + one unpromoted 'future_fmt'
    assert _count(c) == 1
    c.execute("INSERT INTO votes (accession, issuer_name, how_voted, legacy_format, is_duplicate)"
              " VALUES ('A','Z','FOR','proxyedge',0)")
    assert _count(c) == 2
    for fmt, src in (("future_fmt", "legacy_text"), (None, "legacy_html"), ("iss_text", "legacy_html")):
        c.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, legacy_format,"
                  " is_duplicate) VALUES ('A','Z','FOR',?,?,0)", (src, fmt))
    c.commit()
    assert _count(c) == 2   # unknown format, legacy_html (any format) stay quarantined
    c.execute("INSERT INTO votes (accession, issuer_name, how_voted, legacy_format, is_duplicate)"
              " VALUES ('A','Z','FOR','iss_html',0)")
    assert _count(c) == 3


def test_vote_divergence_ignores_legacy(tmp_path):
    c = _seed(tmp_path)
    assert findings.vote_divergence(c) == []  # FOR vs legacy AGAINST is not a split


def test_site_vote_split_themes_and_splits_ignore_legacy(tmp_path):
    c = _seed(tmp_path)
    assert site._vote_split(c) == [("FOR", 1)]
    assert site._vote_split(c, "x") == [("FOR", 1)]
    stances = {d["label"]: d for d in site._theme_stances(c, "x")}
    assert all(d["against"] == 0 for d in stances.values())
    assert site._splits(c, "x") == []


def test_newsroom_pipeline_counts_ignore_legacy(tmp_path):
    c = _seed(tmp_path)
    assert newsroom.pipeline_status(c)[0]["detail"].startswith("1 deduped")


def test_metrics_with_votes_ignores_legacy_only_institution(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('A','1','x','N-PX','u','2026-01-01')")
    c.execute("INSERT INTO votes (accession, issuer_name, how_voted, legacy_format, is_duplicate) "
              "VALUES ('A','Acme','FOR','future_fmt',0)")
    c.commit()
    assert metrics.compute(c)["raw"]["with_votes"] == 0


# ---- static ---------------------------------------------------------------------------
# Reads that must see ALL rows, or that take their WHERE from publish.PUBLIC_TABLES
# (which already embeds the predicate). Keyed by (file, distinctive substring).
ALLOW = [
    ("ledger.py", "SELECT MIN(v.id) FROM votes v"),          # dedupe: must see every row
    ("ledger.py", "SELECT COALESCE(MAX(id), 0) FROM votes"),  # id watermark for dedupe/integrity
    ("ledger.py", "SELECT COUNT(*) FROM votes v JOIN filings f"),  # integrity checks
    ("ledger.py", "vote_series FROM votes WHERE is_duplicate = 0 AND accession IN"),  # integrity
    ("ledger.py", "SELECT v.id, v.accession FROM votes v"),   # integrity / dedupe
    ("engine.py", "SELECT MAX(id) FROM votes"),               # index watermark vs ledger growth
    ("release.py", "SELECT MAX(id) FROM votes"),              # release watermark
    ("release.py", "FROM votes v LEFT JOIN filings f"),       # {where} = PUBLIC_TABLES (has predicate)
    ("release.py", "SELECT COUNT(*) FROM votes {where}"),     # {where} = PUBLIC_TABLES
    ("dataset.py", "SELECT * FROM votes {PUBLIC_TABLES"),     # PUBLIC_TABLES (has predicate)
    ("diff.py", "SELECT COUNT(*) FROM votes WHERE id > ?"),   # raw ledger growth since last run
    ("cli.py", "SELECT COUNT(*) FROM votes"),                 # raw row count diagnostics
    ("ingest/npx.py", "DELETE FROM votes"),                   # re-ingest replaces own accession
    ("ingest/legacy_pe.py", "DELETE FROM votes"),             # re-ingest of legacy rows
]
PRED = re.compile(r"NON_LEGACY_VOTE_SQL|non_legacy_vote_sql|legacy_format|PROMOTED_LEGACY")
READ = re.compile(r"\b(FROM|JOIN)\s+votes\b", re.I)
SQLISH = re.compile(r"\b(SELECT|DELETE)\b")


def test_every_votes_read_applies_the_legacy_predicate():
    bad = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text())
        # an f-string's literal parts are separate Constant nodes; judge the whole JoinedStr
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)}
        parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for node in ast.walk(tree):
            if id(node) in parts or id(node) in docs:
                continue
            if isinstance(node, ast.JoinedStr):
                s = ast.unparse(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
            else:
                continue
            if not READ.search(s) or not SQLISH.search(s) or PRED.search(s):
                continue
            if any(rel == f and sub in s for f, sub in ALLOW):
                continue
            bad.append(f"{rel}: {' '.join(s.split())[:90]}")
    assert not bad, "votes read without the legacy predicate:\n" + "\n".join(bad)
