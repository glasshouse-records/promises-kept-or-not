"""The evidence engine — the query surface an investigator works through.

Everything else in this package was built around one pre-chosen pattern
(say-vs-do, by theme). An investigator does not know the pattern in advance:
they ask a question, look at what comes back, and ask the next one. This module
is the set of questions the record can answer, each returned with the citation
needed to check it by hand.

Three design decisions, each fixing something the earlier analysis got wrong:

  1. THE UNIT IS THE PROPOSAL, NOT THE BALLOT LINE. An N-PX filing reports one
     line per fund per ballot item, so a manager with 60 index funds holding
     Exxon casts "60 votes" on one proposal. The ledger holds 105,795
     shareholder-proposal lines that are only ~19,700 distinct proposals.
     Rates computed over lines weight a proposal by how many funds hold the
     stock. Here each (manager, company, meeting, proposal) counts once, with
     the line split kept so a manager voting both ways is visible as SPLIT.

  2. SAY IS TIME-ALIGNED TO DO. A vote is only ever set against the policy
     version that was public on the day of the meeting.

  3. IT IS A DERIVED INDEX, NOT THE LEDGER. `data/engine.db` is rebuilt from the
     ledger by `build()` and can be deleted at any time. It never holds a fact
     that is not recomputable, and nothing here writes to the ledger.

Every tool returns the same envelope: {tool, args, result, caveats}. Records
inside `result` carry the ids (`proposal_id`, `commitment_id`, accession,
source_url) that `verify.py` resolves when it checks a draft.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from .contradictions import (
    THEMES,
    bound_body,
    extract_text,
    identity_hash,
    proposal_is_oppositional,
)
from .http import DATA_DIR
from .ledger import DB_PATH, NON_LEGACY_VOTE_SQL, iso_meeting_date

logger = logging.getLogger(__name__)

ENGINE_PATH = DATA_DIR / "engine.db"

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE proposals (
    proposal_id    INTEGER PRIMARY KEY,
    institution_id TEXT NOT NULL,
    issuer_name    TEXT,
    cusip          TEXT,
    meeting_date   TEXT,            -- ISO
    year           INTEGER,
    description    TEXT,
    category       TEXT,
    mgmt_rec       TEXT,            -- vote vs management: WITH | AGAINST | MIXED | ''
    position       TEXT NOT NULL,   -- FOR | AGAINST | ABSTAIN | SPLIT | NONE
    n_lines        INTEGER, n_for INTEGER, n_against INTEGER, n_other INTEGER,
    themes         TEXT NOT NULL DEFAULT '',   -- ',climate,nature,' form
    oppositional   INTEGER NOT NULL DEFAULT 0, -- asks to ROLL BACK the theme
    ballot_key     TEXT,            -- same proposal across managers
    accession      TEXT, source_url TEXT, vote_id INTEGER,
    adviser        TEXT,            -- voting adviser key; NULL unless the institution has
                                    -- 2+ known advisers (then 'unlabelled' = no adviser on record)
    weight_basis   TEXT             -- 'lines' = 2022-23 legacy era (no share counts filed; the
                                    -- position counts lines) | 'shares' = XML, share-weighted |
                                    -- 'xml-no-shares' = XML whose lines filed no share counts
);
CREATE INDEX ix_p_inst ON proposals(institution_id, year);
CREATE INDEX ix_p_ballot ON proposals(ballot_key);
CREATE INDEX ix_p_cusip ON proposals(cusip);
CREATE VIRTUAL TABLE proposal_fts USING fts5(description, issuer_name, content='');
CREATE TABLE director_votes (
    director_id    INTEGER PRIMARY KEY,
    institution_id TEXT NOT NULL,
    issuer_name    TEXT, cusip TEXT,
    meeting_date   TEXT, year INTEGER,
    nominee_item   TEXT,            -- the ballot line as filed (names the nominee)
    position       TEXT NOT NULL,   -- FOR | AGAINST (incl. WITHHOLD) | ABSTAIN | SPLIT | NONE
    n_lines INTEGER, n_for INTEGER, n_against INTEGER, n_other INTEGER,
    meeting_key    TEXT,            -- same meeting across managers ('' if no CUSIP)
    accession      TEXT, source_url TEXT, vote_id INTEGER,
    isin_country   TEXT,            -- country that ISSUED the ISIN (not where the company
                                    -- is run); NULL if none, malformed or lines disagree
    adviser        TEXT,            -- as proposals.adviser
    weight_basis   TEXT             -- as proposals.weight_basis
);
CREATE TABLE pay_votes (          -- say-on-pay: management's SECTION 14A items
    pay_id         INTEGER PRIMARY KEY,
    institution_id TEXT NOT NULL,
    issuer_name    TEXT, cusip TEXT,
    meeting_date   TEXT, year INTEGER,
    description    TEXT,            -- the ballot line as filed
    kind           TEXT NOT NULL,   -- approval (FOR/AGAINST) | frequency (1/2/3 years: not for/against)
    position       TEXT NOT NULL,   -- as director_votes.position
    n_lines INTEGER, n_for INTEGER, n_against INTEGER, n_other INTEGER,
    meeting_key    TEXT,
    accession      TEXT, source_url TEXT, vote_id INTEGER,
    isin_country   TEXT,
    adviser        TEXT,            -- as proposals.adviser
    weight_basis   TEXT             -- as proposals.weight_basis
);
CREATE INDEX ix_pay_inst ON pay_votes(institution_id, year);
CREATE INDEX ix_pay_country ON pay_votes(isin_country);
CREATE INDEX ix_d_country ON director_votes(isin_country);
CREATE INDEX ix_d_inst ON director_votes(institution_id, year);
CREATE INDEX ix_d_meeting ON director_votes(meeting_key);
CREATE INDEX ix_d_cusip ON director_votes(cusip);
CREATE TABLE policy_versions (
    commitment_id  INTEGER PRIMARY KEY,   -- ledger commitments.id
    institution_id TEXT, doc_label TEXT, url TEXT,
    captured TEXT,                 -- ISO date the text was demonstrably public
    authored TEXT,                 -- date the manager's own software wrote
    via TEXT,                      -- wayback | live
    wayback_url TEXT, sha256 TEXT, n_sentences INTEGER,
    adviser TEXT,                  -- whose policy this is (config adviser_key/history), or NULL
    adviser_key_date TEXT          -- the date that key was resolved on (= captured)
);
CREATE TABLE registrants (
    institution_id TEXT, cik TEXT,   -- cik without leading zeros
    adviser TEXT, adviser_name TEXT, adviser_source TEXT, adviser_verified TEXT,
    rules TEXT,                      -- JSON: the normalised key rules (see normalize_rules)
    PRIMARY KEY (institution_id, cik)
);
CREATE TABLE adviser_scope (         -- ONLY multi-group institutions have rows
    institution_id TEXT, adviser TEXT,   -- every group key (votes and documents); 'unlabelled'
    PRIMARY KEY (institution_id, adviser)
);
CREATE TABLE scope_notes (institution_id TEXT, seq INTEGER, note TEXT);
CREATE TABLE policy_sentences (
    sentence_id INTEGER PRIMARY KEY,
    commitment_id INTEGER, institution_id TEXT, seq INTEGER, text TEXT, norm TEXT
);
CREATE INDEX ix_s_commit ON policy_sentences(commitment_id);
CREATE VIRTUAL TABLE policy_fts USING fts5(text, content='');
"""

_WS = re.compile(r"\s+")
_SPLIT = re.compile(r"(?<=[.;:?!])\d{0,3}\s+(?=[A-Z(“\"])")
_TRANS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                        " ": " ", "­": ""})
_STOP = {"shareholder", "stockholder", "proposal", "regarding", "report", "on", "the", "a",
         "an", "of", "to", "and", "for", "in", "re", "requesting", "request", "adopt",
         "approve", "sh", "shp", "company", "that", "its", "with", "by", "at", "from"}


def norm(text: str) -> str:
    """Canonical form for comparing text across captures and against quotes:
    typographic variants folded, whitespace collapsed, lower-cased."""
    return _WS.sub(" ", (text or "").translate(_TRANS)).strip().lower()


def sentences(text: str) -> list[str]:
    flat = _WS.sub(" ", (text or "").translate(_TRANS)).strip()
    return [s.strip() for s in _SPLIT.split(flat) if 30 <= len(s.strip()) <= 900]


def diff_key(sentence: str) -> str:
    """Comparison key for diffing two versions: digits and punctuation dropped,
    so a renumbered footnote or page furniture is not reported as an edit."""
    return re.sub(r"[\d\W_]+", " ", norm(sentence)).strip()


READABLE_MIN = 5      # sentences; below this a capture is an empty shell, not a policy
GAP_DAYS = 450        # managers revise annually; longer than this is a hole in the archive


def _ballot_key(cusip: str, issuer: str, date: str, desc: str) -> str:
    """Identify the same proposal across managers. Each filer words the item
    slightly differently, so the key uses the company, the meeting date and the
    description's significant words — deliberately strict: a miss leaves a
    proposal unmatched (fewer comparisons), which is recoverable; a false merge
    would compare votes on two different proposals, which is not."""
    toks = [t for t in re.findall(r"[a-z0-9]+", (desc or "").lower()) if t not in _STOP]
    who = (cusip or "").strip().upper() or re.sub(r"[^a-z0-9]", "", (issuer or "").lower())[:24]
    return f"{who}|{date}|{' '.join(sorted(set(toks))[:14])}"


MIXED_BASIS = "MIXED WEIGHT BASIS"
LEGACY_UNCATEGORISED = (
    "The 2022-23 season (meetings before 2023-07-01) is read from text filings that print no "
    "N-PX category, so those meetings are not categorised and cannot appear in this tool: "
    "its 2022 and 2023 figures undercount or omit that season, and a year-to-year change "
    "that crosses 2023-07-01 reflects coverage, not behaviour.")
SPLIT_FLOOR = 0.05    # the minority side must carry at least this share to be a split


def position_from_shares(for_: float, against: float, n_abstain: int) -> str:
    """A manager's position on one proposal, weighted by SHARES (or by lines
    where no share counts were filed). Funds routinely file a sliver the other
    way — securities on loan, a sub-account — so the minority side must reach
    5% before the position is called SPLIT rather than FOR or AGAINST."""
    decided = for_ + against
    if decided <= 0:
        return "ABSTAIN" if n_abstain else "NONE"
    share = for_ / decided
    if share >= 1 - SPLIT_FLOOR:
        return "FOR"
    if share <= SPLIT_FLOOR:
        return "AGAINST"
    return "SPLIT"


_ROLLBACK_EXTRA = re.compile(
    r"\b(remove|drop|rescind|revisit|reconsider|eliminate)\b.{0,70}"
    r"\b(emissions?|ghg|greenhouse|climate|net[\s-]?zero|decarboni[sz]ation)\b", re.IGNORECASE)
# Anti-DEI rollback wording the shared detector misses (ROADMAP h3). Scoped to the
# DEI acronym / "diversity, equity" so a pro-diversity title never matches.
_DEI = r"(?:\bd\.?e\.?i\b\.?|diversity[,\s]+equity)"
_ROLLBACK_DEI = re.compile(
    r"\b(?:remov\w*|abolish\w*|eliminat\w*|end(?:ing)?|cease|ceasing|rescind\w*)\b[^.]{0,40}?"
    + _DEI + r"|cost[\s-]?benefit\s+analysis\s+of\s+" + _DEI
    + r"|" + _DEI + r"\s+risks?\b", re.IGNORECASE)
_NOT_ROLLBACK = re.compile(
    r"\bclimate\b.{0,25}\brisks?\b.{0,25}\b(retirement|401|pension|beneficiar)", re.IGNORECASE)


def is_rollback(description: str) -> bool:
    """Does the proposal ask to ROLL BACK the theme it names? Extends the shared
    detector with wordings it misses and one it gets backwards: a proposal asking
    a company to report climate risk in its retirement plan is a pro-climate ask."""
    if _NOT_ROLLBACK.search(description or ""):
        return False
    return bool(proposal_is_oppositional(description or "")
                or _ROLLBACK_EXTRA.search(description or "")
                or _ROLLBACK_DEI.search(description or ""))


def _iso(value, name: str) -> str | None:
    """A date argument, or a refusal. A malformed or empty date must never be
    silently dropped: the answer would cover a different period than asked."""
    if value is None:
        return None
    v = str(value)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError
        date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"`{name}` must be one ISO date YYYY-MM-DD, got {value!r}") from None
    return v


_CODE = re.compile(r"[A-Z]{2}")
# the 249 officially assigned ISO 3166-1 alpha-2 codes
ISO_3166_ALPHA2 = frozenset({
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX",
    "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ",
    "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK",
    "CL", "CM", "CN", "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR",
    "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS",
    "GT", "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN",
    "IO", "IQ", "IR", "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT", "LU", "LV",
    "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ",
    "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI",
    "NL", "NO", "NP", "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW", "SA", "SB", "SC",
    "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV",
    "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR",
    "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
})      # the 249 officially assigned ISO 3166-1 alpha-2 codes


def isin_country(isins) -> str | None:
    """The country code that issued an item's ISIN, or None. `isins` are the raw
    ISINs of every fund line grouped into one item: blanks are ignored, but a
    malformed prefix (or one that is no ISO 3166-1 country, like the
    Eurobond XS or EU), or two different prefixes, make the item unknown. A wrong
    country would put a company in the wrong market; an unknown one only leaves
    it out of country filters (and is counted there)."""
    seen = set()
    for raw in isins:
        v = (raw or "").strip().upper()
        if not v:
            continue
        seen.add(v[:2] if v[:2] in ISO_3166_ALPHA2 else None)
    return seen.pop() if len(seen) == 1 and None not in seen else None


def _country(value) -> tuple[str, list[str]] | None:
    """A `country` argument as (SQL condition on isin_country, params), or a
    refusal. One code (`US`), a comma list (`US,CA`) or `non-US`. Never
    silently widened: an unrecognised value would answer a different question."""
    if value is None:
        return None
    v = str(value).strip().upper()
    if v == "NON-US":
        return "d.isin_country IS NOT NULL AND d.isin_country != 'US'", []
    codes = v.split(",")
    if not all(_CODE.fullmatch(c) for c in codes):
        raise ValueError(f"`country` must be one two-letter code (US), a comma list (US,CA) "
                         f"or non-US, got {value!r}")
    return f"d.isin_country IN ({','.join('?' * len(codes))})", codes


