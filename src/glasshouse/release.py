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

from . import dataset, publish, registry
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


class StaleEngineError(RuntimeError):
    """The engine index does not describe the current ledger (or is missing)."""


def _emit_rows(name: str, cols: list[str], rows_fn, n: int, facts: Path,
               with_parquet: bool) -> tuple[str, str | None]:
    """Write a table that is not a plain ledger table (config- or engine-derived).
    `rows_fn()` yields tuples in `cols` order. Same CSV/gzip/Parquet rules as
    the ledger tables."""
    gz = n > GZIP_THRESHOLD_ROWS
    csv_name = f"{name}.csv.gz" if gz else f"{name}.csv"
    opener = (lambda p: gzip.open(p, "wt", newline="", encoding="utf-8")) if gz \
        else (lambda p: open(p, "w", newline="", encoding="utf-8"))
    with opener(facts / csv_name) as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for row in rows_fn():
            w.writerow(row)
    pq_name = None
    if with_parquet:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            pa = None
        if pa is not None:
            data: dict[str, list] = {c: [] for c in cols}
            for row in rows_fn():
                for c, v in zip(cols, row, strict=True):
                    data[c].append(v)
            pq_name = f"{name}.parquet"
            pq.write_table(pa.table(data), facts / pq_name)
    return csv_name, pq_name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()



VOTING_ADVISERS_COLS = ["institution", "registrant_cik", "registrant_name", "series_id",
                        "adviser_key", "from", "until", "adviser", "adviser_source",
                        "adviser_verified"]
POLICY_VERSIONS_COLS = ["commitment_id", "institution", "doc_label", "adviser_key",
                        "adviser_key_date", "authored", "captured", "wayback_timestamp",
                        "source_url", "text_sha256", "file_sha256", "readable"]
PROPOSAL_COLS = ["proposal_id", "institution_id", "issuer_name", "cusip", "meeting_date",
                 "year", "description", "category", "mgmt_rec", "position", "n_lines",
                 "n_for", "n_against", "n_other", "themes", "oppositional", "ballot_key",
                 "adviser_key", "accession", "source_url", "vote_id"]
DIRECTOR_COLS = ["director_id", "institution_id", "issuer_name", "cusip", "meeting_date",
                 "year", "nominee_item", "position", "n_lines", "n_for", "n_against",
                 "n_other", "meeting_key", "adviser_key", "accession", "source_url",
                 "vote_id", "isin_country"]

# Verbatim excerpts of METHODOLOGY.md ("The evidence engine"); tests pin that each
# is still a substring of it (whitespace-collapsed), so this text cannot drift.
METHODOLOGY_PROPOSALS = (
    "N-PX reports one line per fund per ballot item.",
    "Rates over lines weight a proposal by how many of a manager's funds hold the "
    "stock; the engine counts each decision once.",
    "The position is SHARE-weighted: funds routinely file a sliver the other way "
    "(0.2–2.5% of shares at State Street), so the minority side must carry at least "
    "5% of shares voted before the position is `SPLIT`.",
    "the engine never aggregates lines voted by different advisers into one item: "
    "each adviser's decision is its own row",
)
METHODOLOGY_DIRECTORS = (
    "Director items are counted per nominee item as filed and per meeting; `opposed` "
    "is AGAINST or WITHHOLD, share-weighted.",
    "N-PX never records the reason for a vote, so a director-opposition rate cannot "
    "be attributed to any one policy provision (diversity, overboarding, pay).",
    "Each director item carries `isin_country`, the first two letters of the ISIN on "
    "its fund lines. That is the country that *issued the ISIN*, not where the "
    "company is run (a Cayman-registered company is `KY`); it is NULL where no line "
    "has an ISIN, the prefix is malformed, or the lines disagree.",
)

