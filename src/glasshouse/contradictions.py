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


# Commitment-strength scoring: a quotable SAY-side sentence is one where the
# institution binds ITSELF to something. First-person commitment verbs score
# up; definitional/illustrative phrasing ("examples include", "such as") and
# hedges score down. Found necessary 2026-06-11: pure lexical matching ranked
# "Examples of environmental issues include ... climate risk" above actual
# promise language.
# First-person ("we …") and third-person fund voice ("a/the fund …") are
# treated alike — BlackRock writes "we", Vanguard writes "a fund".
_AGENT = r"(?:we|(?:a|the|each|our) funds?)"
_COMMITMENT_UP = [
    (rf"\b{_AGENT} (?:are committed|is committed|commit)\b", 5.0),
    (rf"\b{_AGENT} (?:will|shall|is likely to|are likely to)\b", 4.0),
    (rf"\b{_AGENT} (?:expect|expects|require|requires|ask|asks|encourage|"
     r"encourages|urge|urges)\b", 4.0),
    (r"\b(?:we|funds?) (?:hold|holds|may hold).{0,40}accountable\b", 4.0),
    (rf"\b{_AGENT} (?:engage|engages|vote|votes|advocate|advocates|support|"
     r"supports|oppose|opposes)\b", 3.0),
    (r"\bour (?:expectation|commitment|approach|policy)\b", 2.5),
    (r"\bwe (?:believe|consider|assess|evaluate|look (?:for|to))\b", 1.5),
    (r"\bwe (?:find it helpful|may (?:signal|vote|not support)|seek)\b", 2.5),
    (r"\bwe (?:ask|asking)\b|\basking companies\b", 2.5),
    (r"\bboards? (?:should|are expected)\b", 1.5),
    (r"\bcompanies (?:should|are expected|must)\b", 1.5),
    (r"\bwe \w+\b", 1.0),   # any first-person agency beats pure description
]
_COMMITMENT_DOWN = [
    (r"\bexamples? (?:of|include)\b", -4.0),
    (r"\bsuch as\b", -2.0),
    (r"\bincluding,? but not limited to\b", -4.0),
    (r"\bmay (?:include|vary|differ)\b", -2.0),
    (r"\bfor (?:example|instance)\b", -3.0),
    (r"\bthis document\b|\bthese principles\b", -1.5),
    (r"\bplease (?:refer|see)\b|\bfor more information\b|\bto learn more\b", -3.0),
    (r"\b\w*\d{5,}\w*\b", -3.0),   # page-footer/document-id artifacts
]


def score_commitment_sentence(s: str) -> float:
    """Higher = more binding, more quotable. Negative = definitional filler."""
    score = 0.0
    for pat, w in _COMMITMENT_UP + _COMMITMENT_DOWN:
        if re.search(pat, s, re.IGNORECASE):
            score += w
    # Mild preference for sentences a card can carry whole.
    if len(s) > 450:
        score -= 1.0
    return score


def _repair_extraction(flat: str) -> str:
    """Undo common PDF text-extraction damage so quotes stay verbatim to the
    source document: spaces injected around hyphens ('Climate -related') and
    runs of whitespace. Restores, never rewrites — only artifacts with an
    unambiguous original are repaired."""
    flat = re.sub(r"(\w) +-(\w)", r"\1-\2", flat)
    flat = re.sub(r"(\w)- +(\w)", r"\1-\2", flat)
    return re.sub(r"\s+", " ", flat)


def commitment_sentences(text: str, patterns: list[str]) -> list[str]:
    """Sentences in policy text matching any theme pattern, strongest
    commitment language first — the verbatim words a claim would quote."""
    flat = _repair_extraction(text)
    out = []
    for sentence in _SENTENCE_SPLIT.split(flat):
        s = sentence.strip()
        if 20 <= len(s) <= 600 and any(re.search(p, s, re.IGNORECASE) for p in patterns):
            out.append(s)
    return sorted(out, key=score_commitment_sentence, reverse=True)


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