def _registry_names(institution_id: str) -> dict[str, str]:
    """CIK (no leading zeros) -> registrant name from the `npx_ciks` entries in
    config/institutions.yaml: the only place registrant names live."""
    from . import registry
    try:
        entries = registry.load().get(institution_id, {}).get("npx_ciks") or []
    except (OSError, KeyError, AttributeError):
        return {}
    return {str(e["cik"]).lstrip("0"): e["name"] for e in entries
            if e.get("cik") and e.get("name")}


def adviser_key(entry: dict) -> str | None:
    """The short key naming WHO votes a registrant's shares (or whose policy a
    document is). Only an explicit `adviser_key` counts: the free-text `adviser`
    label is documentation, and two spellings of it must never split a group.
    None = not on record."""
    k = entry.get("adviser_key")
    return str(k).strip() or None if k else None


_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _rule_list(spec) -> list[tuple]:
    """[(key, from, until)] from one rule dict or a list of them; bounds are
    inclusive ISO days (YAML may hand us date objects), either may be absent."""
    out = []
    for r in ([spec] if isinstance(spec, dict) else spec or []):
        k = adviser_key(r) if isinstance(r, dict) else None
        if not k and isinstance(r, dict) and r.get("key"):
            k = str(r["key"]).strip() or None
        if k:
            out.append((k, str(r["from"]) if r.get("from") else None,
                        str(r["until"]) if r.get("until") else None))
    return out


def normalize_rules(entry: dict) -> dict:
    """The registrant's key rules, as plain data (stored in the engine so query
    time resolves exactly as build time did). Resolution order, per vote line:
    series rule matching the meeting date -> registrant history -> default."""
    return {"default": adviser_key(entry),
            "history": _rule_list(entry.get("adviser_key_history")),
            "series": {str(sid).strip().upper(): _rule_list(spec)
                       for sid, spec in (entry.get("series_adviser") or {}).items()}}


def _valid_day(md) -> str | None:
    """`md` if it is a real ISO calendar day, else None."""
    if isinstance(md, str) and _ISO_DAY.fullmatch(md):
        try:
            date.fromisoformat(md)
            return md
        except ValueError:
            return None
    return None


def resolve_key(rules: dict | None, series, md) -> str | None:
    """The adviser group of one vote line. `md` is the ISO meeting date. A line
    whose date does not parse cannot be placed in a dated rule's window: where
    the series or the registrant has ANY dated rule it resolves to UNDATED (its
    own group, never paired with a policy) rather than falling to the default,
    which would be a guess about who voted it."""
    if not rules:
        return None
    day = _valid_day(md)

    def pick(lst):
        for k, lo, hi in lst:
            if lo is None and hi is None:
                return k
            if day and (lo is None or day >= lo) and (hi is None or day <= hi):
                return k
        return None

    def undated(lst):
        return not day and any(lo or hi for _k, lo, hi in lst)
    series_rules = rules["series"].get((series or "").strip().upper(), [])
    for lst in (series_rules, rules["history"]):
        hit = pick(lst)
        if hit:
            return hit
        if undated(lst):
            return UNDATED
    return rules["default"]


def validate_rules(rules: dict, where: str) -> None:
    """Refuse a rule set that would resolve ambiguously: bounds must be ISO
    calendar days, `from` <= `until`, and no two rules of one list may cover the
    same day (the first would silently win). `where` names the registrant or
    document in the error."""
    lists = [("adviser_key_history", rules["history"])] + [
        (f"series {sid}", lst) for sid, lst in rules["series"].items()]
    for name, lst in lists:
        spans = []
        for k, lo, hi in lst:
            for label, v in (("from", lo), ("until", hi)):
                if v is not None and _valid_day(v) is None:
                    raise ValueError(f"{where}, {name}: `{label}` of rule {k!r} must be an "
                                     f"ISO date YYYY-MM-DD, got {v!r}")
            if lo and hi and lo > hi:
                raise ValueError(f"{where}, {name}: rule {k!r} has from {lo} after until {hi} "
                                 "(it would cover no day; `from` must be before `until`)")
            spans.append((lo or "0000-00-00", hi or "9999-12-31", k))
        spans.sort()
        for (_a, hi1, k1), (lo2, _b, k2) in zip(spans, spans[1:], strict=False):
            if lo2 <= hi1:
                raise ValueError(f"{where}, {name}: rules {k1!r} and {k2!r} overlap "
                                 f"(both cover {lo2}): the first would silently win")


def rule_keys(rules: dict | None) -> set[str]:
    """Every key a registrant can resolve to."""
    if not rules:
        return set()
    return ({rules["default"]} - {None}) | {k for k, *_ in rules["history"]} | {
        k for lst in rules["series"].values() for k, *_ in lst}


AUTHORED_LAG_DAYS = 30   # authored this long before first capture: a stretch the archive lacks


def _authored_gap(v) -> str | None:
    """Caveat for a version whose manager-authored date is more than
    AUTHORED_LAG_DAYS before the day it was first captured: the text may have
    governed votes cast in between, and no archived text covers them."""
    a, c = (v["authored"] or "")[:10], v["captured"] or ""
    if not (_valid_day(a) and _valid_day(c)):
        return None
    days = (date.fromisoformat(c) - date.fromisoformat(a)).days
    if days <= AUTHORED_LAG_DAYS:
        return None
    return (f"{v['doc_label']} (adviser {v['adviser'] or 'n/a'}) was authored {a} but first "
            f"captured {c} ({days} days later): the wording may have been in force before "
            f"{c}, and votes between {a} and {c} are not covered by an archived text.")


def _norm_cik(cik) -> str:
    return str(cik or "").strip().lstrip("0")


UNLABELLED = "unlabelled"
UNDATED = "UNDATED"     # a vote line whose meeting date cannot place it in a dated rule
EXTERNAL = "EXTERNAL"   # series advised by an outside manager: no archived policy governs it


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------- build

# How a say-on-pay FREQUENCY ballot is answered (how often to hold the vote). These
# are choices among periods, not for/against, so such items are kept apart.
_FREQ_VOTES = frozenset({"ONE YEAR", "1 YEAR", "TWO YEARS", "2 YEARS", "THREE YEARS",
                         "3 YEARS", "1.0", "2.0", "3.0"})
_FREQ_DESC = re.compile(r"frequen|how often|every\s+((one|1|two|2|three|3)\s*(\(\d\)\s*)?)?years?\b"
                        r"|every\s+(one|1)\s*,\s*(two|2)\s*,?\s*or\s+(three|3)", re.IGNORECASE)


def _grouped(led: sqlite3.Connection, which: str,
             resolvers: dict[str, dict[str, dict]] | None = None) -> dict[tuple, dict]:
    """Collapse fund ballot lines to one decision per (manager, company, meeting,
    item), carrying line and share tallies. `which` is a fixed SQL condition
    chosen by build(), never caller input.

    `resolvers` maps an institution to {cik: key rules} ONLY for multi-group
    institutions. For those the resolved key (by registrant, fund series and
    meeting date) is part of the group key, so lines voted by different advisers
    (under different policies) are never aggregated into one decision. Every
    other institution groups exactly as it always did.

    Lines are read in ledger id order, so group ids are deterministic. Promoted 2022-23
    legacy lines (`legacy_format` set: line-weighted, no share counts) never share a group
    with XML lines: the era is part of the group key. Each group records `weight_basis`."""
    iso = iso_meeting_date("v.meeting_date")
    groups: dict[tuple, dict] = {}
    legacy: dict[tuple, list] = {}   # the pre-adviser group key -> advisers seen
    for v in led.execute(
        f"""SELECT v.id, f.institution_id AS iid, v.issuer_name, v.cusip, v.isin, {iso} AS md,
                   v.vote_description AS d, v.category_type, v.how_voted, v.shares_voted,
                   v.management_recommendation AS mr, v.accession, f.source_url, f.cik AS fcik,
                   v.vote_series AS vseries, (v.legacy_format IS NOT NULL) AS is_legacy
            FROM votes v JOIN filings f ON f.accession = v.accession
            WHERE v.is_duplicate = 0 AND {which} AND {NON_LEGACY_VOTE_SQL}
              AND f.institution_id IS NOT NULL
            ORDER BY v.id"""):
        adv = None
        if resolvers and v["iid"] in resolvers:
            adv = resolve_key(resolvers[v["iid"]].get(_norm_cik(v["fcik"])),
                              v["vseries"], v["md"]) or UNLABELLED
        era = "legacy" if v["is_legacy"] else "xml"
        key = (v["iid"], adv, (v["cusip"] or "").strip().upper() or v["issuer_name"], v["md"],
               norm(v["d"]), era)
        g = groups.get(key)
        if g is None:
            lk = (v["iid"], key[2], key[3], key[4], era)
            seen_adv = legacy.setdefault(lk, [])
            seen_adv.append(adv)
            g = groups[key] = {"row": v, "adviser": adv, "era": era,
                               "extra": len(seen_adv) > 1, "isins": set(), "for": 0, "against": 0, "abstain": 0, "other": 0,
                               "n": 0, "with_m": 0, "against_m": 0, "sf": 0.0, "sa": 0.0, "freq": 0}
        # N-PX's "management recommendation" element records whether THIS vote
        # went with (FOR) or against (AGAINST) management — not what management
        # recommended. Say-on-pay shows it plainly: FOR/FOR and AGAINST/AGAINST.
        g["isins"].add(v["isin"])
        mr = (v["mr"] or "").strip().upper()
        g["with_m"] += mr == "FOR"
        g["against_m"] += mr == "AGAINST"
        hv = (v["how_voted"] or "").strip().upper()
        g["freq"] += hv in _FREQ_VOTES
        g["n"] += 1
        sh = v["shares_voted"] or 0.0
        if hv == "FOR":
            g["for"] += 1
            g["sf"] += sh
        elif hv in ("AGAINST", "WITHHOLD"):
            g["against"] += 1
            g["sa"] += sh
        elif hv == "ABSTAIN":
            g["abstain"] += 1
        else:
            g["other"] += 1

    return groups


def _ids(groups: dict[tuple, dict]) -> list[tuple[int, dict]]:
    """(id, group) pairs. A group that merely splits an older pooled group by
    adviser is numbered after all the others, so every id outside the
    multi-adviser institutions is the one earlier builds gave it: drafts in
    flight cite these ids. Groups of the 2022-23 legacy era come after all XML groups,
    so adding legacy lines never renumbers an XML group."""
    order = []
    for era in ("xml", "legacy"):     # legacy groups are numbered after every XML group
        mine = [g for g in groups.values() if g["era"] == era]
        order += [g for g in mine if not g["extra"]] + [g for g in mine if g["extra"]]
    return list(enumerate(order, 1))


def _multi_group(led: sqlite3.Connection, rules: dict, doc_rules: dict) -> dict[str, set]:
    """The institutions whose votes or policies fall into several adviser groups,
    each with every group key it has (plus UNLABELLED if some line resolves to
    none). Multi-group = vote lines resolve to 2+ distinct keys, OR its policy
    documents carry 2+ distinct keys, OR a document key is none of the
    registrants' keys, OR it has any key at all (registrant or document) and some
    vote lines resolve to none: those lines are a group of their own and must
    never be pooled with, or paired to the policy of, a keyed adviser. Everything
    else builds and answers exactly as before."""
    doc_keys: dict[str, set] = defaultdict(set)
    for (iid, _label), r in doc_rules.items():
        doc_keys[iid] |= rule_keys(r)
    keyed = sorted({iid for iid, m in rules.items() if any(rule_keys(r) for r in m.values())}
                   | set(doc_keys))
    line_keys: dict[str, set] = defaultdict(set)
    unresolved: set[str] = set()
    if keyed:
        iso = iso_meeting_date("v.meeting_date")
        marks = ",".join("?" * len(keyed))
        for v in led.execute(
                f"""SELECT DISTINCT f.institution_id AS iid, f.cik, v.vote_series AS s, {iso} AS md
                    FROM votes v JOIN filings f ON f.accession = v.accession
                    WHERE v.is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL}
                      AND f.institution_id IN ({marks})""", keyed):
            k = resolve_key(rules.get(v["iid"], {}).get(_norm_cik(v["cik"])), v["s"], v["md"])
            (line_keys[v["iid"]].add(k) if k else unresolved.add(v["iid"]))
    out = {}
    for iid in set(keyed) | set(doc_keys):
        reg_keys = set().union(*(rule_keys(r) for r in rules.get(iid, {}).values()))
        if (len(line_keys[iid]) >= 2 or len(doc_keys[iid]) >= 2
                or (reg_keys and doc_keys[iid] - reg_keys)
                or (iid in unresolved and (reg_keys or doc_keys[iid]))):
            out[iid] = line_keys[iid] | doc_keys[iid] | ({UNLABELLED} if iid in unresolved else set())
    return out


def _weight_basis(g: dict) -> str:
    """'lines' for the 2022-23 legacy era (no share counts are ever filed there);
    for XML, 'shares' when share counts weighted the position, else 'xml-no-shares'
    (a pre-existing XML case, e.g. abstain-only, that must not read as legacy)."""
    if g.get("era") == "legacy":
        return "lines"
    return "shares" if g["sf"] + g["sa"] > 0 else "xml-no-shares"


def _position(g: dict) -> str:
    if g["sf"] + g["sa"] > 0:
        return position_from_shares(g["sf"], g["sa"], g["abstain"])
    return position_from_shares(g["for"], g["against"], g["abstain"])