NEW_TABLES: dict[str, dict] = {
    "voting_advisers": {"_": "Which adviser votes which registrant's shares, one row per "
        "key rule, from config/institutions.yaml. Resolution order per vote line: series "
        "rule matching the meeting date, then registrant history, then default. Rules "
        "without a source URL are omitted (counted in DATASHEET.md).",
        "institution": "→ institutions.id", "registrant_cik": "N-PX filer CIK, no leading zeros",
        "registrant_name": "registrant as named in the registry",
        "series_id": "fund series the rule applies to; NULL = registrant-wide",
        "adviser_key": "short key of the voting adviser group",
        "from": "first meeting date (inclusive, ISO) the rule covers; NULL = unbounded",
        "until": "last meeting date (inclusive, ISO) the rule covers; NULL = unbounded",
        "adviser": "adviser's full name as recorded in the registry; filled only where "
                   "the rule's key is the registrant's default key",
        "adviser_source": "SEC filing URL that names the adviser",
        "adviser_verified": "date the source was checked"},
    "voting_scope_notes": {"_": "Verbatim caveats the registry records about who votes an "
        "institution's shares. Read them before pooling votes.",
        "institution": "→ institutions.id", "note": "verbatim from config/institutions.yaml"},
    "policy_versions": {"_": "One row per archived version of a policy document, by TEXT "
        "identity. Hashes, dates and URLs only: no policy text and no local paths.",
        "commitment_id": "→ commitments.id of the first capture of this text",
        "institution": "→ institutions.id", "doc_label": "document",
        "adviser_key": "whose policy this is, as the engine resolved it on adviser_key_date; "
                       "NULL = not on record",
        "adviser_key_date": "date the key was resolved on (= captured)",
        "authored": "date the manager's own software wrote the file (PDF metadata); '' if none",
        "captured": "ISO date the text was demonstrably public (Wayback capture or our fetch)",
        "wayback_timestamp": "Wayback capture timestamp; '' = live fetch",
        "source_url": "the document's URL", "text_sha256": "hash of the extracted text; '' if unreadable",
        "file_sha256": "hash of the file bytes",
        "readable": "1 if text was extracted from the file, else 0"},
    "proposal_decisions": {"_": "DERIVED. One row per (manager, adviser, company, meeting, "
        "proposal) decision on shareholder-sponsored proposals, rebuilt from `votes` by "
        "src/glasshouse/engine.py (`glasshouse engine build`). Not a ledger table.",
        "proposal_id": "engine row id; not stable across rebuilds",
        "institution_id": "→ institutions.id", "issuer_name": "company", "cusip": "CUSIP",
        "meeting_date": "ISO date", "year": "meeting year", "description": "proposal text as filed",
        "category": "N-PX category", "mgmt_rec": "vote vs management: WITH | AGAINST | MIXED | ''",
        "position": "FOR | AGAINST | ABSTAIN | SPLIT | NONE (share-weighted)",
        "n_lines": "ballot lines folded into the decision", "n_for": "lines FOR",
        "n_against": "lines AGAINST", "n_other": "other lines",
        "themes": "lexical theme tags ',climate,' — a lead, not a classification",
        "oppositional": "1 if the proposal asks to roll back the theme",
        "ballot_key": "same proposal across managers (strict match)",
        "adviser_key": "voting adviser group. NULL = institution has fewer than two known "
                       "advisers; 'unlabelled' = no adviser on record; UNRESOLVED / EXTERNAL / "
                       "UNDATED are never comparable with any policy",
        "accession": "→ filings.accession", "source_url": "EDGAR source",
        "vote_id": "→ votes.id of a representative line"},
    "director_decisions": {"_": "DERIVED. One row per management director-nominee item "
        "(`vote_source = ISSUER`, category DIRECTOR ELECTIONS) per manager and adviser, "
        "rebuilt from `votes` by src/glasshouse/engine.py. Not a ledger table.",
        "director_id": "engine row id; not stable across rebuilds",
        "institution_id": "→ institutions.id", "issuer_name": "company", "cusip": "CUSIP",
        "meeting_date": "ISO date", "year": "meeting year",
        "nominee_item": "the ballot line as filed (names the nominee)",
        "position": "FOR | AGAINST (incl. WITHHOLD) | ABSTAIN | SPLIT | NONE",
        "n_lines": "ballot lines folded in", "n_for": "lines FOR", "n_against": "lines AGAINST",
        "n_other": "other lines", "meeting_key": "same meeting across managers (CUSIP|date)",
        "adviser_key": "voting adviser group; same semantics as proposal_decisions",
        "accession": "→ filings.accession", "source_url": "EDGAR source",
        "vote_id": "→ votes.id of a representative line",
        "isin_country": "country that ISSUED the ISIN (not where the company is run); "
                        "NULL if none, malformed or lines disagree"},
}


