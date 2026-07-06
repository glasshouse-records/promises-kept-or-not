"""The walk-back timeline: how a manager's policy language changed across
archived versions, documented as pure fact — quote, date, archived URL —
paired (when cached) with the vote trend for the same theme.

Registrar voice by construction: the output states that a sentence IS present
in one dated version and NOT present in a later one. It never characterizes
the change ("dropped", "abandoned", "walked back" are for downstream writers
to argue; the registrar only remembers).

Precision rules, each with a regression test in tests/test_timeline.py:
  • A version whose extracted text is shorter than MIN_TEXT_CHARS (error page,
    image-only PDF, failed extraction) is EXCLUDED from diffs — an extraction
    failure must never read as a removal.
  • Diffs happen only WITHIN one document lineage (same doc_label); a
    stewardship report and separate voting guidelines are never compared.
  • A reworded sentence (normalized similarity ≥ REVISION_RATIO) is reported
    as a revision pair, not a removal + addition.
  • Every event carries both versions' dates and URLs.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from .contradictions import (
    THEMES,
    commitment_is_discretionary,
    commitment_sentences,
    extract_text,
    is_binding_commitment,
    score_commitment_sentence,
)
from .http import DATA_DIR

TIMELINES_PATH = DATA_DIR / "investigate" / "timelines.json"

MIN_TEXT_CHARS = 400
REVISION_RATIO = 0.72


def _norm(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip(" .;").lower()
    # PDF line-break hyphenation ("long -term") must compare equal to
    # "long-term" — an extractor artifact is never a policy change.
    return re.sub(r"\s*-\s*", "-", s)


def policy_versions(conn: sqlite3.Connection, inst_id: str) -> list[dict]:
    """Distinct archived versions (deduped by content hash), oldest first per
    document lineage. Version date = wayback timestamp when present, else the
    retrieval date."""
    rows = conn.execute(
        """SELECT doc_label, url, sha256, content_path, wayback_timestamp,
                  CASE WHEN wayback_timestamp != '' THEN substr(wayback_timestamp, 1, 8)
                       ELSE replace(substr(retrieval_date, 1, 10), '-', '') END AS version
           FROM commitments WHERE institution_id = ?
           ORDER BY doc_label, version, wayback_timestamp, id""", (inst_id,))
    # Dedupe CONSECUTIVE identical content within one lineage only. A version
    # whose content REAPPEARS later (removed, then restored) must survive, or
    # the public record's last word stays a removal the manager reversed.
    last_sha: dict[str, str] = {}
    out = []
    for r in rows:
        if last_sha.get(r["doc_label"]) == r["sha256"]:
            continue
        last_sha[r["doc_label"]] = r["sha256"]
        out.append({"doc_label": r["doc_label"], "url": r["url"], "sha256": r["sha256"],
                    "content_path": r["content_path"], "version": r["version"],
                    "wayback": bool(r["wayback_timestamp"])})
    return out


def theme_sentences(text: str, theme: str) -> list[str]:
    """Binding, non-discretionary commitment sentences for a theme, in one
    version's text — the same guards the investigation engine uses."""
    pats = THEMES[theme]["commitment"]
    return [q for q in commitment_sentences(text, pats)
            if is_binding_commitment(q) and not commitment_is_discretionary(q)
            and score_commitment_sentence(q) >= 1.0]


def diff_sentences(prev: list[str], curr: list[str]) -> dict:
    """Set difference of commitment sentences between two versions, with
    near-identical (old, new) pairs reported as revisions."""
    pn = {_norm(s): s for s in prev}
    cn = {_norm(s): s for s in curr}
    removed = [pn[k] for k in pn if k not in cn]
    added = [cn[k] for k in cn if k not in pn]
    revised: list[list[str]] = []
    for old in list(removed):
        best, ratio = None, 0.0
        for new in added:
            r = SequenceMatcher(None, _norm(old), _norm(new)).ratio()
            if r > ratio:
                best, ratio = new, r
        if best is not None and ratio >= REVISION_RATIO:
            revised.append([old, best])
            removed.remove(old)
            added.remove(best)
    kept = sum(1 for k in pn if k in cn)
    return {"added": added, "removed": removed, "revised": revised, "kept": kept}


