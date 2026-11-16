"""The desk — where an investigating agent files, and where its work is checked.

An LLM that writes well will also write a wrong number well. The answer here is
not to trust the writer more but to make every factual sentence carry a claim
that a program can re-run. A draft is a JSON file:

    {"slug": "...", "headline": "...", "standfirst": "...",
     "body": "markdown with [c1] markers after each factual statement",
     "claims": [{"id": "c1", "text": "what is being asserted",
                 "check": {...}}],
     "headline_claims": ["c1", "c3"],   # the claims the headline rests on
     "limitations": ["what this does NOT show", ...],  # two or more
     "institutions_named": ["blackrock", ...]}

Check types (each re-executed against the engine, never taken on trust):

    {"type": "quote",    "commitment_id": 12, "text": "exact words"}
    {"type": "absent",   "commitment_id": 14, "text": "exact words"}
    {"type": "stat",     "tool": "voting_record", "args": {...},
                         "path": "overall.support_rate", "equals": 0.0541}
    {"type": "proposal", "proposal_id": 991, "institution": "blackrock",
                         "position": "AGAINST", "company": "EXXON",
                         "meeting_date": "2024-05-29"}
    {"type": "director", "director_id": 5512, "institution": "vanguard",
                         "position": "AGAINST", "company": "EXXON",
                         "meeting_date": "2024-05-29", "nominee": "Jane Roe"}
    {"type": "enforcement", "id": 4410}

`verify()` also lints the prose: every paragraph must cite a claim; every
number in a paragraph must be one its cited claims establish (percentages are
matched to rates); every long quotation must be a verified quote; and words that
assert or insinuate motive or wrongdoing are rejected — the record shows what
was said and done, never why.

LLM output is advisory only (CLAUDE.md): drafts live under data/desk/, never in
the ledger, and nothing here publishes or sends. A verified draft is still a
LEAD until a person reviews it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from . import engine
from .http import DATA_DIR

DESK_DIR = DATA_DIR / "desk"

# Words that assert intent, illegality or bad faith. The record cannot support
# them, and for an uninsured publisher they are the difference between a
# statement of fact and a defamation claim.
_CHARACTERISATION = re.compile(
    r"\b(lie[sd]?|lying|liars?|fraud\w*|hypocri\w*|deceiv\w*|decepti\w*|dishonest\w*|"
    r"greenwash\w*|betray\w*|scam\w*|cover[- ]?up|illegal\w*|unlawful\w*|criminal\w*|"
    r"corrupt\w*|mislead\w*|misled|cynical\w*|sham|pretend\w*|"
    r"broke(n)? (its|their|a) promise\w*|abandon\w*|reneg\w*|"
    # Insinuation does the same work as accusation with less courage.
    r"quietly|silently|secretly|stealth\w*|walk\w* back|backtrack\w*|back[- ]?pedal\w*|"
    r"retreat\w*|revers\w+ (itself|course)|water\w* down|gut(s|ted|ting)?|"
    r"dodg\w*|evad\w*|hid(es?|den|ing)?|bur(y|ied|ies))\b", re.IGNORECASE)
_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_DATE = re.compile(r"\b(?:19|20)\d\d-\d\d-\d\d\b")
_CLAIM_ID = re.compile(r"c\d+")


def _numbers(text: str) -> list[str]:
    """Figures in prose, with thousands separators folded: 3,229 is one number."""
    return [n.replace(",", "") for n in _NUM.findall(text)]
# A quantity written as a word is still a quantity, and escapes a digit check.
_NUMBER_WORD = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?|twice|thrice|"
    r"doubl\w+|tripl\w+|quadrupl\w+|halv\w+)\b", re.IGNORECASE)
# Words that assert a proportion, a frequency or a size of change without one.
_VAGUE = re.compile(
    r"\b(most|mostly|majority|minority|nearly|almost|virtually|practically|vast|"
    r"overwhelming\w*|many|few|several|numerous|rarely|seldom|often|usually|"
    r"typically|routinely|consistently|frequently|never|always|sharp\w*|steep\w*|"
    r"dramatic\w*|drastic\w*|plung\w*|plummet\w*|collaps\w*|soar\w*|surg\w*|"
    r"slump\w*|tumbl\w*|significant\w*|substantial\w*|marked(ly)?|largely|"
    r"increasingly|roughly|approximately)\b", re.IGNORECASE)

STANDING_LIMITATIONS = (
    "Votes are from SEC N-PX filings: US-registered funds only, and only the fund "
    "registrants ingested for each manager.",
    "Proposal figures cover shareholder-sponsored proposals only. Director figures "
    "cover management's nominees, and the filings never state the reason for a vote.",
    "Policy dates are archive capture dates: the wording was public by then, not "
    "necessarily published then. Gaps between captures are gaps in the archive.",
    "Wording and voting are shown side by side. Nothing here establishes why a "
    "manager voted as it did.",
)
_MARK = re.compile(r"\[(c\d+)\]")
_QUOTED = re.compile(r"[“\"]([^”\"]{25,})[”\"]")
_FACTUAL = re.compile(r"\d|[“\"]")


def _dig(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            if part not in obj and part.isdigit() and int(part) in obj:
                part = int(part)
            obj = obj[part]
        else:
            raise KeyError(part)
    return obj


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.0005
    return str(a) == str(b)


def _check(eng: engine.Engine, check: dict) -> tuple[bool, str]:
    kind = check.get("type")
    if kind in ("quote", "absent"):
        r = eng.verify_quote(int(check["commitment_id"]), check["text"])["result"]
        v = r["version"]
        where = f"{v['institution_id']}/{v['doc_label']} captured {v['captured']}"
        if kind == "quote":
            return r["present"], ("found in " if r["present"] else "NOT in ") + where
        if len(check["text"]) < 25:
            return False, "an absence claim needs at least 25 characters to mean anything"
        return (not r["present"]), ("absent from " if not r["present"] else "PRESENT in ") + where
    if kind == "stat":
        if check["tool"] in ("sql", "verify_quote"):
            return False, "stat claims must use a guarded tool, not raw sql"
        res = getattr(eng, check["tool"])(**check.get("args", {}))["result"]
        got = _dig(res, check["path"])
        ok = _same(got, check["equals"])
        return ok, f"{check['tool']}→{check['path']} = {got!r}" + (
            "" if ok else f", draft says {check['equals']!r}")
    if kind == "proposal":
        row = eng.db.execute("SELECT institution_id, position, issuer_name, meeting_date,"
                             " description "
                             "FROM proposals WHERE proposal_id=?",
                             (int(check["proposal_id"]),)).fetchone()
        if not row:
            return False, "no such proposal"
        # The company and date are checked too: prose beside a valid proposal_id
        # could otherwise name the wrong meeting and still verify.
        for field in ("company", "meeting_date"):
            if not check.get(field):
                return False, f"a proposal claim must state `{field}` so the prose is checked"
        ok = (row["position"] == check["position"].upper()
              and row["institution_id"] == eng._inst(check["institution"])
              and check["company"].lower() in (row["issuer_name"] or "").lower()
              and row["meeting_date"] == check["meeting_date"]
              and (not check.get("title")
                   or engine.norm(check["title"]) in engine.norm(row["description"])))
        return ok, (f"{row['institution_id']} voted {row['position']} at "
                    f"{row['issuer_name']} {row['meeting_date']}")
    if kind == "director":
        row = eng.db.execute("SELECT institution_id, position, issuer_name, meeting_date,"
                             " nominee_item FROM director_votes WHERE director_id=?",
                             (int(check["director_id"]),)).fetchone()
        if not row:
            return False, "no such director item"
        for field in ("company", "meeting_date", "nominee"):
            if not check.get(field):
                return False, f"a director claim must state `{field}` so the prose is checked"
        ok = (row["position"] == check["position"].upper()
              and row["institution_id"] == eng._inst(check["institution"])
              and check["company"].lower() in (row["issuer_name"] or "").lower()
              and row["meeting_date"] == check["meeting_date"]
              and engine.norm(check["nominee"]) in engine.norm(row["nominee_item"]))
        return ok, (f"{row['institution_id']} voted {row['position']} on "
                    f"{row['nominee_item']!r} at {row['issuer_name']} {row['meeting_date']}")
    if kind == "enforcement":
        row = eng.ledger.execute(
            "SELECT resolution_type, company_name FROM enforcement_actions WHERE id=?",
            (int(check["id"]),)).fetchone()
        if not row:
            return False, "no such enforcement action"
        ok = row["resolution_type"] not in ("unverified", "allegation", "sanction_designation")
        return ok, f"{row['company_name']}: {row['resolution_type']}" + (
            "" if ok else " — quarantined class, may not be cited as fact")
    return False, f"unknown check type {kind!r}"


def verify(draft: dict, eng: engine.Engine | None = None) -> dict:
    """Re-run every claim and lint the prose. Returns a report; never raises on
    a bad draft — a failed check is a result, not an error."""
    eng = eng or engine.Engine()
    problems: list[str] = []
    results = []
    claims = {c.get("id"): c for c in draft.get("claims", [])}

    for cid, c in claims.items():
        try:
            ok, detail = _check(eng, c.get("check") or {})
        except Exception as exc:                      # a malformed check is a failed check
            ok, detail = False, f"could not run: {type(exc).__name__}: {exc}"
        results.append({"id": cid, "ok": ok, "text": c.get("text", ""), "detail": detail})
        if not ok:
            problems.append(f"claim {cid} failed: {detail}")

    text = " ".join(str(draft.get(k, "")) for k in ("headline", "standfirst", "body"))
    used = (set(_MARK.findall(text)) | set(draft.get("headline_claims") or [])
            | set(_MARK.findall(" ".join(map(str, draft.get("limitations") or [])))))
    for m in sorted(used - set(claims)):
        problems.append(f"text cites [{m}] but there is no such claim")
    for m in sorted(set(claims) - used):
        problems.append(f"claim {m} is never cited in the text")

    detail = {r["id"]: r["detail"] for r in results}

    def backing(ids) -> tuple[list[float], set[str]]:
        """Every number, and every whole date, the cited claims establish."""
        # Internal identifiers and path indices are not facts about the world:
        # a proposal_id of 7 must not make a stray "7" in the prose look sourced.
        parts = []
        for i in ids:
            if i not in claims:
                continue
            chk = claims[i].get("check", {})
            parts.append(json.dumps({k: v for k, v in chk.items()
                                     if k not in ("proposal_id", "commitment_id", "id",
                                                  "path", "type")}))
            parts += re.findall(r"\b(?:19|20)\d\d\b", str(chk.get("path", "")))
            parts.append(detail.get(i, "").split("→")[-1].split(" = ", 1)[-1]
                         if chk.get("type") == "stat" else detail.get(i, ""))
        blob = " ".join(parts)
        return [float(x) for x in _numbers(blob)], set(_DATE.findall(blob))

    def unbacked(prose: str, ids) -> list[str]:
        have, dates = backing(ids)
        prose = _MARK.sub("", prose)
        # A date is one fact, not three loose numbers: 2024-05-02 must not pass
        # because some cited claim happens to contain a 2024, a 5 and a 2.
        bad = [f"date {d}" for d in _DATE.findall(prose) if d not in dates]
        return bad + [f"figure {n}" for n in _numbers(_DATE.sub(" ", prose))
                      if not any(abs(float(n) - h) < 1e-9 or abs(float(n) - h * 100) <= 0.06
                                 for h in have)]

    # Headline and standfirst are the most-read sentences and had no check at all.
    head = f"{draft.get('headline', '')} {draft.get('standfirst', '')}"
    head_ids = list(draft.get("headline_claims") or []) + _MARK.findall(head)
    if not head_ids:
        problems.append("headline_claims is empty: the headline must rest on named claims")
    for n in unbacked(head, head_ids):
        problems.append(f"headline/standfirst {n} is not established by its claims")

    # Every paragraph rests on claims — not only the ones with digits in them:
    # "opposed nearly all such resolutions" is as factual as "49 of 52".
    for para in re.split(r"\n\s*\n", str(draft.get("body", ""))):
        pt = para.strip()
        if not pt or pt.startswith("#"):
            continue
        ids = _MARK.findall(pt)
        if not ids:
            problems.append(f"paragraph has no claim: “{pt[:70]}…”")
            continue
        for n in unbacked(pt, ids):
            problems.append(f"{n} in “{pt[:50]}…” is not established by the claims "
                            f"that paragraph cites ({', '.join(ids)})")

    # A proposal's title may be quoted verbatim when its claim carries `title`.
    quotes = [engine.norm(c["check"]["text"]) for c in claims.values()
              if (c.get("check") or {}).get("type") == "quote"]
    quotes += [engine.norm(c["check"]["title"]) for c in claims.values()
               if (c.get("check") or {}).get("type") == "proposal"
               and c["check"].get("title")]
    for q in _QUOTED.findall(text):
        if not any(engine.norm(q) in v or v in engine.norm(q) for v in quotes):
            problems.append(f"quotation not backed by a quote claim: “{q[:60]}…”")

    unquoted = _QUOTED.sub("", text)
    for m in _NUMBER_WORD.finditer(unquoted):
        problems.append(f"number written as a word ({m.group(0)!r}): write figures in "
                        "digits so they are checked against the claims")
    for m in _VAGUE.finditer(unquoted):
        problems.append(f"vague quantity {m.group(0)!r}: state the count and what it is "
                        "a count of, or leave it out")

    # Limitations are read as fact too; a figure there needs a claim like any other.
    for lim in draft.get("limitations") or []:
        for n in unbacked(str(lim), _MARK.findall(str(lim))):
            problems.append(f"{n} in limitation “{str(lim)[:50]}…” is not "
                            "established by a claim cited in it")

    for cid in claims:
        if not _CLAIM_ID.fullmatch(str(cid)):
            problems.append(f"claim id {cid!r} must be the letter c and digits (c1, c2 …); "
                            "markers of any other shape are not seen in the text")
    unquoted += " " + _QUOTED.sub("", " ".join(map(str, draft.get("limitations") or [])))
    for m in _CHARACTERISATION.finditer(unquoted):
        problems.append(f"characterisation {m.group(0)!r}: state what the record shows, "
                        "not motive or wrongdoing")

    if len(draft.get("limitations") or []) < 2:
        problems.append("state at least two limitations specific to THIS piece (the "
                        "standing ones are attached automatically)")
    if not claims:
        problems.append("no claims: nothing here can be checked")

    return {"slug": draft.get("slug"), "verified": not problems,
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "engine_built_at": eng.db.execute(
                "SELECT value FROM meta WHERE key='built_at'").fetchone()[0],
            "claims": results, "problems": problems,
            "standing_limitations": list(STANDING_LIMITATIONS),
            "status": "LEAD — unpublished; human review required before any use"}


def verify_file(path: Path) -> dict:
    """Verify a draft on disk and write the report beside it."""
    path = Path(path)
    report = verify(json.loads(path.read_text()))
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report


def listing() -> list[dict]:
    out = []
    for f in sorted(DESK_DIR.glob("*.json")):
        if f.name.endswith(".report.json"):
            continue
        rep = f.with_suffix(".report.json")
        r = json.loads(rep.read_text()) if rep.exists() else None
        d = json.loads(f.read_text())
        out.append({"slug": d.get("slug", f.stem), "headline": d.get("headline", ""),
                    "claims": len(d.get("claims", [])),
                    "verified": None if r is None else r["verified"],
                    "problems": None if r is None else len(r["problems"]), "path": str(f)})
    return out
