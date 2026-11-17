"""Rebuild a working ledger from a published release bundle.

A fresh clone has no ledger, and the only other way to make one is a full SEC
ingest (many hours of 65-124 MB downloads). The release bundle already carries
every fact the engine reads, so `glasshouse restore <bundle>` writes a ledger
from it and `glasshouse engine build` then works.

What the restored ledger IS, honestly:

* the bundle's rows, verified against MANIFEST.sha256 first, loaded through
  `ledger.connect` (the ledger's own schema, never a copy of it);
* votes carry `is_duplicate = 0` because the bundle ships only kept rows
  (publish.PUBLIC_TABLES); the as-filed duplicates and the quarantined
  `legacy_html` rows are not in it, and no duplicate is invented here;
* stamped as restored: one `ingest_runs` row whose source is
  `restore:<bundle>:<manifest hash>`. No live-ingest check looks for that
  source, so nothing can read the ledger as a live ingest. The engine copies
  it into its own meta table.

What it is NOT: policy text is not in the bundle, so `commitments.content_path`
is '' and the engine's `policy_sentences` come out empty. The versions, URLs,
hashes and Wayback timestamps are all there; the wording is re-fetched from the
public sources with `glasshouse ingest commitments --wayback`.

The ledger is written beside its destination and renamed into place, so a
failed restore leaves nothing behind.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from . import ledger

RESTORE_SOURCE_PREFIX = "restore:"

# Load order respects foreign keys. Columns the ledger does not have (the two
# release-time additions to votes) are dropped; any other unknown column aborts.
TABLES = ("institutions", "filings", "fund_series", "votes", "holdings",
          "enforcement_actions", "entities", "entity_cusips", "commitments", "findings")
RELEASE_ONLY_COLS = {"votes": {"institution_id", "adviser_key"}}
# Rows that decide whether an existing ledger is "non-empty". `institutions` is
# excluded: `glasshouse init-db` seeds it and a seeded-only ledger holds no facts.
FACT_TABLES = ("filings", "votes", "holdings", "enforcement_actions", "commitments",
               "findings", "fund_series", "entities")
BATCH = 50_000


class RestoreError(Exception):
    """The bundle or the destination is not acceptable; nothing was written."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(bundle: Path) -> str:
    """Check every file listed in MANIFEST.sha256 and refuse any unlisted file under
    facts/. Returns the sha256 of the manifest itself (the bundle's identity)."""
    manifest = bundle / "MANIFEST.sha256"
    if not manifest.is_file():
        raise RestoreError(f"{bundle} has no MANIFEST.sha256: not a release bundle")
    listed: set[str] = set()
    for n, line in enumerate(manifest.read_text().splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            raise RestoreError(f"MANIFEST.sha256 line {n} is malformed")
        target = (bundle / rel).resolve()
        if bundle.resolve() not in target.parents:
            raise RestoreError(f"MANIFEST.sha256 names a path outside the bundle: {rel}")
        if not target.is_file():
            raise RestoreError(f"MANIFEST.sha256 lists {rel}, which is missing")
        if _sha256(target) != digest:
            raise RestoreError(f"checksum mismatch for {rel}: the bundle is corrupt or "
                               "has been altered; refusing to restore")
        listed.add(rel)
    extra = sorted(str(p.relative_to(bundle)) for p in (bundle / "facts").rglob("*")
                   if p.is_file() and str(p.relative_to(bundle)) not in listed)
    if extra:
        raise RestoreError(f"files under facts/ that MANIFEST.sha256 does not list: {extra}")
    return _sha256(manifest)


def _check_destination(dest: Path) -> None:
    if not dest.exists():
        return
    conn = ledger.connect(dest)
    try:
        for t in FACT_TABLES:
            if conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone():
                raise RestoreError(f"{dest} already holds data ({t} is not empty); "
                                   "refusing to overwrite a ledger. Point "
                                   "GLASSHOUSE_DATA_DIR at an empty directory.")
    finally:
        conn.close()


def _load_table(conn, bundle: Path, table: str) -> int:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:    # pragma: no cover - environment
        raise RestoreError("restore reads the bundle's Parquet files: "
                           "`pip install -e \".[release]\"` (pyarrow)") from exc
    path = bundle / "facts" / f"{table}.parquet"
    if not path.is_file():
        return 0
    have = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    pf = pq.ParquetFile(path)
    cols = [c for c in pf.schema_arrow.names if c not in RELEASE_ONLY_COLS.get(table, ())]
    unknown = [c for c in cols if c not in have]
    if unknown:
        raise RestoreError(f"{table}.parquet has columns the ledger does not: {unknown}")
    sql_cols = list(cols)
    fixed: dict[str, object] = {}
    if table == "votes":
        fixed["is_duplicate"] = 0          # the bundle holds only kept rows
    if table == "commitments":
        fixed["content_path"] = ""         # policy text is not in the bundle
    sql_cols += list(fixed)
    sql = (f"INSERT INTO {table} ({','.join(sql_cols)}) "
           f"VALUES ({','.join('?' * len(sql_cols))})")
    extra = tuple(fixed.values())
    n = 0
    for batch in pf.iter_batches(batch_size=BATCH, columns=cols):
        data = batch.to_pydict()
        conn.executemany(sql, [tuple(row) + extra
                               for row in zip(*(data[c] for c in cols), strict=True)])
        n += batch.num_rows
    return n


def restore(bundle: Path | str, dest: Path | str | None = None) -> dict:
    """Create the ledger at `dest` (default: the configured data dir) from `bundle`.
    Raises RestoreError, with nothing written, if the bundle does not verify or the
    destination already holds data."""
    bundle = Path(bundle)
    dest = Path(dest) if dest is not None else ledger.DB_PATH
    t0 = time.monotonic()
    manifest_sha = verify_manifest(bundle)
    _check_destination(dest)
    version = bundle.resolve().name
    tmp = dest.with_name(dest.name + ".restoring")
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    conn = ledger.connect(tmp)
    counts: dict[str, int] = {}
    try:
        for table in TABLES:
            counts[table] = _load_table(conn, bundle, table)
            conn.commit()
        total = sum(counts.values())
        ledger.record_ingest_run(
            conn, f"{RESTORE_SOURCE_PREFIX}{version}:{manifest_sha[:12]}", total, total)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        conn = None
        for suffix in ("-wal", "-shm"):
            Path(str(tmp) + suffix).unlink(missing_ok=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(dest) + suffix).unlink(missing_ok=True)
        tmp.replace(dest)
    except BaseException:
        if conn is not None:
            conn.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(tmp) + suffix).unlink(missing_ok=True)
        raise
    return {"version": version, "manifest_sha256": manifest_sha, "ledger": str(dest),
            "counts": counts, "seconds": round(time.monotonic() - t0, 1),
            "votes_is_duplicate": 0}
