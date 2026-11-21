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

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .ledger import NON_LEGACY_VOTE_SQL, VERSION_DATE_SQL

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
    # Environmental beyond climate. Patterns are specific (no bare "water"/"nature"
    # that would match unrelated text) so an AGAINST vote is a real say-vs-do gap.
    "nature": {
        "commitment": [r"deforestation", r"biodiversity", r"natural capital",
                       r"nature[\s-]related", r"water (?:risk|stewardship|security)"],
        "proposal": [r"deforestation", r"biodiversity", r"natural capital",
                     r"nature[\s-]related", r"water (?:risk|stewardship|security)",
                     r"single[\s-]use plastic", r"plastic pollution"],
    },
    # Worker treatment (distinct from human-rights' forced/child-labour focus).
    # Commitment side is broadened to how managers actually phrase it in
    # stewardship policy ("human capital", "workforce"), not just union terms.
    "labor-rights": {
        "commitment": [r"labou?r rights", r"freedom of association", r"collective bargaining",
                       r"living wage", r"worker (?:safety|health)", r"human capital",
                       r"workforce", r"fair (?:labou?r|treatment)"],
        "proposal": [r"freedom of association", r"collective bargaining", r"living wage",
                     r"paid sick leave", r"worker (?:safety|health)", r"workplace safety"],
    },
}

# Split on sentence-ending punctuation, tolerating a trailing footnote marker
# ("…value creation.16 As a long-term…" → two sentences). Without this, PDF
# footnote superscripts merge a descriptive sentence into the next, so a
# heading/description leads the quote instead of the actual commitment.
_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\d{0,3}\s+")


