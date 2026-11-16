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
import re
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .contradictions import THEMES, extract_text, proposal_is_oppositional
from .http import DATA_DIR
from .ledger import DB_PATH, iso_meeting_date

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
    accession      TEXT, source_url TEXT, vote_id INTEGER
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
    accession      TEXT, source_url TEXT, vote_id INTEGER
);
CREATE INDEX ix_d_inst ON director_votes(institution_id, year);
CREATE INDEX ix_d_meeting ON director_votes(meeting_key);
CREATE INDEX ix_d_cusip ON director_votes(cusip);
CREATE TABLE policy_versions (
    commitment_id  INTEGER PRIMARY KEY,   -- ledger commitments.id
    institution_id TEXT, doc_label TEXT, url TEXT,
    captured TEXT,                 -- ISO date the text was demonstrably public
    authored TEXT,                 -- date the manager's own software wrote
    via TEXT,                      -- wayback | live
    wayback_url TEXT, sha256 TEXT, n_sentences INTEGER
);
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
_NOT_ROLLBACK = re.compile(
    r"\bclimate\b.{0,25}\brisks?\b.{0,25}\b(retirement|401|pension|beneficiar)", re.IGNORECASE)


def is_rollback(description: str) -> bool:
    """Does the proposal ask to ROLL BACK the theme it names? Extends the shared
    detector with wordings it misses and one it gets backwards: a proposal asking
    a company to report climate risk in its retirement plan is a pro-climate ask."""
    if _NOT_ROLLBACK.search(description or ""):
        return False
    return bool(proposal_is_oppositional(description or "")
                or _ROLLBACK_EXTRA.search(description or ""))


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------- build

def _grouped(led: sqlite3.Connection, which: str) -> dict[tuple, dict]:
    """Collapse fund ballot lines to one decision per (manager, company, meeting,
    item), carrying line and share tallies. `which` is a fixed SQL condition
    chosen by build(), never caller input."""
    iso = iso_meeting_date("v.meeting_date")
    groups: dict[tuple, dict] = {}
    for v in led.execute(
        f"""SELECT v.id, f.institution_id AS iid, v.issuer_name, v.cusip, {iso} AS md,
                   v.vote_description AS d, v.category_type, v.how_voted, v.shares_voted,
                   v.management_recommendation AS mr, v.accession, f.source_url
            FROM votes v JOIN filings f ON f.accession = v.accession
            WHERE v.is_duplicate = 0 AND {which}
              AND f.institution_id IS NOT NULL"""):
        key = (v["iid"], (v["cusip"] or "").strip().upper() or v["issuer_name"], v["md"],
               norm(v["d"]))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"row": v, "for": 0, "against": 0, "abstain": 0, "other": 0,
                               "n": 0, "with_m": 0, "against_m": 0, "sf": 0.0, "sa": 0.0}
        # N-PX's "management recommendation" element records whether THIS vote
        # went with (FOR) or against (AGAINST) management — not what management
        # recommended. Say-on-pay shows it plainly: FOR/FOR and AGAINST/AGAINST.
        mr = (v["mr"] or "").strip().upper()
        g["with_m"] += mr == "FOR"
        g["against_m"] += mr == "AGAINST"
        hv = (v["how_voted"] or "").strip().upper()
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


def _position(g: dict) -> str:
    if g["sf"] + g["sa"] > 0:
        return position_from_shares(g["sf"], g["sa"], g["abstain"])
    return position_from_shares(g["for"], g["against"], g["abstain"])


