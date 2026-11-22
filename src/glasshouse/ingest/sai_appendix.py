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
import statistics
from datetime import date

from .. import http
from ..contradictions import IDENTITY_VERSION, identity_hash_from_file
from . import commitments as cm
from . import edgar

logger = logging.getLogger(__name__)

VIA = "edgar-sai"


# Bump when extraction/normalisation changes: every SAI version of a label is then
# rebuilt from EDGAR; the old rows are marked superseded, never deleted.
EXTRACTION_VERSION = 5

_SPACE_BEFORE_PUNCT = re.compile(r" +([.,;:])")
# A printed page number: a 1-3 digit token straight after a sentence end and before a
# capitalised word, or ending the section. Opt-in per document (`strip_page_numbers`).
_PAGE_NUMBER = re.compile(r"(?<=[.!?\u201d\"\u2019)]) \d{1,3}(?= [A-Z])| \d{1,3}$")


# A standalone 2-3 digit number: not part of a figure ("$150", "75%", "1,200"), an entity ("&#216;"), a citation
# ("162(m)") or a range. Page furniture is one run of CONSECUTIVE such numbers (the SAI's own page number at every
# page foot, sometimes between two words of a sentence), so only a long run is removed; a real number is never
# removed on its own. Opt-in per document (`page_sequence`).
_SEQ_NUMBER = re.compile(r"(?<![\w$#&.,%/(-])(\d{2,3})(?=\s|$)(?![-/%])")
PAGE_RUN_MIN = 8


def strip_page_sequence(text: str, min_run: int = PAGE_RUN_MIN) -> str:
    """`text` without its longest run of consecutive page numbers (each the previous plus one, in reading
    order), provided the run has at least `min_run` members. Where a real number equals the next page number
    the mark at the page foot (the LATER one) is the page number, so the real one stays."""
    cands = [(m.start(), m.end(), int(m.group(1))) for m in _SEQ_NUMBER.finditer(text)]
    n = len(cands)
    if n < min_run:
        return text
    run, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if cands[j][2] + 1 == cands[i][2] and run[j] + 1 >= run[i]:
                run[i], prev[i] = run[j] + 1, j
    end = max(range(n), key=lambda k: (run[k], -k))
    if run[end] < min_run:
        return text
    chain = []
    while end != -1:
        chain.append(end)
        end = prev[end]
    for k in sorted(chain, reverse=True):
        a, b, _ = cands[k]
        text = text[:a] + " " + text[b:]
    return re.sub(r"\s+", " ", text).strip()


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


def extract_section(text: str, start: str | list[str], end: str | list[str],
                    allow_identical_copies: bool = False,
                    strip_page_numbers: bool = False,
                    strip_patterns: list[str] | None = None,
                    page_sequence: bool = False) -> str | None:
    """The normalised text from `start` up to (not including) the first `end`
    that follows it, or None when it cannot be extracted without guessing.
    `end` may list alternatives (editions differ in what follows the policy);
    the earliest one after the start wins.

    A multi-fund filing can print the same appendix once per SAI. With
    `allow_identical_copies` several start markers are accepted ONLY if every
    copy extracts to exactly the same text; any disagreement gives None.

    `strip_patterns` (opt-in regexes) delete running page furniture that carries
    the SAI's own date (Columbia: "Statement of Additional Information - March 1,
    2023 B-2"), which would otherwise make every filing a new "edition"."""
    text = normalise(text)
    heads = [normalise(h) for h in ([start] if isinstance(start, str) else start)]
    ends = [normalise(e) for e in ([end] if isinstance(end, str) else end)]
    if not heads or not all(heads) or not all(ends):
        return None
    # `start` may list alternative headings (editions retitle the exhibit); every
    # occurrence of any of them counts, so two headings in one filing is ambiguity.
    starts = sorted((i, len(h)) for h in heads for i in _all_positions(text, h))
    if not starts or (len(starts) > 1 and not allow_identical_copies):
        return None
    sections = set()
    for s, hlen in starts:
        found = [e for e in (text.find(m, s + hlen) for m in ends) if e != -1]
        if not found:
            return None
        sec = text[s:min(found)].strip()
        for pat in strip_patterns or []:
            sec = re.sub(r"\s+", " ", re.sub(pat, " ", sec)).strip()
        if strip_page_numbers:
            sec = _PAGE_NUMBER.sub("", sec).strip()
        if page_sequence:
            sec = strip_page_sequence(sec)
        sections.add(sec)
    if len(sections) > 1:
        # Embedded copies of one appendix can differ only in typography: a
        # non-breaking hyphen (U+2011) in one copy, an ASCII hyphen in the other.
        # Same wording, so fold it; any other difference still refuses.
        sections = {sec.replace("\u2011", "-") for sec in sections}
    return sections.pop() if len(sections) == 1 else None


