"""The contradiction engine (Phase 3 core): joins SAY × DO.

Implemented finding class (a) — commitment ⟷ vote, the flagship:
an institution's own archived policy language commits to a theme; the same
institution's funds vote AGAINST shareholder proposals on that theme.

Every candidate carries the full citation chain:
  - the commitment: document label, version date (live or Wayback), sha256,
    the verbatim sentence, and the source URL;
  - the vote: filing accession, issuer, meeting date, proposal text,
    how voted, management recommendation.

ALL output is quarantined by design. Theme matching is lexical; a human
must read the commitment sentence and the proposal text together before
anything is published. This engine produces *candidates for the first ten
findings*, not findings.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Themes: commitment-side patterns (in policy language) and proposal-side
# patterns (in N-PX voteDescription text). Both must hit to form a candidate.
THEMES: dict[str, dict[str, list[str]]] = {
    "anti-corruption": {
        "commitment": [r"anti-?corruption", r"anti-?bribery", r"business ethics"],
        "proposal": [r"anti-?corruption", r"bribery", r"ethics report"],
    },
    "human-rights": {
        "commitment": [r"human rights"],
        "proposal": [r"human rights", r"human capital", r"forced labou?r", r"child labou?r"],
    },
    "climate": {
        "commitment": [r"climate", r"net.?zero", r"greenhouse gas", r"\bGHG\b"],
        "proposal": [r"climate", r"greenhouse gas", r"\bGHG\b", r"emissions? (?:reduction|target|report)",
                     r"paris agreement"],
    },
    "lobbying-disclosure": {
        "commitment": [r"lobbying", r"political (?:spending|contributions|activit)"],
        "proposal": [r"lobbying", r"political (?:spending|contributions|expenditures)"],
    },
    "board-diversity": {
        "commitment": [r"board diversity", r"diverse board", r"diversity.{0,40}board"],
        "proposal": [r"board diversity", r"diversity report", r"\bDEI\b", r"civil rights audit"],
    },
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")


def extract_text(pdf_path: Path) -> str:
    """Plain text of a commitment PDF (best-effort; pypdf). Cached as a
    sibling .txt so policy diffs and quote lookups are cheap."""
    txt_path = pdf_path.with_suffix(pdf_path.suffix + ".txt")
    if txt_path.exists():
        return txt_path.read_text(errors="replace")
    if pdf_path.suffix.lower() in (".html", ".txt"):
        text = pdf_path.read_text(errors="replace")
    else:
        from pypdf import PdfReader
        try:
            reader = PdfReader(str(pdf_path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            logger.warning("text extraction failed for %s: %s", pdf_path.name, exc)
            return ""
    txt_path.write_text(text)
    return text


def commitment_sentences(text: str, patterns: list[str]) -> list[str]:
    """Sentences in policy text matching any theme pattern — the verbatim
    words a claim would quote."""
    flat = re.sub(r"\s+", " ", text)
    out = []
    for sentence in _SENTENCE_SPLIT.split(flat):
        s = sentence.strip()
        if 20 <= len(s) <= 600 and any(re.search(p, s, re.IGNORECASE) for p in patterns):
            out.append(s)
    return out


@dataclass
class ContradictionCandidate:
    theme: str
    institution_id: str
    # SAY side
    doc_label: str
    doc_version: str          # retrieval date or wayback timestamp
    doc_sha256: str
    doc_url: str
    commitment_quote: str
    # DO side
    accession: str
    issuer_name: str
    cusip: str
    meeting_date: str
    vote_description: str
    how_voted: str
    management_recommendation: str
    shares_voted: float
    quarantined: bool = field(default=True, init=False)  # ALWAYS — human review required


def find_commitment_vote_contradictions(
    conn: sqlite3.Connection, *, limit_per_theme: int = 25,
) -> list[ContradictionCandidate]:
    """Candidates where an institution's archived commitment language and its
    AGAINST votes on same-theme shareholder proposals coexist.

    Vote side is restricted to the strongest shape: the institution voted
    AGAINST while management also recommended AGAINST (i.e. the fund sided
    with management to kill a proposal on a theme its policy embraces).
    """
    docs = conn.execute(
        """SELECT c.institution_id, c.doc_label, c.url, c.sha256, c.content_path,
                  COALESCE(NULLIF(c.wayback_timestamp,''), c.retrieval_date) AS version
           FROM commitments c
           WHERE c.id IN (SELECT MAX(id) FROM commitments GROUP BY institution_id, doc_label)"""
    ).fetchall()

    candidates: list[ContradictionCandidate] = []
    for doc in docs:
        text = extract_text(Path(doc["content_path"]))
        if not text:
            continue
        for theme, pats in THEMES.items():
            quotes = commitment_sentences(text, pats["commitment"])
            if not quotes:
                continue
            proposal_re = "|".join(pats["proposal"])
            votes = conn.execute(
                """SELECT v.accession, v.issuer_name, v.cusip, v.meeting_date,
                          v.vote_description, v.how_voted,
                          v.management_recommendation, v.shares_voted
                   FROM votes v
                   JOIN filings f ON f.accession = v.accession
                   WHERE f.institution_id = ?
                     AND v.how_voted = 'AGAINST'
                     AND v.management_recommendation = 'AGAINST'
                   ORDER BY v.shares_voted DESC""",
                (doc["institution_id"],),
            ).fetchall()
            n = 0
            for v in votes:
                desc = v["vote_description"] or ""
                if not re.search(proposal_re, desc, re.IGNORECASE):
                    continue
                candidates.append(ContradictionCandidate(
                    theme=theme,
                    institution_id=doc["institution_id"],
                    doc_label=doc["doc_label"], doc_version=doc["version"],
                    doc_sha256=doc["sha256"], doc_url=doc["url"],
                    commitment_quote=quotes[0][:400],
                    accession=v["accession"], issuer_name=v["issuer_name"],
                    cusip=v["cusip"], meeting_date=v["meeting_date"],
                    vote_description=desc[:300], how_voted=v["how_voted"],
                    management_recommendation=v["management_recommendation"],
                    shares_voted=v["shares_voted"] or 0.0,
                ))
                n += 1
                if n >= limit_per_theme:
                    break
    return candidates