def build(ledger_path: Path = DB_PATH, engine_path: Path = ENGINE_PATH) -> dict:
    """Rebuild the derived index from the ledger. Reads the ledger read-only."""
    led = _ro(ledger_path)
    tmp = engine_path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    eng = sqlite3.connect(tmp)
    eng.executescript(SCHEMA)

    theme_rx = {t: re.compile("|".join(spec["proposal"]), re.IGNORECASE)
                for t, spec in THEMES.items()}
    groups = _grouped(led, "v.vote_source = 'SECURITY HOLDER'")

    rows, fts = [], []
    for pid, g in enumerate(groups.values(), 1):
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
                     v["accession"], v["source_url"] or "", v["id"]))
        fts.append((pid, desc, v["issuer_name"] or ""))
    eng.executemany("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    eng.executemany("INSERT INTO proposal_fts(rowid, description, issuer_name) VALUES (?,?,?)", fts)

    # Management's director nominees: where board-composition policy is acted on.
    dgroups = _grouped(led, "v.vote_source = 'ISSUER' AND v.category_type = 'DIRECTOR ELECTIONS'")
    drows = []
    for did, g in enumerate(dgroups.values(), 1):
        v = g["row"]
        md = v["md"] or ""
        cusip = (v["cusip"] or "").strip().upper()
        drows.append((did, v["iid"], v["issuer_name"], cusip, md,
                      int(md[:4]) if md[:4].isdigit() else None, v["d"] or "", _position(g),
                      g["n"], g["for"], g["against"], g["abstain"] + g["other"],
                      f"{cusip}|{md}" if cusip and md else "",
                      v["accession"], v["source_url"] or "", v["id"]))
    eng.executemany("INSERT INTO director_votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", drows)
    del dgroups

    # Policy text: one row per distinct TEXT version (earliest capture wins —
    # that is the date the wording is first demonstrably public).
    seen: set[tuple] = set()
    sid = 0
    for c in led.execute(
        """SELECT id, institution_id, doc_label, url, sha256, text_sha256, content_path,
                  wayback_timestamp, retrieval_date, doc_created_at
           FROM commitments
           ORDER BY COALESCE(NULLIF(substr(wayback_timestamp,1,8),''),
                             replace(retrieval_date,'-','')), id"""):
        ident = (c["institution_id"], c["doc_label"], c["text_sha256"] or "raw:" + c["sha256"])
        if ident in seen:
            continue
        seen.add(ident)
        path = Path(c["content_path"])
        text = extract_text(path) if path.exists() else ""
        sents = sentences(text)
        wb = c["wayback_timestamp"] or ""
        captured = (f"{wb[:4]}-{wb[4:6]}-{wb[6:8]}" if wb else c["retrieval_date"][:10])
        eng.execute("INSERT INTO policy_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (c["id"], c["institution_id"], c["doc_label"], c["url"], captured,
                     (c["doc_created_at"] or "")[:10], "wayback" if wb else "live",
                     f"https://web.archive.org/web/{wb}/{c['url']}" if wb else "",
                     c["sha256"], len(sents)))
        for seq, s in enumerate(sents):
            sid += 1
            eng.execute("INSERT INTO policy_sentences VALUES (?,?,?,?,?,?)",
                        (sid, c["id"], c["institution_id"], seq, s, norm(s)))
            eng.execute("INSERT INTO policy_fts(rowid, text) VALUES (?,?)", (sid, s))

    stats = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ballot_lines": sum(g["n"] for g in groups.values()),
        "proposals": len(rows),
        "director_items": len(drows),
        "policy_versions": len(seen),
        "policy_sentences": sid,
        "ledger_max_vote_id": led.execute("SELECT MAX(id) FROM votes").fetchone()[0],
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

    def _where(self, *, institution=None, theme=None, query=None, company=None, year=None,
               position=None, include_rollback=False, since=None, until=None):
        w, p, join = ["1=1"], [], ""
        if institution:
            w.append("p.institution_id = ?")
            p.append(self._inst(institution))
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
        if since:
            w.append("p.meeting_date >= ?")
            p.append(since)
        if until:
            w.append("p.meeting_date <= ?")
            p.append(until)
        if position:
            w.append("p.position = ?")
            p.append(position.upper())
        return join, " AND ".join(w), p

    @staticmethod
    def _prop(r) -> dict:
        return {"proposal_id": r["proposal_id"], "institution": r["institution_id"],
                "company": r["issuer_name"], "cusip": r["cusip"],
                "meeting_date": r["meeting_date"], "proposal": r["description"],
                "category": r["category"], "voted_vs_management": r["mgmt_rec"],
                "position": r["position"],
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
                per.append({"institution": iid, "name": name,
                            "fund_registrants_on_file": reg,
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
                     "(director_record, director_votes, director_peers). Other management "
                     "proposals (say-on-pay, auditors) are in the ledger but not indexed.",
                     "A year with few proposals is thin coverage, not a quiet year. Check "
                     "each manager's `proposals_by_year` before comparing two years: a "
                     "sharp fall usually means filings are missing, not that behaviour "
                     "changed.",
                     "`fund_registrants_on_file` is how many of a manager's fund trusts are "
                     "ingested — often a handful of a large complex. Use filers() before "
                     "writing 'X's funds'; say 'the funds on file'.",
                     "An institution with one policy version has no edit history."])

    # -- 2. what they said
    def policy_versions(self, institution: str) -> dict:
        """Every archived version of a manager's policy documents, dated."""
        iid = self._inst(institution)
        rows = [{**dict(r), "readable": r["n_sentences"] >= READABLE_MIN}
                for r in self.db.execute(
                    "SELECT * FROM policy_versions WHERE institution_id=? ORDER BY captured",
                    (iid,))]
        return _env("policy_versions", {"institution": iid}, rows,
                    ["`readable: false` is a capture whose text could not be extracted. It "
                     "proves nothing about what the policy said and is never treated as "
                     "the policy in force.",
                     "Gaps between captures are gaps in the ARCHIVE. Managers revise "
                     "annually; a missing year is a version we do not hold.",
                     "`captured` is the day the text was archived: it proves the wording "
                     "was public by then, not when it was published.",
                     "`authored` is the creation date written by the manager's own "
                     "software; it corroborates the order of versions, nothing more."])

    def policy_search(self, query: str, institution: str | None = None, limit: int = 40) -> dict:
        """Full-text search of archived policy sentences. Each hit says which
        version it is in, so presence and absence over time can be read off."""
        w, p = "policy_fts MATCH ?", [query]
        if institution:
            w += " AND s.institution_id = ?"
            p.append(self._inst(institution))
        rows = self.db.execute(
            f"""SELECT s.sentence_id, s.commitment_id, s.institution_id, s.text,
                       pv.doc_label, pv.captured, pv.authored, pv.url, pv.wayback_url
                FROM policy_fts JOIN policy_sentences s ON s.sentence_id = policy_fts.rowid
                JOIN policy_versions pv ON pv.commitment_id = s.commitment_id
                WHERE {w} ORDER BY s.institution_id, pv.captured, s.seq LIMIT ?""",
            p + [limit]).fetchall()
        return _env("policy_search", {"query": query, "institution": institution},
                    [dict(r) for r in rows],
                    ["A sentence missing from a later version may have been reworded, not "
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
                    ["`pattern` is a case-insensitive REGEX filter (policy_search's "
                     "`query` is full-text syntax; they differ).",
                     "Footnote renumbering and digit-only changes are ignored.",
                     "Sentence-level diff of extracted PDF text. A sentence that was "
                     "reflowed or lightly reworded appears as one removal plus one "
                     "addition: read both lists before calling anything a deletion.",
                     "Compare adjacent versions; a diff across many years mixes many edits."])

    def policy_in_force(self, institution: str, date: str) -> dict:
        """The latest version demonstrably public on `date` (ISO)."""
        iid = self._inst(institution)
        rows = [dict(r) for r in self.db.execute(
            """SELECT * FROM policy_versions pv
               WHERE institution_id=? AND captured <= ? AND n_sentences >= ?
               AND captured = (SELECT MAX(captured) FROM policy_versions
                               WHERE institution_id=pv.institution_id AND n_sentences >= ?
                                 AND doc_label=pv.doc_label AND captured <= ?)""",
            (iid, date, READABLE_MIN, READABLE_MIN, date))]
        for r in rows:
            r["readable"] = True
            r["days_since_capture"] = (datetime.fromisoformat(date)
                                       - datetime.fromisoformat(r["captured"])).days
        return _env("policy_in_force", {"institution": iid, "date": date}, rows,
                    ["Empty means no readable archived version predates this date — the "
                     "record cannot say what the policy was then.",
                     f"Over ~{GAP_DAYS} `days_since_capture`, later versions probably exist "
                     "that the archive does not hold: do not assert this wording was "
                     "still current."])

    # -- 3. what they did
    def proposals(self, institution=None, theme=None, query=None, company=None, year=None,
                  position=None, include_rollback=False, limit: int = 50) -> dict:
        """List individual proposals and how the manager voted, each cited."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company, year=year, position=position,
                                 include_rollback=include_rollback)
        total = self.db.execute(
            f"SELECT COUNT(*) FROM proposals p {join} WHERE {w}", p).fetchone()[0]
        rows = self.db.execute(
            f"SELECT p.* FROM proposals p {join} WHERE {w} "
            "ORDER BY p.meeting_date DESC, p.n_lines DESC LIMIT ?", p + [limit]).fetchall()
        return _env("proposals", _clean(institution=institution, theme=theme, query=query,
                                        company=company, year=year, position=position,
                                        include_rollback=include_rollback, limit=limit),
                    {"matching": total,
                                                   "shown": [self._prop(r) for r in rows]},
                    ["SPLIT means the manager's own funds voted both ways on the same item."])

    def voting_record(self, institution: str, theme=None, query=None, company=None,
                      include_rollback=False, since=None, until=None) -> dict:
        """One manager's record on a theme or free-text query, by year, counted
        per proposal. `support_rate` = FOR / (FOR + AGAINST)."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company, include_rollback=include_rollback,
                                 since=since, until=until)
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
                                            include_rollback=include_rollback),
                    {"overall": self._tally(rows),
                     "by_year": {y: self._tally(rs) for y, rs in sorted(years.items(),
                                 key=lambda kv: kv[0] or 0)},
                     "against_management": {
                         "count": mr["agm"] or 0, "of": mr["decided"] or 0}},
                    ["Counts are proposals, not fund ballot lines.",
                     "Position is share-weighted: SPLIT means the minority side carried at "
                     "least 5% of the shares voted. Use fund_votes() to see which funds.",
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
              since=None, until=None) -> dict:
        """Managers compared on the SAME proposals — the control for 'they just
        faced different ballots'. Only proposals at least `min_managers` voted on."""
        join, w, p = self._where(theme=theme, query=query, year=year, since=since,
                                 until=until)
        rows = self.db.execute(
            f"SELECT p.ballot_key, p.institution_id, p.position FROM proposals p {join} "
            f"WHERE {w}", p).fetchall()
        by_ballot, undecided = defaultdict(dict), defaultdict(lambda: defaultdict(int))
        for r in rows:
            if r["position"] in ("FOR", "AGAINST"):
                by_ballot[r["ballot_key"]][r["institution_id"]] = r["position"]
            else:
                undecided[r["ballot_key"]][r["institution_id"]] += 1
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
        return _env("peers", _clean(theme=theme, query=query, year=year, since=since,
                                    until=until, min_managers=min_managers),
                    {"shared_proposals": len(shared), "candidate_proposals": len(by_ballot),
                     "managers": table},
                    ["Proposals are matched across managers by company, meeting date and "
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
                               "ORDER BY institution_id", (r["ballot_key"],)).fetchall()
        return _env("ballot", {"proposal_id": proposal_id}, [self._prop(x) for x in rows], [])

    # -- 4. say against do
    def say_vs_do(self, institution: str, query: str, theme: str | None = None) -> dict:
        """Policy sentences matching `query`, by version, beside the voting
        record for the period each version was the one in force."""
        iid = self._inst(institution)
        vers = [dict(r) for r in self.db.execute(
            "SELECT * FROM policy_versions WHERE institution_id=? AND n_sentences >= ? "
            "ORDER BY captured", (iid, READABLE_MIN))]
        last_vote = self.db.execute("SELECT MAX(meeting_date) FROM proposals "
                                    "WHERE institution_id=?", (iid,)).fetchone()[0]
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
                                     query=None if theme else query)
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
        return _env("say_vs_do", {"institution": iid, "query": query, "theme": theme}, out,
                    ["Each vote is set only against the version public on the meeting date.",
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

    def reversals(self, institution: str, theme=None, query=None, company=None) -> dict:
        """The same proposal at the same company, voted one way one year and the
        other way a later year."""
        join, w, p = self._where(institution=institution, theme=theme, query=query,
                                 company=company)
        rows = self.db.execute(
            f"SELECT p.* FROM proposals p {join} WHERE {w} "
            "AND p.position IN ('FOR','AGAINST') ORDER BY p.meeting_date", p).fetchall()
        # Titles drift a little year to year ("Report on Political Spending" /
        # "Political Contributions Disclosure"), so within one company a later
        # proposal is paired with its closest earlier one by shared title words.
        by_company = defaultdict(list)
        for r in rows:
            who, _date, toks = r["ballot_key"].split("|", 2)
            by_company[who].append((r, set(toks.split())))
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
                                        company=company), out,
                    ["Matched on company and the proposal title's significant words. The "
                     "two proposals can differ in substance or sponsor behind a similar "
                     "title, and the company may have changed what it discloses: read "
                     "both proxy statements before calling this a change of stance.",
                     "Check ballot() on each side: if peers moved the same way, the "
                     "proposal changed, not this manager."])

    # -- directors
    def _dwhere(self, *, institution=None, company=None, year=None, since=None, until=None,
                position=None):
        w, p = ["1=1"], []
        if institution:
            w.append("d.institution_id = ?")
            p.append(self._inst(institution))
        if company:
            w.append("(d.issuer_name LIKE ? OR d.cusip = ?)")
            p += [f"%{company}%", company.upper()]
        if year:
            w.append("d.year = ?")
            p.append(int(year))
        if since:
            w.append("d.meeting_date >= ?")
            p.append(since)
        if until:
            w.append("d.meeting_date <= ?")
            p.append(until)
        if position:
            w.append("d.position = ?")
            p.append(position.upper())
        return " AND ".join(w), p

    @staticmethod
    def _dtally(t: dict) -> dict:
        decided = t["FOR"] + t["AGAINST"]
        return {"nominees": t["FOR"] + t["AGAINST"] + t["SPLIT"] + t["ABSTAIN"] + t["NONE"],
                "for": t["FOR"], "opposed": t["AGAINST"], "split": t["SPLIT"],
                "abstain": t["ABSTAIN"], "none": t["NONE"],
                "opposition_rate": round(t["AGAINST"] / decided, 4) if decided else None,
                "meetings": t["meetings"], "meetings_with_opposition": t["opp_meetings"]}

    _DIRECTOR_CAVEATS = [
        "Covers management's nominees only (N-PX source ISSUER, category DIRECTOR "
        "ELECTIONS). Dissident nominees in contested elections are in proposals().",
        "`opposed` = AGAINST or WITHHOLD, share-weighted across the funds on file. "
        "ABSTAIN is counted separately, though in some markets it is the only way to "
        "oppose a nominee.",
        "The record never says WHY a nominee was opposed: board diversity, "
        "overboarding, pay, attendance and independence all look identical here. "
        "A change in the rate is not evidence about any one reason.",
        "Counts are ballot items as each filer worded them; a slate voted as one "
        "item counts once. Non-US meetings are included: narrow with company=.",
        "Year-to-year change can reflect which companies the funds held."]

    def director_record(self, institution: str, company=None, since=None, until=None) -> dict:
        """How often one manager opposed management's board nominees, by year,
        counted per nominee item and per meeting."""
        w, p = self._dwhere(institution=institution, company=company, since=since, until=until)
        years: dict = defaultdict(lambda: defaultdict(int))
        for r in self.db.execute(
                f"SELECT d.year, d.position, COUNT(*) n FROM director_votes d WHERE {w} "
                "GROUP BY d.year, d.position", p):
            years[r["year"]][r["position"]] += r["n"]
        for r in self.db.execute(
                f"""SELECT year, COUNT(*) m, SUM(opp > 0) om FROM (
                        SELECT d.year, SUM(d.position='AGAINST') opp FROM director_votes d
                        WHERE {w} GROUP BY d.year, d.cusip, d.issuer_name, d.meeting_date)
                    GROUP BY year""", p):
            years[r["year"]]["meetings"] = r["m"]
            years[r["year"]]["opp_meetings"] = r["om"] or 0
        total: dict = defaultdict(int)
        for t in years.values():
            for k, n in t.items():
                total[k] += n
        return _env("director_record", _clean(institution=institution, company=company,
                                              since=since, until=until),
                    {"overall": self._dtally(total),
                     "by_year": {y: self._dtally(t) for y, t in
                                 sorted(years.items(), key=lambda kv: kv[0] or 0)}},
                    self._DIRECTOR_CAVEATS)

    def director_votes(self, institution: str, company=None, year=None, position=None,
                       since=None, until=None, limit: int = 60) -> dict:
        """The nominee items behind director_record(), each with its filing."""
        w, p = self._dwhere(institution=institution, company=company, year=year,
                            since=since, until=until, position=position)
        rows = self.db.execute(
            f"SELECT d.* FROM director_votes d WHERE {w} "
            "ORDER BY d.meeting_date DESC, d.issuer_name, d.director_id LIMIT ?",
            [*p, int(limit)]).fetchall()
        return _env("director_votes", _clean(institution=institution, company=company,
                                             year=year, position=position, since=since,
                                             until=until, limit=limit),
                    [{"director_id": r["director_id"], "institution": r["institution_id"],
                      "company": r["issuer_name"], "cusip": r["cusip"],
                      "meeting_date": r["meeting_date"], "nominee_item": r["nominee_item"],
                      "position": r["position"],
                      "fund_lines": {"total": r["n_lines"], "for": r["n_for"],
                                     "against": r["n_against"], "other": r["n_other"]},
                      "accession": r["accession"], "source_url": r["source_url"]}
                     for r in rows],
                    [*self._DIRECTOR_CAVEATS, f"At most {limit} rows; raise limit= for more."])

    def director_peers(self, year=None, since=None, until=None, company=None,
                       min_managers: int = 3) -> dict:
        """Managers compared on the SAME shareholder meetings: at how many did
        each oppose at least one management nominee?"""
        w, p = self._dwhere(company=company, year=year, since=since, until=until)
        per: dict = defaultdict(dict)
        for r in self.db.execute(
                f"""SELECT d.meeting_key k, d.institution_id i, SUM(d.position='FOR') f,
                           SUM(d.position='AGAINST') a
                    FROM director_votes d WHERE {w} AND d.meeting_key != ''
                    GROUP BY d.meeting_key, d.institution_id""", p):
            if r["f"] + r["a"]:
                per[r["k"]][r["i"]] = (r["f"], r["a"])
        shared = {k: v for k, v in per.items() if len(v) >= min_managers}
        out: dict = defaultdict(lambda: {"shared_meetings": 0, "meetings_with_opposition": 0,
                                         "nominees": 0, "opposed": 0})
        for votes in shared.values():
            for iid, (f, a) in votes.items():
                o = out[iid]
                o["shared_meetings"] += 1
                o["meetings_with_opposition"] += a > 0
                o["nominees"] += f + a
                o["opposed"] += a
        for o in out.values():
            o["opposition_rate"] = round(o["opposed"] / o["nominees"], 4) if o["nominees"] else None
            o["share_of_meetings_with_opposition"] = round(
                o["meetings_with_opposition"] / o["shared_meetings"], 4)
        table = dict(sorted(out.items(), key=lambda kv: -(kv[1]["opposition_rate"] or 0)))
        return _env("director_peers", _clean(year=year, since=since, until=until,
                                             company=company, min_managers=min_managers),
                    {"shared_meetings": len(shared), "candidate_meetings": len(per),
                     "managers": table},
                    ["Meetings are matched by CUSIP and meeting date. Nominee items are "
                     "NOT matched one-to-one: filers word them differently, and one may "
                     "file a slate as a single item, so compare "
                     "`share_of_meetings_with_opposition` before `opposition_rate`.",
                     "Each manager's figures cover only the shared meetings IT voted at.",
                     *self._DIRECTOR_CAVEATS])

    def fund_votes(self, proposal_id: int) -> dict:
        """The individual fund lines behind one position: which fund series voted
        how, with how many shares, from which filing."""
        r = self.db.execute("SELECT * FROM proposals WHERE proposal_id=?",
                            (proposal_id,)).fetchone()
        if not r:
            raise ValueError(f"no proposal {proposal_id}")
        iso = iso_meeting_date("v.meeting_date")
        lines = []
        for v in self.ledger.execute(
            f"""SELECT v.vote_series, v.how_voted, v.shares_voted, v.vote_description,
                       v.accession, f.cik, f.source_url
                FROM votes v JOIN filings f ON f.accession = v.accession
                WHERE f.institution_id=? AND v.is_duplicate=0
                  AND v.vote_source='SECURITY HOLDER' AND {iso}=?
                  AND (v.cusip=? OR v.issuer_name=?)""",
                (r["institution_id"], r["meeting_date"], r["cusip"], r["issuer_name"])):
            if norm(v["vote_description"]) == norm(r["description"]):
                lines.append({"fund_series": v["vote_series"], "registrant_cik": v["cik"],
                              "how_voted": v["how_voted"], "shares": v["shares_voted"],
                              "accession": v["accession"], "source_url": v["source_url"]})
        tot = defaultdict(float)
        for ln in lines:
            hv = (ln["how_voted"] or "").upper()
            tot["for" if hv == "FOR" else "against" if hv in ("AGAINST", "WITHHOLD")
                else "other"] += ln["shares"] or 0.0
        return _env("fund_votes", {"proposal_id": proposal_id},
                    {"proposal": self._prop(r), "lines": lines,
                     "shares": {k: tot[k] for k in ("for", "against", "other")}},
                    ["One fund series can file several lines for one item. Compare the "
                     "same series across years before saying a manager changed its vote: "
                     "a different mix of funds can move the total on its own."])

    def filers(self, institution: str) -> dict:
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
        return _env("filers", {"institution": iid},
                    {"registrants": len(rows), "filers": rows},
                    ["A registrant is one fund trust. Large managers have dozens; this is "
                     "the subset ingested. Different registrants of one group can be "
                     "advised by different entities with their own voting policies.",
                     "Which adviser votes a given fund is NOT in this record: confirm it "
                     "from the fund's prospectus before attributing a vote to a policy."])

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


TOOLS = ("coverage", "policy_versions", "policy_search", "policy_diff", "policy_in_force",
         "proposals", "voting_record", "peers", "ballot", "fund_votes", "reversals", "say_vs_do", "filers",
         "director_record", "director_votes", "director_peers",
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
