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
import re
import sqlite3
from datetime import date
from html import unescape
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


# Error-page signatures. A rotted policy URL returns (or Wayback captured) an
# HTML 404/error page; recording it as a "policy version" is provenance rot —
# found 2026-06 when 6 of 7 archived Vanguard versions were the site's 404
# page, masquerading as policy drift and silently killing the contradiction
# engine for that institution.
_ERROR_SIGNATURES = (
    "404 error", "page not found", "page cannot be found", "page isn't available",
    "404 - ", "error 404", "not found | ", "access denied", "forbidden",
)


def looks_like_error_page(content: bytes, content_type: str = "") -> bool:
    """True if content is an HTML error/404 page rather than a real document.

    Only inspects HTML-ish payloads (a real PDF's bytes won't trip these).
    Checks the <title> and document head, where error pages announce
    themselves, not the whole body (a real policy may discuss '404'
    nowhere meaningful)."""
    base = (content_type or "").split(";")[0].strip().lower()
    head = content[:2000].decode("utf-8", "replace").lower()
    is_html = base in ("text/html", "application/xhtml+xml") or head.lstrip().startswith(
        ("<!doctype html", "<html"))
    if not is_html:
        return False
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", head, re.DOTALL)
    if m:
        title = m.group(1)
    hay = title + " " + head[:600]
    return any(sig in hay for sig in _ERROR_SIGNATURES)


# --- Version identity -------------------------------------------------------
# A "version" is a change in what the institution SAYS, not a change in bytes.
# BNY's policy page is served behind Akamai, whose mPulse beacon carries a
# per-REQUEST token: two captures of an unchanged policy hash differently.
# Deduping on raw bytes therefore filed phantom versions (8 of BNY's 10), and
# with a daily capture cron that would compound every single day. Raw sha256
# still records byte-integrity of what we stored; THIS decides what counts as
# a new version.

_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|noscript)\b.*?</\1\s*>")
_TAG = re.compile(r"(?s)<[^>]+>")
_MIN_TEXT = 200        # below this, extraction is untrustworthy — see policy_text()


def html_to_text(raw: str) -> str:
    """Visible prose from an HTML page: no markup, no script bodies.

    Used on both sides of the archive — the capture path (to decide what is a
    new version) and the analysis path (the commitment scorer must weigh
    promise language, not navigation markup)."""
    txt = _SCRIPT_STYLE.sub(" ", raw)
    txt = _TAG.sub(" ", txt)
    txt = unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def policy_text(content: bytes, content_type: str = "", url: str = "") -> str:
    """The readable policy text of a snapshot, or '' if it can't be read.

    An empty return is deliberate and load-bearing: callers must fall back to
    byte identity rather than treat every unreadable document as the same
    version. Over-counting versions is recoverable; silently merging two
    genuinely different policies is not."""
    ext = _ext_for(content_type, url)
    if ext == ".pdf":
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            logger.warning("policy-text extraction failed (%s): %s", url, exc)
            return ""
        return re.sub(r"\s+", " ", text).strip()
    raw = content.decode("utf-8", "replace")
    base = (content_type or "").split(";")[0].strip().lower()
    if base in ("text/html", "application/xhtml+xml") or raw.lstrip()[:200].lower().startswith(
            ("<!doctype html", "<html")):
        return html_to_text(raw)
    return re.sub(r"\s+", " ", raw).strip()


def version_identity(content: bytes, content_type: str = "", url: str = "") -> tuple[str, str]:
    """(raw_sha256, text_sha256). text_sha256 is '' when the text could not be
    read or is too short to trust — the caller then dedupes on bytes."""
    raw_sha = hashlib.sha256(content).hexdigest()
    text = policy_text(content, content_type, url)
    if len(text) < _MIN_TEXT:
        return raw_sha, ""
    return raw_sha, hashlib.sha256(text.encode()).hexdigest()


