"""Legacy (July 2022 - June 2023) N-PX votes from Broadridge ProxyEdge text filings.

Precision over recall. Two parsers written independently from one contract
(`legacy_pe_blocks`, `legacy_pe_lines`) read each document; only rows BOTH produce
identically over all 13 contract fields (multiset intersection) are kept, and a
filing is rejected outright when they disagree by more than `MAX_DISAGREEMENT`.
A fund's votes are attributed to a series ONLY through the filing's own SGML header
(name -> series id); anything that does not map exactly is dropped and counted.

Rows land with `legacy_format = 'proxyedge'` and `shares_voted` NULL (the format has no
share counts). They are quarantined from releases and analysis by
`ledger.NON_LEGACY_VOTE_SQL` until a human promotes them.
"""

from __future__ import annotations

import gzip
import logging
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import http
from . import legacy_pe_blocks, legacy_pe_lines
from .edgar import Filing, filing_directory

logger = logging.getLogger(__name__)

KEYS = legacy_pe_blocks.KEYS
MAX_DISAGREEMENT = 0.005
PERIOD = "2023-06-30"
CACHE_DIR = http.DATA_DIR / "legacy_cache"
REPORT_OK = "LEGACY_PROXYEDGE"
REPORT_REJECTED = "LEGACY_PROXYEDGE_REJECTED"

# Closed mapping of the document's vote words to the ledger's how_voted. Anything
# else ('None', 'Take No Action', ...) is dropped: no guess about what the XML
# format would have called it.
HOW_VOTED = {"For": "FOR", "Against": "AGAINST", "Abstain": "ABSTAIN",
             "Withheld": "WITHHOLD", "Withhold": "WITHHOLD",
             "1 Year": "1 YEAR", "2 Years": "2 YEARS", "3 Years": "3 YEARS"}
VOTE_SOURCE = {"Mgmt": "ISSUER", "Shr": "SECURITY HOLDER"}


# -- two-parser agreement ----------------------------------------------------

def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEYS)


def agreed(text: str) -> tuple[list[dict], dict]:
    """Rows both parsers produced identically (multiset intersection, in parser A's
    order) and the agreement stats."""
    rows_a = legacy_pe_blocks.parse(text)
    rows_b = legacy_pe_lines.parse(text)
    ca, cb = Counter(map(_key, rows_a)), Counter(map(_key, rows_b))
    common = ca & cb
    left = Counter(common)
    out = []
    for r in rows_a:
        k = _key(r)
        if left[k] > 0:
            left[k] -= 1
            out.append(r)
    n_agreed = sum(common.values())
    a_only, b_only = sum((ca - cb).values()), sum((cb - ca).values())
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only,
                 "disagreement_rate": (a_only + b_only) / max(1, n_agreed + a_only + b_only)}


# -- series map --------------------------------------------------------------

def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


_SGML = re.compile(r"<SERIES-ID>\s*(S\d{9})\s*\n\s*<SERIES-NAME>([^\n<]*)", re.I)
_PLAIN = re.compile(r"^\s*(S\d{9})\b[ \t]*(.*)$")


def series_map(hdr_text: str) -> dict[str, str]:
    """Normalised fund name -> series id from the filing's own header. A name that
    maps to two different series is removed (ambiguous)."""
    pairs: list[tuple[str, str]] = [(m.group(2), m.group(1)) for m in _SGML.finditer(hdr_text)]
    if not pairs:
        lines = hdr_text.splitlines()
        for i, line in enumerate(lines):
            m = _PLAIN.match(line)
            if not m or "<" in line:
                continue
            name = m.group(2).strip()
            if not name:
                nxt = next((x for x in lines[i + 1:i + 3] if x.strip()), "")
                name = "" if _PLAIN.match(nxt) else nxt
            if name.strip():
                pairs.append((name, m.group(1)))
    seen: dict[str, set[str]] = {}
    for name, sid in pairs:
        if _norm(name):
            seen.setdefault(_norm(name), set()).add(sid)
    return {n: next(iter(s)) for n, s in seen.items() if len(s) == 1}


# -- ledger rows -------------------------------------------------------------

def to_vote_rows(rows: list[dict], smap: dict[str, str]) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts, plus drop counters. Only funds named in THIS
    filing's header are kept (a combined document can carry other registrants' funds)."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"dropped_type": 0, "dropped_vote": 0, "dropped_date": 0}
    for r in rows:
        sid = smap.get(_norm(r["fund_name"]))
        if sid is None:
            unmapped[r["fund_name"]] += 1
            continue
        source = VOTE_SOURCE.get(r["proposal_type"])
        if source is None:
            info["dropped_type"] += 1
            continue
        how = HOW_VOTED.get(r["vote"])
        if how is None:
            info["dropped_vote"] += 1
            continue
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", r["meeting_date"])
        if not m:
            info["dropped_date"] += 1
            continue
        fa = r["for_against_management"]
        rec = ""
        if how in ("FOR", "AGAINST") and fa in ("For", "Against"):
            rec = how if fa == "For" else ("AGAINST" if how == "FOR" else "FOR")
        out.append({
            "issuer_name": r["issuer_name"], "cusip": r["security_id"], "isin": r["isin"],
            "meeting_date": f"{m.group(2)}/{m.group(3)}/{m.group(1)}",
            "vote_description": r["proposal_text"], "category_type": "",
            "vote_source": source, "shares_on_loan": None, "vote_series": sid,
            "how_voted": how, "shares_voted": None, "management_recommendation": rec,
            "legacy_format": "proxyedge", "for_against_management": fa,
        })
    info["funds_unmapped"] = dict(unmapped)
    return out, info


