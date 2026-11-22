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


# -- precision guards (shared with legacy_iss) -------------------------------

_MEETING_FIELDS = ("fund_name", "fund_heading", "issuer_name", "meeting_date",
                   "security_id", "ticker")


def meeting_key(row: dict) -> tuple:
    """Fund heading, issuer, meeting date and security id/ticker, where the row has them."""
    return tuple(row[f] for f in _MEETING_FIELDS if f in row)


def _issuer_sort_key(name: str) -> str:
    """First alphanumeric character, casefolded. ISS's collation of punctuation is not
    reproducible (real order: E-GUARDIAN, E.ON SE, E-J HOLDINGS; stripping punctuation
    still gives eon > ej), so only a drop to an earlier initial counts as a reset."""
    return next((c for c in name.casefold() if c.isalnum()), "")


def drop_disputed_meetings(out: list[dict], disputed_rows: list[dict]) -> tuple[list[dict], dict]:
    """Any meeting with a row only one parser produced loses ALL its agreed rows."""
    bad = {meeting_key(r) for r in disputed_rows}
    kept = [r for r in out if meeting_key(r) not in bad]
    return kept, {"meetings_dropped_disputed": len(bad),
                  "rows_dropped_disputed": len(out) - len(kept)}


def order_guard(rows: list[dict], fund_field: str) -> tuple[list[dict], dict]:
    """Within a fund section meetings are listed in alphabetical issuer order. A later
    issuer that sorts before the previous one (a reset) may mean a missed fund boundary:
    drop the section from the reset to its end, unless that tail exactly repeats an
    earlier run of the same section (an as-filed repeat, kept)."""
    sections: list[list[dict]] = []
    for r in rows:
        if sections and sections[-1][0][fund_field] == r[fund_field]:
            sections[-1].append(r)
        else:
            sections.append([r])
    kept: list[dict] = []
    resets = repeats = dropped = 0
    for sec in sections:
        meetings: list[tuple] = []   # (meeting key, issuer, first row index)
        for i, r in enumerate(sec):
            mk = meeting_key(r)
            if not meetings or meetings[-1][0] != mk:
                meetings.append((mk, r["issuer_name"], i))
        cut = None
        for m in range(1, len(meetings)):
            if _issuer_sort_key(meetings[m][1]) < _issuer_sort_key(meetings[m - 1][1]):
                resets += 1
                tail = [x[0] for x in meetings[m:]]
                head = [x[0] for x in meetings[:m]]
                if any(head[j:j + len(tail)] == tail for j in range(len(head) - len(tail) + 1)):
                    repeats += 1
                else:
                    cut = meetings[m][2]
                break
        if cut is None:
            kept.extend(sec)
        else:
            kept.extend(sec[:cut])
            dropped += len(sec) - cut
    if resets:
        logger.info("order guard: resets=%d repeats=%d rows_dropped=%d", resets, repeats, dropped)
    return kept, {"order_resets": resets, "order_repeats": repeats, "rows_dropped_order": dropped}


def guarded(out: list[dict], rows_a: list[dict], rows_b: list[dict], ca: Counter,
            cb: Counter, fund_field: str, keyfn=None) -> tuple[list[dict], dict]:
    """Both guards over the multiset-intersection rows; returns rows and the new stats."""
    keyfn = keyfn or _key
    by_key = {keyfn(r): r for r in rows_b} | {keyfn(r): r for r in rows_a}
    disputed = [by_key[k] for k in [*(ca - cb), *(cb - ca)]]
    out, s1 = drop_disputed_meetings(out, disputed)
    out, s2 = order_guard(out, fund_field)
    st = {**s1, **s2}
    if s1["meetings_dropped_disputed"]:
        logger.info("disputed meetings dropped=%d rows=%d", s1["meetings_dropped_disputed"],
                    s1["rows_dropped_disputed"])
    return out, st


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
    out, guard_stats = guarded(out, rows_a, rows_b, ca, cb, "fund_name")
    return out, {"rows_a": len(rows_a), "rows_b": len(rows_b), "agreed": n_agreed,
                 "a_only": a_only, "b_only": b_only,
                 "disagreement_rate": (a_only + b_only) / max(1, n_agreed + a_only + b_only),
                 **guard_stats}


# -- series map --------------------------------------------------------------

_MARKS = re.compile(r"\((?:R|SM|TM)\)|[\u00ae\u2122\u2120]")


def _norm(name: str) -> str:
    """Printed fund name -> comparison key: trademark marks removed ("(R)", "(SM)", "(TM)"
    as printed, and the characters), whitespace collapsed, casefolded. Nothing else."""
    return " ".join(_MARKS.sub(" ", name).split()).casefold()


_SGML = re.compile(r"<SERIES-ID>\s*(S\d{9})\s*\n\s*<SERIES-NAME>([^\n<]*)", re.I)
_PLAIN = re.compile(r"^\s*(S\d{9})\b[ \t]*(.*)$")


def _header_pairs(hdr_text: str) -> list[tuple[str, str]]:
    """(printed series name, series id) pairs from the filing's own header."""
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
    return pairs


def header_series_ids(hdr_text: str) -> set[str]:
    """Every series id the filing's own header lists (named or not)."""
    ids = {m.group(1) for m in re.finditer(r"<SERIES-ID>\s*(S\d{9})", hdr_text, re.I)}
    return ids or {sid for _, sid in _header_pairs(hdr_text)}