def build(ledger_path: Path = DB_PATH, engine_path: Path = ENGINE_PATH,
          institutions: dict | None = None) -> dict:
    """Rebuild the derived index from the ledger. Reads the ledger read-only.
    `institutions` is the registry (config/institutions.yaml) that says which
    adviser votes each registrant and whose policy each document is."""
    if institutions is None:
        from . import registry
        try:
            institutions = registry.load()
        except (OSError, KeyError, AttributeError):
            institutions = {}
    rules = {iid: {_norm_cik(e["cik"]): normalize_rules(e)
                   for e in (inst.get("npx_ciks") or []) if e.get("cik")}
             for iid, inst in institutions.items()}
    doc_rules = {(iid, c["label"]): normalize_rules(c) for iid, inst in institutions.items()
                 for c in (inst.get("commitments") or []) if c.get("label")}
    # Optional per-label `body: {start, end}` regexes bounding the policy text of an
    # HTML page whose navigation would otherwise mint phantom versions.
    body_specs = {}
    for iid, inst in institutions.items():
        for c in inst.get("commitments") or []:
            b = c.get("body")
            if c.get("label") and b:
                if not (isinstance(b, dict) and b.get("start") and b.get("end")):
                    raise ValueError(f"{iid} document {c['label']}: body needs start and end")
                re.compile(b["start"]), re.compile(b["end"])      # bad regex stops the build
                body_specs[(iid, c["label"])] = {"start": b["start"], "end": b["end"]}
    for iid, m in rules.items():
        for cik, r in m.items():
            validate_rules(r, f"{iid} CIK {cik}")
    for (iid, label), r in doc_rules.items():
        validate_rules(r, f"{iid} document {label}")
    led = _ro(ledger_path)
    tmp = engine_path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    eng = sqlite3.connect(tmp)
    eng.executescript(SCHEMA)
    split = _multi_group(led, rules, doc_rules)

    theme_rx = {t: re.compile("|".join(spec["proposal"]), re.IGNORECASE)
                for t, spec in THEMES.items()}
    for iid, inst in institutions.items():
        for e in inst.get("npx_ciks") or []:
            if e.get("cik"):
                r = rules[iid][_norm_cik(e["cik"])]
                eng.execute("INSERT OR REPLACE INTO registrants VALUES (?,?,?,?,?,?,?)",
                            (iid, _norm_cik(e["cik"]), adviser_key(e),
                             e.get("adviser") or adviser_key(e), e.get("adviser_source"),
                             str(e["adviser_verified"]) if e.get("adviser_verified") else None,
                             json.dumps(r) if rule_keys(r) else None))
        for n, note in enumerate(inst.get("voting_scope_notes") or []):
            eng.execute("INSERT INTO scope_notes VALUES (?,?,?)", (iid, n, str(note)))
    for iid, keys in split.items():
        eng.executemany("INSERT INTO adviser_scope VALUES (?,?)", [(iid, k) for k in sorted(keys)])
    resolvers = {iid: rules[iid] for iid in split}
    groups = _grouped(led, "v.vote_source = 'SECURITY HOLDER'", resolvers)

    rows, fts = [], []
    for pid, g in _ids(groups):
        v = g["row"]
        desc = v["d"] or ""
        themes = [t for t, rx in theme_rx.items() if rx.search(desc)]
        md = v["md"] or ""
        year = int(md[:4]) if md[:4].isdigit() else None
        rows.append((pid, v["iid"], v["issuer_name"], (v["cusip"] or "").strip().upper(), md,
                     year, desc, v["category_type"],
                     ("MIXED" if g["with_m"] and g["against_m"] else
                      "AGAINST" if g["against_m"] else "WITH" if g["with_m"] else ""),
                     _position(g),
                     g["n"], g["for"],
                     g["against"], g["abstain"] + g["other"],
                     "," + ",".join(themes) + "," if themes else "",
                     int(is_rollback(desc)),
                     _ballot_key(v["cusip"], v["issuer_name"], md, desc),
                     v["accession"], v["source_url"] or "", v["id"], g["adviser"],
                     _weight_basis(g)))
        fts.append((pid, desc, v["issuer_name"] or ""))
    eng.executemany("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    eng.executemany("INSERT INTO proposal_fts(rowid, description, issuer_name) VALUES (?,?,?)", fts)

    # Management's director nominees: where board-composition policy is acted on.
    dgroups = _grouped(led, "v.vote_source = 'ISSUER' AND v.category_type = 'DIRECTOR ELECTIONS'",
                       resolvers)
    drows = []
    for did, g in _ids(dgroups):
        v = g["row"]
        md = v["md"] or ""
        cusip = (v["cusip"] or "").strip().upper()
        drows.append((did, v["iid"], v["issuer_name"], cusip, md,
                      int(md[:4]) if md[:4].isdigit() else None, v["d"] or "", _position(g),
                      g["n"], g["for"], g["against"], g["abstain"] + g["other"],
                      f"{cusip}|{md}" if cusip and md else "",
                      v["accession"], v["source_url"] or "", v["id"],
                      isin_country(g["isins"]), g["adviser"], _weight_basis(g)))
    eng.executemany("INSERT INTO director_votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", drows)
    del dgroups

    # Management's say-on-pay items (N-PX category SECTION 14A SAY-ON-PAY VOTES), so
    # pay policy can be set beside pay votes. Frequency items are kept, marked.
    pgroups = _grouped(led, "v.category_type = 'SECTION 14A SAY-ON-PAY VOTES'", resolvers)
    prows = []
    for pid_, g in _ids(pgroups):
        v = g["row"]
        md = v["md"] or ""
        cusip = (v["cusip"] or "").strip().upper()
        desc = v["d"] or ""
        prows.append((pid_, v["iid"], v["issuer_name"], cusip, md,
                      int(md[:4]) if md[:4].isdigit() else None, desc,
                      "frequency" if g["freq"] or _FREQ_DESC.search(desc) else "approval",
                      _position(g), g["n"], g["for"], g["against"], g["abstain"] + g["other"],
                      f"{cusip}|{md}" if cusip and md else "",
                      v["accession"], v["source_url"] or "", v["id"],
                      isin_country(g["isins"]), g["adviser"], _weight_basis(g)))
    eng.executemany("INSERT INTO pay_votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", prows)
    del pgroups

    # Policy text: one row per distinct TEXT version (earliest capture wins —
    # that is the date the wording is first demonstrably public).
    seen: set[tuple] = set()
    sid = 0
    for c in led.execute(
        """SELECT id, institution_id, doc_label, url, sha256, identity_sha256, content_path,
                  wayback_timestamp, retrieval_date, doc_created_at, public_by, via
           FROM commitments WHERE superseded=0
           ORDER BY COALESCE(NULLIF(substr(wayback_timestamp,1,8),''),
                             NULLIF(replace(public_by,'-',''),''),
                             replace(retrieval_date,'-','')), id"""):
        # '' = no local file (a ledger restored from a release bundle): Path('')
        # is the current directory, which exists, so test for the string first.
        path = Path(c["content_path"]) if c["content_path"] else None
        text = extract_text(path) if path is not None and path.is_file() else ""
        spec = body_specs.get((c["institution_id"], c["doc_label"]))
        if spec:
            # Bounded to the policy body. A capture whose markers do not match
            # is unreadable: no sentences, logged.
            body = bound_body(text, spec) if text else None
            if body is None and text:
                logger.warning("%s/%s capture %s: body markers not found; treated as "
                               "unreadable", c["institution_id"], c["doc_label"], c["id"])
            text = body or ""
        # Identity: the persisted hash first; else computed from the bounded text; else
        # unreadable. Never the raw bytes. Shared with release/site/dataset/newsroom.
        ih = c["identity_sha256"] or identity_hash(text)
        if not ih:
            logger.warning("%s/%s capture %s: no identity hash and no readable text; "
                           "treated as unreadable", c["institution_id"], c["doc_label"], c["id"])
        ident = (c["institution_id"], c["doc_label"], "text:" + ih if ih else "unreadable:" + c["sha256"])
        if ident in seen:
            continue
        seen.add(ident)
        sents = sentences(text)
        wb = c["wayback_timestamp"] or ""
        captured = (f"{wb[:4]}-{wb[4:6]}-{wb[6:8]}" if wb
                    else (c["public_by"] or c["retrieval_date"][:10]))
        # The version's key is resolved from the document's history on the day
        # the text was demonstrably public (`captured`), the same date the
        # in-force rule uses. The authored date is NOT used: a policy is
        # routinely written days before it takes effect (VPM's authored
        # 2026-01-06, effective 2026-01-12), which would key it to the old group.
        drules = doc_rules.get((c["institution_id"], c["doc_label"]))
        eng.execute("INSERT INTO policy_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (c["id"], c["institution_id"], c["doc_label"], c["url"], captured,
                     (c["doc_created_at"] or "")[:10],
                     "wayback" if wb else (c["via"] or "live"),
                     f"https://web.archive.org/web/{wb}/{c['url']}" if wb else "",
                     c["sha256"], len(sents),
                     resolve_key(drules, None, captured), captured))
        for seq, s in enumerate(sents):
            sid += 1
            eng.execute("INSERT INTO policy_sentences VALUES (?,?,?,?,?,?)",
                        (sid, c["id"], c["institution_id"], seq, s, norm(s)))
            eng.execute("INSERT INTO policy_fts(rowid, text) VALUES (?,?)", (sid, s))

    restored = led.execute("SELECT source FROM ingest_runs WHERE source LIKE 'restore:%' "
                           "ORDER BY id DESC LIMIT 1").fetchone()
    stats = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ballot_lines": sum(g["n"] for g in groups.values()),
        "proposals": len(rows),
        "director_items": len(drows),
        "pay_items": len(prows),
        "multi_adviser_institutions": ",".join(sorted(split)),
        "policy_versions": len(seen),
        "policy_sentences": sid,
        "ledger_max_vote_id": led.execute("SELECT MAX(id) FROM votes").fetchone()[0],
        **({"restored_from": restored["source"][len("restore:"):]} if restored else {}),
    }
    eng.executemany("INSERT INTO meta VALUES (?,?)", [(k, str(v)) for k, v in stats.items()])
    eng.commit()
    eng.close()
    led.close()
    tmp.replace(engine_path)
    return stats


# --------------------------------------------------------------------- tools