def supersede_label(conn: sqlite3.Connection, institution_id: str, doc_label: str) -> int:
    """Mark this label's live edgar-sai rows superseded so a changed extraction
    can rebuild them. NOTHING is deleted: a commitment id, once published, must
    never later point at different text (the table has no AUTOINCREMENT, so a
    deleted top row's id would be reused). Only via='edgar-sai' rows are touched;
    website captures and Wayback lineages never are."""
    cur = conn.execute("UPDATE commitments SET superseded=1 WHERE institution_id=? "
                       "AND doc_label=? AND via=? AND superseded=0",
                       (institution_id, doc_label, VIA))
    conn.commit()
    return cur.rowcount


def record_version(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                   url: str, section: str, filing_date: str,
                   retrieval_date: str | None = None) -> bool:
    """Store one extracted section. True when a row was added, revived or moved
    to an earlier filing; False when the text is already on file from this or an
    earlier filing. A row's url and stored text file always refer to the SAME
    filing, so re-extracting the cited url reproduces its text."""
    data = section.encode()
    sha = hashlib.sha256(data).hexdigest()   # file custody: the stored text file
    # Version identity ignores ALL whitespace: HTML inline tags leave spacing
    # artefacts ("Issuer -specific", '" excessive "') that are not edits.
    text_sha = hashlib.sha256("".join(section.split()).encode()).hexdigest()
    live = conn.execute(
        "SELECT MIN(public_by) FROM commitments WHERE institution_id=? AND doc_label=? "
        "AND text_sha256=? AND superseded=0", (institution_id, doc_label, text_sha)).fetchone()[0]
    if live is not None and live <= filing_date:
        return False   # this text is already on file from this or an earlier filing
    same_bytes = conn.execute(
        "SELECT id FROM commitments WHERE institution_id=? AND doc_label=? AND sha256=? "
        "AND wayback_timestamp=''", (institution_id, doc_label, sha)).fetchone()
    if same_bytes:
        # The stored file IS this filing's text (identical bytes), so the row may be
        # revived or moved to cite this filing: url and file stay consistent.
        conn.execute("UPDATE commitments SET superseded=0, public_by=?, url=? WHERE id=?",
                     (filing_date, url, same_bytes["id"]))
        conn.commit()
        return True
    # New text, or the same text from an EARLIER filing whose own bytes differ
    # (whitespace): a row of its own, citing and storing that filing. The engine
    # dedupes by text identity and takes the earliest.
    dest = cm.COMMITMENTS_DIR / institution_id / f"{doc_label}__{filing_date}__{sha[:8]}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    conn.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256, "
        "content_path, content_type, size_bytes, wayback_timestamp, text_sha256, "
        "public_by, via, identity_sha256, identity_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (institution_id, doc_label, url, retrieval_date or date.today().isoformat(), sha,
         str(dest), "text/plain", len(data), "", text_sha, filing_date, VIA,
         identity_hash_from_file(institution_id, doc_label, dest), IDENTITY_VERSION))
    conn.commit()
    return True


OUTLIER_FACTOR = 3