def _http(u) -> bool:
    return isinstance(u, str) and u.strip().lower().startswith(("http://", "https://"))


def voting_advisers_rows(institutions: dict) -> tuple[list[tuple], int]:
    """([row], n_omitted): one row per key rule of every registrant in the registry.
    A rule whose registrant has no source URL is omitted and counted."""
    from . import engine
    out: list[tuple] = []
    omitted = 0
    for iid in sorted(institutions):
        for e in institutions[iid].get("npx_ciks") or []:
            if not e.get("cik"):
                continue
            r = engine.normalize_rules(e)
            rules = ([(None, r["default"], None, None)] if r["default"] else [])
            rules += [(None, k, lo, hi) for k, lo, hi in r["history"]]
            rules += [(sid, k, lo, hi) for sid, lst in sorted(r["series"].items())
                      for k, lo, hi in lst]
            src = e.get("adviser_source")
            for sid, k, lo, hi in rules:
                if not _http(src):
                    omitted += 1
                    continue
                out.append((iid, engine._norm_cik(e["cik"]), e.get("name"), sid, k, lo, hi,
                            (e.get("adviser") or None) if k == r["default"] else None,
                            str(src).strip(),
                            str(e["adviser_verified"]) if e.get("adviser_verified") else None))
    return out, omitted


def scope_notes_rows(institutions: dict) -> list[tuple]:
    return [(iid, str(n)) for iid in sorted(institutions)
            for n in institutions[iid].get("voting_scope_notes") or []]


def _engine_ro(engine_path: Path) -> sqlite3.Connection:
    if not Path(engine_path).exists():
        raise StaleEngineError(f"engine index {engine_path} not found: run "
                               "`glasshouse engine build` (or pass --no-derived)")
    e = sqlite3.connect(f"file:{engine_path}?mode=ro", uri=True)
    e.row_factory = sqlite3.Row
    return e


def check_engine_current(conn: sqlite3.Connection, eng: sqlite3.Connection) -> int:
    """The engine's ledger_max_vote_id, refusing (StaleEngineError) if it is not the
    ledger's current max vote id."""
    row = eng.execute("SELECT value FROM meta WHERE key='ledger_max_vote_id'").fetchone()
    cur = conn.execute("SELECT MAX(id) FROM votes").fetchone()[0]
    if row is None or str(row[0]) != str(cur):
        raise StaleEngineError(
            f"engine index is stale: it covers votes up to id {row[0] if row else None}, the "
            f"ledger's max vote id is {cur}. Run `glasshouse engine build`, or pass "
            "--no-derived to ship without proposal_decisions/director_decisions.")
    return int(cur) if cur is not None else 0


def policy_versions_rows(conn: sqlite3.Connection, eng: sqlite3.Connection) -> list[tuple]:
    out = []
    for p in eng.execute("SELECT * FROM policy_versions ORDER BY institution_id, doc_label, "
                         "captured, commitment_id"):
        c = conn.execute("SELECT text_sha256, wayback_timestamp, sha256 FROM commitments "
                         "WHERE id=?", (p["commitment_id"],)).fetchone()
        out.append((p["commitment_id"], p["institution_id"], p["doc_label"], p["adviser"],
                    p["adviser_key_date"], p["authored"] or "", p["captured"],
                    (c["wayback_timestamp"] if c else "") or "", p["url"],
                    (c["text_sha256"] if c else "") or "", p["sha256"],
                    int((p["n_sentences"] or 0) > 0)))
    return out


def _engine_rows(eng, table: str, src_cols: list[str], names: list[str], order: str):
    sel = ",".join(f"{s} AS {n}" if s != n else s for s, n in zip(src_cols, names, strict=True))

    def fn():
        for r in eng.execute(f"SELECT {sel} FROM {table} ORDER BY {order}"):
            yield tuple(r[n] for n in names)
    return fn