class Engine:
    """Read-only query surface. One instance per process; cheap to create."""

    def __init__(self, engine_path: Path = ENGINE_PATH, ledger_path: Path = DB_PATH):
        if not Path(engine_path).exists():
            raise FileNotFoundError(
                f"{engine_path} not built — run `glasshouse engine build` first")
        self.db = _ro(Path(engine_path))
        self.ledger = _ro(Path(ledger_path))
        self._names = {r["id"]: r["display_name"] for r in
                       self.ledger.execute("SELECT id, display_name FROM institutions")}

    # -- helpers
    def _inst(self, q: str | None) -> str | None:
        if not q:
            return None
        ql = q.strip().lower()
        if ql in self._names:
            return ql
        hits = [i for i, n in self._names.items() if ql in n.lower() or ql in i]
        if len(hits) != 1:
            raise ValueError(f"institution {q!r} matches {hits or 'nothing'}; "
                             f"known ids: {', '.join(sorted(self._names))}")
        return hits[0]

    def _has(self, table: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM sqlite_master WHERE name=?",
                                    (table,)).fetchone())

    def advisers_of(self, institution: str) -> dict:
        """The adviser groups of an institution: the distinct known keys (votes
        and policy documents), whether some votes have none on record, and
        whether the answer is `multi` (two or more groups = separately voted
        funds or documents that do not govern all the votes)."""
        iid = self._inst(institution)
        if self._has("adviser_scope"):
            keys = {r[0] for r in self.db.execute(
                "SELECT adviser FROM adviser_scope WHERE institution_id=?", (iid,))}
            if keys:
                return {"institution": iid, "known": sorted(keys - {UNLABELLED}),
                        "unlabelled": int(UNLABELLED in keys), "multi": True}
            rows = self.db.execute("SELECT adviser FROM registrants WHERE institution_id=?",
                                   (iid,)).fetchall()
            known = sorted({r["adviser"] for r in rows if r["adviser"]})
            return {"institution": iid, "known": known,
                    "unlabelled": sum(1 for r in rows if not r["adviser"]), "multi": False}
        rows = self.db.execute("SELECT adviser FROM registrants WHERE institution_id=?",
                               (iid,)).fetchall()      # an engine built before series rules
        known = sorted({r["adviser"] for r in rows if r["adviser"]})
        return {"institution": iid, "known": known,
                "unlabelled": sum(1 for r in rows if not r["adviser"]),
                "multi": len(known) >= 2}

    def _notes(self, institution) -> list[str]:
        """The institution's `voting_scope_notes`, verbatim."""
        if not institution or not self._has("scope_notes"):
            return []
        iid = self._inst(institution)
        return [r[0] for r in self.db.execute(
            "SELECT note FROM scope_notes WHERE institution_id=? ORDER BY seq", (iid,))]

    def _need_policy(self, iid: str, sc) -> None:
        """Pairing policy text with one adviser's votes needs a document THAT
        adviser published: never another group's text as a stand-in."""
        if not sc or not self.advisers_of(iid)["multi"]:
            return
        if sc == EXTERNAL:
            raise ValueError(f"{iid}: adviser {EXTERNAL} (externally advised series) is never "
                             "paired with a policy document: no archived document governs "
                             "those votes")
        if sc == UNDATED:
            raise ValueError(f"{iid}: {UNDATED} votes (meeting date unreadable, so the adviser "
                             "in force cannot be told) are never paired with a policy document")
        if not self.db.execute("SELECT 1 FROM policy_versions WHERE institution_id=? "
                               "AND adviser=?", (iid, sc)).fetchone():
            raise ValueError(f"{iid}: no archived policy for the adviser that cast these votes "
                             f"({sc}); another adviser's document is not a substitute")

    def _scope(self, institution, adviser) -> str | None:
        """Validate `adviser=` for an institution. Returns the key to filter on, or
        None when no filter applies (none given, or the institution has only one
        adviser so there is nothing to separate). Strict: an adviser the
        institution does not have is refused, never ignored."""
        if adviser in (None, ""):
            return None
        if not institution:
            raise ValueError("`adviser` needs `institution`: advisers belong to one institution")
        info = self.advisers_of(institution)
        if info["multi"]:
            valid = info["known"] + ([UNLABELLED] if info["unlabelled"] else [])
            if adviser not in valid:
                raise ValueError(f"{info['institution']} has no adviser {adviser!r}; "
                                 f"valid: {', '.join(valid)}")
            return adviser
        if info["known"] == [adviser] and not info["unlabelled"]:
            return None
        raise ValueError(f"{info['institution']} has no adviser {adviser!r} on record; "
                         f"valid: {', '.join(info['known']) or 'none (no registrant carries one)'}")

    def _need_adviser(self, institution: str, adviser, what: str) -> str | None:
        """For tools that pair policy text with votes: a multi-adviser institution
        is refused without `adviser`, because the pairing would be false."""
        info = self.advisers_of(institution)
        if info["multi"] and not adviser:
            raise ValueError(
                f"{what} pairs policy text with votes, but {info['institution']}'s funds are "
                f"voted by different advisers under different policies "
                f"({', '.join(info['known'])}): pass adviser= (one of them)")
        return self._scope(institution, adviser)

    def _only_group(self, table: dict, institution, adviser) -> dict:
        """Restrict a peers-type table (keyed `institution` or `institution/ADVISER`) to
        one group's row(s). `adviser` needs `institution` and is validated like
        everywhere else; the ranking and the shared set were already computed over
        ALL managers, so scoping changes what is shown, never the figures."""
        iid = self._inst(institution)
        sc = self._scope(iid, adviser)
        if not iid:
            return table
        if sc:
            keep = {f"{iid}/{sc}"}
        elif adviser:                      # the group's only adviser: its row is the group
            keep = {iid}
        else:
            keep = {k for k in table if k == iid or k.startswith(f"{iid}/")}
        return {k: v for k, v in table.items() if k in keep}

    def _pooled(self, institution, adviser) -> list[str]:
        """Caveats for a vote answer about an institution: its own scope notes,
        and the pooled-advisers warning for an unscoped multi-group answer."""
        if not institution:
            return []
        out = self._notes(institution)
        info = self.advisers_of(institution)
        if not info["multi"]:
            return out
        if EXTERNAL in info["known"] and adviser in (None, "", EXTERNAL):
            out.append(f"{EXTERNAL} votes belong to series advised by an outside manager: "
                       "no archived policy document governs them, so they are never paired "
                       "with one.")
        if UNDATED in info["known"] and adviser in (None, "", UNDATED):
            out.append(f"{UNDATED} votes are lines whose meeting date cannot be read on a "
                       "registrant or series whose adviser changes by date: the adviser in "
                       "force is unknown, so they are never paired with a policy document.")
        if adviser:
            return out
        return [*out, f"POOLED ADVISERS: {info['institution']}'s funds are voted by different "
                f"advisers ({', '.join(info['known'])}) under different voting policies. These "
                "figures pool separately-voted funds (each adviser's decision is its own item). "
                "Pass adviser= to scope them, and never set them against one adviser's policy."]

    def _where(self, *, institution=None, theme=None, query=None, company=None, year=None,
               position=None, include_rollback=False, since=None, until=None, adviser=None):
        w, p, join = ["1=1"], [], ""
        if institution:
            w.append("p.institution_id = ?")
            p.append(self._inst(institution))
        sc = self._scope(institution, adviser)
        if sc:
            w.append("p.adviser = ?")
            p.append(sc)
        if theme:
            if theme not in THEMES:
                raise ValueError(f"unknown theme {theme!r}; known: {', '.join(THEMES)}. "
                                 "Use query= for free text.")
            w.append("p.themes LIKE ?")
            p.append(f"%,{theme},%")
            if not include_rollback:
                w.append("p.oppositional = 0")
        if query:
            join = "JOIN proposal_fts ON proposal_fts.rowid = p.proposal_id"
            w.append("proposal_fts MATCH ?")
            p.append(query)
        if company:
            w.append("(p.issuer_name LIKE ? OR p.cusip = ?)")
            p += [f"%{company}%", company.upper()]
        if year:
            w.append("p.year = ?")
            p.append(int(year))
        if _iso(since, "since"):
            w.append("p.meeting_date >= ?")
            p.append(since)
        if _iso(until, "until"):
            w.append("p.meeting_date <= ?")
            p.append(until)
        if position:
            w.append("p.position = ?")
            p.append(position.upper())
        return join, " AND ".join(w), p

    @staticmethod
    def _prop(r) -> dict:
        return {"proposal_id": r["proposal_id"], "institution": r["institution_id"],
                "adviser": r["adviser"],
                "company": r["issuer_name"], "cusip": r["cusip"],
                "meeting_date": r["meeting_date"], "proposal": r["description"],
                "category": r["category"], "voted_vs_management": r["mgmt_rec"],
                "position": r["position"], "weight_basis": r["weight_basis"],
                "fund_lines": {"total": r["n_lines"], "for": r["n_for"],
                               "against": r["n_against"], "other": r["n_other"]},
                "themes": [t for t in r["themes"].split(",") if t],
                "asks_to_roll_back_theme": bool(r["oppositional"]),
                "accession": r["accession"], "source_url": r["source_url"]}

    @staticmethod
    def _tally(rows) -> dict:
        t = defaultdict(int)
        for r in rows:
            t[r["position"]] += r["n"]
        decided = t["FOR"] + t["AGAINST"]
        return {"proposals": sum(t.values()), "for": t["FOR"], "against": t["AGAINST"],
                "split": t["SPLIT"], "abstain": t["ABSTAIN"], "none": t["NONE"],
                "support_rate": round(t["FOR"] / decided, 4) if decided else None}

    def _basis(self, table: str, alias: str, join: str, w: str, p: list) -> list[str]:
        """A caveat when the rows an answer draws on mix weight bases: 2022-23 legacy
        decisions are line-weighted (no share counts filed), July 2023+ are share-weighted.
        A rate or year-to-year change across both compares unlike things. Empty otherwise."""
        by_year: dict = defaultdict(dict)
        for r in self.db.execute(
                f"SELECT {alias}.year y, {alias}.weight_basis b, COUNT(*) n FROM {table} {alias} "
                f"{join} WHERE {w} GROUP BY y, b", p):
            by_year[r["y"]][r["b"]] = r["n"]
        bases = {b for bs in by_year.values() for b in bs}
        if "lines" not in bases or len(bases) < 2:   # only the legacy era mixes bases
            return []
        detail = "; ".join(f"{y}: " + ", ".join(f"{n} {b}-weighted" for b, n in sorted(bs.items()))
                           for y, bs in sorted(by_year.items(), key=lambda kv: kv[0] or 0))
        return [f"{MIXED_BASIS}: these results mix line-weighted decisions (2022-23 legacy "
                "filings print no share counts: the position counts each fund line once) with "
                f"share-weighted decisions (July 2023 onward) [{detail}]. Rates, positions and "
                "year-to-year changes are NOT comparable across the two bases: a fund holding "
                "one share counts like one holding a million. Compare within one basis, or "
                "narrow with since=/until=."]

    def _weighting(self, table: str, alias: str, join: str, w: str, p: list) -> list[str]:
        """What weights the positions in THESE rows, stated from the rows themselves:
        share-weighted only for `shares` decisions, line-weighted for `lines` (2022-23
        legacy) and `xml-no-shares` ones; both, never pooled, when mixed."""
        bases = {r["b"] for r in self.db.execute(
            f"SELECT DISTINCT {alias}.weight_basis b FROM {table} {alias} {join} WHERE {w}", p)}
        out = []
        if "shares" in bases:
            out.append("Share-weighted decisions: SPLIT means the minority side carried at "
                       "least 5% of the shares voted.")
        if bases - {"shares"}:
            out.append("Line-weighted decisions (2022-23 legacy filings, or XML lines that "
                       "filed no share counts): no share counts exist, each fund line counts "
                       "once, and SPLIT means the minority side carried at least 5% of the "
                       "lines.")
        if len(out) == 2:
            out.append("Both weightings are present in this result: positions are not "
                       "comparable across them (each decision carries its `weight_basis`).")
        return out

    # -- 1. orientation
    def coverage(self) -> dict:
        """What the record contains and where it stops. Read this first."""
        meta = {r["key"]: r["value"] for r in self.db.execute("SELECT * FROM meta")}
        per = []
        for iid, name in sorted(self._names.items()):
            v = self.db.execute(
                "SELECT COUNT(*) n, MIN(meeting_date) lo, MAX(meeting_date) hi "
                "FROM proposals WHERE institution_id=?", (iid,)).fetchone()
            pv = self.db.execute(
                "SELECT COUNT(*) n, MIN(captured) lo, MAX(captured) hi "
                "FROM policy_versions WHERE institution_id=?", (iid,)).fetchone()
            reg = self.ledger.execute(
                "SELECT COUNT(DISTINCT cik) FROM filings WHERE institution_id=? "
                "AND form_type LIKE 'N-PX%'", (iid,)).fetchone()[0]
            if v["n"] or pv["n"]:
                yrs = {r["year"]: r["n"] for r in self.db.execute(
                    "SELECT year, COUNT(*) n FROM proposals WHERE institution_id=? "
                    "GROUP BY year ORDER BY year", (iid,))}
                seasons: dict = defaultdict(int)
                for r in self.ledger.execute(
                        "SELECT period_of_report p FROM filings WHERE institution_id=? "
                        "AND form_type LIKE 'N-PX%' AND report_type LIKE '%VOTING REPORT%'",
                        (iid,)):
                    pr = (r["p"] or "").strip()
                    y = pr[:4] if pr[:4].isdigit() else pr[-4:]
                    seasons[int(y) if y.isdigit() else "unknown"] += 1
                dyrs = {r["year"]: r["n"] for r in self.db.execute(
                    "SELECT year, COUNT(*) n FROM director_votes WHERE institution_id=? "
                    "GROUP BY year ORDER BY year", (iid,))}
                pyrs = {r["year"]: r["n"] for r in self.db.execute(
                    "SELECT year, COUNT(*) n FROM pay_votes WHERE institution_id=? "
                    "AND kind='approval' GROUP BY year ORDER BY year", (iid,))}
                adv = {}
                if self.advisers_of(iid)["multi"]:
                    for r in self.db.execute(
                            "SELECT adviser, COUNT(*) n FROM proposals WHERE institution_id=? "
                            "GROUP BY adviser", (iid,)):
                        adv[r["adviser"]] = {"shareholder_proposals": r["n"]}
                    for r in self.db.execute(
                            "SELECT adviser, COUNT(*) n FROM director_votes WHERE "
                            "institution_id=? GROUP BY adviser", (iid,)):
                        adv.setdefault(r["adviser"], {})["director_items"] = r["n"]
                    for r in self.db.execute(
                            "SELECT adviser, COUNT(*) n FROM pay_votes WHERE "
                            "institution_id=? AND kind='approval' GROUP BY adviser", (iid,)):
                        adv.setdefault(r["adviser"], {})["pay_items"] = r["n"]
                per.append({"institution": iid, "name": name,
                            **({"by_adviser": adv, "advisers": sorted(adv)} if adv else {}),
                            "fund_registrants_on_file": reg,
                            "vote_filings_by_season": dict(sorted(
                                seasons.items(), key=lambda kv: str(kv[0]))),
                            "director_items_by_year": dyrs,
                            "pay_items_by_year": pyrs,
                            "proposals_by_year": yrs,
                            "shareholder_proposals": v["n"],
                            "votes_from": v["lo"], "votes_to": v["hi"],
                            "policy_versions": pv["n"],
                            "policy_from": pv["lo"], "policy_to": pv["hi"]})
        by_year = {r["year"]: r["n"] for r in self.db.execute(
            "SELECT year, COUNT(*) n FROM proposals GROUP BY year ORDER BY year")}
        return _env("coverage", {}, {"index": meta, "institutions": per,
                                     "proposals_by_year": by_year,
                                     "themes": sorted(THEMES)},
                    ["Votes are SEC N-PX filings: US-registered funds only. A manager's "
                     "separate accounts and non-US funds are not here.",
                     "proposals() and its tools cover shareholder-sponsored items only. "
                     "Management's director nominees have their own tools "
                     "(director_record, director_votes, director_peers). Say-on-pay "
                     "items are indexed too (pay_record). Other management proposals "
                     "(auditors, etc.) are in the ledger but not indexed.",
                     "`vote_filings_by_season` counts voting reports on file per N-PX "
                     "season (July to June, named by its end year). A season with fewer "
                     "filings than the one before may be only partly ingested: do not "
                     "compare it with a full season.",
                     "A year with few proposals is thin coverage, not a quiet year. Check "
                     "each manager's `proposals_by_year` before comparing two years: a "
                     "sharp fall usually means filings are missing, not that behaviour "
                     "changed.",
                     "`fund_registrants_on_file` is how many of a manager's fund trusts are "
                     "ingested — often a handful of a large complex. Use filers() before "
                     "writing 'X's funds'; say 'the funds on file'.",
                     "An institution with one policy version has no edit history.",
                     "Meetings before 2023-07-01 come from 2022-23 legacy text filings: "
                     "positions there are line-weighted (no share counts filed) and the "
                     "items are not categorised, so director_record and pay_record omit "
                     "that season. Each proposal carries `weight_basis`.",
                     *[f"POOLED ADVISERS: {p['institution']} has separately-voted funds "
                       f"({', '.join(p['advisers'])}); its totals pool them. See `by_adviser` "
                       "and pass adviser= to the vote tools."
                       for p in per if p.get("advisers")]])

    # -- 2. what they said
    def policy_versions(self, institution: str, adviser=None) -> dict:
        """Every archived version of a manager's policy documents, dated."""
        iid = self._inst(institution)
        sc = self._scope(iid, adviser)
        rows = [{**dict(r), "readable": r["n_sentences"] >= READABLE_MIN}
                for r in self.db.execute(
                    "SELECT * FROM policy_versions WHERE institution_id=? "
                    + ("AND adviser=? " if sc else "") + "ORDER BY captured",
                    (iid, sc) if sc else (iid,))]
        return _env("policy_versions", _clean(institution=iid, adviser=adviser), rows,
                    [*self._notes(iid), *self._policy_owner_note(iid, adviser),
                     *self._no_text_notes(),
                     "`readable: false` is a capture whose text could not be extracted. It "
                     "proves nothing about what the policy said and is never treated as "
                     "the policy in force.",
                     "Gaps between captures are gaps in the ARCHIVE. Managers revise "
                     "annually; a missing year is a version we do not hold.",
                     "`captured` is the day the text was archived: it proves the wording "
                     "was public by then, not when it was published.",
                     "`authored` is the creation date written by the manager's own "
                     "software; it corroborates the order of versions, nothing more.",
                     *(["A version's `adviser` key is resolved from the document's "
                        "adviser_key_history on its `captured` date (`adviser_key_date`), "
                        "not its `authored` date: a policy is often written days before it "
                        "takes effect."] if any(r["adviser"] for r in rows) else []),
                     *[g for g in (_authored_gap(r) for r in rows) if g]])

    def policy_counts(self, institution: str, adviser=None) -> dict:
        """How many versions of each policy document the archive holds — one row
        per document, so a draft can cite a count (`[doc_label=…].versions`)."""
        pv = self.policy_versions(institution, adviser)
        by: dict = {}
        for v in pv["result"]:
            r = by.setdefault(v["doc_label"], {
                "doc_label": v["doc_label"], "institution_id": v["institution_id"],
                "adviser": v["adviser"], "versions": 0, "readable_versions": 0,
                "first_captured": v["captured"], "last_captured": v["captured"]})
            r["versions"] += 1
            r["readable_versions"] += bool(v["readable"])
            r["first_captured"] = min(r["first_captured"], v["captured"])
            r["last_captured"] = max(r["last_captured"], v["captured"])
            if r["adviser"] != v["adviser"]:
                r["adviser"] = None          # a document whose owner changed
        return _env("policy_counts", pv["args"], sorted(by.values(), key=lambda r: r["doc_label"]),
                    ["A count of versions HELD in the archive, not of versions the manager "
                     "published: gaps between captures are versions we do not hold.",
                     "`versions` counts every capture with distinct text, including "
                     "unreadable ones; cite `readable_versions` for versions whose wording "
                     "is on file.",
                     "`adviser` is null when the document's versions belong to different "
                     "advisers over time; see policy_versions for each one."])

    def _no_text_notes(self, ids=None) -> list[str]:
        """Say so when archived versions are on record but their wording is not on disk
        (a ledger restored from a release bundle ships URLs and hashes, not text).
        `ids` limits the check to those commitment ids; None = any version."""
        q, p = "SELECT COUNT(*) FROM policy_versions WHERE n_sentences = 0", []
        if ids:
            q += f" AND commitment_id IN ({','.join('?' * len(ids))})"
            p = list(ids)
        if not self.db.execute(q, p).fetchone()[0]:
            return []
        row = self._has("meta") and self.db.execute(
            "SELECT value FROM meta WHERE key='restored_from'").fetchone()
        origin = (f"This ledger was restored from release bundle {row[0].split(':')[0]}, "
                  "which carries policy URLs, hashes and dates but not policy text. "
                  if row else "")
        return [f"{origin}Some archived versions have no policy text on disk, so there is no "
                "wording to search or diff: an empty result here is NOT evidence that a "
                "policy lacks or dropped a provision. Re-fetch the public text with "
                "`glasshouse ingest commitments --wayback`, then `glasshouse engine build`."]

    def _policy_owner_note(self, iid, adviser) -> list[str]:
        info = self.advisers_of(iid) if iid else None
        if info and info["multi"] and not adviser:
            return [f"Each document belongs to ONE adviser ({', '.join(info['known'])}); see "
                    "`adviser` on every row. A policy may only be set against votes cast by "
                    "the adviser that published it."]
        return []

    def policy_search(self, query: str, institution: str | None = None, limit: int = 40,
                      adviser=None) -> dict:
        """Full-text search of archived policy sentences. Each hit says which
        version it is in, so presence and absence over time can be read off."""
        w, p = "policy_fts MATCH ?", [query]
        if institution:
            w += " AND s.institution_id = ?"
            p.append(self._inst(institution))
        sc = self._scope(institution, adviser)
        if sc:
            w += " AND pv.adviser = ?"
            p.append(sc)
        rows = self.db.execute(
            f"""SELECT s.sentence_id, s.commitment_id, s.institution_id, s.text,
                       pv.doc_label, pv.captured, pv.authored, pv.url, pv.wayback_url,
                       pv.adviser
                FROM policy_fts JOIN policy_sentences s ON s.sentence_id = policy_fts.rowid
                JOIN policy_versions pv ON pv.commitment_id = s.commitment_id
                WHERE {w} ORDER BY s.institution_id, pv.captured, s.seq LIMIT ?""",
            p + [limit]).fetchall()
        return _env("policy_search", _clean(query=query, institution=institution,
                                            adviser=adviser),
                    [dict(r) for r in rows],
                    [*self._notes(institution), *self._no_text_notes(),
                     *(["Hits carry the `adviser` whose policy they are: never pair a hit "
                        "with votes cast by a different adviser."]
                       if any(r["adviser"] for r in rows) else []),
                     "A sentence missing from a later version may have been reworded, not "
                     "dropped — check with policy_diff before saying it was removed."])

    def policy_diff(self, institution: str, from_id: int, to_id: int,
                    pattern: str | None = None) -> dict:
        """Sentences present in one version and not the other, verbatim."""
        iid = self._inst(institution)
        vs = {r["commitment_id"]: dict(r) for r in self.db.execute(
            "SELECT * FROM policy_versions WHERE institution_id=? AND commitment_id IN (?,?)",
            (iid, from_id, to_id))}
        if len(vs) != 2:
            raise ValueError("both ids must be policy versions of this institution "
                             "(see policy_versions)")
        if vs[from_id]["doc_label"] != vs[to_id]["doc_label"]:
            raise ValueError("these are two different documents, not two versions of one")

        def load(cid):
            return {diff_key(r["text"]): r["text"] for r in self.db.execute(
                "SELECT text FROM policy_sentences WHERE commitment_id=?", (cid,))}
        a, b = load(from_id), load(to_id)
        rx = re.compile(pattern, re.IGNORECASE) if pattern else None
        keep = (lambda s: bool(rx.search(s))) if rx else (lambda s: True)
        removed = [t for n, t in a.items() if n not in b and keep(t)]
        added = [t for n, t in b.items() if n not in a and keep(t)]
        return _env("policy_diff", {"institution": iid, "from_id": from_id, "to_id": to_id,
                                    "pattern": pattern},
                    {"from": vs[from_id], "to": vs[to_id],
                     "removed": removed, "added": added,
                     "counts": {"removed": len(removed), "added": len(added)}},
                    [*self._notes(iid), *self._no_text_notes([from_id, to_id]),
                     "`pattern` is a case-insensitive REGEX filter (policy_search's "
                     "`query` is full-text syntax; they differ).",
                     "Footnote renumbering and digit-only changes are ignored.",
                     "Sentence-level diff of extracted PDF text. A sentence that was "
                     "reflowed or lightly reworded appears as one removal plus one "
                     "addition: read both lists before calling anything a deletion.",
                     "Compare adjacent versions; a diff across many years mixes many edits."]
                    + (["`pattern` filters BOTH lists. A replacement sentence that does "
                        "not contain the pattern word is hidden, so a rewording can look "
                        "like a removal: re-run without `pattern`, or search the later "
                        "version for the rest of the sentence, before writing 'removed'."]
                       if pattern else []))

    def policy_in_force(self, institution: str, date: str, adviser=None,
                        doc_label=None) -> dict:
        """The latest version demonstrably public on `date` (ISO). For an
        institution whose funds are voted by several advisers, name the document
        (`doc_label`) or the `adviser`: picking one for you would be a guess."""
        iid = self._inst(institution)
        info = self.advisers_of(iid)
        if info["multi"] and not (adviser or doc_label):
            raise ValueError(
                f"{iid} has policies from different advisers ({', '.join(info['known'])}): "
                "pass adviser= or doc_label= (see policy_versions)")
        sc = self._scope(iid, adviser)
        self._need_policy(iid, sc)
        extra, xp = "", []
        if sc:
            extra += " AND pv.adviser = ?"
            xp.append(sc)
        if doc_label:
            labels = {r[0] for r in self.db.execute(
                "SELECT DISTINCT doc_label FROM policy_versions WHERE institution_id=?", (iid,))}
            if doc_label not in labels:
                raise ValueError(f"{iid} has no document {doc_label!r}; "
                                 f"documents: {', '.join(sorted(labels))}")
            extra += " AND pv.doc_label = ?"
            xp.append(doc_label)
        rows = [dict(r) for r in self.db.execute(
            f"""SELECT * FROM policy_versions pv
               WHERE institution_id=? AND captured <= ? AND n_sentences >= ?{extra}
               AND captured = (SELECT MAX(captured) FROM policy_versions
                               WHERE institution_id=pv.institution_id AND n_sentences >= ?
                                 AND doc_label=pv.doc_label AND captured <= ?)""",
            (iid, date, READABLE_MIN, *xp, READABLE_MIN, date))]
        for r in rows:
            r["readable"] = True
            r["days_since_capture"] = (datetime.fromisoformat(date)
                                       - datetime.fromisoformat(r["captured"])).days
        none = not rows
        result = {"versions": rows, "none_in_force": none,
                  "reason": ("no readable archived version of the selected document(s) was "
                             f"captured on or before {date}: the record cannot say what the "
                             "policy was then") if none else None}
        return _env("policy_in_force", _clean(institution=iid, date=date, adviser=adviser,
                                              doc_label=doc_label), result,
                    [*self._notes(iid),
                     "`none_in_force: true` means no readable archived version predates this "
                     "date: the record cannot say what the policy was then. That is an "
                     "absence in the archive, not evidence the manager had no policy.",
                     f"Over ~{GAP_DAYS} `days_since_capture`, later versions probably exist "
                     "that the archive does not hold: do not assert this wording was "
                     "still current.",
                     *[g for g in (_authored_gap(r) for r in rows) if g]])

    # -- 3. what they did
    def proposals(self, institution=None, theme=None, query=None, company=None, year=None,
                  position=None, include_rollback=False, limit: int = 50,
                  adviser=None) -> dict:
        """List individual proposals and how the manager voted, each cited."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company, year=year, position=position,
                                 include_rollback=include_rollback, adviser=adviser)
        total = self.db.execute(
            f"SELECT COUNT(*) FROM proposals p {join} WHERE {w}", p).fetchone()[0]
        rows = self.db.execute(
            f"SELECT p.* FROM proposals p {join} WHERE {w} "
            "ORDER BY p.meeting_date DESC, p.n_lines DESC LIMIT ?", p + [limit]).fetchall()
        return _env("proposals", _clean(institution=institution, theme=theme, query=query,
                                        company=company, year=year, position=position,
                                        include_rollback=include_rollback, limit=limit,
                                        adviser=adviser),
                    {"matching": total,
                                                   "shown": [self._prop(r) for r in rows]},
                    ["SPLIT means the manager's own funds voted both ways on the same item.",
                     *self._pooled(institution, adviser),
                     *self._basis("proposals", "p", join, w, p)])

    def voting_record(self, institution: str, theme=None, query=None, company=None,
                      include_rollback=False, since=None, until=None, adviser=None) -> dict:
        """One manager's record on a theme or free-text query, by year, counted
        per proposal. `support_rate` = FOR / (FOR + AGAINST)."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company, include_rollback=include_rollback,
                                 since=since, until=until, adviser=adviser)
        rows = self.db.execute(
            f"SELECT p.year, p.position, COUNT(*) n FROM proposals p {join} WHERE {w} "
            "GROUP BY p.year, p.position", p).fetchall()
        years = defaultdict(list)
        for r in rows:
            years[r["year"]].append(r)
        mr = self.db.execute(
            f"""SELECT SUM(p.position IN ('FOR','AGAINST') AND p.mgmt_rec='AGAINST') agm,
                       SUM(p.position IN ('FOR','AGAINST')) decided
                FROM proposals p {join} WHERE {w}""", p).fetchone()
        return _env("voting_record", _clean(institution=institution, theme=theme, query=query,
                                            company=company, since=since, until=until,
                                            include_rollback=include_rollback,
                                            adviser=adviser),
                    {"overall": self._tally(rows),
                     "by_year": {y: self._tally(rs) for y, rs in sorted(years.items(),
                                 key=lambda kv: kv[0] or 0)},
                     "against_management": {
                         "count": mr["agm"] or 0, "of": mr["decided"] or 0}},
                    [*self._pooled(institution, adviser),
                     *self._basis("proposals", "p", join, w, p),
                     "Counts are proposals, not fund ballot lines.",
                     *self._weighting("proposals", "p", join, w, p),
                     "Use fund_votes() to see which funds.",
                     "`since`/`until` take ISO dates for periods finer than a year.",
                     "`none` includes duplicate cards from contested meetings; it does not "
                     "affect the support rate.",
                     "Rollback detection recognises anti-DEI and anti-climate wording only. "
                     "Other themes (lobbying, human rights) can mix proposals from sponsors "
                     "with opposing aims: read the titles via proposals().",
                     "Rates on fewer than ~20 proposals are anecdote, not pattern.",
                     "Year-to-year change can reflect which proposals were filed, not a "
                     "change of stance. Use peers() to compare on identical proposals."]
                    + ([] if include_rollback or not theme else
                       ["Proposals asking to roll the theme back are excluded."]))

    def peers(self, theme=None, query=None, year=None, min_managers: int = 3,
              since=None, until=None, institution=None, adviser=None) -> dict:
        """Managers compared on the SAME proposals — the control for 'they just
        faced different ballots'. Only proposals at least `min_managers` voted on."""
        join, w, p = self._where(theme=theme, query=query, year=year, since=since,
                                 until=until)
        rows = self.db.execute(
            f"SELECT p.ballot_key, {_ENTITY.format('p')} AS ent, p.position "
            f"FROM proposals p {join} WHERE {w}", p).fetchall()
        by_ballot, undecided = defaultdict(dict), defaultdict(lambda: defaultdict(int))
        for r in rows:
            if r["position"] in ("FOR", "AGAINST"):
                by_ballot[r["ballot_key"]][r["ent"]] = r["position"]
            else:
                undecided[r["ballot_key"]][r["ent"]] += 1
        shared = {k: v for k, v in by_ballot.items() if len(v) >= min_managers}
        out = defaultdict(lambda: {"shared_proposals": 0, "for": 0, "with_majority": 0,
                                   "alone_against": 0, "alone_for": 0,
                                   "split_or_unvoted_not_counted": 0})
        for key, votes in shared.items():
            n_for = sum(1 for x in votes.values() if x == "FOR")
            maj = "FOR" if n_for * 2 > len(votes) else "AGAINST" if n_for * 2 < len(votes) else None
            for iid, pos in votes.items():
                o = out[iid]
                o["shared_proposals"] += 1
                o["for"] += pos == "FOR"
                o["with_majority"] += pos == maj
                o["alone_against"] += pos == "AGAINST" and n_for == len(votes) - 1
                o["alone_for"] += pos == "FOR" and n_for == 1
            for iid, n in undecided.get(key, {}).items():
                out[iid]["split_or_unvoted_not_counted"] += n
        for o in out.values():
            o["support_rate"] = (round(o["for"] / o["shared_proposals"], 4)
                                 if o["shared_proposals"] else None)
        table = dict(sorted(out.items(), key=lambda kv: (kv[1]["support_rate"] is None,
                                                         kv[1]["support_rate"] or 0)))
        table = self._only_group(table, institution, adviser)
        return _env("peers", _clean(theme=theme, query=query, year=year, since=since,
                                    until=until, min_managers=min_managers,
                                    institution=institution, adviser=adviser),
                    {"shared_proposals": len(shared), "candidate_proposals": len(by_ballot),
                     "managers": table},
                    [*_ENTITY_NOTE, *self._basis("proposals", "p", join, w, p),
                     "Proposals are matched across managers by company, meeting date and "
                     "wording. Matching is strict, so some identical proposals go "
                     "unmatched; no two different proposals are merged.",
                     "Each manager's rate covers only the shared proposals IT voted on, so "
                     "rows are comparable in kind but not over identical sets.",
                     "`split_or_unvoted_not_counted` proposals are outside that manager's "
                     "rate; if it is large relative to `shared_proposals`, say so."])

    def ballot(self, proposal_id: int) -> dict:
        """One proposal: how every tracked manager voted on it."""
        r = self.db.execute("SELECT * FROM proposals WHERE proposal_id=?",
                            (proposal_id,)).fetchone()
        if not r:
            raise ValueError(f"no proposal {proposal_id}")
        rows = self.db.execute("SELECT * FROM proposals WHERE ballot_key=? "
                               "ORDER BY institution_id, adviser", (r["ballot_key"],)).fetchall()
        return _env("ballot", {"proposal_id": proposal_id}, [self._prop(x) for x in rows],
                    _ENTITY_NOTE if any(x["adviser"] for x in rows) else [])

    # -- 4. say against do
    def say_vs_do(self, institution: str, query: str, theme: str | None = None,
                  adviser=None) -> dict:
        """Policy sentences matching `query`, by version, beside the voting
        record for the period each version was the one in force. For an
        institution whose funds are voted by several advisers, `adviser` is
        required: only that adviser's policy documents are set against only that
        adviser's votes."""
        iid = self._inst(institution)
        sc = self._need_adviser(iid, adviser, "say_vs_do")
        self._need_policy(iid, sc)
        vers = [dict(r) for r in self.db.execute(
            "SELECT * FROM policy_versions WHERE institution_id=? AND n_sentences >= ? "
            + ("AND adviser=? " if sc else "") + "ORDER BY captured",
            (iid, READABLE_MIN, *([sc] if sc else [])))]
        last_vote = self.db.execute(
            "SELECT MAX(meeting_date) FROM proposals WHERE institution_id=?"
            + (" AND adviser=?" if sc else ""), (iid, *([sc] if sc else []))).fetchone()[0]
        out = []
        for i, v in enumerate(vers):
            nxt = [x["captured"] for x in vers[i + 1:] if x["doc_label"] == v["doc_label"]]
            until = nxt[0] if nxt else "9999-12-31"
            said = [r["text"] for r in self.db.execute(
                """SELECT s.text FROM policy_fts JOIN policy_sentences s
                   ON s.sentence_id = policy_fts.rowid
                   WHERE policy_fts MATCH ? AND s.commitment_id=? ORDER BY s.seq LIMIT 8""",
                (query, v["commitment_id"]))]
            join, w, p = self._where(institution=iid, theme=theme,
                                     query=None if theme else query, adviser=sc)
            did = self.db.execute(
                f"SELECT p.position, COUNT(*) n FROM proposals p {join} WHERE {w} "
                "AND p.meeting_date >= ? AND p.meeting_date < ? GROUP BY p.position",
                p + [v["captured"], until]).fetchall()
            end = until if not until.startswith("9999") else (last_vote or v["captured"])
            days = (datetime.fromisoformat(end) - datetime.fromisoformat(v["captured"])).days
            out.append({"commitment_id": v["commitment_id"], "doc_label": v["doc_label"],
                        "in_force_from": v["captured"],
                        "in_force_until": None if until.startswith("9999") else until,
                        "window_days": days, "archive_gap": days > GAP_DAYS,
                        "said": said, "did": self._tally(did)})
        jb, wb, pb = self._where(institution=iid, theme=theme,
                                 query=None if theme else query, adviser=sc)
        uncovered = []
        if vers:
            first = min(v["captured"] for v in vers)
            join, w, p = self._where(institution=iid, theme=theme,
                                     query=None if theme else query, adviser=sc)
            n = self.db.execute(f"SELECT COUNT(*) FROM proposals p {join} WHERE {w} "
                                "AND p.meeting_date < ?", p + [first]).fetchone()[0]
            if n:
                uncovered.append(
                    f"{n} proposal{'s' if n != 1 else ''} voted"
                    f"{' by ' + sc if sc else ''} before the first archived text ({first}) "
                    "are set against no version: the record cannot say what the policy "
                    "was when they were cast.")
        return _env("say_vs_do", _clean(institution=iid, query=query, theme=theme,
                                        adviser=adviser), out,
                    [*self._notes(iid), *uncovered,
                     *self._basis("proposals", "p", jb, wb, pb),
                     *[g for g in (_authored_gap(v) for v in vers) if g],
                     *([f"Scoped to adviser {sc}: only that adviser's policy documents and "
                        "only votes cast by its funds."] if sc else []),
                     "Each vote is set only against the version public on the meeting date.",
                     "`archive_gap: true` means no capture for over a year: versions "
                     "almost certainly exist that the archive lacks, so votes late in "
                     "that window are NOT evidence against this wording. Do not build a "
                     "claim on a gapped window.",
                     "An empty `said` means the query matched nothing in that version — "
                     "check the wording with policy_search before reading it as silence.",
                     "`in_force_from` is a capture date, so the true window starts earlier; "
                     "votes just before it are attributed to the previous version.",
                     "A sentence matching the query is not necessarily a commitment. Read "
                     "it: 'we may consider' binds nothing.",
                     "This shows co-occurrence. It cannot show why a manager voted as it did."])

    def reversals(self, institution: str, theme=None, query=None, company=None,
                  adviser=None) -> dict:
        """The same proposal at the same company, voted one way one year and the
        other way a later year."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company, adviser=adviser)
        rows = self.db.execute(
            f"SELECT p.* FROM proposals p {join} WHERE {w} "
            "AND p.position IN ('FOR','AGAINST') ORDER BY p.meeting_date", p).fetchall()
        # Titles drift a little year to year ("Report on Political Spending" /
        # "Political Contributions Disclosure"), so within one company a later
        # proposal is paired with its closest earlier one by shared title words.
        by_company = defaultdict(list)
        for r in rows:
            who, _date, toks = r["ballot_key"].split("|", 2)
            # one adviser's vote is never paired with another adviser's
            by_company[(r["adviser"], who)].append((r, set(toks.split())))
        out = []
        for items in by_company.values():
            for i, (b, tb) in enumerate(items):
                best, score = None, 0.0
                for a, ta in items[:i]:
                    if a["year"] == b["year"] or not (ta | tb):
                        continue
                    j = len(ta & tb) / len(ta | tb)
                    if j > score or (j == score and best is not None
                                     and a["meeting_date"] > best["meeting_date"]):
                        best, score = a, j
                if best is not None and score >= 0.6 and best["position"] != b["position"] \
                        and (set(best["themes"].split(",")) & set(b["themes"].split(","))):
                    out.append({"from": self._prop(best), "to": self._prop(b),
                                "title_similarity": round(score, 2)})
        f2a = sum(1 for x in out if x["from"]["position"] == "FOR")
        out = {"summary": {"pairs": len(out), "for_to_against": f2a,
                           "against_to_for": len(out) - f2a}, "pairs": out}
        return _env("reversals", _clean(institution=institution, theme=theme, query=query,
                                        company=company, adviser=adviser), out,
                    [*self._pooled(institution, adviser),
                     *self._basis("proposals", "p", join,
                                  w + " AND p.position IN ('FOR','AGAINST')", p),
                     "Matched on company and the proposal title's significant words. The "
                     "two proposals can differ in substance or sponsor behind a similar "
                     "title, and the company may have changed what it discloses: read "
                     "both proxy statements before calling this a change of stance.",
                     "Check ballot() on each side: if peers moved the same way, the "
                     "proposal changed, not this manager."])

    # -- directors
    def _dwhere(self, *, institution=None, company=None, year=None, since=None, until=None,
                position=None, country=None, adviser=None):
        w, p = ["1=1"], []
        if institution:
            w.append("d.institution_id = ?")
            p.append(self._inst(institution))
        sc = self._scope(institution, adviser)
        if sc:
            w.append("d.adviser = ?")
            p.append(sc)
        if company:
            w.append("(d.issuer_name LIKE ? OR d.cusip = ?)")
            p += [f"%{company}%", company.upper()]
        if year:
            w.append("d.year = ?")
            p.append(int(year))
        if _iso(since, "since"):
            w.append("d.meeting_date >= ?")
            p.append(since)
        if _iso(until, "until"):
            w.append("d.meeting_date <= ?")
            p.append(until)
        if position:
            w.append("d.position = ?")
            p.append(position.upper())
        c = _country(country)
        if c:
            w.append(c[0])
            p += c[1]
        return " AND ".join(w), p

    def _unmatched_country(self, country, table="director_votes") -> list[str]:
        """A well-formed code that no indexed item carries is almost always a
        wrong code (UK for GB), not a market with no votes: say so, never raise."""
        c = _country(country)
        if not c or not c[1]:
            return []
        known = {r[0] for r in self.db.execute(
            f"SELECT DISTINCT isin_country FROM {table} WHERE isin_country IS NOT NULL")}
        if any(code in known for code in c[1]):
            return []
        return [f"`country` {str(country).strip().upper()!r} matches no item in the index. "
                "ISIN prefixes are ISO 3166 country codes (GB, not UK); a valid country "
                "with no votes also gives an empty result."]

    def _dexcluded(self, country, *, only_used_by_peers=False, table="director_votes",
                   noun="nominee", **filters) -> list[str]:
        """Caveats for a country-filtered query: how many items the query's OTHER
        filters matched that had no usable ISIN country (so the filter dropped
        them), and what the country means. `only_used_by_peers` restricts the
        count to items director_peers would otherwise have used (a meeting key
        and a FOR/AGAINST position), so its figure is the true count for it."""
        if country is None:
            return []
        w, p = self._dwhere(**filters)
        if only_used_by_peers:
            w += " AND d.meeting_key != '' AND d.position IN ('FOR','AGAINST')"
        n = self.db.execute(
            f"SELECT COUNT(*) FROM {table} d WHERE {w} AND d.isin_country IS NULL",
            p).fetchone()[0]
        return [f"{n} {noun} {'item was' if n == 1 else 'items were'} excluded for lacking an "
                "ISIN with a usable country (missing, malformed, or fund lines that "
                "disagreed): the country filter cannot say where those companies are.",
                "`country` is the country that issued the ISIN, not where the company is "
                "run: Cayman- or Bermuda-registered companies (KY, BM) are non-US here "
                "even when run from the US.",
                *self._unmatched_country(country, table)]

    @staticmethod
    def _dtally(t: dict) -> dict:
        # `opposed` = AGAINST/WITHHOLD only; its rate is over FOR + AGAINST.
        # `not_supported` = AGAINST/WITHHOLD + ABSTAIN; its rate is over FOR + AGAINST +
        # ABSTAIN. SPLIT (funds disagreeing) and NONE are in neither numerator nor
        # either rate's denominator, exactly as for `opposed`.
        decided = t["FOR"] + t["AGAINST"]
        ns = t["AGAINST"] + t["ABSTAIN"]
        return {"nominees": t["FOR"] + t["AGAINST"] + t["SPLIT"] + t["ABSTAIN"] + t["NONE"],
                "for": t["FOR"], "opposed": t["AGAINST"], "split": t["SPLIT"],
                "abstain": t["ABSTAIN"], "none": t["NONE"],
                "opposition_rate": round(t["AGAINST"] / decided, 4) if decided else None,
                "not_supported": ns,
                "non_support_rate": (round(ns / (decided + t["ABSTAIN"]), 4)
                                     if decided + t["ABSTAIN"] else None),
                "meetings": t["meetings"], "meetings_with_opposition": t["opp_meetings"],
                "meetings_with_non_support": t["ns_meetings"]}

    @staticmethod
    def _coding_shift(parts: dict) -> list[str]:
        """The prominent caveat for a result that lists several periods of one
        group. `parts` maps a period label to (abstain, not_supported). A filer may
        record a withheld vote as WITHHOLD (counted in `opposed`) or as ABSTAIN
        (not), and a change of filing agent changes that. If the abstain share of
        not_supported moves by more than 15 points between two periods, and one of
        them holds at least 30 abstain items, `opposed` is not comparable. So too
        when abstain vanishes: one period holds at least 30 abstain items and
        another, with at least 30 not_supported, holds none (a category that
        disappears is a recording change even when its share was small)."""
        shares = {k: a / ns for k, (a, ns) in parts.items() if ns}
        if len(shares) < 2 or max(a for a, _ in parts.values()) < _CODING_MIN_ABSTAIN:
            return []
        vanished = any(a == 0 and ns >= _CODING_MIN_ABSTAIN for a, ns in parts.values())
        if not vanished and max(shares.values()) - min(shares.values()) <= _CODING_SHIFT_POINTS:
            return []
        counts = "; ".join(f"{k}: {a} abstain of {ns} not_supported ({a / ns:.0%})"
                           for k, (a, ns) in parts.items() if ns)
        return [f"{CODING_SHIFT}: the filer's coding of withheld votes appears to differ "
                f"between these periods ({counts}). `opposed` and `opposition_rate` are "
                "NOT comparable across them: a withheld vote is counted as opposed in one "
                "and as abstain in another. Compare `not_supported` and `non_support_rate`."]

    _DIRECTOR_CAVEATS = [
        "Covers management's nominees only (N-PX source ISSUER, category DIRECTOR "
        "ELECTIONS). Dissident nominees in contested elections are in proposals().",
        "`opposed` = AGAINST or WITHHOLD, weighted across the funds on file as stated below. "
        "ABSTAIN is counted separately, though in some markets it is the only way to "
        "oppose a nominee, and in US plurality elections withhold vs abstain is a filer's "
        "coding choice in N-PX that the filings do not define: ABSTAIN may be how a filer "
        "records a withheld vote. `not_supported` = opposed + abstain and "
        "`non_support_rate` = not_supported / (for + opposed + abstain) are immune to that "
        "choice; SPLIT and NONE items are in neither figure, as for `opposed`.",
        "The record never says WHY a nominee was opposed: board diversity, "
        "overboarding, pay, attendance and independence all look identical here. "
        "A change in the rate is not evidence about any one reason.",
        "Counts are ballot items as each filer worded them; a slate voted as one "
        "item counts once. Non-US meetings are included: narrow with country= "
        "(US, US,CA or non-US) or company=.",
        "Year-to-year change can reflect which companies the funds held.",
        LEGACY_UNCATEGORISED]

    def _dcaveats(self, w: str, p: list) -> list[str]:
        """The director caveats plus the weighting actually present in these rows."""
        return [*self._DIRECTOR_CAVEATS, *self._weighting("director_votes", "d", "", w, p)]

    def _dtotal(self, w: str, p: list, table="director_votes") -> dict:
        years = self._dyears(w, p, table)
        total: dict = defaultdict(int)
        for t in years.values():
            for k, n in t.items():
                total[k] += n
        return total

    def _dyears(self, w: str, p: list, table="director_votes") -> dict:
        years: dict = defaultdict(lambda: defaultdict(int))
        for r in self.db.execute(
                f"SELECT d.year, d.position, COUNT(*) n FROM {table} d WHERE {w} "
                "GROUP BY d.year, d.position", p):
            years[r["year"]][r["position"]] += r["n"]
        for r in self.db.execute(
                f"""SELECT year, COUNT(*) m, SUM(opp > 0) om, SUM(ns > 0) nm FROM (
                        SELECT d.year, SUM(d.position='AGAINST') opp,
                               SUM(d.position IN ('AGAINST','ABSTAIN')) ns
                        FROM {table} d
                        WHERE {w} GROUP BY d.year, d.cusip, d.issuer_name, d.meeting_date)
                    GROUP BY year""", p):
            years[r["year"]]["meetings"] = r["m"]
            years[r["year"]]["opp_meetings"] = r["om"] or 0
            years[r["year"]]["ns_meetings"] = r["nm"] or 0
        return years

    _BUCKETS = (("US", "d.isin_country = 'US'"),
                ("non-US", "d.isin_country IS NOT NULL AND d.isin_country != 'US'"),
                ("unknown", "d.isin_country IS NULL"))

    def director_record(self, institution: str, company=None, since=None, until=None,
                        country=None, adviser=None) -> dict:
        """How often one manager opposed management's board nominees, by year,
        counted per nominee item and per meeting. Without `country`, also split
        into US / non-US / unknown by the country that issued the ISIN."""
        w, p = self._dwhere(institution=institution, company=company, since=since,
                            until=until, country=country, adviser=adviser)
        years = self._dyears(w, p)
        out = {"overall": self._dtally(self._dtotal(w, p)),
               "by_year": {y: self._dtally(t) for y, t in
                           sorted(years.items(), key=lambda kv: kv[0] or 0)}}
        caveats = [*self._pooled(institution, adviser), *self._dcaveats(w, p),
                   *self._basis("director_votes", "d", "", w, p),
                   *self._coding_shift({y: (t["ABSTAIN"], t["AGAINST"] + t["ABSTAIN"])
                                        for y, t in years.items()})]
        if country is None:
            out["by_country"] = {
                name: self._dtally(self._dtotal(f"{w} AND {cond}", p))
                for name, cond in self._BUCKETS}
            caveats.append(
                "`by_country` splits by the country that issued the ISIN, not where the "
                "company is run; `unknown` = no usable ISIN. Nominee counts add up to "
                "`overall`; a meeting with items in two groups is counted in both.")
        else:
            caveats += self._dexcluded(country, institution=institution, company=company,
                                       since=since, until=until, adviser=adviser)
        return _env("director_record", _clean(institution=institution, company=company,
                                              since=since, until=until, country=country,
                                              adviser=adviser),
                    out, caveats)

    _PAY_CAVEATS = [
        "Covers management's say-on-pay items only (N-PX category SECTION 14A SAY-ON-PAY "
        "VOTES): advisory votes to approve executive compensation, and non-US remuneration "
        "report / policy votes the filer filed under that category. Pay votes the filer "
        "filed under COMPENSATION (equity plans, director fees) are not here.",
        "`opposed` = AGAINST or WITHHOLD, `abstain` counted apart; `not_supported` = "
        "opposed + abstain and `non_support_rate` is immune to how a filer codes a "
        "withheld vote. `opposition_rate` is over for + opposed. SPLIT and NONE items "
        "are in neither figure. One item per ballot line: funds voting alike count once.",
        "Say-on-pay FREQUENCY items (how often to hold the vote: 1, 2 or 3 years) are NOT "
        "for/against votes and are excluded from every count and rate; they are reported "
        "only as `frequency_items`.",
        "The record never says WHY pay was opposed. Year-to-year change can reflect which "
        "companies the funds held. Non-US meetings are included: narrow with country= "
        "(US, US,CA or non-US) or company=.",
        LEGACY_UNCATEGORISED]

    def pay_record(self, institution: str, company=None, year=None, since=None, until=None,
                   country=None, adviser=None) -> dict:
        """How often one manager opposed management's say-on-pay items, by year,
        counted per ballot item and per meeting (frequency items excluded)."""
        f = {"institution": institution, "company": company, "year": year,
             "since": since, "until": until, "country": country, "adviser": adviser}
        w, p = self._dwhere(**f)
        wa = f"{w} AND d.kind = 'approval'"
        years = self._dyears(wa, p, "pay_votes")

        def tally(t: dict) -> dict:
            o = self._dtally(t)
            o["items"] = o.pop("nominees")
            return o

        nfreq = self.db.execute(
            f"SELECT COUNT(*) FROM pay_votes d WHERE {w} AND d.kind = 'frequency'",
            p).fetchone()[0]
        out = {"overall": tally(self._dtotal(wa, p, "pay_votes")),
               "by_year": {y: tally(t) for y, t in
                           sorted(years.items(), key=lambda kv: kv[0] or 0)},
               "frequency_items": nfreq}
        caveats = [*self._pooled(institution, adviser), *self._PAY_CAVEATS,
                   *self._basis("pay_votes", "d", "", wa, p),
                   *self._coding_shift({y: (t["ABSTAIN"], t["AGAINST"] + t["ABSTAIN"])
                                        for y, t in years.items()})]
        if country is not None:
            caveats += self._dexcluded(country, table="pay_votes", noun="say-on-pay",
                                       **{k: v for k, v in f.items() if k != "country"})
        return _env("pay_record", _clean(**f), out, caveats)

    def director_votes(self, institution: str, company=None, year=None, position=None,
                       since=None, until=None, limit: int = 60, country=None,
                       adviser=None) -> dict:
        """The nominee items behind director_record(), each with its filing."""
        w, p = self._dwhere(institution=institution, company=company, year=year,
                            since=since, until=until, position=position,
                            country=country, adviser=adviser)
        rows = self.db.execute(
            f"SELECT d.* FROM director_votes d WHERE {w} "
            "ORDER BY d.meeting_date DESC, d.issuer_name, d.director_id LIMIT ?",
            [*p, int(limit)]).fetchall()
        return _env("director_votes", _clean(institution=institution, company=company,
                                             year=year, position=position, since=since,
                                             until=until, limit=limit, country=country,
                                             adviser=adviser),
                    [{"director_id": r["director_id"], "institution": r["institution_id"],
                      "adviser": r["adviser"],
                      "company": r["issuer_name"], "cusip": r["cusip"],
                      "meeting_date": r["meeting_date"], "nominee_item": r["nominee_item"],
                      "position": r["position"], "weight_basis": r["weight_basis"],
                      "fund_lines": {"total": r["n_lines"], "for": r["n_for"],
                                     "against": r["n_against"], "other": r["n_other"]},
                      "accession": r["accession"], "source_url": r["source_url"]}
                     for r in rows],
                    [*self._pooled(institution, adviser), *self._dcaveats(w, p),
                     *self._basis("director_votes", "d", "", w, p),
                     f"At most {limit} rows; raise limit= for more.",
                     *self._dexcluded(country, institution=institution, company=company,
                                      year=year, since=since, until=until,
                                      position=position, adviser=adviser)])

    def director_peers(self, year=None, since=None, until=None, company=None,
                       min_managers: int = 3, country=None, institution=None,
                       adviser=None) -> dict:
        """Managers compared on the SAME shareholder meetings: at how many did
        each oppose at least one management nominee? `institution` (and
        `adviser`) show only that group's row; the figures are unchanged."""
        w, p = self._dwhere(company=company, year=year, since=since, until=until,
                            country=country)
        per: dict = defaultdict(dict)
        for r in self.db.execute(
                f"""SELECT d.meeting_key k, {_ENTITY.format('d')} i, SUM(d.position='FOR') f,
                           SUM(d.position='AGAINST') a,
                           SUM(d.position='ABSTAIN') b
                    FROM director_votes d WHERE {w} AND d.meeting_key != ''
                    GROUP BY d.meeting_key, i""", p):
            if r["f"] + r["a"]:
                per[r["k"]][r["i"]] = (r["f"], r["a"], r["b"])
        shared = {k: v for k, v in per.items() if len(v) >= min_managers}
        out: dict = defaultdict(lambda: {"shared_meetings": 0, "meetings_with_opposition": 0,
                                         "nominees": 0, "opposed": 0, "abstain": 0,
                                         "meetings_with_non_support": 0})
        for votes in shared.values():
            for iid, (f, a, b) in votes.items():
                o = out[iid]
                o["shared_meetings"] += 1
                o["meetings_with_opposition"] += a > 0
                o["meetings_with_non_support"] += a + b > 0
                o["nominees"] += f + a
                o["opposed"] += a
                o["abstain"] += b
        for o in out.values():
            o["opposition_rate"] = round(o["opposed"] / o["nominees"], 4) if o["nominees"] else None
            o["not_supported"] = o["opposed"] + o["abstain"]
            den = o["nominees"] + o["abstain"]
            o["non_support_rate"] = round(o["not_supported"] / den, 4) if den else None
            o["share_of_meetings_with_opposition"] = round(
                o["meetings_with_opposition"] / o["shared_meetings"], 4)
        table = dict(sorted(out.items(), key=lambda kv: -(kv[1]["opposition_rate"] or 0)))
        table = self._only_group(table, institution, adviser)
        return _env("director_peers", _clean(year=year, since=since, until=until,
                                             company=company, min_managers=min_managers,
                                             country=country, institution=institution,
                                             adviser=adviser),
                    {"shared_meetings": len(shared), "candidate_meetings": len(per),
                     "managers": table},
                    [*_ENTITY_NOTE, *self._basis("director_votes", "d", "", w, p),
                     "Meetings are matched by CUSIP and meeting date. Nominee items are "
                     "NOT matched one-to-one: filers word them differently, and one may "
                     "file a slate as a single item, so compare "
                     "`share_of_meetings_with_opposition` before `opposition_rate`.",
                     "`nominees` counts FOR and AGAINST items; `non_support_rate` is "
                     "`not_supported` over `nominees` + `abstain`. A filer that codes "
                     "withheld votes as ABSTAIN shows a low `opposition_rate`: compare "
                     "managers on `non_support_rate` when their `abstain` counts differ.",
                     "Each manager's figures cover only the shared meetings IT voted at.",
                     *self._dcaveats(w, p),
                     *self._dexcluded(country, only_used_by_peers=True, company=company,
                                      year=year, since=since, until=until)])

    def director_panel(self, institution: str, windows: str, country=None,
                       adviser=None) -> dict:
        """The same-companies control: director opposition in each of several
        date windows, restricted to companies the manager voted at in EVERY
        window. `windows` = "2024-01-01:2024-06-30,2025-01-01:2025-06-30"."""
        iid = self._inst(institution)
        sc = self._scope(iid, adviser)
        aw, ap = (" AND d.adviser = ?", [sc]) if sc else ("", [])
        cond = _country(country)
        cw, cp = (f" AND {cond[0]}", cond[1]) if cond else ("", [])
        spans = []
        for part in str(windows).split(","):
            a, _, b = part.strip().partition(":")
            spans.append((_iso(a, "windows start"), _iso(b, "windows end")))
        if len(spans) < 2:
            raise ValueError("`windows` needs at least two start:end spans, comma-separated")
        per = []
        for a, b in spans:
            per.append({r["cusip"]: (r["n"], r["o"], r["b"]) for r in self.db.execute(
                f"""SELECT d.cusip, SUM(d.position IN ('FOR','AGAINST')) n,
                          SUM(d.position='AGAINST') o, SUM(d.position='ABSTAIN') b
                   FROM director_votes d WHERE d.institution_id=? AND d.cusip != ''
                     AND d.meeting_date BETWEEN ? AND ?{cw}{aw} GROUP BY d.cusip""",
                (iid, a, b, *cp, *ap))
                if r["n"]})
        panel = set(per[0]).intersection(*per[1:])
        out = []
        for (a, b), w in zip(spans, per, strict=True):
            n = sum(w[c][0] for c in panel)
            o = sum(w[c][1] for c in panel)
            ab = sum(w[c][2] for c in panel)
            out.append({"since": a, "until": b, "companies_voted": len(w),
                        "nominees": n, "opposed": o,
                        "opposition_rate": round(o / n, 4) if n else None,
                        "abstain": ab, "not_supported": o + ab,
                        "non_support_rate": round((o + ab) / (n + ab), 4) if n + ab else None,
                        "companies_with_opposition": sum(1 for c in panel if w[c][1]),
                        "companies_with_non_support": sum(1 for c in panel
                                                          if w[c][1] + w[c][2])})
        first = {c for c in panel if per[0][c][1]}
        last = {c for c in panel if per[-1][c][1]}
        ns_first = {c for c in panel if per[0][c][1] + per[0][c][2]}
        ns_last = {c for c in panel if per[-1][c][1] + per[-1][c][2]}
        excluded = []
        ors_w = " OR ".join("d.meeting_date BETWEEN ? AND ?" for _ in spans)
        if country is not None:
            ors = ors_w
            n = self.db.execute(
                "SELECT COUNT(*) FROM director_votes d WHERE d.institution_id=? AND "
                f"d.cusip != '' AND d.isin_country IS NULL AND ({ors}){aw}",
                [iid, *[x for span in spans for x in span], *ap]).fetchone()[0]
            excluded = [f"{n} nominee {'item was' if n == 1 else 'items were'} excluded for "
                        "lacking an ISIN with a usable country (missing, malformed, or fund "
                        "lines that disagreed) within these windows.",
                        self._dexcluded(country, institution=institution, adviser=adviser)[1],
                        *self._unmatched_country(country)]
        return _env("director_panel", _clean(institution=institution, windows=windows,
                                             country=country, adviser=adviser),
                    {"companies_in_every_window": len(panel), "windows": out,
                     "opposed_in_first_and_last": len(first & last),
                     "opposed_in_first_only": len(first - last),
                     "opposed_in_last_only": len(last - first),
                     "non_support_in_first_and_last": len(ns_first & ns_last),
                     "non_support_in_first_only": len(ns_first - ns_last),
                     "non_support_in_last_only": len(ns_last - ns_first)},
                    [*self._pooled(institution, adviser),
                     *self._basis("director_votes", "d", "",
                                  f"d.institution_id=? AND d.cusip != ''{cw}{aw} AND ({ors_w})",
                                  [iid, *cp, *ap, *[x for span in spans for x in span]]),
                     *self._coding_shift({f"{x['since']}:{x['until']}":
                                          (x["abstain"], x["not_supported"]) for x in out}),
                     "Companies are matched by CUSIP; a company that changed CUSIP or "
                     "filed none drops out of the panel.",
                     "The companies are constant; the nominees and the funds holding "
                     "them are not.",
                     *self._dcaveats(
                         f"d.institution_id=? AND d.cusip != ''{cw}{aw} AND ({ors_w})",
                         [iid, *cp, *ap, *[x for span in spans for x in span]]),
                     *excluded])

    def fund_votes(self, proposal_id: int, adviser=None) -> dict:
        """The individual fund lines behind one position: which fund series voted
        how, with how many shares, from which filing. A proposal id already
        belongs to one adviser; `adviser`, if given, must agree with it."""
        r = self.db.execute("SELECT * FROM proposals WHERE proposal_id=?",
                            (proposal_id,)).fetchone()
        if not r:
            raise ValueError(f"no proposal {proposal_id}")
        if adviser and adviser != r["adviser"]:
            raise ValueError(f"proposal {proposal_id} was voted by adviser "
                             f"{r['adviser']!r}, not {adviser!r}")
        rules = {}                 # cik -> the registrant's key rules (see normalize_rules)
        if r["adviser"]:
            rules = {x["cik"]: json.loads(x["rules"]) if x["rules"] else
                     {"default": x["adviser"], "history": [], "series": {}}
                     for x in self.db.execute(
                         "SELECT cik, adviser, rules FROM registrants WHERE institution_id=?",
                         (r["institution_id"],))}
        iso = iso_meeting_date("v.meeting_date")
        lines = []
        names: dict[str, str | None] = {}

        def series_name(sid):
            """Name of the series from the most recent filing that names it."""
            if sid not in names:
                row = self.ledger.execute(
                    """SELECT fs.name FROM fund_series fs JOIN filings f
                         ON f.accession = fs.accession
                       WHERE fs.series_id=? AND fs.name IS NOT NULL AND fs.name != ''
                       ORDER BY COALESCE(f.filing_date, f.period_of_report, '') DESC,
                                f.accession DESC LIMIT 1""", (sid,)).fetchone()
                names[sid] = row[0] if row else None
            return names[sid]

        for v in self.ledger.execute(
            f"""SELECT v.vote_series, v.how_voted, v.shares_voted, v.vote_description,
                       v.accession, f.cik, f.source_url
                FROM votes v JOIN filings f ON f.accession = v.accession
                WHERE f.institution_id=? AND v.is_duplicate=0 AND {NON_LEGACY_VOTE_SQL}
                  AND v.vote_source='SECURITY HOLDER' AND {iso}=?
                  AND (v.cusip=? OR v.issuer_name=?)""",
                (r["institution_id"], r["meeting_date"], r["cusip"], r["issuer_name"])):
            if r["adviser"] and (resolve_key(rules.get(_norm_cik(v["cik"])),
                                             v["vote_series"], r["meeting_date"])
                                 or UNLABELLED) != r["adviser"]:
                continue                       # another adviser's fund, another policy
            if norm(v["vote_description"]) == norm(r["description"]):
                lines.append({"fund_series": v["vote_series"],
                              "fund_series_name": series_name(v["vote_series"]),
                              "registrant_cik": v["cik"],
                              "how_voted": v["how_voted"], "shares": v["shares_voted"],
                              "accession": v["accession"], "source_url": v["source_url"]})
        tot = defaultdict(float)
        for ln in lines:
            hv = (ln["how_voted"] or "").upper()
            tot["for" if hv == "FOR" else "against" if hv in ("AGAINST", "WITHHOLD")
                else "other"] += ln["shares"] or 0.0
        return _env("fund_votes", _clean(proposal_id=proposal_id, adviser=adviser),
                    {"proposal": self._prop(r), "lines": lines,
                     "shares": {k: tot[k] for k in ("for", "against", "other")}},
                    [*self._notes(r["institution_id"]),
                     "One fund series can file several lines for one item. Compare the "
                     "same series across years before saying a manager changed its vote: "
                     "a different mix of funds can move the total on its own."])

    def filers(self, institution: str, adviser=None) -> dict:
        """Which of a manager's fund registrants are on file — how much of the
        manager the vote record actually covers."""
        iid = self._inst(institution)
        rows = [dict(r) for r in self.ledger.execute(
            f"""SELECT f.cik, COUNT(*) AS filings,
                      MIN({iso_meeting_date("f.period_of_report")}) AS first_period,
                      MAX({iso_meeting_date("f.period_of_report")}) AS last_period,
                      (SELECT COUNT(DISTINCT fs.series_id) FROM fund_series fs
                        JOIN filings f2 ON f2.accession = fs.accession
                        WHERE f2.cik = f.cik) AS fund_series
               FROM filings f WHERE f.institution_id=? AND f.form_type LIKE 'N-PX%'
               GROUP BY f.cik ORDER BY filings DESC""", (iid,))]
        names = _registry_names(iid)
        reg = {x["cik"]: x for x in self.db.execute(
            "SELECT * FROM registrants WHERE institution_id=?", (iid,))}
        sc = self._scope(iid, adviser)
        for r in rows:
            k = _norm_cik(r["cik"])
            r["registrant_name"] = names.get(k)
            x = reg.get(k)
            r["adviser"] = (x["adviser"] if x else None) or None
            r["adviser_name"] = x["adviser_name"] if x and x["adviser"] else None
            r["adviser_source"] = x["adviser_source"] if x else None
            r["adviser_verified"] = x["adviser_verified"] if x else None
            rl = json.loads(x["rules"]) if x and x["rules"] else None
            r["adviser_history"] = [{"key": k, "from": lo, "until": hi}
                                    for k, lo, hi in (rl["history"] if rl else [])]
            r["series_overrides"] = len(rl["series"]) if rl else 0
            r["advisers"] = sorted(rule_keys(rl) or ({r["adviser"]} - {None}))
        if sc:
            rows = [r for r in rows if sc in r["advisers"]]
        return _env("filers", _clean(institution=iid, adviser=adviser),
                    {"registrants": len(rows), "filers": rows,
                     "name_source": "config/institutions.yaml npx_ciks (the ledger stores "
                                    "no registrant names); null = no name on record"},
                    [*self._pooled(iid, adviser),
                     "A registrant is one fund trust. Large managers have dozens; this is "
                     "the subset ingested. Different registrants of one group can be "
                     "advised by different entities with their own voting policies.",
                     "`adviser` is who votes the fund's shares, from config/institutions.yaml "
                     "with the prospectus cited in `adviser_source`. null = none on record: "
                     "confirm it from the fund's prospectus before attributing a vote to a "
                     "policy."])

    # -- 5. context
    def company(self, name: str, year: int | None = None, limit: int = 60) -> dict:
        """Every shareholder proposal at a company, and each manager's vote."""
        join, w, p = self._where(company=name, year=year)
        rows = self.db.execute(
            f"SELECT p.* FROM proposals p WHERE {w} "
            "ORDER BY p.meeting_date DESC, p.ballot_key, p.institution_id LIMIT ?",
            p + [limit]).fetchall()
        enf = [dict(r) for r in self.ledger.execute(
            """SELECT id, agency, company_name, action_date, resolution_type, penalty_usd,
                      primary_ref, source_url FROM enforcement_actions
               WHERE company_name LIKE ? AND is_duplicate=0
                 AND resolution_type NOT IN ('sanction_designation','unverified','allegation')
               ORDER BY action_date DESC LIMIT 15""", (f"%{name}%",))]
        return _env("company", {"name": name, "year": year},
                    {"proposals": [self._prop(r) for r in rows],
                     "enforcement_name_matches": enf},
                    ["Enforcement rows are matched to the company BY NAME ONLY. A name "
                     "match is a lead to check against the primary document, never a fact "
                     "about this company."])

    def enforcement(self, institution: str) -> dict:
        """Concluded enforcement actions naming the manager itself."""
        iid = self._inst(institution)
        name = self._names[iid]
        stem = re.split(r"[ ,(]", name)[0]
        rows = [dict(r) for r in self.ledger.execute(
            """SELECT id, agency, company_name, action_date, resolution_type, penalty_usd,
                      primary_ref, description, source_url, retrieval_date
               FROM enforcement_actions WHERE company_name LIKE ? AND is_duplicate=0
                 AND resolution_type NOT IN ('sanction_designation','unverified','allegation')
               ORDER BY action_date DESC LIMIT 60""", (f"%{stem}%",))]
        return _env("enforcement", {"institution": iid}, rows,
                    [f"Matched on the name stem {stem!r}: confirm each row names this "
                     "group and not an unrelated company before using it.",
                     "Resolution types are legally distinct. A settlement or DPA is not a "
                     "conviction; say exactly what the row says."])

    def holdings(self, institution: str, company: str) -> dict:
        """A manager's reported 13-F position in a company, by filing."""
        iid = self._inst(institution)
        rows = [dict(r) for r in self.ledger.execute(
            """SELECT h.issuer_name, h.cusip, SUM(h.value_usd) value_usd, SUM(h.shares) shares,
                      f.accession, f.period_of_report, f.source_url
               FROM holdings h JOIN filings f ON f.accession = h.accession
               WHERE f.institution_id=? AND (h.issuer_name LIKE ? OR h.cusip=?)
               GROUP BY f.accession, h.cusip ORDER BY f.period_of_report DESC LIMIT 20""",
            (iid, f"%{company}%", company.upper()))]
        return _env("holdings", {"institution": iid, "company": company}, rows,
                    ["13-F positions. An index fund holds a stock because the index does; "
                     "a holding alone says nothing about the manager's view."])

    # -- 6. checking
    def verify_quote(self, commitment_id: int, text: str) -> dict:
        """Is this exact wording in that archived version? Whitespace and
        typographic quotes are normalised; nothing else is forgiven."""
        v = self.db.execute("SELECT * FROM policy_versions WHERE commitment_id=?",
                            (commitment_id,)).fetchone()
        if not v:
            raise ValueError(f"no policy version {commitment_id}")
        body = " ".join(r["norm"] for r in self.db.execute(
            "SELECT norm FROM policy_sentences WHERE commitment_id=? ORDER BY seq",
            (commitment_id,)))
        return _env("verify_quote", {"commitment_id": commitment_id, "text": text},
                    {"present": norm(text) in body, "version": dict(v)}, [])

    def sql(self, query: str, limit: int = 200) -> dict:
        """Read-only SQL over the engine index (tables: proposals,
        policy_versions, policy_sentences). For questions no tool covers."""
        if not query.lstrip().lower().startswith(("select", "with")):
            raise ValueError("read-only: SELECT / WITH only")
        rows = [dict(r) for r in self.db.execute(query).fetchmany(limit)]
        return _env("sql", {"query": query}, rows,
                    ["Hand-written SQL bypasses the tools' guards. `proposals` is already "
                     "one row per manager per proposal; do not re-weight by n_lines."])


