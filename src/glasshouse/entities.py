"""Entity resolution — a first-class module.

Join keys in strict priority order: CUSIP → LEI → CIK → guarded fuzzy name
match. Precision over recall: a false accusation is fatal, a missed match is
Tuesday. Every fuzzy match (accepted or not) is logged to match_log.

The fuzzy matcher is adapted from the predecessor project's production
matcher (token-set similarity, legal-suffix stripping, length-ratio guard),
re-verified by this repo's test suite.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

# Threshold for any fuzzy join used in a finding (stricter than exploration).
FINDING_THRESHOLD = 0.85

# Legal suffixes stripped entirely so "BP plc" / "BP p.l.c." normalise to "bp".
_LEGAL_SUFFIX_TOKENS: frozenset[str] = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "llc", "lp", "llp", "plc",
    "holdings", "holding", "hldgs", "hldg",
    "group", "grp",
    "international", "intl", "intrnl",
    "technologies", "technology", "technol",
    "solutions", "systems", "enterprises", "services",
    "resources", "energy",
    "ag", "sa", "spa", "nv", "bv", "ab", "oy", "se",
    "pjsc", "ojsc", "zao", "oao",
    "gmbh", "kg", "ky",
    "brands", "industries",
})

_STOP_TOKENS: frozenset[str] = frozenset({
    "the", "and", "of", "for", "a", "an", "in", "at",
}) | _LEGAL_SUFFIX_TOKENS

_PUNCT_RE = re.compile(r"[^a-z0-9\s]")

# Real CUSIPs: exactly 9 alphanumeric chars with at least one digit.
_CUSIP_RE = re.compile(r"^(?=[A-Z0-9]{9}$)(?=[^0-9]*[0-9]).*$")


def normalize_name(name: str) -> str:
    """Lower-case, strip punctuation and legal suffixes. Stable join key.

    "Goldman Sachs Group Inc." → "goldman sachs"; "BP p.l.c." → "bp".
    """
    stripped = name.strip()
    if _CUSIP_RE.match(stripped.upper()):
        return stripped.lower()
    lower = _PUNCT_RE.sub(" ", stripped.lower())
    tokens = [
        t for t in lower.split()
        if t and t not in _STOP_TOKENS and (len(t) > 1 or t.isdigit())
    ]
    return " ".join(tokens)


def _token_set(name: str) -> frozenset[str]:
    lower = _PUNCT_RE.sub(" ", name.lower())
    return frozenset(t for t in lower.split() if t and t not in _STOP_TOKENS)


def jaccard_similarity(a: str, b: str) -> float:
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _is_token_subsequence(short: str, long_: str) -> bool:
    return _token_set(short).issubset(_token_set(long_))


def _length_ratio(a: str, b: str) -> float:
    ta, tb = len(_token_set(a)), len(_token_set(b))
    if ta == 0 or tb == 0:
        return 0.0
    return min(ta, tb) / max(ta, tb)


def fuzzy_match(query: str, candidate: str, threshold: float = 0.55) -> tuple[bool, float]:
    """Return (matched, score in [0,1]).

    1. Exact normalized match → 1.0
    2. Token-subsequence both ways with length ratio ≥ 0.40 → 0.85
       (handles "goldman sachs" ⊆ "goldman sachs group inc"; the ratio guard
       stops "bp" matching "british petroleum exploration ltd")
    3. Token Jaccard ≥ threshold → Jaccard score
    """
    if not query or not candidate:
        return False, 0.0

    if _CUSIP_RE.match(query.strip().upper()) or _CUSIP_RE.match(candidate.strip().upper()):
        return query.strip().upper() == candidate.strip().upper(), 0.0

    nq, nc = normalize_name(query), normalize_name(candidate)
    if nq == nc and nq:
        return True, 1.0

    if _length_ratio(query, candidate) >= 0.40:
        if _is_token_subsequence(query, candidate) or _is_token_subsequence(candidate, query):
            return True, 0.85

    j = jaccard_similarity(query, candidate)
    if j >= threshold:
        return True, j
    return False, j


def best_match(query: str, candidates: list[str], threshold: float = 0.55) -> Optional[tuple[str, float]]:
    best: Optional[tuple[str, float]] = None
    for c in candidates:
        matched, score = fuzzy_match(query, c, threshold=threshold)
        if matched and (best is None or score > best[1]):
            best = (c, score)
    return best


def log_match(conn: sqlite3.Connection, query: str, candidate: str,
              method: str, score: float, accepted: bool) -> None:
    conn.execute(
        "INSERT INTO match_log (ts, query, candidate, method, score, accepted) VALUES (?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         query, candidate, method, score, int(accepted)),
    )


def resolve(conn: sqlite3.Connection, *, name: str = "", cusip: str = "",
            lei: str = "", cik: str = "",
            threshold: float = FINDING_THRESHOLD) -> Optional[sqlite3.Row]:
    """Resolve to an `entities` row by CUSIP → LEI → CIK → fuzzy name.

    Exact-key hits are not logged (they are deterministic); fuzzy attempts
    are always logged, accepted or not.
    """
    if cusip:
        row = conn.execute(
            "SELECT e.* FROM entities e JOIN entity_cusips c ON c.entity_id = e.id WHERE c.cusip = ?",
            (cusip.upper(),),
        ).fetchone()
        if row:
            return row
    if lei:
        row = conn.execute("SELECT * FROM entities WHERE lei = ?", (lei,)).fetchone()
        if row:
            return row
    if cik:
        row = conn.execute(
            "SELECT * FROM entities WHERE cik = ?", (cik.lstrip("0"),)
        ).fetchone()
        if row:
            return row
    if name:
        norm = normalize_name(name)
        row = conn.execute(
            "SELECT * FROM entities WHERE normalized_name = ?", (norm,)
        ).fetchone()
        if row:
            return row
        best: Optional[tuple[sqlite3.Row, float]] = None
        for cand in conn.execute("SELECT * FROM entities").fetchall():
            matched, score = fuzzy_match(name, cand["canonical_name"], threshold=threshold)
            accepted = matched and score >= threshold
            if matched or score > 0.4:
                log_match(conn, name, cand["canonical_name"], "fuzzy", score, accepted)
            if accepted and (best is None or score > best[1]):
                best = (cand, score)
        if best:
            return best[0]
    return None


def upsert_entity(conn: sqlite3.Connection, canonical_name: str, *,
                  cik: str = "", lei: str = "", cusips: list[str] | None = None) -> int:
    norm = normalize_name(canonical_name)
    conn.execute(
        "INSERT INTO entities (canonical_name, normalized_name, cik, lei) VALUES (?,?,?,?) "
        "ON CONFLICT(canonical_name) DO UPDATE SET "
        "cik = CASE WHEN excluded.cik != '' THEN excluded.cik ELSE entities.cik END, "
        "lei = CASE WHEN excluded.lei != '' THEN excluded.lei ELSE entities.lei END",
        (canonical_name, norm, cik.lstrip("0") if cik else "", lei),
    )
    row = conn.execute("SELECT id FROM entities WHERE canonical_name = ?", (canonical_name,)).fetchone()
    entity_id = row["id"]
    for cusip in cusips or []:
        conn.execute(
            "INSERT OR IGNORE INTO entity_cusips (cusip, entity_id) VALUES (?,?)",
            (cusip.upper(), entity_id),
        )
    return entity_id