def _derived_extra(pkg: dict, datasheet: str, notes: dict) -> str:
    """Insert the comparison warning near the top of the datasheet and document the
    new tables before the reading guide."""
    warn = [
        "## Before you compare a policy with votes", "",
        "**Read this first. Pooling votes cast by different advisers, or comparing them "
        "with another adviser's policy, produces false results.**", "",
        "- One institution's registrants can be voted by different advisers under "
        "different policies. Group votes by `adviser_key` "
        "(`proposal_decisions`, `director_decisions`; for raw `votes`, resolve the key "
        "from `voting_advisers` by registrant CIK, `fund_series.series_id` and meeting date).",
        "- A policy version (`policy_versions`) applies only to votes with the SAME "
        "`adviser_key`, and only when the version was captured on or before the meeting date.",
        "- Keys `UNRESOLVED`, `EXTERNAL` and `UNDATED` (and `unlabelled`, no adviser on "
        "record) are never comparable with any policy. `EXTERNAL` = a series advised by "
        "an outside manager; `UNDATED` = the meeting date cannot place the vote in a "
        "dated rule.",
        "- `isin_country` is the country that ISSUED the ISIN, not where the company is run.",
        "- Read `voting_scope_notes` for each institution before pooling anything.",
        "- Never sum `shares_voted` without `is_duplicate = 0` (the shipped `votes` table "
        "already applies it).", ""]
    if notes["omitted"]:
        warn += [f"- {notes['omitted']} voting rule(s) have no source URL in the registry and "
                 "are **unverified**: they are omitted from `voting_advisers`, so a key may "
                 "appear in the derived tables without a matching rule row.", ""]
    else:
        warn += ["- Unverified voting rules (no source URL): 0 (none omitted).", ""]
    if notes["derived"]:
        warn += [f"Derived tables were built from an engine index covering ledger votes up to "
                 f"id {notes['ledger_max_vote_id']} (equal to the ledger's maximum at build).", ""]
    else:
        warn += ["**This bundle was built with `--no-derived`: `proposal_decisions` and "
                 "`director_decisions` are NOT included.**", ""]
    marker = "## Provenance guarantees"
    datasheet = datasheet.replace(marker, "\n".join(warn) + "\n" + marker, 1)

    doc = ["## Voting-adviser tables, policy versions and DERIVED tables", ""]
    for res in pkg["resources"]:
        if res["name"] not in NEW_TABLES:
            continue
        tag = " — DERIVED" if res.get("derived") else ""
        doc.append(f"### `{res['name']}`{tag} ({res['rowCount']:,} rows)")
        doc.append(res["description"])
        if res.get("derived"):
            doc += ["", "**DERIVED, not a ledger table.** It is rebuilt from `votes` by code in "
                    "this repository (`src/glasshouse/engine.py`, run as `glasshouse engine "
                    "build`) and can be regenerated at any time. "
                    + " ".join(res["methodology"])]
        for f in res["schema"]["fields"]:
            doc.append(f"- **{f['name']}** — {f['description']}")
        doc.append("")
    marker2 = "## How to read this dataset"
    return datasheet.replace(marker2, "\n".join(doc) + "\n" + marker2, 1)


def build_release(conn: sqlite3.Connection, root: Path | str | None = None,
                  version: str | None = None, with_parquet: bool = True,
                  with_sqlite: bool = False, no_derived: bool = False,
                  engine_path: Path | str | None = None,
                  institutions: dict | None = None) -> dict:
    """Build a complete, verifiable, self-describing release bundle. Returns a
    summary dict; the bundle on disk is the deliverable.

    CSV + Parquet are the canonical consumable formats. The SQLite browse view
    (`with_sqlite`) is opt-in: it roughly doubles bundle size and duplicates the
    facts, so it ships only when a Datasette-style local browse is wanted."""
    from . import engine as engine_mod
    version = version or date.today().isoformat()
    # The version becomes a directory name we later rmtree — never let it escape
    # the releases root (no separators / traversal).
    if version in (".", "..") or any(c in version for c in "/\\"):
        raise ValueError(f"invalid release version: {version!r}")
    root = Path(root) if root else RELEASES_DIR
    # Everything that can refuse does so BEFORE the old bundle dir is removed.
    eng = _engine_ro(Path(engine_path) if engine_path else engine_mod.ENGINE_PATH)
    try:
        max_vote_id = None
        if not no_derived:
            max_vote_id = check_engine_current(conn, eng)
        institutions = registry.load() if institutions is None else institutions
        pv_rows = policy_versions_rows(conn, eng)
        va_rows, omitted = voting_advisers_rows(institutions)
        sn_rows = scope_notes_rows(institutions)
        eng_meta = {r[0]: r[1] for r in eng.execute("SELECT key, value FROM meta")}
        return _build(conn, eng, root, version, with_parquet, with_sqlite, no_derived,
                      max_vote_id, eng_meta, pv_rows, va_rows, omitted, sn_rows)
    finally:
        eng.close()