def institution_timeline(conn: sqlite3.Connection, inst_id: str) -> dict:
    """Per-theme change events between consecutive valid versions of each
    document lineage, plus a presence series (which versions carry binding
    language for the theme at all)."""
    row = conn.execute("SELECT display_name FROM institutions WHERE id = ?",
                       (inst_id,)).fetchone()
    name = row["display_name"] if row else inst_id
    lineages: dict[str, list[dict]] = {}
    for v in policy_versions(conn, inst_id):
        lineages.setdefault(v["doc_label"], []).append(v)

    themes: dict[str, dict] = {th: {"events": [], "presence": []} for th in THEMES}
    for doc_label, vs in lineages.items():
        valid: list[tuple[dict, str]] = []
        for v in vs:
            cp = v["content_path"]
            text = extract_text(Path(cp)) if cp and Path(cp).exists() else ""
            if len(text) < MIN_TEXT_CHARS:
                continue  # extraction failure / error page — never a diff side
            valid.append((v, text))
        for th in THEMES:
            by_version = [(v, theme_sentences(text, th), text) for v, text in valid]
            for v, sents, _ in by_version:
                if sents:
                    themes[th]["presence"].append(
                        {"doc_label": doc_label, "version": v["version"],
                         "url": v["url"], "n": len(sents), "sample": sents[0]})
            for (v1, s1, t1), (v2, s2, t2) in zip(by_version, by_version[1:]):
                if len(t2) < 0.5 * len(t1):
                    continue  # partial extraction (dropped pages/stub) — never diff into it
                d = diff_sentences(s1, s2)
                # The raw text is the arbiter: a sentence still present
                # verbatim in the other version's text is not added/removed,
                # whatever the sentence extractor scored (threshold flapping).
                nt1, nt2 = _norm(t1), _norm(t2)
                d["removed"] = [q for q in d["removed"] if _norm(q) not in nt2]
                d["added"] = [q for q in d["added"] if _norm(q) not in nt1]
                if d["added"] or d["removed"] or d["revised"]:
                    themes[th]["events"].append({
                        "doc_label": doc_label,
                        "from": {"version": v1["version"], "url": v1["url"],
                                 "wayback": v1["wayback"]},
                        "to": {"version": v2["version"], "url": v2["url"],
                               "wayback": v2["wayback"]},
                        **d})
    themes = {th: t for th, t in themes.items() if t["events"] or t["presence"]}
    return {"institution_id": inst_id, "name": name, "themes": themes,
            "versions": [{k: v[k] for k in ("doc_label", "version", "url", "wayback", "sha256")}
                         for lin in lineages.values() for v in lin]}


def build_timelines(conn: sqlite3.Connection) -> dict:
    """Timelines for every institution; attaches the cached per-theme vote
    trend (matrix cache) where one exists, so a language change can be read
    next to the voting record for the same theme."""
    trends: dict[str, dict[str, dict]] = {}
    with contextlib.suppress(Exception):  # trend enrichment is optional
        from .investigate import load_matrix
        matrix = load_matrix()
        if matrix:
            for inst in matrix["institutions"]:
                for th, c in inst["cells"].items():
                    if c.get("trend"):
                        trends.setdefault(inst["id"], {})[th] = c["trend"]
    out = {"generated": datetime.now(UTC).isoformat(timespec="seconds"), "institutions": {}}
    for r in conn.execute("SELECT id FROM institutions ORDER BY id"):
        t = institution_timeline(conn, r["id"])
        if not t["themes"]:
            continue
        for th, data in t["themes"].items():
            tr = trends.get(r["id"], {}).get(th)
            if tr:
                data["trend"] = tr
        out["institutions"][r["id"]] = t
    return out


def cache_timelines(conn: sqlite3.Connection) -> Path:
    data = build_timelines(conn)
    TIMELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMELINES_PATH.write_text(json.dumps(data, default=str))
    return TIMELINES_PATH


def load_timelines() -> dict | None:
    if TIMELINES_PATH.exists():
        return json.loads(TIMELINES_PATH.read_text())
    return None


def timeline_markdown(t: dict) -> str:
    """Registrar-voice Markdown: dated, linked statements of what the archived
    record contains — no characterization."""
    lines = [f"# {t['name']} — policy language over time", "",
             "Facts of record. Each entry cites the archived document versions in "
             "which the quoted language is, or is no longer, present. Verify against "
             "the linked sources; interpretation is the reader's.", ""]
    for th, data in sorted(t["themes"].items()):
        if not data["events"]:
            continue
        lines.append(f"## {th}")
        for ev in data["events"]:
            frm, to = ev["from"], ev["to"]
            lines.append(f"- **{ev['doc_label']}**, version `{frm['version']}` → "
                         f"`{to['version']}` ([earlier]({frm['url']}), [later]({to['url']})):")
            for s in ev["removed"]:
                lines.append(f"  - present in `{frm['version']}`, not present in "
                             f"`{to['version']}`: “{s}”")
            for s in ev["added"]:
                lines.append(f"  - not present in `{frm['version']}`, present in "
                             f"`{to['version']}`: “{s}”")
            for old, new in ev["revised"]:
                lines.append(f"  - revised: “{old}” → “{new}”")
        lines.append("")
    return "\n".join(lines)
