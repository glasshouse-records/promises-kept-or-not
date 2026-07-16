"""FIRST STONE — the accountability newsroom built on the Glasshouse registrar.

Glasshouse is the registrar: it remembers and accuses no one. First Stone is
the newsroom that works ON that record — a separate identity with its own
masthead, so the dataset's neutrality is never contaminated by the stories.

It is organized the way a publishing house is, because the discipline of a
newsroom IS the safety mechanism:

    The Assignment Desk   ranks the field; decides what is worth chasing
    The Records Desk      builds the evidence file — every quote, vote, and
                          language change, each with its citation
    The Ledger Desk       fact-checks by RECOMPUTING every number from the
                          ledger; a mismatch kills the story
    The Copy Desk         writes the headline and standfirst from the facts
                          (an optional LLM pass may rephrase, never add)
    The Standards Desk    enforces the written code: no motive language, the
                          lead-not-finding banner, right of reply, citations
    The Editor            assembles the piece and sends it upstairs

    The Publisher         is ALWAYS a human. Nothing is published without an
                          explicit human decision and a written note.

Every desk stamps the story's trail — the byline block a reader can audit.
All desks are deterministic code over ledger facts; the pipeline runs with no
LLM configured. Stories live under data/newsroom/, never in ledger facts.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from . import investigate, registry, timeline
from .contradictions import extract_text
from .http import DATA_DIR

NEWSROOM_DIR = DATA_DIR / "newsroom"

# ── the staff ────────────────────────────────────────────────────────────────
# First Stone reads like a real masthead — a named editor-in-chief, a standards
# editor, and correspondents with beats — because that structure is the
# discipline. But the staff are software agents, and the newsroom SAYS SO on
# every surface (DISCLOSURE below). Honesty is the whole product: we never let
# a reader believe a person wrote what a program assembled from the ledger.

DISCLOSURE = (
    "First Stone's editors and correspondents are automated agents, not people. "
    "They read the public Glasshouse registry, assemble stories from cited "
    "primary sources, and check each other's numbers — but they do not publish. "
    "Every story is a documented lead until a human publisher verifies the "
    "primary sources and signs it. Bylines name the automated correspondent "
    "responsible for the beat, never a human author.")

EDITOR = {
    "name": "Margaret Aldous",
    "role": "Editor-in-Chief (automated)",
    "note": ("runs the edition, keeps the wall between the desks and the human "
             "publisher, and answers for every word First Stone files."),
}

STANDARDS_EDITOR = {
    "name": "The Standards Editor",
    "role": "Standards & Practices (automated)",
    "note": ("holds the written code — facts and dates, never motive; right of "
             "reply for every subject; a citation behind every claim."),
}

# Correspondents by beat. Each theme maps to exactly one correspondent so a
# story's byline is deterministic. Bios are static persona copy (no facts).
CORRESPONDENTS = [
    {"id": "climate", "name": "Iris Calder", "beat": "Climate & Environment",
     "themes": ("climate", "nature"),
     "bio": "covers how the largest asset managers vote the climate, emissions "
            "and nature commitments they publish."},
    {"id": "governance", "name": "Theo Marsh", "beat": "Boards & Governance",
     "themes": ("board-diversity",),
     "bio": "tracks board composition, diversity and director-accountability votes."},
    {"id": "labor", "name": "Nadia Okonkwo", "beat": "Labor & Human Rights",
     "themes": ("labor-rights", "human-rights"),
     "bio": "reports on workforce, human-capital and human-rights proposals."},
    {"id": "influence", "name": "Ellis Vance", "beat": "Money & Influence",
     "themes": ("lobbying-disclosure", "anti-corruption"),
     "bio": "follows political-spending, lobbying-disclosure and anti-corruption votes."},
]

_THEME_CORRESPONDENT = {th: c for c in CORRESPONDENTS for th in c["themes"]}


def correspondent_for(theme: str) -> dict:
    """The correspondent whose beat covers this theme (deterministic)."""
    return _THEME_CORRESPONDENT.get(
        theme, {"id": "desk", "name": "The News Desk", "beat": "General",
                "themes": (), "bio": "covers the say-vs-do record across beats."})


MASTHEAD = {
    "name": "First Stone",
    "tagline": "Stories from the public record, checked twice, published by a human.",
    "about": (
        "First Stone is an automated newsroom working over the Glasshouse "
        "registry — the neutral public record of what financial institutions "
        "say and how they vote. Its editors and correspondents are software "
        "agents: they select, document, fact-check and edit. They do not "
        "publish. Every story is a documented lead until a human publisher "
        "verifies both primary sources and signs a publication note, and every "
        "subject is offered the right of reply. Every number can be recomputed "
        "from the public ledger."),
    "disclosure": DISCLOSURE,
    "editor": EDITOR,
    "standards_editor": STANDARDS_EDITOR,
    "correspondents": CORRESPONDENTS,
    "ethics": [
        ("Facts, not motive", "We report acts, dates, amounts and votes — never "
         "what an institution 'really' intended. The record speaks; the reader judges."),
        ("A citation behind every claim", "Every number is recomputed from the "
         "public Glasshouse ledger and every policy quote links its archived, "
         "content-hashed source. If you can't verify it, we don't print it."),
        ("Leads, not verdicts", "A First Stone story is a documented lead until a "
         "human publisher verifies the primary sources. Theme matching is lexical; "
         "a person confirms intent before publication."),
        ("Right of reply", "Every institution named is offered the chance to "
         "respond before publication, and any response is published in full."),
        ("We correct openly", "Errors are fixed on the record, dated, with the "
         "correction shown — provenance is the point."),
    ],
    "corrections": (
        "Found an error? Every First Stone claim traces to a primary source you "
        "can open. Report it with the story, the figure, and the source link; "
        "corrections are made on the record and dated."),
    # The pipeline the desks run — shown so readers see how a story is made.
    "desks": [
        ("assignment", "The Assignment Desk", "ranks the field; decides what is worth chasing"),
        ("records", "The Records Desk", "builds the evidence file, citation by citation"),
        ("ledger", "The Ledger Desk", "fact-checks by recomputing every number from the ledger"),
        ("copy", "The Copy Desk", "writes the headline the facts can carry"),
        ("standards", "The Standards Desk", "holds the written code: no motive, right of reply"),
        ("editor", "The Editor", "assembles the piece and sends it upstairs"),
        ("publisher", "The Publisher (human)", "the only chair software never sits in"),
    ],
}

# The Standards Desk's written code, part 1: language that characterizes
# motive or moral state is banned — the record speaks, the reader judges.
BANNED_LEXICON = (
    "hypocrisy", "hypocrite", "hypocritical", "greenwash", "betray", "lied",
    "lying", "deceive", "deceit", "dishonest", "shameful", "disgrace",
    "broke its promise", "broken promise", "two-faced", "duplicit",
)

_LABEL = {"board-diversity": "board diversity", "lobbying-disclosure": "lobbying disclosure",
          "anti-corruption": "anti-corruption", "human-rights": "human rights",
          "labor-rights": "labor rights"}

# The newsroom's bar is HIGHER than the registrar's: the matrix may show a
# "will consider / we find it helpful / we rely on" quote with framing, but a
# story headlined "commits to X" needs a quote where the manager binds itself
# or demands something of companies. Weak-verb quotes are never assigned.
_STRONG_SAY_RE = re.compile(
    r"\b(?:we|our|the\s+funds?)\b[^.]{0,80}\b"
    r"(?:committ?(?:ed|s)?|pledg\w*|will\s+(?:vote|support|oppose|engage|press|hold)|"
    r"expect\w*|ask\w*|urge\w*|require\w*|encourag\w*|advocat\w*|seek\w*|"
    r"support\w*|oppos\w*|press\w*|hold\w*\s+(?:boards?|companies|directors)\s+accountable)\b",
    re.IGNORECASE)


def _label(theme: str) -> str:
    return _LABEL.get(theme, theme.replace("-", " "))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp(story: dict, desk: str, verdict: str, note: str) -> dict:
    entry = {"desk": desk, "verdict": verdict, "note": note, "at": _now()}
    story["trail"].append(entry)
    if verdict == "spike":
        story["state"] = "spiked"
    return entry


# ── the desks ────────────────────────────────────────────────────────────────

def _desk_assignment(conn: sqlite3.Connection, *, min_rate: float, min_votes: int,
                     top_n: int, matrix: dict | None = None) -> list[dict]:
    """Pitch list: committed say-vs-do cells with enough votes to matter,
    scored transparently (gap × evidence volume × manager size)."""
    reg = registry.load()
    bm = matrix if matrix is not None else investigate.build_matrix(conn)
    pitches = []
    for inst in bm["institutions"]:
        aum = float(reg.get(inst["id"], {}).get("aum_usd_tr") or 0)
        for theme, c in inst["cells"].items():
            n = c["for"] + c["against"]
            if not (c["committed"] and n >= min_votes and c["rate"] >= min_rate):
                continue
            if not _STRONG_SAY_RE.search(c["quote"] or ""):
                continue  # weak say (consider/helpful/rely): registrar yes, story no
            score = round(c["rate"] * (n ** 0.25) * ((aum + 0.1) ** 0.3), 4)
            corr = correspondent_for(theme)
            pitches.append({
                "slug": f"{inst['id']}-{theme}",
                "state": "assigned", "trail": [],
                "institution_id": inst["id"], "institution_name": inst["name"],
                "theme": theme, "score": score,
                "against_rate": c["rate"], "votes_for": c["for"],
                "votes_against": c["against"], "n_votes": n,
                "quote": c["quote"], "doc_label": c["doc_label"],
                "doc_version": c["doc_version"], "doc_url": c["doc_url"],
                "examples": c["examples"], "trend": c.get("trend") or {},
                "byline": corr["name"], "beat": corr["beat"],
                "correspondent_id": corr["id"],
            })
    pitches.sort(key=lambda p: -p["score"])
    chosen = pitches[:top_n]
    for p in chosen:
        _stamp(p, "assignment", "pass",
               f"assigned to {p['byline']} ({p['beat']}) at score {p['score']} — "
               f"gap {round(p['against_rate']*100)}% on {p['n_votes']} votes")
    return chosen


def _desk_records(conn: sqlite3.Connection, s: dict) -> dict:
    """Attach the full evidence file: the policy's change history for this
    theme (the registrar's walk-back record) joins the votes and the quote."""
    tl = timeline.institution_timeline(conn, s["institution_id"])
    td = tl["themes"].get(s["theme"], {})
    s["events"] = td.get("events", [])
    s["presence"] = td.get("presence", [])
    return _stamp(s, "records", "pass",
                  f"evidence file: {len(s['examples'])} cited votes, "
                  f"{len(s['events'])} language-change events, "
                  f"{len(s['presence'])} policy versions carrying the commitment")


def _desk_ledger(conn: sqlite3.Connection, s: dict) -> dict:
    """Fact-check by recomputation: re-count the theme votes straight from the
    ledger and verify the commitment quote appears verbatim in an archived
    version. Any mismatch spikes the story."""
    _, proposal_pats, prefilter = investigate._theme_spec(s["theme"], None)
    scan = investigate._scan_one(conn, proposal_pats, prefilter)
    got = scan.get(s["institution_id"], {"for": 0, "against": 0})
    if (got["for"], got["against"]) != (s["votes_for"], s["votes_against"]):
        return _stamp(s, "ledger", "spike",
                      f"recount mismatch: draft says {s['votes_for']} FOR / "
                      f"{s['votes_against']} AGAINST; the ledger recount says "
                      f"{got['for']} FOR / {got['against']} AGAINST")
    # Whitespace collapse + hyphen-adjacent whitespace removal: PDF extraction
    # renders line-break hyphenation as "long -term" / "long- term"; a true
    # quote must not be spiked for the extractor's line breaks.
    def norm(t: str) -> str:
        t = re.sub(r"\s+", " ", t or "").strip()
        return re.sub(r"\s*-\s*", "-", t)
    quote_ok = False
    for r in conn.execute("SELECT content_path FROM commitments WHERE institution_id=? "
                          "AND doc_label=?", (s["institution_id"], s["doc_label"])):
        p = Path(r["content_path"])
        if p.exists() and norm(s["quote"]) in norm(extract_text(p)):
            quote_ok = True
            break
    if not quote_ok:
        return _stamp(s, "ledger", "spike",
                      "quote not found verbatim in any archived version of "
                      f"{s['doc_label']}")
    return _stamp(s, "ledger", "pass",
                  f"recount matched ({s['votes_for']} FOR / {s['votes_against']} AGAINST); "
                  "quote verified verbatim against the archived document")


def _desk_copy(conn: sqlite3.Connection | None, s: dict, llm: bool = False) -> dict:
    """Headline and standfirst composed from the facts. The optional LLM pass
    may rephrase but never add or alter a number, name, date, or quote."""
    label = _label(s["theme"])
    pct = round(s["against_rate"] * 100)
    s["headline"] = (f"{s['institution_name']} policy commits to {label}; its funds "
                     f"voted against {pct}% of {label} proposals on record")
    s["standfirst"] = (
        f"The manager's own {s['doc_label']} (version {s['doc_version']}) states: "
        f"“{(s['quote'] or '').strip()}” Across {s['n_votes']} shareholder proposals "
        f"advancing {label} in the Glasshouse registrar, its funds voted against "
        f"{s['votes_against']}.")
    note = "deterministic copy"
    if llm and conn is not None:
        from . import llm as _llm
        det_head, det_stand = s["headline"], s["standfirst"]
        try:
            out = _llm.call(
                conn, purpose="firststone_copy", input_key=s["slug"],
                system=("You are the copy desk of a sober accountability newsroom. "
                        "Sharpen the headline and standfirst using ONLY the given facts — "
                        "never add, drop, or alter any number, name, date, or quote; never "
                        "characterize motive. Return exactly two lines:\n"
                        "HEADLINE: <one line>\nSTANDFIRST: <2-3 sentences>"),
                user=f"HEADLINE: {det_head}\nSTANDFIRST: {det_stand}",
                max_tokens=400)
            head, stand = det_head, det_stand
            for line in out.splitlines():
                if line.upper().startswith("HEADLINE:"):
                    head = line.split(":", 1)[1].strip() or head
                elif line.upper().startswith("STANDFIRST:"):
                    stand = line.split(":", 1)[1].strip() or stand
            # The fact gate (the copy desk runs AFTER the fact-check, so this
            # is what keeps the Ledger Desk's stamp honest): every number and
            # every quoted span in the polished copy must already exist in the
            # deterministic copy. Anything else is a hallucination — discard.
            det_all = det_head + " " + det_stand
            nums_ok = set(re.findall(r"\d[\d,.%]*", head + " " + stand)) <= \
                set(re.findall(r"\d[\d,.%]*", det_all))
            quotes_ok = all(q in det_all
                            for q in re.findall(r"“([^”]+)”", head + " " + stand))
            if nums_ok and quotes_ok:
                s["headline"], s["standfirst"] = head, stand
                note = "LLM-polished (advisory, logged in llm_log; fact gate passed)"
            else:
                note = ("LLM output DISCARDED by the fact gate (introduced a number "
                        "or quote not in the deterministic copy); deterministic copy stands")
        except _llm.NotConfigured:
            note = "deterministic copy (LLM tier not configured)"
    return _stamp(s, "copy", "pass", note)


def _compose_body(s: dict) -> str:
    """The Records Desk's file, in print order. Called by the editor; the
    Standards Desk reviews this exact text. Composed like a broadsheet: kicker,
    headline, byline block, dateline, then the reported piece."""
    label = _label(s["theme"])
    corr = correspondent_for(s["theme"])
    credit = ("reported by the Records Desk · fact-checked by the Ledger Desk · "
              f"standards by {STANDARDS_EDITOR['name']} · edited by {EDITOR['name']}")
    lines = [f"**{corr['beat'].upper()}**", "",   # kicker
             f"# {s['headline']}", "",
             f"**By {s.get('byline', corr['name'])}**, First Stone {corr['beat']} Desk "
             f"— an automated correspondent", "",
             f"FIRST STONE · {date.today().isoformat()} · {credit}", "",
             "> **DRAFT — awaiting the publisher.** A First Stone story is a documented "
             "lead, not a finding, until the human publisher verifies both primary "
             "sources and signs the publication note.", "",
             s["standfirst"], "",
             "## What the policy says", "",
             f"> “{(s['quote'] or '').strip()}”", "",
             f"— {s['doc_label']}, version {s['doc_version']} "
             f"([archived source]({s['doc_url']}))", "",
             "## How the funds voted", "",
             f"{s['votes_against']} AGAINST / {s['votes_for']} FOR across {s['n_votes']} "
             f"proposals advancing {label} "
             f"(against-rate {round(s['against_rate'] * 100)}%). Largest cited votes:", ""]
    for e in s["examples"][:6]:
        lines.append(f"- {e['issuer_name']} ({e['meeting_date']}): voted AGAINST "
                     f"“{e['vote_description']}” with {int(e['shares_voted']):,} shares "
                     f"— N-PX `{e['accession']}`"
                     + (f" ([filing]({e['source_url']}))" if e.get("source_url") else ""))
    if s.get("trend"):
        lines += ["", "Against-rate by meeting year: " + " · ".join(
            f"{y}: {round(d['rate'] * 100)}% ({d['against']}/{d['for'] + d['against']})"
            for y, d in sorted(s["trend"].items()))]
    if s.get("events"):
        lines += ["", "## What changed in their own words", ""]
        for ev in s["events"]:
            frm, to = ev["from"], ev["to"]
            for q in ev["removed"]:
                lines.append(f"- present in version `{frm['version']}`, not present in "
                             f"`{to['version']}`: “{q}” ([earlier]({frm['url']}), "
                             f"[later]({to['url']}))")
            for q in ev["added"]:
                lines.append(f"- added in version `{to['version']}`: “{q}” "
                             f"([earlier]({frm['url']}), [later]({to['url']}))")
            for old, new in ev["revised"]:
                lines.append(f"- revised between `{frm['version']}` and `{to['version']}`: "
                             f"“{old}” → “{new}”")
    fps = s.get("case_footprints") or []
    lines += ["", "## What converges on this case", ""]
    if fps:
        lines.append(f"Beyond this story's core gap, {len(fps)} other detector "
                     f"footprint(s) independently converge on {s['institution_name']} × "
                     f"{label} ({s.get('n_strong', 1)} strong in total):")
        lines += [f"- **{f['name']}** (_{f['evidence_class']}_): {f['headline']}"
                  for f in fps]
        lines += ["", "Footprint classes: strong = an active choice or documented act; "
                  "supporting = a weaker class (holdings carry an index alibi); "
                  "descriptive = discriminating power unproven on this record."]
    else:
        lines.append("This gap is the sole footprint on this case so far — no other "
                     "detector in the library independently corroborates it yet.")
    ledger_stamp = next((t for t in s["trail"] if t["desk"] == "ledger"), None)
    lines += ["", "## What the Ledger Desk checked", "",
              f"- {ledger_stamp['note'] if ledger_stamp else 'recount pending'}",
              "- Every vote above carries its SEC N-PX accession number; every policy "
              "quote links its archived, content-hashed source.", "",
              "## Editor's note", "",
              f"This piece was assembled by {s.get('byline', corr['name'])}, First "
              f"Stone's automated {corr['beat']} correspondent, from the public "
              f"Glasshouse registry, and its figures were re-computed independently "
              f"by the Ledger Desk. It is a documented lead: theme matching is "
              f"lexical, so {EDITOR['name']} holds it for a human publisher to "
              f"confirm the proposals' intent and the policy version in force before "
              "publication. " + DISCLOSURE, "",
              "## Right of reply", "",
              f"{s['institution_name']} will be offered the opportunity to respond "
              "before publication. Any response will be published in full alongside "
              "this story.", "",
              "## Corrections", "",
              MASTHEAD["corrections"], "",
              "## Sources", "",
              f"- Policy: {s['doc_url']} (version {s['doc_version']})"]
    lines += [f"- N-PX `{e['accession']}`" + (f": {e['source_url']}" if e.get("source_url") else "")
              for e in s["examples"][:6]]
    lines += ["", "*Data: the Glasshouse registry — every claim independently "
              "verifiable against the public ledger.*"]
    return "\n".join(lines)


def _desk_standards(s: dict) -> dict:
    """The written code, enforced on the exact text going upstairs: no motive
    language anywhere; right of reply present; lead-not-finding banner
    present; the citations the reader needs are in the text."""
    text = " ".join([s.get("headline", ""), s.get("standfirst", ""), s.get("body", "")])
    low = text.lower()
    hits = [w for w in BANNED_LEXICON if w in low]
    if hits:
        return _stamp(s, "standards", "spike",
                      "banned characterization in copy: " + ", ".join(sorted(hits)))
    missing = []
    if "right of reply" not in low:
        missing.append("right-of-reply block")
    if "lead" not in low:
        missing.append("lead-not-finding banner")
    if s["examples"] and not any(e["accession"] in text for e in s["examples"]):
        missing.append("vote citations")
    if s.get("doc_url") and s["doc_url"] not in text:
        missing.append("policy source link")
    if missing:
        return _stamp(s, "standards", "spike", "missing: " + ", ".join(missing))
    return _stamp(s, "standards", "pass",
                  "code held: no characterization, right of reply present, citations present")


def _desk_editor(s: dict) -> dict:
    s["state"] = "awaiting_publisher"
    return _stamp(s, "editor", "pass",
                  "assembled and sent upstairs — awaiting the human publisher")


# ── the pipeline ─────────────────────────────────────────────────────────────

def run(conn: sqlite3.Connection, *, min_rate: float = 0.5, min_votes: int = 10,
        top_n: int = 8, llm: bool = False) -> list[dict]:
    """One edition cycle: assignment → records → ledger → copy → (compose) →
    standards → editor. Writes the run to data/newsroom/runs/<date>/ and
    returns the stories (spiked ones included — the kill file is part of the
    record). Publishing is NOT part of this function."""
    matrix = investigate.build_matrix(conn)
    stories = _desk_assignment(conn, min_rate=min_rate, min_votes=min_votes,
                               top_n=top_n, matrix=matrix)
    # The case file: what ELSE converges on each story's manager × theme. The
    # publisher must see the whole case, not just the single say-vs-do pattern.
    from . import casefile
    from . import detectors as _det
    _reg = _det.registry()
    cases = {(c.institution_id, c.subject): c
             for c in casefile.build_cases(conn, min_rate=min_rate,
                                           min_votes=min_votes, matrix=matrix)}
    for s in stories:
        case = cases.get((s["institution_id"], s["theme"]))
        s["case_footprints"] = ([
            {"detector_id": f.detector_id, "name": _reg[f.detector_id].name,
             "evidence_class": _reg[f.detector_id].evidence_class,
             "headline": f.headline, "strength": f.strength}
            for f in sorted(case.footprints, key=lambda x: -x.strength)
            if f.detector_id != "broken-promise"] if case else [])
        s["n_strong"] = case.n_strong if case else 1
    for s in stories:
        _desk_records(conn, s)
        if _desk_ledger(conn, s)["verdict"] == "spike":
            continue
        _desk_copy(conn, s, llm=llm)
        s["body"] = _compose_body(s)
        if _desk_standards(s)["verdict"] == "spike":
            continue
        _desk_editor(s)
    out = NEWSROOM_DIR / "runs" / date.today().isoformat()
    if out.exists():
        shutil.rmtree(out)  # a re-run replaces the day's edition wholesale — no stale bodies
    out.mkdir(parents=True)
    for s in stories:
        if s.get("body"):
            (out / f"{s['slug']}.md").write_text(s["body"])
    (out / "stories.json").write_text(json.dumps(
        {"generated": _now(), "masthead": MASTHEAD["name"],
         "params": {"min_rate": min_rate, "min_votes": min_votes, "top_n": top_n},
         "stories": [{k: v for k, v in s.items() if k != "body"} for s in stories]},
        indent=2, default=str))
    return stories


def _latest_run_dir() -> Path | None:
    runs = NEWSROOM_DIR / "runs"
    if not runs.exists():
        return None
    dirs = sorted(p for p in runs.iterdir() if p.is_dir() and (p / "stories.json").exists())
    return dirs[-1] if dirs else None


def load_run() -> dict | None:
    """The most recent edition cycle, bodies included — what the operator
    reviews in the workbench."""
    d = _latest_run_dir()
    if not d:
        return None
    idx = json.loads((d / "stories.json").read_text())
    for s in idx["stories"]:
        md = d / f"{s['slug']}.md"
        s["body"] = md.read_text() if md.exists() else ""
        # The publish gate binds to this: the operator's approval covers THIS
        # body, not whatever a later re-run put under the same slug.
        s["body_sha256"] = hashlib.sha256(s["body"].encode()).hexdigest()
    idx["dir"] = str(d)
    return idx


def _rewrite_run(d: Path, idx: dict) -> None:
    (d / "stories.json").write_text(json.dumps(
        {k: v for k, v in idx.items() if k != "dir"} |
        {"stories": [{k: v for k, v in s.items() if k != "body"} for s in idx["stories"]]},
        indent=2, default=str))


_SLUG_RE = re.compile(r"^[a-z0-9._-]+$")


def publish(slug: str, *, note: str, human_confirmed: bool,
            body_sha256: str | None = None) -> dict:
    """The Publisher's act — always human. Requires explicit confirmation AND
    a written note (the same discipline as promoting a finding). When the
    caller supplies body_sha256 (the workbench always does), it must match
    the story body on disk — the approval covers what the human READ, not
    whatever a re-run put under the slug since. Moves the story to
    data/newsroom/published/ with the DRAFT banner replaced by the signed
    publication note."""
    if not _SLUG_RE.fullmatch(slug or ""):
        raise ValueError(f"invalid slug {slug!r}")
    if not human_confirmed:
        raise PermissionError("publishing requires an explicit human decision "
                              "(human_confirmed=True)")
    if not (note or "").strip():
        raise ValueError("publishing requires a written publisher's note")
    idx = load_run()
    if not idx:
        raise LookupError("no newsroom run on file")
    s = next((x for x in idx["stories"] if x["slug"] == slug), None)
    if s is None:
        raise LookupError(f"no story {slug!r} in the latest run")
    if s["state"] != "awaiting_publisher":
        raise ValueError(f"story {slug!r} is {s['state']}, not awaiting_publisher")
    if body_sha256 is not None and body_sha256 != s["body_sha256"]:
        raise ValueError("the story body changed since it was reviewed (a re-run "
                         "replaced the edition) — re-read it before publishing")
    published_date = _now()
    banner = (f"> **Published {published_date[:10]}** — publisher's note: {note.strip()} "
              f"Subject offered right of reply; any response is published alongside.")
    body = re.sub(r"^> \*\*DRAFT[^\n]*\n", lambda m: banner + "\n",
                  s["body"], count=1, flags=re.M)
    s["state"] = "published"
    s["trail"].append({"desk": "publisher", "verdict": "publish", "note": note.strip(),
                       "at": published_date})
    pub_dir = NEWSROOM_DIR / "published"
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / f"{slug}.md").write_text(body)
    plist = []
    pj = pub_dir / "published.json"
    if pj.exists():
        plist = json.loads(pj.read_text())
    rec = {"slug": slug, "headline": s.get("headline", ""), "standfirst": s.get("standfirst", ""),
           "institution_id": s["institution_id"], "institution_name": s["institution_name"],
           "theme": s["theme"], "published": published_date, "publisher_note": note.strip(),
           "state": "published"}
    plist = [p for p in plist if p["slug"] != slug] + [rec]
    pj.write_text(json.dumps(plist, indent=2))
    _rewrite_run(Path(idx["dir"]), idx)
    return rec | {"body": body}


def spike(slug: str, *, note: str) -> None:
    """The human kill: spike a story with a written reason, on the record."""
    if not _SLUG_RE.fullmatch(slug or ""):
        raise ValueError(f"invalid slug {slug!r}")
    idx = load_run()
    if not idx:
        raise LookupError("no newsroom run on file")
    s = next((x for x in idx["stories"] if x["slug"] == slug), None)
    if s is None:
        raise LookupError(f"no story {slug!r} in the latest run")
    s["state"] = "spiked"
    s["trail"].append({"desk": "publisher", "verdict": "spike",
                       "note": (note or "").strip() or "spiked without note", "at": _now()})
    _rewrite_run(Path(idx["dir"]), idx)


def load_published() -> list[dict]:
    """Published stories, bodies included — the ONLY stories the public site
    may render."""
    pj = NEWSROOM_DIR / "published" / "published.json"
    if not pj.exists():
        return []
    out = json.loads(pj.read_text())
    for p in out:
        md = NEWSROOM_DIR / "published" / f"{p['slug']}.md"
        p["body"] = md.read_text() if md.exists() else ""
    return sorted(out, key=lambda p: p["published"], reverse=True)