# ── polarity guards (added 2026-06-15 after an interactive council review) ──
# The engine flags "voted AGAINST a theme proposal." But AGAINST is only a
# contradiction when the proposal ADVANCES the theme. Half of one live batch
# were false positives: voting AGAINST an anti-DEI proposal DEFENDS diversity;
# a "case by case" policy can't be contradicted by one vote. Precision beats
# recall — when these fire, drop the candidate rather than risk a backwards
# (defamatory) accusation.

# Oppositional verb aimed at the theme's OWN program (anti-theme), not at a
# harm the theme opposes — "cease DEI efforts" (anti) vs "end forced labour"
# (pro). Requires a theme-program noun, so harms like forced labour/corruption
# don't trip it.
_ANTI_THEME = re.compile(
    r"\b(cease|stop|end|eliminate|abolish|repeal|reverse|terminate|rescind|"
    r"reconsider|scale\s*back|wind\s*down|phase\s*out|roll\s*back)\b[^.]{0,30}?"
    r"\b(dei|d\.e\.i|diversity|equity|inclusion|esg|climate|net[\s-]?zero|"
    r"sustainability|emissions[\s-]?reduction|affirmative\s+action)\b",
    re.IGNORECASE)

# Known anti-ESG / anti-DEI shareholder-proposal genres: a counter-report, or
# a "risks/costs of [theme] to returns/beneficiaries" framing, or anti-DEI
# discrimination framing. Voting AGAINST these is consistent with a pro-theme
# policy.
_ANTI_GENRE = re.compile(
    r"alternative\s+\w*\s*report|"
    r"\b(risks?|costs?|harms?|burden|impact)\b[^.]{0,40}\b(retirement|pension|"
    r"beneficiar|shareholder\s+returns?|fiduciary)\b|"
    r"\bmerit[\s-]?based\b|\bviewpoint\s+discrimination\b|"
    r"\breverse\s+discrimination\b|\bracial\s+discrimination\b",
    re.IGNORECASE)

# Policy language that reserves discretion or merely lists "factors we
# consider" — neither is a binding commitment, so a single vote can't
# contradict it. (The factors-list phrasing was behind several weak-quote
# false positives the council flagged.)
_DISCRETIONARY = re.compile(
    r"\bcase[\s-]?by[\s-]?case\b|\bon\s+a\s+case\b|\bvote\s+case\b|"
    r"\bcase\s+basis\b|\bat\s+(the|our|its)\b[^.]{0,20}\bdiscretion\b|"
    r"\bmay\s+vote\s+(either|for\s+or\s+against)\b|"
    r"\bfactors?\b[^.]{0,30}\bconsider(ation)?s?\b|"      # "factors ... to consider"
    r"\bconsiderations?\s+include\b|\bfactors?\s+include\b",
    re.IGNORECASE)


def proposal_is_oppositional(text: str) -> bool:
    """True if the proposal works AGAINST the theme (so voting it down is
    consistent, not hypocritical)."""
    return bool(_ANTI_THEME.search(text) or _ANTI_GENRE.search(text))


def commitment_is_discretionary(quote: str) -> bool:
    """True if the policy sentence explicitly reserves case-by-case discretion."""
    return bool(_DISCRETIONARY.search(quote))