CODING_SHIFT = "CODING SHIFT"          # prefix of the caveat desk.py looks for
_CODING_SHIFT_POINTS = 0.15
_CODING_MIN_ABSTAIN = 30

# Peers-type tools compare managers: a group with several advisers is several
# managers, so each adviser is its own entry (`t_rowe_price/TRPA`).
_ENTITY = ("CASE WHEN {0}.adviser IS NULL THEN {0}.institution_id "
           "ELSE {0}.institution_id || '/' || {0}.adviser END")
_ENTITY_NOTE = ["An entry written `institution/ADVISER` is one adviser of a group whose funds "
                "are voted by different advisers under different policies; advisers are "
                "compared separately, never pooled."]

# Tools that report votes (the desk requires `adviser` on a claim from one of
# these about a multi-adviser institution).
VOTE_TOOLS = ("proposals", "voting_record", "reversals", "say_vs_do", "director_record",
              "director_votes", "director_panel", "pay_record")

TOOLS = ("coverage", "policy_versions", "policy_counts", "policy_search", "policy_diff", "policy_in_force",
         "proposals", "voting_record", "peers", "ballot", "fund_votes", "reversals", "say_vs_do", "filers",
         "director_record", "director_votes", "director_peers", "director_panel", "pay_record",
         "company",
         "enforcement", "holdings", "verify_quote", "sql")


def _clean(**kw) -> dict:
    """Args as the caller gave them, minus the unset ones — so an envelope's
    `args` can be fed straight back to `call()` to reproduce the result."""
    return {k: v for k, v in kw.items() if v not in (None, False)}


def _env(tool: str, args: dict, result, caveats: list[str]) -> dict:
    return {"tool": tool, "args": args, "result": result, "caveats": caveats}


def call(tool: str, **kwargs) -> dict:
    """Dispatch by name — the one entry point the CLI, MCP server and the draft
    verifier all share, so a claim is checked by the same code that produced it."""
    if tool not in TOOLS:
        raise ValueError(f"unknown tool {tool!r}; tools: {', '.join(TOOLS)}")
    return getattr(Engine(), tool)(**kwargs)


def dumps(env: dict) -> str:
    return json.dumps(env, indent=1, default=str, ensure_ascii=False)
