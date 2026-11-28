"""Screens over the evidence engine (roadmap 3b-b; spec docs/research/insight-rubric.md).

A screen turns the engine's proposal-level index into ranked LEADS. Nothing here is a
finding: every candidate goes to the investigative-journalist, `desk verify` and the owner.
Read-only: the engine is opened read-only and nothing is written.

Rules from the rubric, enforced here:
  * under 30 ballots -> dropped, not down-ranked;
  * rates are engine (proposal-level) rates only, never mixed with the line-level layer;
  * advisers are never pooled (an entity is `institution` or `institution/ADVISER`);
  * 2022-23 legacy rows (weight_basis 'lines') are counted and flagged: every candidate
    gives its counts and rate with and without them, and `holds_without_legacy`.

S3 peer outlier. Ballots are `ballot_key`s voted FOR/AGAINST by >= 3 entities (the engine's
`peers` definition). For entity E in theme T and year Y: `entity_rate` is E's FOR-rate on
those ballots; each other entity P gets a rate over the ballots E and P both voted (only if
that overlap is >= 30 ballots); `peer_median` is the median of those rates and `n_peers`
their number (>= 2 required). `gap_pp` = (entity_rate - peer_median) * 100. Candidate when
|gap_pp| >= 15 and n_ballots >= 30. score = |gap_pp| * sqrt(n_ballots): size matters as
much as distance (rubric item 2).

S5 ESG-labelled funds. A fund series whose name matches ESG_NAME is compared with the
SAME entity's (institution + adviser) other, non-ESG-named series on the SAME
environmental/social shareholder proposals (roll-back proposals excluded as the engine
does). A series' position on a proposal is FOR or AGAINST only if all its decided lines
agree. `entity_rate` = the ESG series' FOR-rate over the shared proposals; `peer_median` =
mean over proposals of the FOR share among the other series. Both directions are reported:
`differs` (gap >= +15 pp), `with_house` (gap <= +5 pp, i.e. within 5 pp or below),
`between`. Each theme (ES_THEMES) is scored on its own, the 30-ballot floor applies per
row, and the `pooled` row (all themes) is a summary only. An ESG adviser group (adviser
key ending _SUSTAINABILITY/_SOCIAL/_ESG/_SUSTAINABLE, or every series ESG-named) is
compared, kind `group`, with the same institution's non-ESG group sharing the most items.
An item filed under several proposal ids (same company, meeting, wording) counts once.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict

from . import engine
from .ledger import NON_LEGACY_VOTE_SQL, iso_meeting_date

MIN_BALLOTS = 30
MIN_MANAGERS = 3
MIN_OVERLAP = 30
MIN_PEERS = 2
GAP_PP = 15.0
S5_TOLERANCE = 0.05
S5_DIFFERS_PP = 15.0
ES_THEMES = ("climate", "nature", "human-rights", "labor-rights", "board-diversity")

MIN_MATCH_RATE = 0.5

# Adviser keys that are catch-all buckets, not a manager: never a peer, never a comparison
# group, never an entity. (engine.UNLABELLED, engine.EXTERNAL, and the config key UNRESOLVED.)
CATCH_ALL = frozenset({"UNRESOLVED", engine.EXTERNAL, engine.UNLABELLED})

# Proposal wordings whose direction is uncertain (does FOR mean more or less of the theme?):
# direction uncertain, check sponsor. Excluded from S3/S5 rates by default and counted;
# `include_ambiguous=True` / `--include-ambiguous` keeps them.
AMBIGUOUS_POLARITY = re.compile(
    r"congruen|misalign|third-party|retirement plan.*climate|net zero.*risk"
    r"|climate commitments.*impact", re.IGNORECASE)

ESG_GROUP_KEY = re.compile(r"_(?:SUSTAINABILITY|SOCIAL|ESG|SUSTAINABLE)$", re.IGNORECASE)

# Whole words, except the stems Sustainab* and Responsib* (Sustainable, Sustainability,
# Responsible, Responsibly). "Impactful Growth", "Greenwich", "Socialite", "Cleanse" and
# "Parisian" do not match: precision over recall.
ESG_NAME = re.compile(
    r"\b(?:ESG|Sustainab\w*|Climate|Clean|Green|Responsib\w*|Impact|Social|Paris"
    r"|Low[\s-]Carbon|Fossil[\s-]Fuel[\s-]Free)\b", re.IGNORECASE)


def esg_name(name: str | None) -> bool:
    return bool(name and ESG_NAME.search(name))


def _split_entity(ent: str) -> tuple[str, str | None]:
    inst, _, adv = ent.partition("/")
    return inst, adv or None


def is_catch_all(ent: str) -> bool:
    """`institution/UNRESOLVED`, `/EXTERNAL`, `/unlabelled`: a bucket, not a manager."""
    return _split_entity(ent)[1] in CATCH_ALL


def _firm_keys(eng: engine.Engine) -> dict[str, set]:
    """institution -> the real (non catch-all) adviser keys its registrants can resolve to."""
    out: dict[str, set] = defaultdict(set)
    for r in eng.db.execute("SELECT institution_id, adviser, rules FROM registrants"):
        keys = {r["adviser"]} - {None}
        if r["rules"]:
            keys |= engine.rule_keys(json.loads(r["rules"]))
        out[r["institution_id"]] |= keys - CATCH_ALL
    return out


def firm_of(ent: str, firm_keys: dict[str, set]) -> str:
    """The firm behind an entity, so one adviser filed under two institutions (Harris
    Associates as `harris_oakmark` and `natixis/HARRIS_ASSOCIATES`) is one firm. An entity
    `inst/KEY` is firm KEY; a bare `inst` is firm KEY when the config gives the institution
    exactly one real adviser key, else the institution itself."""
    inst, adv = _split_entity(ent)
    if adv:
        return f"adviser:{adv}"
    keys = firm_keys.get(inst, set())
    return f"adviser:{next(iter(keys))}" if len(keys) == 1 else f"institution:{inst}"


def _reproduce_peers(ent: str, theme: str, year: int) -> str:
    inst, adv = _split_entity(ent)
    cmd = f"glasshouse ask peers theme={theme} year={year} min_managers={MIN_MANAGERS}"
    cmd += f" institution={inst}"
    return cmd + (f" adviser={adv}" if adv else "")


def _rate(votes) -> float:
    votes = list(votes)
    return sum(1 for v in votes if v == "FOR") / len(votes)


# ------------------------------------------------------------------------- S3

def _vs_peers(ent: str, ballots: set, by_ent: dict) -> tuple[float, float, int]:
    """(entity_rate, peer_median, n_peers) over `ballots`, each peer on its overlap."""
    mine = by_ent[ent]
    rates = []
    for other, theirs in by_ent.items():
        if other == ent:
            continue
        common = ballots & theirs.keys()
        if len(common) >= MIN_OVERLAP:
            rates.append(_rate(theirs[b][0] for b in common))
    rate = _rate(mine[b][0] for b in ballots)
    return rate, (statistics.median(rates) if rates else float("nan")), len(rates)


def s3_peer_outliers(eng: engine.Engine, year: int | None = None,
                    include_ambiguous: bool = False) -> dict:
    out, low_match = [], []
    firm_keys = _firm_keys(eng)
    catch_pids, catch_ents, amb_pids, dup_dropped = set(), set(), set(), []
    for theme in engine.THEMES:
        join, w, p = eng._where(theme=theme, year=year)
        rows = eng.db.execute(
            f"SELECT p.proposal_id pid, p.year y, p.ballot_key bk, p.description d, "
            f"{engine._ENTITY.format('p')} ent, p.position pos, p.weight_basis wb "
            f"FROM proposals p {join} WHERE {w} "
            f"AND p.position IN ('FOR','AGAINST') ORDER BY p.proposal_id", p).fetchall()
        ballots = defaultdict(lambda: defaultdict(dict))        # year -> bk -> ent -> row
        decided = defaultdict(lambda: defaultdict(set))         # year -> ent -> proposal ids
        for r in rows:
            if r["y"] is None:
                continue
            if is_catch_all(r["ent"]):
                catch_pids.add(r["pid"])
                catch_ents.add(r["ent"])
                continue
            if not include_ambiguous and AMBIGUOUS_POLARITY.search(r["d"] or ""):
                amb_pids.add(r["pid"])
                continue
            decided[r["y"]][r["ent"]].add(r["pid"])
            if r["bk"] is not None:
                ballots[r["y"]][r["bk"]][r["ent"]] = (r["pos"], r["pid"], r["wb"] == "lines")
        for y, bks in ballots.items():
            # one firm once: of several entities of one firm keep the one with most ballots
            size = defaultdict(int)
            for v in bks.values():
                for e in v:
                    size[e] += 1
            keep: dict[str, str] = {}
            for e in sorted(size, key=lambda e: (-size[e], e)):
                keep.setdefault(firm_of(e, firm_keys), e)
            dropped = {e for e in size if keep[firm_of(e, firm_keys)] != e}
            dup_dropped += [(theme, y, e) for e in sorted(dropped)]
            shared = {bk: {e: x for e, x in v.items() if e not in dropped}
                      for bk, v in bks.items()}
            shared = {bk: v for bk, v in shared.items() if len(v) >= MIN_MANAGERS}
            legacy = {bk for bk, v in shared.items() if any(x[2] for x in v.values())}
            by_ent = defaultdict(dict)
            for bk, v in shared.items():
                for ent, row in v.items():
                    by_ent[ent][bk] = row
            for ent, mine in by_ent.items():
                if len(mine) < MIN_BALLOTS:
                    continue
                allb = set(mine)
                rate, med, n_peers = _vs_peers(ent, allb, by_ent)
                if n_peers < MIN_PEERS:
                    continue
                gap = (rate - med) * 100
                if abs(gap) < GAP_PP:
                    continue
                exb = allb - legacy
                ex = None
                if exb:
                    ex = _vs_peers(ent, exb, by_ent)
                ex_gap = (ex[0] - ex[1]) * 100 if ex and ex[2] >= MIN_PEERS else None
                deviating = sorted(
                    (mine[bk][1], bk) for bk in allb
                    if (mine[bk][0] == "FOR") != (_rate(
                        v[0] for e2, v in shared[bk].items() if e2 != ent) > 0.5))
                ex_ids = deviating[:3]
                n_total = len(decided[y][ent])
                n_matched = len({mine[bk][1] for bk in allb})
                match_rate = n_matched / n_total if n_total else 0.0
                row = {
                    "screen": "S3", "entity": ent, "theme": theme, "year": y,
                    "n_ballots": len(allb), "entity_rate": round(rate, 4),
                    "peer_median": round(med, 4), "n_peers": n_peers,
                    "gap_pp": round(gap, 2),
                    "score": round(abs(gap) * math.sqrt(len(allb)), 2),
                    "match_rate": round(match_rate, 4), "n_matched": n_matched,
                    "n_theme_year_proposals": n_total,
                    "includes_legacy": bool(allb & legacy),
                    "n_legacy_ballots": len(allb & legacy),
                    "n_ballots_ex_legacy": len(exb),
                    "entity_rate_ex_legacy": round(ex[0], 4) if ex else None,
                    "peer_median_ex_legacy": round(ex[1], 4) if ex else None,
                    "gap_pp_ex_legacy": round(ex_gap, 2) if ex_gap is not None else None,
                    "holds_without_legacy": bool(
                        ex_gap is not None and len(exb) >= MIN_BALLOTS
                        and abs(ex_gap) >= GAP_PP and (ex_gap > 0) == (gap > 0)),
                    "example_proposal_ids": [i for i, _ in ex_ids],
                    "example_ballot_keys": [k for _, k in ex_ids],
                    "reproduce": [_reproduce_peers(ent, theme, y)]}
                (out if match_rate >= MIN_MATCH_RATE else low_match).append(row)
    for lst in (out, low_match):
        lst.sort(key=lambda c: (-c["score"], c["entity"], c["theme"], c["year"]))
    return {"screen": "S3", "year": year, "candidates": out, "matched_funds": [],
            "low_match": low_match, "excluded_catch_all": len(catch_pids),
            "excluded_catch_all_entities": len(catch_ents),
            "n_ambiguous_excluded": len(amb_pids),
            "duplicate_firm_entities_dropped": len(dup_dropped)}


# ------------------------------------------------------------------------- S5

def _series_names(eng: engine.Engine) -> dict[str, tuple[str, str]]:
    return eng.series_names()


def _esg_series(eng: engine.Engine) -> dict[str, dict]:
    """series_id -> {institution, name} for series whose latest name matches ESG_NAME."""
    return {sid: {"institution": iid, "name": name}
            for sid, (name, iid) in sorted(_series_names(eng).items()) if esg_name(name)}


def _bulk_lines(eng: engine.Engine, props: dict[int, dict], names: dict) -> dict[int, list]:
    """The fund lines behind each proposal in `props` (the engine's bulk loader, which
    follows the matching rules of `Engine.fund_votes`; a test pins the two together)."""
    return eng.bulk_fund_lines(props, names)


def _positions(lines) -> dict[str, tuple[str, str | None]]:
    """series -> (FOR|AGAINST, name) for series whose decided lines all agree."""
    seen: dict[str, set] = defaultdict(set)
    names: dict[str, str | None] = {}
    for ln in lines:
        hv = (ln["how_voted"] or "").upper()
        if hv in ("FOR", "AGAINST", "WITHHOLD"):
            seen[ln["fund_series"]].add("FOR" if hv == "FOR" else "AGAINST")
            names[ln["fund_series"]] = ln["fund_series_name"]
    return {s: (next(iter(v)), names[s]) for s, v in seen.items() if len(v) == 1}


def s5_label(gap_pp: float) -> str:
    """`differs`: the ESG-named fund votes at least 15 pp MORE favourably than its house;
    `with_house`: within 5 pp of it, or below; otherwise `between`."""
    if gap_pp >= S5_DIFFERS_PP:
        return "differs"
    return "with_house" if gap_pp <= S5_TOLERANCE * 100 else "between"


def _dedupe(rows: list) -> tuple[list, int]:
    """One row per real item (engine.proposal_key), lowest proposal id first."""
    seen, kept = set(), []
    for r in sorted(rows, key=lambda r: r[0]):
        k = engine.proposal_key(r[1])
        if k not in seen:
            seen.add(k)
            kept.append(r)
    return kept, len(rows) - len(kept)


def _s5_row(*, kind, ent, sid, name, theme, rows, n_peers, compared_with, collapsed) -> dict | None:
    """One candidate from `rows` = [(proposal id, proposal, position, comparison FOR-rate)]
    already de-duplicated; None under the 30-ballot floor."""
    n = len(rows)
    if n < MIN_BALLOTS:
        return None
    rate = _rate(r[2] for r in rows)
    med = sum(r[3] for r in rows) / n
    gap = round((rate - med) * 100, 2)
    label = s5_label(gap)
    legacy = [r for r in rows if r[1]["weight_basis"] == "lines"]
    ex = [r for r in rows if r[1]["weight_basis"] != "lines"]
    ex_rate = _rate(r[2] for r in ex) if ex else None
    ex_med = sum(r[3] for r in ex) / len(ex) if ex else None
    ex_gap = round((ex_rate - ex_med) * 100, 2) if ex else None
    deviating = sorted((r[0], r[1]["ballot_key"]) for r in rows
                       if (r[2] == "FOR") != (r[3] > 0.5)) or sorted(
        (r[0], r[1]["ballot_key"]) for r in rows)
    ex_ids = deviating[:3]
    repro = []
    if kind == "series":
        repro.append(f"glasshouse ask fund_record series_id={sid}"
                     + ("" if theme == "pooled" else f" theme={theme}"))
    repro += [f"glasshouse ask fund_votes proposal_id={i}" for i, _ in ex_ids]
    return {
        "screen": "S5", "kind": kind, "label": label, "pooled": theme == "pooled",
        "entity": ent, "series_id": sid, "series_name": name, "theme": theme,
        "compared_with": compared_with,
        "year": ",".join(str(y) for y in sorted({r[1]["year"] for r in rows if r[1]["year"]})),
        "n_ballots": n, "entity_rate": round(rate, 4), "peer_median": round(med, 4),
        "n_peers": n_peers, "gap_pp": gap,
        "score": round(((rate - med) if label != "with_house" else (med - rate))
                       * 100 * math.sqrt(n), 2),
        "n_collapsed_duplicates": collapsed,
        "includes_legacy": bool(legacy), "n_legacy_ballots": len(legacy),
        "n_ballots_ex_legacy": len(ex),
        "entity_rate_ex_legacy": round(ex_rate, 4) if ex else None,
        "peer_median_ex_legacy": round(ex_med, 4) if ex else None,
        "gap_pp_ex_legacy": ex_gap,
        "holds_without_legacy": bool(ex) and len(ex) >= MIN_BALLOTS and (
            s5_label(ex_gap) == label),
        "example_proposal_ids": [i for i, _ in ex_ids],
        "example_ballot_keys": [k for _, k in ex_ids],
        "reproduce": repro}


def _is_esg_group(ent: str, member_names: set) -> bool:
    """An ESG adviser group: its adviser key ends _SUSTAINABILITY, _SOCIAL, _ESG or
    _SUSTAINABLE, or every one of its series carries an ESG name."""
    _, adv = _split_entity(ent)
    if adv and ESG_GROUP_KEY.search(adv):
        return True
    return bool(member_names) and all(esg_name(n) for n in member_names)


def s5_esg_funds(eng: engine.Engine, year: int | None = None,
                 include_ambiguous: bool = False) -> dict:
    esg = _esg_series(eng)
    matched = [{"series_id": s, "institution": v["institution"], "series_name": v["name"]}
               for s, v in esg.items()]
    insts = {v["institution"] for v in esg.values()}
    empty = {"screen": "S5", "year": year, "candidates": [], "matched_funds": matched,
             "summary": _s5_summary([]), "n_collapsed_duplicates": 0,
             "excluded_catch_all": 0, "excluded_catch_all_entities": 0,
             "n_ambiguous_excluded": 0}
    if not insts:
        return empty
    iso = iso_meeting_date("v.meeting_date")
    seen_pairs: set = set()          # (institution, cusip|issuer, ISO date) an ESG series voted
    ids = ",".join("?" * len(esg))
    for r in eng.ledger.execute(
            f"SELECT f.institution_id i, UPPER(TRIM(v.cusip)) c, v.issuer_name n, {iso} d "
            f"FROM votes v JOIN filings f ON f.accession = v.accession "
            f"WHERE v.vote_series IN ({ids}) AND v.vote_source = 'SECURITY HOLDER' "
            f"AND v.is_duplicate = 0 AND {NON_LEGACY_VOTE_SQL}", list(esg)):
        seen_pairs.add((r["i"], r["c"], r["d"]))
        seen_pairs.add((r["i"], r["n"], r["d"]))
    props: dict[int, dict] = {}
    catch_pids, catch_ents, amb_pids = set(), set(), set()
    for theme in ES_THEMES:
        join, w, p = eng._where(theme=theme, year=year)
        for r in eng.db.execute(
                f"SELECT p.*, {engine._ENTITY.format('p')} ent FROM proposals p {join} "
                f"WHERE {w}", p):
            if r["institution_id"] in insts and (
                    (r["institution_id"], r["cusip"], r["meeting_date"]) in seen_pairs
                    or (r["institution_id"], r["issuer_name"], r["meeting_date"]) in seen_pairs):
                if is_catch_all(r["ent"]):
                    catch_pids.add(r["proposal_id"])
                    catch_ents.add(r["ent"])
                    continue
                if not include_ambiguous and AMBIGUOUS_POLARITY.search(r["description"] or ""):
                    amb_pids.add(r["proposal_id"])
                    continue
                row = props.setdefault(r["proposal_id"], dict(r) | {"themes_es": set()})
                row["themes_es"].add(theme)
    all_lines = _bulk_lines(eng, props, _series_names(eng))
    members: dict[str, set] = defaultdict(set)      # entity -> names of its series seen
    acc: dict[tuple, dict] = defaultdict(lambda: {"props": [], "others": set()})
    for pid in sorted(props):
        pr = props[pid]
        for ln in all_lines.get(pid, ()):
            members[pr["ent"]].add(ln["fund_series_name"])
        pos = _positions(all_lines.get(pid, ()))
        other = {s: v[0] for s, v in pos.items() if not esg_name(v[1])}
        if not other:
            continue
        o_for = _rate(other.values())
        for s, (position, name) in pos.items():
            if esg_name(name):
                a = acc[(pr["ent"], s, name)]
                a["props"].append((pid, pr, position, o_for))
                a["others"] |= set(other)
    out, collapsed_total = [], 0
    for (ent, sid, name), a in acc.items():
        pooled_collapsed = 0
        for theme in (*ES_THEMES, "pooled"):
            rows = [r for r in a["props"] if theme == "pooled" or theme in r[1]["themes_es"]]
            rows, collapsed = _dedupe(rows)
            if theme == "pooled":
                pooled_collapsed = collapsed
            row = _s5_row(kind="series", ent=ent, sid=sid, name=name, theme=theme, rows=rows,
                          n_peers=len(a["others"]), compared_with=ent, collapsed=collapsed)
            if row:
                out.append(row)
        collapsed_total += pooled_collapsed
    # ESG adviser groups against the same institution's main group, same items
    by_ent: dict[str, list] = defaultdict(list)
    for pid in sorted(props):
        by_ent[props[pid]["ent"]].append(pid)
    esg_groups = {e for e in by_ent if _split_entity(e)[1]
                  and _is_esg_group(e, members.get(e, set()))}
    for g in sorted(esg_groups):
        inst = _split_entity(g)[0]
        mine = {engine.proposal_key(props[p]): p for p in reversed(by_ent[g])}
        best = None
        for m in sorted(e for e in by_ent if e != g and _split_entity(e)[0] == inst
                        and e not in esg_groups):
            overlap = len(mine.keys() & {engine.proposal_key(props[p]) for p in by_ent[m]})
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, m)
        if not best:
            continue
        main = {engine.proposal_key(props[p]): p for p in reversed(by_ent[best[1]])}
        for theme in (*ES_THEMES, "pooled"):
            rows, kept = [], 0
            for k, pid in sorted(mine.items(), key=lambda kv: kv[1]):
                pr, mp = props[pid], props.get(main.get(k))
                if theme != "pooled" and theme not in pr["themes_es"]:
                    continue
                kept += 1
                if mp and pr["position"] in ("FOR", "AGAINST") and mp["position"] in (
                        "FOR", "AGAINST"):
                    rows.append((pid, pr, pr["position"], 1.0 if mp["position"] == "FOR" else 0.0))
            n_dup = sum(1 for p in by_ent[g] if theme == "pooled" or theme in props[p]["themes_es"]) - kept
            row = _s5_row(kind="group", ent=g, sid="", name=_split_entity(g)[1], theme=theme,
                          rows=rows, n_peers=1, compared_with=best[1], collapsed=n_dup)
            if row:
                out.append(row)
    out.sort(key=lambda c: (-c["score"], c["entity"], c["series_id"], c["theme"]))
    return {"screen": "S5", "year": year, "candidates": out, "matched_funds": matched,
            "summary": _s5_summary(out), "n_collapsed_duplicates": collapsed_total,
            "excluded_catch_all": len(catch_pids),
            "excluded_catch_all_entities": len(catch_ents),
            "n_ambiguous_excluded": len(amb_pids)}


def _s5_summary(cands: list) -> str:
    rows = [c for c in cands if c["kind"] == "series" and c["pooled"]]
    n = {k: sum(1 for c in rows if c["label"] == k) for k in ("with_house", "differs", "between")}
    return (f"{len(rows)} ESG-named series with ≥30 ballots: {n['with_house']} with house "
            f"(±5pp), {n['differs']} differ (+15pp or more), {n['between']} between")


# ------------------------------------------------------------------------- run

SCREENS = {"S3": s3_peer_outliers, "S5": s5_esg_funds}


def run(eng: engine.Engine, which: str = "all", year: int | None = None,
        include_ambiguous: bool = False) -> dict:
    names = list(SCREENS) if which.lower() == "all" else [which.upper()]
    bad = [n for n in names if n not in SCREENS]
    if bad:
        raise ValueError(f"unknown screen {which!r}; known: {', '.join(SCREENS)}, all")
    res = {}
    for n in names:
        r = SCREENS[n](eng, year=year, include_ambiguous=include_ambiguous)
        r["n_candidates"] = len(r["candidates"])
        res[n] = r
    return res


def render(res: dict, top: int | None = None) -> str:
    lines = []
    for n, r in res.items():
        shown = r["candidates"][:top] if top else r["candidates"]
        lines.append(f"== {n}: {r['n_candidates']} candidates (leads, not findings)"
                     f"{'; showing top ' + str(len(shown)) if shown else ''}")
        if r.get("summary"):
            lines.append(r["summary"])
        lines.append(f"excluded: {r.get('excluded_catch_all', 0)} proposals of "
                     f"{r.get('excluded_catch_all_entities', 0)} catch-all entities "
                     f"(UNRESOLVED/EXTERNAL/unlabelled); {r.get('n_ambiguous_excluded', 0)} "
                     f"ambiguous-polarity proposals (--include-ambiguous keeps them)"
                     + (f"; {r['duplicate_firm_entities_dropped']} duplicate-firm entity-years"
                        if "duplicate_firm_entities_dropped" in r else "")
                     + (f"; {len(r['low_match'])} rows under the {MIN_MATCH_RATE:.0%} "
                        f"match guard held out as low_match" if "low_match" in r else ""))
        lines.append(f"{'score':>8} {'entity':<28} {'theme':<16} {'year':<10} {'n':>5} "
                     f"{'rate':>6} {'peers':>6} {'gap_pp':>7} {'np':>3} {'legacy n':>9} "
                     f"{'holds w/o':>9}")
        for c in shown:
            ent = c["entity"] + (f" [{c['series_name']}]" if "series_name" in c else "")
            if c.get("label"):
                ent = f"{c['label']} {ent}"
            lines.append(f"{c['score']:>8.1f} {ent[:60]:<28} {c['theme'][:16]:<16} "
                         f"{str(c['year'])[:10]:<10} {c['n_ballots']:>5} {c['entity_rate']:>6.3f} "
                         f"{c['peer_median']:>6.3f} {c['gap_pp']:>7.1f} {c['n_peers']:>3} "
                         f"{c['n_legacy_ballots']:>9} {str(c['holds_without_legacy']):>9}")
            lines.append(f"{'':>8} ids {c['example_proposal_ids']}  {c['reproduce'][0]}")
        if r["matched_funds"]:
            lines.append(f"-- {n}: series names matched by the ESG regex "
                         f"({len(r['matched_funds'])}); check by eye:")
            lines += [f"   {m['institution']:<22} {m['series_id']:<12} {m['series_name']}"
                      for m in r["matched_funds"]]
    return "\n".join(lines)