def _build(conn, eng, root, version, with_parquet, with_sqlite, no_derived, max_vote_id,
           eng_meta, pv_rows, va_rows, omitted, sn_rows) -> dict:
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

    extra: list[tuple] = [
        ("voting_advisers", VOTING_ADVISERS_COLS, va_rows, None),
        ("voting_scope_notes", ["institution", "note"], sn_rows, None),
        ("policy_versions", POLICY_VERSIONS_COLS, pv_rows, None),
    ]
    if not no_derived:
        p_fn = _engine_rows(eng, "proposals", [c if c != "adviser_key" else "adviser"
                            for c in PROPOSAL_COLS], PROPOSAL_COLS, "proposal_id")
        d_fn = _engine_rows(eng, "director_votes", [c if c != "adviser_key" else "adviser"
                            for c in DIRECTOR_COLS], DIRECTOR_COLS, "director_id")
        extra += [
            ("proposal_decisions", PROPOSAL_COLS, p_fn,
             eng.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]),
            ("director_decisions", DIRECTOR_COLS, d_fn,
             eng.execute("SELECT COUNT(*) FROM director_votes").fetchone()[0])]
    for name, cols, rows, n in extra:
        fn = rows if callable(rows) else (lambda r=rows: iter(r))
        n = len(rows) if n is None else n
        csv_name, pq_name = _emit_rows(name, cols, fn, n, facts, with_parquet)
        if pq_name:
            formats.add("parquet")
        tables[name] = {"csv": f"facts/{csv_name}", "rows": n,
                        "parquet": f"facts/{pq_name}" if pq_name else None}

    # Self-description, generated from the data so it cannot drift.
    pkg = dataset.build_datapackage(conn)
    pkg["derived_tables_included"] = not no_derived
    pkg["engine"] = {"ledger_max_vote_id": max_vote_id if not no_derived else
                     eng_meta.get("ledger_max_vote_id"),
                     "built_at": eng_meta.get("built_at"),
                     "current_at_release": not no_derived}
    for name, spec in NEW_TABLES.items():
        if name not in tables:
            continue
        res = {"name": name, "rowCount": tables[name]["rows"],
               "description": spec["_"],
               "schema": {"fields": [{"name": k, "description": v}
                                     for k, v in spec.items() if k != "_"]}}
        if name in ("proposal_decisions", "director_decisions"):
            res["derived"] = True
            res["derivation"] = ("Rebuilt from `votes` by src/glasshouse/engine.py "
                                 "(`glasshouse engine build`); not a ledger table.")
            res["methodology"] = list(METHODOLOGY_PROPOSALS if name == "proposal_decisions"
                                      else METHODOLOGY_DIRECTORS)
        pkg["resources"].append(res)
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
    (d / "DATASHEET.md").write_text(_derived_extra(
        pkg, dataset.build_datasheet(conn),
        {"omitted": omitted, "derived": not no_derived, "ledger_max_vote_id": max_vote_id}))
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
        "## Leads, not findings (read before publishing)",
        "This is a factual compilation — acts, dates, amounts, votes; never motive. "
        "Any say-vs-do gap you derive is a **lead**: theme matching is lexical, so "
        "confirm each proposal's text/intent and the in-force policy version against "
        "the linked primary source before publishing a claim.",
        "",
        "## Corrections",
        "Spotted an error? Open an issue at the project repository (or email the "
        "maintainer) with the table, the row, and the primary-source link.", "",
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
