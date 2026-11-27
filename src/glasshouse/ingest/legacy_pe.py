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

`management_recommendation` carries the XML meaning (whether THIS vote went WITH = "FOR" or
AGAINST management), copied from the printed For/Against Management column; else "".
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

PARSER_VERSION = "2026-11-27"    # written on every legacy_parse row; bump on any parse/guard change
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
    """First alphanumeric character, casefolded. ISS's collation of punctuation and digits
    is not reproducible (real order: E-GUARDIAN, E.ON SE, E-J HOLDINGS; "&DO HOLDINGS",
    "1&1 AG", "A2A SPA"), so see `_is_reset`."""
    return next((c for c in name.casefold() if c.isalnum()), "")


def _is_letter(c: str) -> bool:
    return len(c) == 1 and "a" <= c <= "z"


def _is_reset(prev_issuer: str, issuer: str) -> bool:
    """A drop to an earlier initial, counted ONLY when both initials are letters a-z."""
    p, c = _issuer_sort_key(prev_issuer), _issuer_sort_key(issuer)
    return _is_letter(p) and _is_letter(c) and c < p


def drop_disputed_meetings(out: list[dict], disputed_rows: list[dict]) -> tuple[list[dict], dict]:
    """Any meeting with a row only one parser produced loses ALL its agreed rows."""
    bad = {meeting_key(r) for r in disputed_rows}
    kept = [r for r in out if meeting_key(r) not in bad]
    removed = {meeting_key(r) for r in out} & bad
    return kept, {"meetings_dropped_disputed": len(removed),
                  "rows_dropped_disputed": len(out) - len(kept)}


def _is_repeat(sec: list[dict], cut: int) -> bool:
    """True when the rows from `cut` on equal, field for field and in order, a contiguous
    run of the section's earlier rows (an as-filed repeat)."""
    head, tail = sec[:cut], sec[cut:]
    n = len(tail)
    return any(head[j] == tail[0] and head[j:j + n] == tail
               for j in range(len(head) - n + 1))


def order_guard(rows: list[dict], fund_field: str) -> tuple[list[dict], dict]:
    """Within a fund section meetings are listed in alphabetical issuer order. A later
    issuer that sorts before the previous one (a reset, letters only) may mean a missed
    fund boundary. At the first reset: if the rows from there to the section's end exactly
    repeat an earlier run of the section (all fields), they are an as-filed repeat and kept.
    Else, if it is the section's only reset and the part before it is at most 2 distinct
    meetings (ProxyEdge sometimes lists one or two meetings first, out of order), only
    those head rows are dropped and the sorted tail kept. Else the section is cut from the
    reset to its end."""
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
        reset_at = [m for m in range(1, len(meetings))
                    if _is_reset(meetings[m - 1][1], meetings[m][1])]
        if not reset_at:
            kept.extend(sec)
            continue
        resets += 1
        m = reset_at[0]
        cut = meetings[m][2]
        if _is_repeat(sec, cut):
            repeats += 1
            kept.extend(sec)
        elif len(reset_at) == 1 and m <= 2:
            kept.extend(sec[cut:])       # drop only the out-of-order head meetings
            dropped += cut
        else:
            kept.extend(sec[:cut])
            dropped += len(sec) - cut
    if resets:
        logger.info("order guard: resets=%d repeats=%d rows_dropped=%d", resets, repeats, dropped)
    return kept, {"order_resets": resets, "order_repeats": repeats, "rows_dropped_order": dropped}


def guarded(out: list[dict], rows_a: list[dict], rows_b: list[dict], ca: Counter,
            cb: Counter, fund_field: str, keyfn=None,
            order: bool = True) -> tuple[list[dict], dict]:
    """Both guards over the multiset-intersection rows; returns rows and the new stats.
    `order=False` skips the issuer-order guard, for layouts that print the fund on every row
    (nothing is inherited from a heading, so an order reset cannot mean a missed one)."""
    keyfn = keyfn or _key
    by_key = {keyfn(r): r for r in rows_b} | {keyfn(r): r for r in rows_a}
    disputed = [by_key[k] for k in [*(ca - cb), *(cb - ca)]]
    out, s1 = drop_disputed_meetings(out, disputed)
    if order:
        out, s2 = order_guard(out, fund_field)
    else:
        s2 = {"order_resets": 0, "order_repeats": 0, "rows_dropped_order": 0}
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