def record_snapshot(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                    url: str, content: bytes, content_type: str = "",
                    wayback_timestamp: str = "",
                    retrieval_date: str | None = None) -> bool:
    """Store one snapshot of a commitment document. Returns True if this is
    new content (a new version), False if already recorded OR rejected as an
    error page (a rotted-URL 404 is not a policy version)."""
    if looks_like_error_page(content, content_type):
        logger.warning("%s/%s: content looks like an error page (rotted URL?) — "
                        "not recording as a policy version", institution_id, doc_label)
        return False
    sha, text_sha = version_identity(content, content_type, url)
    if text_sha:
        # Same words already on file for this document = not a new version,
        # whatever the bytes say. Deliberately NOT scoped to wayback_timestamp:
        # a Wayback capture that reproduces text we already hold is the same
        # version of the policy, filed from a different place.
        exists = conn.execute(
            "SELECT 1 FROM commitments WHERE institution_id=? AND doc_label=? "
            "AND text_sha256=?", (institution_id, doc_label, text_sha)).fetchone()
    else:
        # Unreadable (scanned PDF, extraction failure): fall back to bytes.
        # Over-counting is recoverable; merging two real policies is not.
        exists = conn.execute(
            "SELECT 1 FROM commitments WHERE institution_id=? AND doc_label=? "
            "AND sha256=? AND wayback_timestamp=?",
            (institution_id, doc_label, sha, wayback_timestamp)).fetchone()
    if exists:
        return False

    ext = _ext_for(content_type, url)
    stamp = wayback_timestamp or (retrieval_date or date.today().isoformat())
    dest = COMMITMENTS_DIR / institution_id / f"{doc_label}__{stamp}__{sha[:8]}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
        "sha256, content_path, content_type, size_bytes, wayback_timestamp, "
        "text_sha256) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (institution_id, doc_label, url, retrieval_date or date.today().isoformat(),
         sha, str(dest), content_type, len(content), wayback_timestamp, text_sha),
    )
    conn.commit()
    return True


def backfill_text_hashes(conn: sqlite3.Connection) -> int:
    """Give every already-archived snapshot its text hash. Returns rows filled.

    Without this the dedupe added 2026-08-26 compares each new capture against
    a history of empty hashes, so the first capture of every CDN-served page
    would still land as a phantom version. Idempotent; safe to call on every
    run. Never rewrites an existing hash and never deletes a row — the
    duplicates already on file stay as provenance of what we fetched, and the
    honest version count is COUNT(DISTINCT text_sha256)."""
    todo = conn.execute(
        "SELECT id, content_path, content_type, url FROM commitments "
        "WHERE text_sha256 = ''").fetchall()
    filled = 0
    for row in todo:
        path = Path(row["content_path"] if isinstance(row, sqlite3.Row) else row[1])
        if not path.exists():
            continue
        try:
            content = path.read_bytes()
        except OSError as exc:
            logger.warning("backfill: cannot read %s: %s", path, exc)
            continue
        _raw, text_sha = version_identity(
            content,
            row["content_type"] if isinstance(row, sqlite3.Row) else row[2],
            row["url"] if isinstance(row, sqlite3.Row) else row[3])
        if not text_sha:
            continue                      # unreadable: stays on byte identity
        conn.execute("UPDATE commitments SET text_sha256=? WHERE id=?",
                     (text_sha, row["id"] if isinstance(row, sqlite3.Row) else row[0]))
        filled += 1
    conn.commit()
    return filled


def fetch_live(conn: sqlite3.Connection, institutions: dict[str, dict]) -> dict[str, int]:
    """Fetch the current version of every configured commitment document."""
    backfill_text_hashes(conn)   # history must be comparable before we compare
    new_versions: dict[str, int] = {}
    for inst_id, inst in institutions.items():
        for doc in inst.get("commitments", []):
            label, url = doc["label"], doc["url"]
            try:
                resp = http.get(url, timeout=60)
            except Exception as exc:
                logger.warning("%s/%s fetch failed: %s", inst_id, label, exc)
                continue
            ctype = resp.headers.get("Content-Type", "")
            # Soft-404 guard: a .pdf URL answering with HTML is an error page
            # with status 200 (observed live: Vanguard, 2026-06-11). Recording
            # it would forge a phantom policy "version".
            if url.lower().split("?")[0].endswith(".pdf") and "html" in ctype.lower():
                logger.warning("%s/%s: .pdf URL returned HTML (soft 404) — skipping; "
                               "wayback history may still serve", inst_id, label)
                continue
            is_new = record_snapshot(conn, inst_id, label, url, resp.content, ctype)
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


def purge_error_pages(conn: sqlite3.Connection) -> int:
    """Remove already-ingested commitment rows whose stored content is an
    error page (retroactive fix for snapshots taken before the ingestion
    guard existed). Deletes the row and its on-disk file. Returns count."""
    purged = 0
    for r in conn.execute("SELECT id, content_path, content_type FROM commitments").fetchall():
        p = Path(r["content_path"])
        if not p.exists():
            continue
        if looks_like_error_page(p.read_bytes(), r["content_type"] or ""):
            conn.execute("DELETE FROM commitments WHERE id = ?", (r["id"],))
            p.unlink(missing_ok=True)
            purged += 1
    conn.commit()
    return purged


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
