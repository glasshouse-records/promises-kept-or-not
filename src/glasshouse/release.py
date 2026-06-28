"""Versioned, verifiable, open-format release bundle — the product the world uses.

`glasshouse export` historically produced one ~700 MB VACUUM'd SQLite blob:
not versioned, not checksummed, not partially consumable, impossible to diff or
to cite. The mission needs the opposite — an artifact an outside researcher or
journalist can download, **verify without trusting us**, query in standard
tools, and **cite** in a publication. This module builds that bundle from the
live ledger:

    release/v<DATE>/
      facts/<table>.csv[.gz]    open, deduped, PUBLIC tables only (one per table)
      facts/<table>.parquet     researcher-grade columnar (when pyarrow installed)
      datapackage.json          Frictionless descriptor (schema + provenance + hashes)
      DATASHEET.md              human self-description (schema, coverage, limits)
      COVERAGE.json             honest per-institution scope (absence = no data)
      derived/glasshouse.db     SQLite convenience view for Datasette / browsing
      MANIFEST.sha256           checksum of every file → reproducibility + tamper check
      README.md                 how to cite, how to verify, license, what's NOT here

The disclosure boundary is inherited wholesale from `publish.PUBLIC_TABLES`:
operator-internal tables (triage/llm_log/outreach/signals/match_log/runs) and
unapproved findings never enter a release. That invariant is tested
(test_release.py) on this surface, not just the SQLite one.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from . import dataset, publish
from .http import DATA_DIR

RELEASES_DIR = DATA_DIR / "releases"
# Above this row count we gzip the CSV (votes/holdings get huge); below it we
# leave it plain so small tables stay clickable and diffable.
GZIP_THRESHOLD_ROWS = 50_000


def _existing_public_tables(conn: sqlite3.Connection) -> dict[str, str]:
    """publish.PUBLIC_TABLES restricted to tables that actually exist."""
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: w for t, w in publish.PUBLIC_TABLES.items() if t in have}


def _emit_csv(conn: sqlite3.Connection, table: str, where: str, facts: Path) -> tuple[str, int]:
    """Stream one public table to CSV (gzipped past the threshold). Header is
    always written so every table's contract is visible even when empty."""
    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    gz = n > GZIP_THRESHOLD_ROWS
    name = f"{table}.csv.gz" if gz else f"{table}.csv"
    path = facts / name
    cols = publish.public_columns(conn, table)     # drops operator-only cols (e.g. content_path)
    cur = conn.execute(f"SELECT {','.join(cols)} FROM {table} {where}")
    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8")) if gz \
        else (lambda p: open(p, "w", newline="", encoding="utf-8"))
    with opener(path) as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for row in cur:                      # streamed, not fetchall — votes is millions
            w.writerow([row[c] for c in cols])
    return name, n