class SeriesFallback:
    """The SEC Investment Company Series and Class dataset, narrowed to ONE filing.

    `by_name` = normalised series name -> series id, for the filing's own registrant CIK
    only, and only names that mean exactly one series there. `header_names` = every
    normalised name the filing's own header prints (ambiguous ones included): a heading
    with a header candidate is never looked up here. Same `_norm` as the header path, no
    fuzzy matching: a heading maps only on an exact match to exactly one series."""

    def __init__(self, by_name: dict[str, str], header_names: set[str]):
        self.by_name, self.header_names = by_name, header_names

    def lookup(self, heading: str, suffix: bool = False) -> str | None:
        """Series id for a heading, else None. `suffix` mirrors the ISS header path: exact
        name first, else one trailing ' - SUFFIX' removed."""
        keys = [_norm(heading)]
        if suffix and " - " in heading:
            keys.append(_norm(heading.rsplit(" - ", 1)[0]))
        for k in keys:
            if k in self.header_names:
                return None
            if k in self.by_name:
                return self.by_name[k]
        return None


def build_fallback(dataset: dict[str, dict[str, set[str]]] | None, cik: object,
                   hdr_text: str) -> SeriesFallback | None:
    """Fallback for one filing from `sec_series.load_dataset` output (CIK10 -> normalised
    name -> series ids). None when there is no dataset or no series for the CIK."""
    names = (dataset or {}).get(_cik10(cik))
    if not names:
        return None
    unique = {n: next(iter(ids)) for n, ids in names.items() if len(ids) == 1}
    return SeriesFallback(unique, {_norm(n) for n, _ in _header_pairs(hdr_text)})


def note_fallback(info: dict, heading: str, sid: str) -> None:
    """Record, per (heading, series id), a row mapped through the SEC series dataset."""
    info.setdefault("series_fallback", Counter())[(" ".join(heading.split()), sid)] += 1


def single_fund_map(hdr_text: str, headings) -> dict[str, str]:
    """Single-fund registrant rule. A filing whose SGML header lists NO series at all and
    whose agreed rows (over ALL its documents) carry exactly ONE fund heading (same `_norm`
    as the header path) maps that heading to the empty series, like the XML-era rows of a
    closed-end fund (which has no series). {norm(heading): ""}, else {}."""
    if header_series_ids(hdr_text):
        return {}
    norms = {_norm(h) for h in headings}
    return dict.fromkeys(norms, "") if len(norms) == 1 and "" not in norms else {}


def note_single_fund(info: dict, single: dict[str, str], headings) -> None:
    """Audit: rows mapped by the single-fund rule go to `series_fallback` with series id ""."""
    for h in headings:
        if _norm(h) in single:
            note_fallback(info, h, "")


# -- security identifiers: validated, never repaired ---------------------------

_CUSIP_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#"


def cusip_check_digit(body8: str) -> int:
    """CUSIP check digit of the first 8 characters (mod-10 double-add-double)."""
    total = 0
    for i, ch in enumerate(body8):
        v = _CUSIP_CHARS.index(ch)
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10


def cusip_valid(value: str) -> bool:
    return (len(value) == 9 and all(c in _CUSIP_CHARS for c in value)
            and value[8].isdigit() and int(value[8]) == cusip_check_digit(value[:8]))


def isin_check_digit(body11: str) -> int:
    """ISIN check digit (Luhn over the letters-to-digits expansion) of the first 11 chars."""
    digits = "".join(str(int(c, 36)) for c in body11)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        v = int(ch)
        if i % 2 == 0:               # the check digit will sit at position 0
            v *= 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10


def isin_valid(value: str) -> bool:
    return (len(value) == 12 and value[:2].isalpha() and value[:2].isupper() and value.isascii()
            and value.isalnum() and value[11].isdigit()
            and int(value[11]) == isin_check_digit(value[:11]))


def classify_security_id(raw: str) -> tuple[str, str]:
    """(cusip, isin) from a printed security id; ('', '') when it is neither. A 9-char value
    with a valid CUSIP check digit is a cusip; a 12-char value with a valid ISIN check digit
    is an isin (its embedded cusip is kept only for US/CA ISINs whose 9 chars form a valid
    CUSIP). Nothing is ever repaired."""
    v = (raw or "").strip().upper()
    if cusip_valid(v):
        return v, ""
    if isin_valid(v):
        inner = v[2:11]
        return (inner if v[:2] in ("US", "CA") and cusip_valid(inner) else ""), v
    return "", ""


# -- ledger rows -------------------------------------------------------------

