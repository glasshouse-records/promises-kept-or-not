"""The commitments ledger (Phase 2): what institutions SAY, versioned.

Each institution's published commitment documents (stewardship / proxy-voting
policies, ESG reports) are configured in config/institutions.yaml:

    blackrock:
      commitments:
        - label: investment-stewardship-global-principles
          url: https://www.blackrock.com/...pdf

Every fetch is content-hashed; a document only gets a new ledger row when its
content actually changes. Historical versions come from the Wayback Machine
(CDX API). Silent edits between versions are findings in themselves —
`glasshouse report policy-edits` lists every document with >1 version.

Every hypocrisy claim quotes the institution's own archived words with a
date; this module is where those words and dates come from.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import date
from pathlib import Path

from .. import http

logger = logging.getLogger(__name__)

CDX_URL = "https://web.archive.org/cdx/search/cdx"
COMMITMENTS_DIR = http.DATA_DIR / "commitments"

_EXT_BY_TYPE = {"application/pdf": ".pdf", "text/html": ".html", "text/plain": ".txt"}


def _ext_for(content_type: str, url: str) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    if base in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[base]
    suffix = Path(url.split("?")[0]).suffix
    return suffix if suffix else ".bin"


def record_snapshot(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                    url: str, content: bytes, content_type: str = "",
                    wayback_timestamp: str = "",
                    retrieval_date: str | None = None) -> bool:
    """Store one snapshot of a commitment document. Returns True if this is
    new content (a new version), False if the hash was already recorded."""
    sha = hashlib.sha256(content).hexdigest()
    exists = conn.execute(
        "SELECT 1 FROM commitments WHERE institution_id=? AND doc_label=? "
        "AND sha256=? AND wayback_timestamp=?",
        (institution_id, doc_label, sha, wayback_timestamp),
    ).fetchone()
    if exists:
        return False

    ext = _ext_for(content_type, url)
    stamp = wayback_timestamp or (retrieval_date or date.today().isoformat())
    dest = COMMITMENTS_DIR / institution_id / f"{doc_label}__{stamp}__{sha[:8]}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
        "sha256, content_path, content_type, size_bytes, wayback_timestamp) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (institution_id, doc_label, url, retrieval_date or date.today().isoformat(),
         sha, str(dest), content_type, len(content), wayback_timestamp),
    )
    conn.commit()
    return True


def fetch_live(conn: sqlite3.Connection, institutions: dict[str, dict]) -> dict[str, int]:
    """Fetch the current version of every configured commitment document."""
    new_versions: dict[str, int] = {}
    for inst_id, inst in institutions.items():
        for doc in inst.get("commitments", []):
            label, url = doc["label"], doc["url"]
            try:
                resp = http.get(url, timeout=60)
            except Exception as exc:
                logger.warning("%s/%s fetch failed: %s", inst_id, label, exc)
                continue
            is_new = record_snapshot(conn, inst_id, label, url, resp.content,
                                     resp.headers.get("Content-Type", ""))
            key = f"{inst_id}/{label}"
            new_versions[key] = int(is_new)
            logger.info("%s: %s", key, "NEW VERSION" if is_new else "unchanged")
    return new_versions


def wayback_history(url: str, limit: int = 50) -> list[dict]:
    """Historical snapshots of a URL from the Wayback CDX API, deduplicated
    by content digest (one entry per distinct version)."""
    rows = http.get_json(CDX_URL, params={
        "url": url, "output": "json", "fl": "timestamp,digest,statuscode,mimetype",
        "filter": "statuscode:200", "collapse": "digest", "limit": limit,
    }, timeout=60)
    if not rows or len(rows) < 2:
        return []
    header, entries = rows[0], rows[1:]
    return [dict(zip(header, r)) for r in entries]


def fetch_wayback(conn: sqlite3.Connection, institutions: dict[str, dict],
                  max_versions: int = 10) -> int:
    """Ingest distinct historical versions of every configured commitment doc.

    Uses the `id_` raw-content endpoint so we archive the institution's own
    bytes, not the Wayback chrome around them.
    """
    n_new = 0
    for inst_id, inst in institutions.items():
        for doc in inst.get("commitments", []):
            label, url = doc["label"], doc["url"]
            try:
                history = wayback_history(url, limit=max_versions)
            except Exception as exc:
                logger.warning("%s/%s wayback history failed: %s", inst_id, label, exc)
                continue
            for snap in history:
                ts = snap["timestamp"]
                raw_url = f"https://web.archive.org/web/{ts}id_/{url}"
                try:
                    resp = http.get(raw_url, timeout=120)
                except Exception as exc:
                    logger.warning("wayback %s@%s fetch failed: %s", label, ts, exc)
                    continue
                if record_snapshot(conn, inst_id, label, url, resp.content,
                                   snap.get("mimetype", ""), wayback_timestamp=ts,
                                   retrieval_date=date.today().isoformat()):
                    n_new += 1
                    logger.info("%s/%s: archived wayback version %s", inst_id, label, ts)
    return n_new


def policy_edits(conn: sqlite3.Connection) -> list[dict]:
    """Documents with more than one distinct content version — each a
    potential silent-policy-edit finding (diff the content_paths)."""
    rows = conn.execute(
        """SELECT institution_id, doc_label, COUNT(DISTINCT sha256) AS versions,
                  MIN(COALESCE(NULLIF(wayback_timestamp,''), retrieval_date)) AS first_seen,
                  MAX(COALESCE(NULLIF(wayback_timestamp,''), retrieval_date)) AS last_seen
           FROM commitments
           GROUP BY institution_id, doc_label
           HAVING COUNT(DISTINCT sha256) > 1
           ORDER BY versions DESC"""
    ).fetchall()
    out = []
    for r in rows:
        versions = conn.execute(
            "SELECT sha256, content_path, retrieval_date, wayback_timestamp "
            "FROM commitments WHERE institution_id=? AND doc_label=? "
            "GROUP BY sha256 ORDER BY COALESCE(NULLIF(wayback_timestamp,''), retrieval_date)",
            (r["institution_id"], r["doc_label"]),
        ).fetchall()
        out.append({
            "institution_id": r["institution_id"],
            "doc_label": r["doc_label"],
            "n_versions": r["versions"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
            "versions": [dict(v) for v in versions],
        })
    return out