def series_map(hdr_text: str) -> dict[str, str]:
    """Normalised fund name -> series id from the filing's own header. A name that
    maps to two different series is removed (ambiguous)."""
    pairs = _header_pairs(hdr_text)
    seen: dict[str, set[str]] = {}
    for name, sid in pairs:
        if _norm(name):
            seen.setdefault(_norm(name), set()).add(sid)
    return {n: next(iter(s)) for n, s in seen.items() if len(s) == 1}


# -- reviewed alias file -----------------------------------------------------

ALIAS_PATH = Path(__file__).resolve().parents[3] / "config" / "legacy_series_aliases.csv"


def _cik10(cik: object) -> str:
    return str(cik).strip().zfill(10)


def _heading(heading: str) -> str:
    return " ".join(heading.split())


def load_aliases(path: Path | None = None) -> dict[tuple[str, str], str]:
    """Reviewed (registrant CIK, heading as printed) -> series id. Raises on a duplicate
    key with different series ids. A missing file is an empty alias set."""
    import csv
    p = path or ALIAS_PATH
    if not p.exists():
        return {}
    out: dict[tuple[str, str], str] = {}
    with p.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (_cik10(row["registrant_cik"]), _heading(row["heading"]))
            sid = row["series_id"].strip()
            if out.get(key, sid) != sid:
                raise ValueError(f"conflicting alias for {key}: {out[key]} vs {sid}")
            out[key] = sid
    return out


def filing_aliases(aliases: dict[tuple[str, str], str] | None, cik: object) -> dict[str, str]:
    """The aliases that apply to one filing: heading -> series id for its registrant CIK."""
    c = _cik10(cik)
    return {h: sid for (k, h), sid in (aliases or {}).items() if k == c}


def alias_series(heading: str, aliases: dict[str, str] | None,
                 header_sids: set[str] | None) -> tuple[str | None, bool]:
    """(series id, alias_not_in_header). An alias counts only if its series is in this
    filing's own header."""
    sid = (aliases or {}).get(_heading(heading))
    if sid is None:
        return None, False
    if sid in (header_sids or set()):
        return sid, False
    return None, True


# -- ledger rows -------------------------------------------------------------

def to_vote_rows(rows: list[dict], smap: dict[str, str],
                 aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None) -> tuple[list[dict], dict]:
    """Agreed rows -> ledger vote dicts, plus drop counters. Only funds named in THIS
    filing's header are kept (a combined document can carry other registrants' funds)."""
    out: list[dict] = []
    unmapped: Counter = Counter()
    info = {"dropped_type": 0, "dropped_vote": 0, "dropped_date": 0,
            "alias_not_in_header": 0}
    for r in rows:
        sid = smap.get(_norm(r["fund_name"]))
        if sid is None:
            sid, bad = alias_series(r["fund_name"], aliases, header_sids)
            info["alias_not_in_header"] += bad
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
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None) -> int:
    """Parse every vote document of one filing, gate it, record it. One transaction
    (no network inside). Returns votes inserted."""
    smap = series_map(hdr_text)
    fa, sids = filing_aliases(aliases, filing.cik), header_series_ids(hdr_text)
    parsed = []
    for name, text in sorted(docs.items()):
        if "Agenda Number:" not in text:
            continue
        rows, st = agreed(text)
        votes, info = to_vote_rows(rows, smap, fa, sids)
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


COMPLETE_MARKER = ".complete"


def _read_cache(d: Path, acc: str) -> tuple[dict[str, str], str]:
    docs = {p.name[:-3]: gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
            for p in sorted(d.glob("*.gz"))}
    return docs, (d / f"{acc}.hdr.sgml").read_text("utf-8", "replace")


def load_filing_texts(filing: Filing, cache_dir: Path | None = None
                      ) -> tuple[dict[str, str], str]:
    """({document name: text}, header text). Reads data/legacy_cache/<accession>/ only when
    it is known complete; otherwise fetches (and caches gzip). A folder is complete when
    it holds the `.complete` marker, written after every document and the header are saved.
    A folder without the marker (older caches, or an interrupted download) is trusted only
    if it has the header and exactly as many documents as the filing's listing; the
    listing is fetched to check (honest UA, no document downloads). Else it is re-fetched."""
    d = (cache_dir or CACHE_DIR) / filing.accession_number
    acc = filing.accession_number
    marker, hp = d / COMPLETE_MARKER, d / f"{acc}.hdr.sgml"
    if marker.exists():
        return _read_cache(d, acc)
    names = list_documents(filing)
    if d.is_dir() and hp.exists() and len(list(d.glob("*.gz"))) == len(names) and \
            {p.name[:-3] for p in d.glob("*.gz")} == set(names):
        marker.write_text("")           # an older, complete cache: adopt it
        return _read_cache(d, acc)
    d.mkdir(parents=True, exist_ok=True)
    for p in d.glob("*.gz"):            # stale partial files never mix with a fresh fetch
        p.unlink()
    docs: dict[str, str] = {}
    for name in names:
        raw = http.get(f"{filing.directory_url}/{name}").content
        docs[name] = raw.decode("utf-8", "replace")
        (d / f"{name}.gz").write_bytes(gzip.compress(raw))
    hdr = http.get(f"{filing.directory_url}/{acc}.hdr.sgml").text
    hp.write_text(hdr)
    marker.write_text("")               # last: only now is the folder a whole filing
    return docs, hdr


def ingest_filing_from_sources(conn: sqlite3.Connection, filing: Filing,
                               institution_id: str | None, today: str) -> int:
    """Fetch (network/cache, no write lock held) then ingest one filing."""
    docs, hdr = load_filing_texts(filing)
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, load_aliases())
    logger.info("ingested LEGACY_PROXYEDGE %s: %d votes", filing.accession_number, n)
    return n