def to_vote_rows(rows: list[dict], smap: dict[str, str],
                 aliases: dict[str, str] | None = None,
                 header_sids: set[str] | None = None,
                 fallback: SeriesFallback | None = None) -> tuple[list[dict], dict]:
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
        if sid is None and fallback and _heading(r["fund_name"]) not in (aliases or {}):
            sid = fallback.lookup(r["fund_name"])
            if sid:
                note_fallback(info, r["fund_name"], sid)
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
        # XML meaning: WITH (FOR) / AGAINST management, copied from the printed column.
        rec = {"For": "FOR", "Against": "AGAINST"}.get(fa, "")
        cusip, isin = "", ""
        for raw in (r["security_id"], r["isin"]):
            c, i = classify_security_id(raw)
            cusip, isin = cusip or c, isin or i
        out.append({
            "issuer_name": r["issuer_name"], "cusip": cusip, "isin": isin,
            "meeting_date": f"{m.group(2)}/{m.group(3)}/{m.group(1)}",
            "vote_description": r["proposal_text"], "category_type": "",
            "vote_source": source, "shares_on_loan": None, "vote_series": sid,
            "how_voted": how, "shares_voted": None, "management_recommendation": rec,
            "legacy_format": "proxyedge", "for_against_management": fa,
            "proposal_number": (r.get("proposal_id") or "").strip() or None,
        })
    info["funds_unmapped"] = dict(unmapped)
    return out, info


_INSERT = """INSERT INTO votes
    (accession, issuer_name, cusip, isin, meeting_date, vote_description, category_type,
     vote_source, shares_on_loan, vote_series, how_voted, shares_voted,
     management_recommendation, legacy_format, for_against_management, proposal_number)
    VALUES (:accession,:issuer_name,:cusip,:isin,:meeting_date,:vote_description,
            :category_type,:vote_source,:shares_on_loan,:vote_series,:how_voted,
            :shares_voted,:management_recommendation,:legacy_format,
            :for_against_management,:proposal_number)"""


def is_candidate(filing: Filing) -> bool:
    return filing.form_type in ("N-PX", "N-PX/A") and filing.period_of_report == PERIOD


def ingest_filing(conn: sqlite3.Connection, filing: Filing, institution_id: str | None,
                  today: str, docs: dict[str, str], hdr_text: str,
                  aliases: dict[tuple[str, str], str] | None = None,
                  series_dataset: dict | None = None) -> int:
    """Parse every vote document of one filing, gate it, record it. One transaction
    (no network inside). Returns votes inserted."""
    smap = series_map(hdr_text)
    fa, sids = filing_aliases(aliases, filing.cik), header_series_ids(hdr_text)
    fb = build_fallback(series_dataset, filing.cik, hdr_text)
    ag = [(name, text, *agreed(text)) for name, text in sorted(docs.items())
          if "Agenda Number:" in text]
    single = single_fund_map(hdr_text, (r["fund_name"] for _, _, rows, _ in ag for r in rows))
    smap = {**smap, **single}
    parsed = []
    for name, text, rows, st in ag:
        votes, info = to_vote_rows(rows, smap, fa, sids, fb)
        note_single_fund(info, single, (r["fund_name"] for r in rows))
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
                                    period_of_report, report_type, source_url, retrieval_date,
                                    notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (acc, filing.cik, institution_id, filing.form_type, filing.filing_date,
             filing.period_of_report, report_ok if accepted else report_rejected,
             filing.directory_url, today, filing.period_note or None))
        inserted = 0
        for name, meetings, st, votes, info in parsed:
            n = 0
            if accepted:
                conn.executemany(_INSERT, [{"proposal_number": None, **v, "accession": acc} for v in votes])
                n = len(votes)
            inserted += n
            conn.execute(
                """INSERT INTO legacy_parse (accession, document, meetings, rows_a, rows_b,
                       agreed, a_only, b_only, disagreement_rate, funds_unmapped,
                       rows_inserted, parsed_at, rows_dropped_disputed,
                       meetings_dropped_disputed, order_resets, order_repeats,
                       rows_dropped_order, parser_version, series_fallback)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (acc, name, meetings, st["rows_a"], st["rows_b"], st["agreed"], st["a_only"],
                 st["b_only"], st["disagreement_rate"],
                 repr(sorted(info["funds_unmapped"].items())) if info["funds_unmapped"]
                 else "", n, now, st.get("rows_dropped_disputed"),
                 st.get("meetings_dropped_disputed"), st.get("order_resets"),
                 st.get("order_repeats"), st.get("rows_dropped_order"), PARSER_VERSION,
                 repr(sorted((h, sid, c) for (h, sid), c in info["series_fallback"].items()))
                 if info.get("series_fallback") else ""))
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
    from . import sec_series
    n = ingest_filing(conn, filing, institution_id, today, docs, hdr, load_aliases(),
                      sec_series.load_dataset())
    logger.info("ingested LEGACY_PROXYEDGE %s: %d votes", filing.accession_number, n)
    return n