_INSERT = """INSERT INTO votes
    (accession, issuer_name, cusip, isin, meeting_date, vote_description, category_type,
     vote_source, shares_on_loan, vote_series, how_voted, shares_voted,
     management_recommendation, legacy_format, for_against_management)
    VALUES (:accession,:issuer_name,:cusip,:isin,:meeting_date,:vote_description,
            :category_type,:vote_source,:shares_on_loan,:vote_series,:how_voted,
            :shares_voted,:management_recommendation,:legacy_format,
            :for_against_management)"""


def is_candidate(filing: Filing) -> bool:
    return filing.form_type in ("N-PX", "N-PX/A") and filing.period_of_report == PERIOD


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str) -> int:
    """Parse every vote document of one filing, gate it, record it. One transaction
    (no network inside). Returns votes inserted."""
    smap = series_map(hdr_text)
    parsed = []
    for name, text in sorted(docs.items()):
        if "Agenda Number:" not in text:
            continue
        rows, st = agreed(text)
        votes, info = to_vote_rows(rows, smap)
        parsed.append((name, text.count("Agenda Number:"), st, votes, info))
    return record_filing(conn, filing, institution_id, today, parsed, REPORT_OK,
                         REPORT_REJECTED)


def record_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, parsed: list, report_ok: str, report_rejected: str) -> int:
    """Gate the parsed documents and write the filing, its votes and its parse stats in
    one transaction. `parsed` = [(document, meetings, agreement stats, vote dicts, info)].
    Shared by every legacy text format (ProxyEdge, ISS). Returns votes inserted."""
    worst = max((p[2]["disagreement_rate"] for p in parsed), default=0.0)
    total_agreed = sum(p[2]["agreed"] for p in parsed)
    accepted = bool(parsed) and worst <= MAX_DISAGREEMENT and total_agreed > 0

    acc = filing.accession_number
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        conn.execute("DELETE FROM legacy_parse WHERE accession = ?", (acc,))
        prior = conn.execute("SELECT report_type FROM filings WHERE accession = ?",
                             (acc,)).fetchone()
        if prior:
            conn.execute("DELETE FROM votes WHERE accession = ? AND legacy_format IS NOT NULL",
                         (acc,))
            conn.execute("DELETE FROM filings WHERE accession = ?", (acc,))
        conn.execute(
            """INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                                    period_of_report, report_type, source_url, retrieval_date)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (acc, filing.cik, institution_id, filing.form_type, filing.filing_date,
             filing.period_of_report, report_ok if accepted else report_rejected,
             filing.directory_url, today))
        inserted = 0
        for name, meetings, st, votes, info in parsed:
            n = 0
            if accepted:
                conn.executemany(_INSERT, [{**v, "accession": acc} for v in votes])
                n = len(votes)
            inserted += n
            conn.execute(
                """INSERT INTO legacy_parse (accession, document, meetings, rows_a, rows_b,
                       agreed, a_only, b_only, disagreement_rate, funds_unmapped,
                       rows_inserted, parsed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (acc, name, meetings, st["rows_a"], st["rows_b"], st["agreed"], st["a_only"],
                 st["b_only"], st["disagreement_rate"],
                 repr(sorted(info["funds_unmapped"].items())) if info["funds_unmapped"]
                 else "", n, now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return inserted


# -- fetching (local cache first; honest UA via http) --------------------------

def list_documents(filing: Filing) -> list[str]:
    """Names of the filing's documents: not the full-submission .txt, not index/header pages."""
    names = []
    for item in filing_directory(filing):
        name = item.get("name", "")
        low = name.lower()
        if not low.endswith((".txt", ".htm", ".html")):
            continue
        if low == f"{filing.accession_number}.txt" or "index" in low or "header" in low:
            continue
        if "primary_doc" in low or "xslform" in low:
            continue
        names.append(name)
    return names


def load_filing_texts(filing: Filing, cache_dir: Path | None = None
                      ) -> tuple[dict[str, str], str]:
    """({document name: text}, header text). Reads data/legacy_cache/<accession>/ when
    present; otherwise fetches (and caches gzip)."""
    d = (cache_dir or CACHE_DIR) / filing.accession_number
    acc = filing.accession_number
    cached = sorted(p for p in d.glob("*.gz")) if d.is_dir() else []
    docs: dict[str, str] = {}
    if cached:
        for p in cached:
            docs[p.name[:-3]] = gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
    else:
        for name in list_documents(filing):
            raw = http.get(f"{filing.directory_url}/{name}").content
            docs[name] = raw.decode("utf-8", "replace")
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.gz").write_bytes(gzip.compress(raw))
    hp = d / f"{acc}.hdr.sgml"
    if hp.exists():
        hdr = hp.read_text("utf-8", "replace")
    else:
        hdr = http.get(f"{filing.directory_url}/{acc}.hdr.sgml").text
        d.mkdir(parents=True, exist_ok=True)
        hp.write_text(hdr)
    return docs, hdr


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int:
    """Fetch (network/cache, no write lock held) then ingest one filing."""
    docs, hdr = load_filing_texts(filing)
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr)
    logger.info("ingested LEGACY_PROXYEDGE %s: %d votes", filing.accession_number, n)
    return n