def extract_text(pdf_path: Path) -> str:
    """Plain text of a commitment PDF (best-effort; pypdf). Cached as a
    sibling .txt so policy diffs and quote lookups are cheap."""
    # Cache suffix is versioned: every .txt written before 2026-08-26 holds
    # RAW HTML for html sources (25,479 chars of BNY page source for 2,851
    # chars of policy), which the commitment scorer then read as prose.
    txt_path = pdf_path.with_suffix(pdf_path.suffix + ".v2.txt")
    if txt_path.exists():
        return txt_path.read_text(errors="replace")
    if pdf_path.suffix.lower() in (".html", ".htm", ".xhtml"):
        from .ingest.commitments import html_to_text
        text = html_to_text(pdf_path.read_text(errors="replace"))
    elif pdf_path.suffix.lower() == ".txt":
        text = pdf_path.read_text(errors="replace")
    else:
        from pypdf import PdfReader
        try:
            reader = PdfReader(str(pdf_path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            logger.warning("text extraction failed for %s: %s", pdf_path.name, exc)
            # Remember the failure. A corrupt PDF (T. Rowe Price's 2023 capture
            # is truncated) is otherwise re-parsed on every call, which took a
            # detector pass from ~26s past ten minutes.
            text = ""
    try:
        txt_path.write_text(text)
    except OSError as exc:                       # read-only archive: still usable
        logger.warning("could not cache extracted text for %s: %s", pdf_path.name, exc)
    return text


def bound_body(text: str, body: dict | None) -> str | None:
    """The policy body of a capture: from the start of the first `start` match to
    the end of the first `end` match after it, whitespace-normalised. No `body`
    spec returns the text unchanged. None means UNREADABLE: a marker did not
    match, so the span cannot be known. Never the full page in its place (page
    navigation is not policy; a menu change would otherwise be a phantom version)."""
    if not body:
        return text
    t = re.sub(r"\s+", " ", text or "").strip()
    start = re.search(body["start"], t)
    if not start:
        return None
    end = re.compile(body["end"]).search(t, start.start())
    if not end:
        return None
    return t[start.start():end.end()]


# Spacing around a trademark sign never changes meaning ("Investments®" vs
# "Investments ®", or a superscript marker that survived extraction).
_TM = re.compile(r"\s*(?:\{sup\}|<sup>)?\s*([\u00ae\u2122\u00a9])(?:\s*(?:\{/sup\}|</sup>))?",
                 re.IGNORECASE)
# Typography never changes meaning: curly vs straight quotes, em/en dashes vs a spaced
# hyphen, and "15 %" vs "15%". Bump IDENTITY_VERSION whenever identity_text changes so
# the backfill recomputes every stored identity.
IDENTITY_VERSION = 3
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_DASH = re.compile(r"\s*[\u2013\u2014]\s*|\s-\s")
_PCT = re.compile(r"(\d) %")
# Layout, not wording (v3): a soft hyphen and the space after it, and the space a line
# break leaves after a hyphen inside a word ("pay-for- performance", "N- PX").
_SOFT_HYPHEN = re.compile("\u00ad\\s*")
_BROKEN_HYPHEN = re.compile(r"(?<=[A-Za-z0-9])-\s+(?=[A-Za-z])")
_MIN_IDENTITY_CHARS = 200      # below this, extraction is untrustworthy: identity is the bytes


def identity_text(text: str) -> str:
    """The text a policy version's identity is made of: whitespace-normalised, with
    no whitespace before a trademark sign or a percent sign, typographic quotes as
    ASCII, every dash (em, en, spaced hyphen) as " - ", no soft hyphens, and no space
    after a hyphen inside a word (a line break)."""
    t = _SOFT_HYPHEN.sub("", text or "")
    t = _TM.sub(r"\1", re.sub(r"\s+", " ", t).strip())
    t = _DASH.sub(" - ", t.translate(_QUOTES))
    t = _BROKEN_HYPHEN.sub("-", t)
    return _PCT.sub(r"\1%", t)


def identity_hash(text: str) -> str:
    """SHA-256 of the identity text, or '' when the text is empty or too short to
    trust (an unreadable capture never shares an identity)."""
    t = identity_text(text)
    return hashlib.sha256(t.encode()).hexdigest() if len(t) >= _MIN_IDENTITY_CHARS else ""


_AUTO = object()


def identity_hash_from_file(institution_id: str, doc_label: str, path: Path,
                            spec=_AUTO) -> str:
    """The identity hash of a stored capture ('' if unreadable): the text bounded by
    the label's `body` spec (unreadable if its markers miss)."""
    if spec is _AUTO:
        spec = body_spec(institution_id, doc_label)
    text = extract_text(path)
    if spec:
        text = (bound_body(text, spec) if text else None) or ""
    return identity_hash(text)


def commitment_identity(institution_id: str, doc_label: str, content_path: str,
                        identity_sha256: str, sha256: str, spec=_AUTO) -> str:
    """THE version identity of an archived capture, shared by the engine, release,
    site, dataset, newsroom and timeline: the persisted `identity_sha256` first;
    only if that is empty AND a local file exists, computed from the file. Never
    the raw bytes and never the whole-page ledger text hash: a capture with
    neither is 'unreadable:<sha>' (its own row, never merged, never a readable
    version) and is logged."""
    if identity_sha256:
        return "text:" + identity_sha256
    path = Path(content_path) if content_path else None
    if path is not None and path.is_file():
        h = identity_hash_from_file(institution_id, doc_label, path, spec)
        if h:
            return "text:" + h
    logger.warning("%s/%s capture %s: no identity hash and no readable local text; "
                   "treated as unreadable", institution_id, doc_label, sha256[:12])
    return "unreadable:" + sha256


def distinct_versions(conn, where: str = "1=1", params: tuple = (),
                      newest_first: bool = False) -> list[tuple[str, sqlite3.Row]]:
    """(identity, first row) per distinct policy version among live commitments,
    in id order (or newest first)."""
    out, seen = [], set()
    order = "DESC" if newest_first else "ASC"
    for r in conn.execute(f"SELECT * FROM commitments WHERE superseded=0 AND ({where}) "
                          f"ORDER BY id {order}", params):
        ident = commitment_identity(r["institution_id"], r["doc_label"], r["content_path"],
                                    r["identity_sha256"], r["sha256"])
        if ident not in seen:
            seen.add(ident)
            out.append((ident, r))
    return out


_BODY_SPECS: dict | None = None


def body_spec(institution_id: str, doc_label: str) -> dict | None:
    """The `body` key of a commitment label in config/institutions.yaml, if any."""
    global _BODY_SPECS
    if _BODY_SPECS is None:
        from . import registry
        reg = registry.load()      # a failed load must raise, never fall back to whole pages
        _BODY_SPECS = {(i, c["label"]): c["body"] for i, inst in reg.items()
                       for c in (inst.get("commitments") or []) if c.get("label") and c.get("body")}
    return _BODY_SPECS.get((institution_id, doc_label))


def capture_text(institution_id: str, doc_label: str, path: Path) -> str:
    """extract_text of a capture, bounded to the policy body where the label
    configures one. '' (unreadable) if its markers do not match."""
    text = extract_text(path)
    spec = body_spec(institution_id, doc_label)
    if not spec or not text:
        return text
    body = bound_body(text, spec)
    if body is None:
        logger.warning("%s/%s %s: body markers not found; treated as unreadable",
                       institution_id, doc_label, path.name)
        return ""
    return body


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


# The manager binding ITSELF — first-person/fund agent.
_AGENT_RE = re.compile(r"\b(?:we|our|us|(?:a|the|each|our|its) funds?)\b", re.IGNORECASE)
# A genuine commitment/expectation VERB (not just any "we …"). Without this, a
# sentence that merely mentions a topic near a stray "our" passes as a promise.
_COMMIT_VERB_RE = re.compile(
    r"\b(?:committ\w*|pledg\w*|will|shall|expect\w*|requir\w*|ask\w*|encourag\w*|urg\w*|"
    r"engag\w*|vot\w*|advocat\w*|support\w*|oppos\w*|seek\w*|believ\w*|consider\w*|"
    r"assess\w*|evaluat\w*|incorporat\w*|find[^.]{0,12}helpful|hold[^.]{0,20}accountable)\b",
    re.IGNORECASE)


def is_binding_commitment(s: str) -> bool:
    """A quote may anchor a say-vs-do claim ONLY if it is (1) real prose — not a
    table-of-contents / title-case list fragment (a PDF-extraction artifact),
    (2) the manager binding ITSELF (first-person/fund agent), and (3) actually
    promising/expecting something (a commitment verb), not merely describing a
    topic. Precision over recall: better to drop a borderline quote than to
    accuse a manager of breaking a 'commitment' it never made."""
    s = s.strip()
    toks = [t for t in s.split() if t]
    if len(toks) < 5:
        return False
    if sum(1 for t in toks if t[:1].isupper()) / len(toks) > 0.5:
        return False                    # mostly Title-Case → a list/heading
    run = mx = 0                          # a run of ≥6 consecutive Title-Case tokens = a heading/TOC
    for t in toks:
        run = run + 1 if t[:1].isupper() else 0
        mx = max(mx, run)
    if mx >= 6:
        return False
    return bool(_AGENT_RE.search(s) and _COMMIT_VERB_RE.search(s))


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
    r"reconsider|revisit|revis\w*|reevaluat\w*|reassess\w*|scale\s*back|"
    r"wind\s*down|phase\s*out|roll\s*back)\b[^.]{0,30}?"
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
    # The anti-ESG "risks OF the program" genre: "risks of (maintaining) DEI",
    # "DEI and related risks". The PROGRAM is framed as the risk (anti) — vs
    # "risks related to biodiversity/climate LOSS" (the harm), which is pro and
    # must keep counting, so this is scoped to DEI/diversity-equity/affirmative
    # action only, never to environmental nouns.
    r"\brisks?\b[^.]{0,30}\b(?:d\.?e\.?i\.?|diversity[,\s]+equity|affirmative\s+action|"
    r"maintaining\s+(?:dei|diversity))\b|"
    r"\b(?:d\.?e\.?i\.?|diversity[,\s]+equity)\b[^.]{0,20}\brelated\s+risks?\b|"
    r"\bmerit[\s-]?based\b|\bviewpoint\s+discrimination\b|"
    r"\breverse\s+discrimination\b|\bracial\s+discrimination\b|"
    # The 2024-25 anti-DEI "executive pay" campaign (e.g. the National Legal
    # and Policy Center's proposals to ELIMINATE DEI goals from executive pay).
    # The N-PX title can't distinguish 'eliminate DEI pay goals' (anti) from
    # 'link pay to DEI' (pro), so this whole class is polarity-AMBIGUOUS and is
    # excluded from gap-scoring — voting it down is not evidence of a gap.
    r"\b(?:d\.?e\.?i\.?|diversity[,\s]+equity[,\s]+(?:and\s+)?inclusion)\b[^.]{0,40}"
    r"\bexecutive\s+(?:pay|compensation|comp\b|incentive)|"
    r"\bexecutive\s+(?:pay|compensation|comp\b|incentive)[^.]{0,40}"
    r"\b(?:d\.?e\.?i\.?|diversity[,\s]+equity)\b|"
    # "report on the effectiveness of DEI" — ambiguous (accountability vs. a
    # skeptic's framing that DEI is ineffective); excluded for the same reason.
    r"\beffectiveness\s+of\s+(?:its\s+|the\s+)?(?:d\.?e\.?i\.?|diversity[,\s]+equity)",
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
    r"\bconsiderations?\s+include\b|\bfactors?\s+include\b|"
    # "may support / may vote for" reserves discretion (live false positive
    # 2026-07-06: T. Rowe's "we may support shareholder resolutions asking
    # for more transparency").
    r"\bmay\s+(?:support|vote\s+for|vote\s+in\s+favor)\b|"
    # Deference to the company's own management/board is the OPPOSITE of a
    # commitment (live false positive 2026-07-06: Goldman's "it is the role of
    # boards and management to determine the appropriate level of disclosure"
    # was quoted as a lobbying-disclosure commitment).
    r"\b(?:it\s+is|remains?|rests?\s+with)\s+the\s+(?:role|responsibility|purview|"
    r"prerogative)\s+of\s+(?:the\s+)?(?:boards?|management|companies|issuers?)\b|"
    r"\bpurview\s+of\s+the\s+board\b|"
    r"\b(?:boards?|management)\s+(?:is|are)\s+best\s+(?:placed|positioned)\s+to\b",
    re.IGNORECASE)


def proposal_is_oppositional(text: str) -> bool:
    """True if the proposal works AGAINST the theme (so voting it down is
    consistent, not hypocritical)."""
    return bool(_ANTI_THEME.search(text) or _ANTI_GENRE.search(text))


def commitment_is_discretionary(quote: str) -> bool:
    """True if the policy sentence explicitly reserves case-by-case discretion."""
    return bool(_DISCRETIONARY.search(quote))


# A SAY-side sentence whose object is voting down PROPOSALS/RESOLUTIONS is an
# anti-commitment: voting against such proposals is consistent with it, so it
# can never anchor a say-vs-do gap. (Live false positive 2026-07-06: Goldman's
# "We generally will vote AGAINST proposals asking for detailed disclosure of
# … lobbying expenditures" was quoted as a lobbying-disclosure commitment.)
# The object matters: "vote against DIRECTORS who fail climate oversight" is a
# PRO-theme commitment and must not match.
_OPPOSITIONAL_SAY = re.compile(
    r"\b(?:(?:generally|typically|usually|normally)\s+)?"
    r"(?:will\s+)?(?:vote|votes|voting)\s+against\s+(?:such\s+|these\s+|shareholder\s+)?"
    r"(?:proposals?|resolutions?)\b|"
    r"\b(?:do\s+not|does\s+not|will\s+not|won'?t|not\s+(?:generally\s+)?)\s*support\s+"
    r"(?:such\s+|these\s+|shareholder\s+)?(?:proposals?|resolutions?)\b|"
    r"\boppose[sd]?\s+(?:such\s+|these\s+|shareholder\s+)?(?:proposals?|resolutions?)\b",
    re.IGNORECASE)


def commitment_is_oppositional(quote: str) -> bool:
    """True if the sentence commits AGAINST theme proposals (an honest
    anti-commitment), so a vote against them cannot contradict it."""
    return bool(_OPPOSITIONAL_SAY.search(quote))


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
        f"""SELECT c.institution_id, c.doc_label, c.url, c.sha256, c.identity_sha256,
                  c.content_path,
                  {VERSION_DATE_SQL} AS version
           FROM commitments c WHERE c.superseded=0"""):
        versions.setdefault((d["institution_id"], d["doc_label"]), []).append(d)
    for vs in versions.values():
        vs.sort(key=lambda d: _yyyymmdd(d["version"]))
    # Collapse byte-distinct captures of identical policy TEXT before anything
    # diffs version N against N+1 — otherwise a CDN beacon token manufactures a
    # "policy edit" out of a document compared with itself.
    for key, vs in list(versions.items()):
        seen: set[str] = set()
        kept = []
        for d in vs:
            ident = commitment_identity(d["institution_id"], d["doc_label"],
                                       d["content_path"], d["identity_sha256"], d["sha256"])
            if ident in seen:
                continue
            seen.add(ident)
            kept.append(d)
        versions[key] = kept

    # The best promissory, non-discretionary quote for (version, theme),
    # cached so each PDF is parsed once.
    quote_cache: dict[tuple[str, str], str | None] = {}

    def theme_quote(doc_row, theme: str, pats: dict) -> str | None:
        ck = (doc_row["content_path"], theme)
        if ck not in quote_cache:
            text = capture_text(doc_row["institution_id"], doc_row["doc_label"],
                                Path(doc_row["content_path"]))
            qs = commitment_sentences(text, pats["commitment"]) if text else []
            qs = [q for q in qs if is_binding_commitment(q)
                  and not commitment_is_discretionary(q)
                  and not commitment_is_oppositional(q)
                  and score_commitment_sentence(q) >= 1.0]
            quote_cache[ck] = qs[0] if qs else None
        return quote_cache[ck]

    candidates: list[ContradictionCandidate] = []
    for (inst_id, label), vs in versions.items():
        votes = conn.execute(
            f"""SELECT v.accession, v.issuer_name, v.cusip, v.meeting_date,
                      v.vote_description, v.how_voted,
                      v.management_recommendation, v.shares_voted
               FROM votes v JOIN filings f ON f.accession = v.accession
               WHERE f.institution_id = ?
                 AND v.how_voted = 'AGAINST' AND v.is_duplicate = 0
                 AND {NON_LEGACY_VOTE_SQL}
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