def find_commitment_vote_contradictions(
    conn: sqlite3.Connection, *, limit_per_theme: int = 25,
) -> list[ContradictionCandidate]:
    """Candidates where an institution's archived commitment language and its
    AGAINST votes on same-theme shareholder proposals coexist.

    Vote side: the institution voted AGAINST a proposal on a theme its
    policy embraces. The management recommendation is carried through for
    disclosure, not filtered on — live data (2026-06-11) shows theme votes
    split both ways relative to management (say-on-climate items are
    management-sponsored with mgmt FOR; US shareholder proposals have mgmt
    AGAINST), and both shapes are reviewable candidates.
    """
    # All commitment versions, grouped by document and sorted oldest→newest.
    versions: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for d in conn.execute(
        """SELECT c.institution_id, c.doc_label, c.url, c.sha256, c.content_path,
                  COALESCE(NULLIF(c.wayback_timestamp,''), c.retrieval_date) AS version
           FROM commitments c"""):
        versions.setdefault((d["institution_id"], d["doc_label"]), []).append(d)
    for vs in versions.values():
        vs.sort(key=lambda d: _yyyymmdd(d["version"]))

    # The best promissory, non-discretionary quote for (version, theme),
    # cached so each PDF is parsed once.
    quote_cache: dict[tuple[str, str], str | None] = {}

    def theme_quote(doc_row, theme: str, pats: dict) -> str | None:
        ck = (doc_row["content_path"], theme)
        if ck not in quote_cache:
            text = extract_text(Path(doc_row["content_path"]))
            qs = commitment_sentences(text, pats["commitment"]) if text else []
            qs = [q for q in qs if not commitment_is_discretionary(q)
                  and score_commitment_sentence(q) >= 1.0]
            quote_cache[ck] = qs[0] if qs else None
        return quote_cache[ck]

    candidates: list[ContradictionCandidate] = []
    for (inst_id, label), vs in versions.items():
        votes = conn.execute(
            """SELECT v.accession, v.issuer_name, v.cusip, v.meeting_date,
                      v.vote_description, v.how_voted,
                      v.management_recommendation, v.shares_voted
               FROM votes v JOIN filings f ON f.accession = v.accession
               WHERE f.institution_id = ?
                 AND v.how_voted = 'AGAINST' AND v.is_duplicate = 0
               ORDER BY v.shares_voted DESC""", (inst_id,)).fetchall()
        for theme, pats in THEMES.items():
            proposal_re = "|".join(pats["proposal"])
            n = 0
            seen: set[tuple] = set()
            for v in votes:
                desc = v["vote_description"] or ""
                if not re.search(proposal_re, desc, re.IGNORECASE):
                    continue
                # Polarity guard: skip proposals that work AGAINST the theme.
                if proposal_is_oppositional(desc):
                    continue
                key = (v["issuer_name"], v["meeting_date"], desc)
                if key in seen:
                    continue
                # Temporal alignment: quote the latest policy version that was
                # in force ON OR BEFORE the vote — never accuse an institution
                # of breaking a commitment it had not yet made. If no version
                # predates the vote, there is no fair contradiction to draw.
                vote_day = _yyyymmdd(v["meeting_date"])
                chosen, quote = None, None
                for d in reversed(vs):  # newest first
                    dday = _yyyymmdd(d["version"])
                    if not (dday and vote_day and dday <= vote_day):
                        continue
                    q = theme_quote(d, theme, pats)
                    if q:
                        chosen, quote = d, q
                        break
                if not chosen:
                    continue
                seen.add(key)
                candidates.append(ContradictionCandidate(
                    theme=theme, institution_id=inst_id,
                    doc_label=label, doc_version=chosen["version"],
                    doc_sha256=chosen["sha256"], doc_url=chosen["url"],
                    commitment_quote=quote[:400],
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


def _yyyymmdd(s: str) -> str:
    """Normalize a date to a sortable YYYYMMDD string. Handles N-PX meeting
    dates (MM/DD/YYYY), ISO retrieval dates (YYYY-MM-DD), and Wayback
    timestamps (YYYYMMDDhhmmss). Returns '' if unparseable."""
    s = (s or "").strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            mm, dd, yy = parts
            if mm.isdigit() and dd.isdigit():
                return f"{yy}{int(mm):02d}{int(dd):02d}"
        return ""
    digits = s.replace("-", "")
    return digits[:8] if len(digits) >= 8 and digits[:8].isdigit() else ""