def _emit_parquet(conn: sqlite3.Connection, table: str, where: str, facts: Path) -> str | None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return None
    cols = publish.public_columns(conn, table)
    cur = conn.execute(f"SELECT {','.join(cols)} FROM {table} {where}")
    data: dict[str, list] = {c: [] for c in cols}
    for row in cur:
        for c in cols:
            data[c].append(row[c])
    name = f"{table}.parquet"
    pq.write_table(pa.table(data), facts / name)
    return name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_release(conn: sqlite3.Connection, root: Path | str | None = None,
                  version: str | None = None, with_parquet: bool = True,
                  with_sqlite: bool = False) -> dict:
    """Build a complete, verifiable, self-describing release bundle. Returns a
    summary dict; the bundle on disk is the deliverable.

    CSV + Parquet are the canonical consumable formats. The SQLite browse view
    (`with_sqlite`) is opt-in: it roughly doubles bundle size and duplicates the
    facts, so it ships only when a Datasette-style local browse is wanted."""
    version = version or date.today().isoformat()
    # The version becomes a directory name we later rmtree — never let it escape
    # the releases root (no separators / traversal).
    if version in (".", "..") or any(c in version for c in "/\\"):
        raise ValueError(f"invalid release version: {version!r}")
    root = Path(root) if root else RELEASES_DIR
    d = root / f"v{version}"
    if d.exists():            # reproducible: the dir reflects exactly this build
        shutil.rmtree(d)
    facts = d / "facts"
    facts.mkdir(parents=True, exist_ok=True)

    public = _existing_public_tables(conn)
    tables: dict[str, dict] = {}
    formats = {"csv"}
    for table, where in public.items():
        csv_name, rows = _emit_csv(conn, table, where, facts)
        pq_name = _emit_parquet(conn, table, where, facts) if with_parquet else None
        if pq_name:
            formats.add("parquet")
        tables[table] = {"csv": f"facts/{csv_name}", "rows": rows,
                         "parquet": f"facts/{pq_name}" if pq_name else None}

    # Self-description, generated from the data so it cannot drift.
    pkg = dataset.build_datapackage(conn)
    for res in pkg["resources"]:                      # attach real paths + hashes
        t = tables.get(res["name"])
        if not t:
            continue
        paths = [t["csv"]] + ([t["parquet"]] if t["parquet"] else [])
        res["path"] = paths
        res["format"] = "csv"
        res["sha256"] = _sha256(d / t["csv"])
        res["bytes"] = (d / t["csv"]).stat().st_size
    (d / "datapackage.json").write_text(json.dumps(pkg, indent=2))
    (d / "DATASHEET.md").write_text(dataset.build_datasheet(conn))
    (d / "COVERAGE.json").write_text(json.dumps(dataset.coverage(conn), indent=2))

    # SQLite convenience view (same disclosure boundary) for Datasette/browsing —
    # opt-in, because it duplicates the facts and ~doubles the bundle.
    if with_sqlite:
        (d / "derived").mkdir(parents=True, exist_ok=True)
        publish.build_public_snapshot(conn, d / "derived" / "glasshouse.db")

    (d / "README.md").write_text(_readme(pkg, tables, version, with_sqlite))

    # Manifest LAST, over everything else — checksums make the bundle verifiable
    # without trusting us (`sha256sum -c MANIFEST.sha256`).
    files = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [f"{_sha256(p)}  {p.relative_to(d)}" for p in files]
    (d / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")

    total = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
    return {"version": version, "dir": str(d), "tables": tables,
            "formats": sorted(formats), "file_count": len(files) + 1,
            "bytes": total, "with_sqlite": with_sqlite}


def _readme(pkg: dict, tables: dict, version: str, with_sqlite: bool = False) -> str:
    rows = sum(t["rows"] for t in tables.values())
    has_pq = any(t["parquet"] for t in tables.values())
    cite = (f"Glasshouse evidence dataset, v{version} (commit {pkg['git_commit']}). "
            "CC-BY-4.0. https://github.com/ (add release/DOI URL).")
    lines = [
        f"# Glasshouse evidence dataset — v{version}", "",
        pkg["description"], "",
        f"**{rows:,} public rows** across {len(tables)} tables · "
        f"formats: CSV{' + Parquet' if has_pq else ''} · license CC-BY-4.0 · "
        f"commit `{pkg['git_commit']}`", "",
        "## What this is",
        "A primary-source-cited, deduplicated, **versioned** snapshot of what major "
        "financial institutions say (archived policy documents) versus what they do "
        "(SEC N-PX proxy votes and 13-F / N-PORT holdings), plus the enforcement "
        "record. Built for researchers and journalists to find and cite insights.", "",
        "## Verify it (don't trust us)",
        "```sh",
        "sha256sum -c MANIFEST.sha256   # every file's checksum",
        "```",
        "Each row carries `source_url` + `retrieval_date`; `datapackage.json` lists "
        "per-table schema and content hashes; `DATASHEET.md` documents coverage and "
        "limits.", "",
        "## Use it",
        "- `facts/*.csv[.gz]` — open everywhere (pandas, R, DuckDB, spreadsheets).",
        *(["- `facts/*.parquet` — typed, columnar, for analysis at scale."] if has_pq else []),
        *(["- `derived/glasshouse.db` — SQLite; browse with "
           "`datasette derived/glasshouse.db`."] if with_sqlite else []), "",
        "## Cite it", "```", cite, "```", "",
        "## Provenance guarantees",
        *[f"- {g}" for g in pkg["provenance_guarantees"]], "",
        "## What is NOT here (by construction)",
        "- Operator-internal tables (advisory LLM output, unsent outreach drafts, "
        "internal signals) — never published.",
        "- Findings that a human has **not** approved — the `findings` table holds "
        "approved claims only; everything else stays a private lead.",
        "- Full coverage — this is a **partial, growing** snapshot. See "
        "`COVERAGE.json` / `DATASHEET.md` for exactly what is in. Absence means no "
        "data was collected, not a clean record.", "",
    ]
    return "\n".join(lines) + "\n"
