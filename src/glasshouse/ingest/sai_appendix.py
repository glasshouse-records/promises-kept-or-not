"""Policy text printed in a fund's SAI on EDGAR, dated by the filing date.

Some managers (Geode, Wellington) have no Wayback history for their own policy
page, but the funds they sub-advise reproduce the policy in an SAI appendix
(form 485BPOS / 497). An EDGAR filing date is a public, immutable timestamp: the
text was public by that day. This module extracts that one section from each
filing and records it as a policy version under its OWN doc_label (never the
website PDF's: different formatting would invent alternating versions).

Configured under a commitments entry in config/institutions.yaml:

    - label: geode-voting-policies-as-printed-in-sai
      adviser_key: GEODE
      sai_appendix: {cik: "0000819118", forms: ["485BPOS"], since: "2023-01-01",
                     start: "<heading opening the policy>", end: "<heading after it>"}

Precision over recall: if the start marker is not found exactly once (or the end
marker never follows it) the filing contributes NOTHING. Version identity is the
sha256 of the section text with all whitespace removed; identical text across filings
is one version, dated by the EARLIEST filing. `public_by` is that filing date: it
proves the text was public, not when the manager wrote it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

from .. import http
from . import commitments as cm
from . import edgar

logger = logging.getLogger(__name__)

VIA = "edgar-sai"


# Bump when extraction/normalisation changes: every SAI version of a label is then
# rebuilt from EDGAR (the rows are fully derived from public filings).
EXTRACTION_VERSION = 3

_SPACE_BEFORE_PUNCT = re.compile(r" +([.,;:])")
# A printed page number: a 1-3 digit token straight after a sentence end and before a
# capitalised word, or ending the section. Opt-in per document (`strip_page_numbers`).
_PAGE_NUMBER = re.compile(r"(?<=[.!?\u201d\"\u2019)]) \d{1,3}(?= [A-Z])| \d{1,3}$")


def normalise(text: str) -> str:
    """Whitespace collapsed, and the space HTML conversion leaves before a
    punctuation mark removed ("1 . Attendance" == "1. Attendance")."""
    return _SPACE_BEFORE_PUNCT.sub(r"\1", re.sub(r"\s+", " ", text).strip())


def _all_positions(hay: str, needle: str) -> list[int]:
    out, i = [], hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def extract_section(text: str, start: str, end: str,
                    allow_identical_copies: bool = False,
                    strip_page_numbers: bool = False) -> str | None:
    """The normalised text from `start` up to (not including) the first `end`
    that follows it, or None when it cannot be extracted without guessing.

    A multi-fund filing can print the same appendix once per SAI. With
    `allow_identical_copies` several start markers are accepted ONLY if every
    copy extracts to exactly the same text; any disagreement gives None."""
    text, start, end = normalise(text), normalise(start), normalise(end)
    if not start or not end:
        return None
    starts = _all_positions(text, start)
    if not starts or (len(starts) > 1 and not allow_identical_copies):
        return None
    sections = set()
    for s in starts:
        e = text.find(end, s + len(start))
        if e == -1:
            return None
        sec = text[s:e].strip()
        if strip_page_numbers:
            sec = _PAGE_NUMBER.sub("", sec).strip()
        sections.add(sec)
    return sections.pop() if len(sections) == 1 else None


def purge_label(conn: sqlite3.Connection, institution_id: str, doc_label: str) -> int:
    """Drop this label's edgar-sai rows (and their text files) so a changed
    extraction rebuilds them from EDGAR. Only via='edgar-sai' rows are ever
    touched: website captures and Wayback lineages are never affected."""
    rows = conn.execute("SELECT id, content_path FROM commitments WHERE institution_id=? "
                        "AND doc_label=? AND via=?", (institution_id, doc_label, VIA)).fetchall()
    for r in rows:
        conn.execute("DELETE FROM commitments WHERE id=?", (r["id"],))
        Path(r["content_path"]).unlink(missing_ok=True)
    conn.commit()
    return len(rows)


def record_version(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                   url: str, section: str, filing_date: str,
                   retrieval_date: str | None = None) -> bool:
    """Store one extracted section. True when it is a new version (or moved an
    existing version to an earlier filing date); False when already on file."""
    data = section.encode()
    sha = hashlib.sha256(data).hexdigest()   # file custody: the stored text file
    # Version identity ignores ALL whitespace: HTML inline tags leave spacing
    # artefacts ("Issuer -specific", '" excessive "') that are not edits.
    text_sha = hashlib.sha256("".join(section.split()).encode()).hexdigest()
    row = conn.execute(
        "SELECT id, public_by FROM commitments WHERE institution_id=? AND doc_label=? "
        "AND text_sha256=?", (institution_id, doc_label, text_sha)).fetchone()
    if row:
        if filing_date < row["public_by"]:
            # EDGAR lists newest first, and an earlier filing may only turn up
            # on a later run: the version's date is the earliest filing's.
            conn.execute("UPDATE commitments SET public_by=?, url=? WHERE id=?",
                         (filing_date, url, row["id"]))
            conn.commit()
            return True
        return False
    dest = cm.COMMITMENTS_DIR / institution_id / f"{doc_label}__{filing_date}__{sha[:8]}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256, "
        "content_path, content_type, size_bytes, wayback_timestamp, text_sha256, "
        "public_by, via) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (institution_id, doc_label, url, retrieval_date or date.today().isoformat(), sha,
         str(dest), "text/plain", len(data), "", text_sha, filing_date, VIA))
    conn.commit()
    return True


def ingest_filings(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                   filings: list[dict], start: str, end: str,
                   allow_identical_copies: bool = False,
                   strip_page_numbers: bool = False) -> int:
    """Extract and record each filing ({accession, filing_date, url, text}),
    oldest first. Returns the number of versions added or back-dated."""
    n = 0
    for f in sorted(filings, key=lambda f: (f["filing_date"], f["accession"])):
        section = extract_section(f["text"], start, end, allow_identical_copies,
                                  strip_page_numbers)
        if section is None:
            logger.info("%s/%s: no clean section in %s (%s); nothing recorded",
                        institution_id, doc_label, f["accession"], f["url"])
            continue
        n += record_version(conn, institution_id, doc_label, f["url"], section,
                            f["filing_date"])
    return n


def fetch_sai_appendices(conn: sqlite3.Connection, institutions: dict[str, dict]) -> dict[str, int]:
    """Live: every configured `sai_appendix` document. {inst/label: versions added}."""
    out: dict[str, int] = {}
    for inst_id, inst in institutions.items():
        for doc in inst.get("commitments") or []:
            cfg = doc.get("sai_appendix")
            if not cfg:
                continue
            label = doc["label"]
            listing = f"https://data.sec.gov/submissions/CIK{str(cfg['cik']).zfill(10)}.json"
            try:
                found = [f for f in edgar.list_filings(str(cfg["cik"]), cfg.get("forms", ["485BPOS"]))
                         if f.filing_date >= str(cfg.get("since", "2023-01-01")) and f.primary_document]
                # A filing is immutable: skip those already read under THESE markers
                # (changing the markers re-reads everything).
                sig = hashlib.sha256(json.dumps(
                    [EXTRACTION_VERSION, cfg["start"], cfg["end"],
                     bool(cfg.get("allow_identical_copies")), bool(cfg.get("strip_page_numbers"))]
                ).encode()).hexdigest()[:16]
                have = {r[0] for r in conn.execute(
                    "SELECT url FROM capture_attempts WHERE institution_id=? AND doc_label=? "
                    "AND outcome='unchanged' AND detail=?", (inst_id, label, "sai-read:" + sig))}
                if not have:
                    # Never read under THESE settings: rows from an older
                    # extraction are stale, rebuild them from the filings.
                    purged = purge_label(conn, inst_id, label)
                    if purged:
                        logger.info("%s/%s: rebuilt, dropped %d stale SAI row(s)",
                                    inst_id, label, purged)
                n = 0
                for f in found:
                    url = f"{f.directory_url}/{f.primary_document}"
                    if url in have:
                        continue
                    try:
                        raw = http.get(url, timeout=180).content.decode("utf-8", "replace")
                    except Exception as exc:
                        logger.warning("%s/%s: fetch failed %s: %s", inst_id, label, url, exc)
                        continue
                    n += ingest_filings(
                        conn, inst_id, label,
                        [{"accession": f.accession_number, "filing_date": f.filing_date,
                          "url": url, "text": cm.html_to_text(raw)}],
                        cfg["start"], cfg["end"], bool(cfg.get("allow_identical_copies")),
                        bool(cfg.get("strip_page_numbers")))
                    # Commit per iteration, never across a network wait.
                    cm.log_attempt(conn, inst_id, label, url, "unchanged", "sai-read:" + sig)
            except Exception as exc:
                logger.warning("%s/%s: SAI listing failed: %s", inst_id, label, exc)
                cm.log_attempt(conn, inst_id, label, listing, "failed", f"sai listing failed: {exc}")
                continue
            cm.log_attempt(conn, inst_id, label, listing, "new_version" if n else "unchanged")
            out[f"{inst_id}/{label}"] = n
            logger.info("%s/%s: %d SAI version(s) added", inst_id, label, n)
    return out