def ingest_filings(conn: sqlite3.Connection, institution_id: str, doc_label: str,
                   filings: list[dict], start: str | list[str], end: str | list[str],
                   allow_identical_copies: bool = False,
                   strip_page_numbers: bool = False,
                   flagged: list[str] | None = None,
                   strip_patterns: list[str] | None = None,
                   page_sequence: bool = False,
                   accepted_outliers: list[dict] | None = None) -> int:
    """Extract and record each filing ({accession, filing_date, url, text} or
    a pre-extracted `section`), oldest first. Returns rows added or moved.

    Length guard: a section more than OUTLIER_FACTOR times longer or shorter
    than the label's median (rows on file plus this batch) is logged and not
    recorded: it is almost certainly a different document (Wellington's 2023 SAI
    printed the voting guidelines too), and diffing it against its neighbours
    would report hundreds of sentences "removed". An edition a human has checked and listed in
    the label's `accepted_outliers` (config: {accession, sha256}, with a note) is recorded
    anyway, logged and written as an 'accepted_outlier' capture attempt. The sha256 is the
    version identity of the reviewed section (`commitments.text_sha256`: sha256 of the text
    with all whitespace removed), so a changed section under the same accession is not
    accepted; a bare accession string is never accepted."""
    accepted = {(str(a.get("accession")), str(a.get("sha256")))
                for a in accepted_outliers or [] if isinstance(a, dict)}
    cands = []
    for f in sorted(filings, key=lambda f: (f["filing_date"], f["accession"])):
        section = f.get("section")
        if section is None:
            section = extract_section(f["text"], start, end, allow_identical_copies,
                                      strip_page_numbers, strip_patterns, page_sequence)
        if section is None:
            logger.info("%s/%s: no clean section in %s (%s); nothing recorded",
                        institution_id, doc_label, f["accession"], f["url"])
            continue
        cands.append((f, section))
    sizes = [r[0] for r in conn.execute(
        "SELECT size_bytes FROM commitments WHERE institution_id=? AND doc_label=? "
        "AND via=? AND superseded=0", (institution_id, doc_label, VIA))]
    sizes += [len(sec.encode()) for _, sec in cands]
    median = statistics.median(sizes) if sizes else 0
    n = 0
    for f, section in cands:
        size = len(section.encode())
        outlier = bool(median) and (size > OUTLIER_FACTOR * median
                                    or size * OUTLIER_FACTOR < median)
        text_sha = hashlib.sha256("".join(section.split()).encode()).hexdigest()
        if outlier and (f["accession"], text_sha) in accepted:
            logger.warning("%s/%s: length outlier %d bytes vs median %.0f in %s accepted "
                           "(reviewed, listed in accepted_outliers)", institution_id,
                           doc_label, size, median, f["accession"])
            cm.log_attempt(conn, institution_id, doc_label, f["url"], "accepted_outlier",
                           f"{f['accession']} sha256 {text_sha}: {size} bytes vs median {median:.0f}")
        elif outlier:
            detail = f"length outlier: {size} bytes vs median {median:.0f}"
            logger.warning("%s/%s: %s in %s (%s); NOT recorded, needs a human look "
                           "(a genuine rewrite would be skipped otherwise)",
                           institution_id, doc_label, detail, f["accession"], f["url"])
            # Not 'unchanged': the doctor reports it until a later read is clean.
            cm.log_attempt(conn, institution_id, doc_label, f["url"], "needs_review", detail)
            if flagged is not None:
                flagged.append(f["url"])
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
                found.sort(key=lambda f: (f.filing_date, f.accession_number))
                copies = bool(cfg.get("allow_identical_copies"))
                pages = bool(cfg.get("strip_page_numbers"))
                patterns = [str(p) for p in cfg.get("strip_patterns") or []]
                sequence = bool(cfg.get("page_sequence"))
                # A filing is immutable: skip those already read under THESE settings
                # (changing them re-reads everything).
                # strip_patterns joins the signature only when set, so every existing
                # label keeps its signature (and is not re-read).
                sig = hashlib.sha256(json.dumps(
                    [EXTRACTION_VERSION, cfg["start"], cfg["end"], copies, pages]
                    + ([patterns] if patterns else []) + (["page_sequence"] if sequence else [])).encode()
                ).hexdigest()[:16]
                have = {r[0] for r in conn.execute(
                    "SELECT url FROM capture_attempts WHERE institution_id=? AND doc_label=? "
                    "AND outcome='unchanged' AND detail=?", (inst_id, label, "sai-read:" + sig))}
                if not have:
                    # Never read under THESE settings: rows from an older
                    # extraction are stale. Supersede (never delete) and rebuild.
                    old = supersede_label(conn, inst_id, label)
                    if old:
                        logger.info("%s/%s: settings changed, superseded %d SAI row(s)",
                                    inst_id, label, old)
                batch, urls = [], []
                for f in found:
                    url = f"{f.directory_url}/{f.primary_document}"
                    if url in have:
                        continue
                    try:
                        raw = http.get(url, timeout=180).content.decode("utf-8", "replace")
                    except Exception as exc:
                        logger.warning("%s/%s: fetch failed %s: %s", inst_id, label, url, exc)
                        continue
                    # Keep only the extracted section (or None), not the 2-5 MB page.
                    batch.append({"accession": f.accession_number, "filing_date": f.filing_date,
                                  "url": url,
                                  "section": extract_section(cm.html_to_text(raw), cfg["start"],
                                                             cfg["end"], copies, pages, patterns, sequence)})
                    urls.append(url)
                flagged: list[str] = []
                n = ingest_filings(conn, inst_id, label,
                                   [b for b in batch if b["section"] is not None],
                                   cfg["start"], cfg["end"], copies, pages, flagged, patterns, sequence,
                                   accepted_outliers=[a for a in cfg.get("accepted_outliers") or []
                                                      if isinstance(a, dict)])
                for b in batch:
                    if b["section"] is None:
                        logger.info("%s/%s: no clean section in %s (%s); nothing recorded",
                                    inst_id, label, b["accession"], b["url"])
                for url in urls:
                    if url in flagged:
                        continue   # already logged as needs_review: read again next run
                    cm.log_attempt(conn, inst_id, label, url, "unchanged", "sai-read:" + sig)
            except Exception as exc:
                logger.warning("%s/%s: SAI listing failed: %s", inst_id, label, exc)
                cm.log_attempt(conn, inst_id, label, listing, "failed", f"sai listing failed: {exc}")
                continue
            cm.log_attempt(conn, inst_id, label, listing, "new_version" if n else "unchanged")
            out[f"{inst_id}/{label}"] = n
            logger.info("%s/%s: %d SAI version(s) added", inst_id, label, n)
    return out
