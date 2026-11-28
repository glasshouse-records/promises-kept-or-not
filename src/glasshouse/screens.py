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
environmental/social shareholder proposals (themes in ES_THEMES, roll-back proposals
excluded as the engine does; the engine's proposals are all vote_source SECURITY HOLDER).
A series' position on a proposal is FOR or AGAINST only if all its decided lines agree.
Shared proposals = those where the ESG series and >= 1 other series have a position.
`entity_rate` = the ESG series' FOR-rate over them; `peer_median` = mean over proposals of
the FOR share among the other series (one proposal, one vote); `n_peers` = the number of
other series seen. Candidate when entity_rate <= peer_median + 0.05 and n_ballots >= 30.
score = (peer_median - entity_rate) * 100 * sqrt(n_ballots).
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
ES_THEMES = ("climate", "nature", "human-rights", "labor-rights", "board-diversity")

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


def s3_peer_outliers(eng: engine.Engine, year: int | None = None) -> dict:
    out = []
    for theme in engine.THEMES:
        join, w, p = eng._where(theme=theme, year=year)
        rows = eng.db.execute(
            f"SELECT p.proposal_id pid, p.year y, p.ballot_key bk, "
            f"{engine._ENTITY.format('p')} ent, p.position pos, p.weight_basis wb "
            f"FROM proposals p {join} WHERE {w} AND p.ballot_key IS NOT NULL "
            f"AND p.position IN ('FOR','AGAINST') ORDER BY p.proposal_id", p).fetchall()
        ballots = defaultdict(lambda: defaultdict(dict))        # year -> bk -> ent -> row
        for r in rows:
            if r["y"] is not None:
                ballots[r["y"]][r["bk"]][r["ent"]] = (r["pos"], r["pid"], r["wb"] == "lines")
        for y, bks in ballots.items():
            shared = {bk: v for bk, v in bks.items() if len(v) >= MIN_MANAGERS}
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
                out.append({
                    "screen": "S3", "entity": ent, "theme": theme, "year": y,
                    "n_ballots": len(allb), "entity_rate": round(rate, 4),
                    "peer_median": round(med, 4), "n_peers": n_peers,
                    "gap_pp": round(gap, 2),
                    "score": round(abs(gap) * math.sqrt(len(allb)), 2),
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
                    "reproduce": [_reproduce_peers(ent, theme, y)]})
    out.sort(key=lambda c: (-c["score"], c["entity"], c["theme"], c["year"]))
    return {"screen": "S3", "year": year, "candidates": out, "matched_funds": []}


# ------------------------------------------------------------------------- S5

def _series_names(eng: engine.Engine) -> dict[str, tuple[str, str]]:
    """series_id -> (name, institution) from the most recent filing naming it (the rule
    `fund_votes` uses for `fund_series_name`)."""
    latest: dict[str, tuple] = {}
    for r in eng.ledger.execute(
            "SELECT fs.series_id sid, fs.name name, f.institution_id iid, "
            "COALESCE(f.filing_date, f.period_of_report, '') d, f.accession acc "
            "FROM fund_series fs JOIN filings f ON f.accession = fs.accession "
            "WHERE fs.name IS NOT NULL AND fs.name != ''"):
        key = (r["d"], r["acc"])
        if r["sid"] not in latest or key > latest[r["sid"]][0]:
            latest[r["sid"]] = (key, r["name"], r["iid"])
    return {sid: (name, iid) for sid, (_, name, iid) in latest.items()}


def _esg_series(eng: engine.Engine) -> dict[str, dict]:
    """series_id -> {institution, name} for series whose latest name matches ESG_NAME."""
    return {sid: {"institution": iid, "name": name}
            for sid, (name, iid) in sorted(_series_names(eng).items()) if esg_name(name)}


def _bulk_lines(eng: engine.Engine, props: dict[int, dict], names: dict) -> dict[int, list]:
    """The fund lines behind each proposal in `props`, in ONE pass over the ledger.
    Same matching rules as `Engine.fund_votes` (which costs ~0.3 s a call, too slow for
    thousands of proposals); a test pins the two together. Returns pid -> lines with
    fund_series, fund_series_name and how_voted."""
    rules = defaultdict(dict)       # institution -> cik -> key rules
    for x in eng.db.execute("SELECT institution_id, cik, adviser, rules FROM registrants"):
        rules[x["institution_id"]][x["cik"]] = (
            json.loads(x["rules"]) if x["rules"] else
            {"default": x["adviser"], "history": [], "series": {}})
    full = {pid: eng.db.execute("SELECT * FROM proposals WHERE proposal_id=?",
                                (pid,)).fetchone() for pid in props}
    index = defaultdict(list)       # (institution, cusip|issuer, ISO day) -> proposal ids
    for pid, r in full.items():
        index[(r["institution_id"], r["cusip"], r["meeting_date"])].append(pid)
        index[(r["institution_id"], r["issuer_name"], r["meeting_date"])].append(pid)
    first = {}
    for pid, r in full.items():     # a legacy decision is one printed item: its number
        f = eng.ledger.execute(
            "SELECT legacy_format IS NOT NULL, proposal_number FROM votes WHERE id=?",
            (r["vote_id"],)).fetchone()
        first[pid] = (bool(f and f[0]), ((f[1] if f else "") or "").strip())
    want = {pid: engine.norm(r["description"]) for pid, r in full.items()}
    iso = iso_meeting_date("v.meeting_date")
    insts = sorted({r["institution_id"] for r in full.values()})
    out: dict[int, list] = defaultdict(list)
    for v in eng.ledger.execute(
            f"SELECT f.institution_id AS inst, v.vote_series, v.how_voted, "
            f"v.vote_description, f.cik, UPPER(TRIM(v.cusip)) AS cusip, v.issuer_name, "
            f"{iso} AS md, v.proposal_number AS pnum, (v.legacy_format IS NOT NULL) AS lg "
            f"FROM votes v JOIN filings f ON f.accession = v.accession "
            f"WHERE f.institution_id IN ({','.join('?' * len(insts))}) "
            f"AND v.is_duplicate=0 AND {NON_LEGACY_VOTE_SQL} "
            f"AND v.vote_source='SECURITY HOLDER'", insts):
        inst = v["inst"]
        pids = {*index.get((inst, v["cusip"], v["md"]), ()),
                *index.get((inst, v["issuer_name"], v["md"]), ())}
        for pid in pids:
            r = full[pid]
            if r["adviser"] and (engine.resolve_key(
                    rules[inst].get(engine._norm_cik(v["cik"])), v["vote_series"],
                    r["meeting_date"]) or engine.UNLABELLED) != r["adviser"]:
                continue                    # another adviser's fund
            is_legacy, item_no = first[pid]
            if bool(v["lg"]) != is_legacy:
                continue                    # the other era's line
            if is_legacy and (v["pnum"] or "").strip() != item_no:
                continue
            if engine.norm(v["vote_description"]) == want[pid]:
                out[pid].append({
                    "fund_series": v["vote_series"], "how_voted": v["how_voted"],
                    "fund_series_name": (names.get(v["vote_series"]) or (None,))[0]})
    return out


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


def s5_esg_funds(eng: engine.Engine, year: int | None = None) -> dict:
    esg = _esg_series(eng)
    matched = [{"series_id": s, "institution": v["institution"], "series_name": v["name"]}
               for s, v in esg.items()]
    insts = {v["institution"] for v in esg.values()}
    if not insts:
        return {"screen": "S5", "year": year, "candidates": [], "matched_funds": []}
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
    for theme in ES_THEMES:
        join, w, p = eng._where(theme=theme, year=year)
        for r in eng.db.execute(
                f"SELECT p.proposal_id pid, p.institution_id i, p.cusip c, p.issuer_name n, "
                f"p.meeting_date d, p.ballot_key bk, p.weight_basis wb, p.year y, "
                f"{engine._ENTITY.format('p')} ent FROM proposals p {join} WHERE {w}", p):
            if r["i"] in insts and ((r["i"], r["c"], r["d"]) in seen_pairs
                                    or (r["i"], r["n"], r["d"]) in seen_pairs):
                row = props.setdefault(r["pid"], dict(r) | {"themes": set()})
                row["themes"].add(theme)
    acc: dict[tuple, dict] = defaultdict(lambda: {"props": [], "others": set()})
    all_lines = _bulk_lines(eng, props, _series_names(eng))
    for pid in sorted(props):
        pr = props[pid]
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
    out = []
    for (ent, sid, name), a in acc.items():
        rows = a["props"]
        n = len(rows)
        if n < MIN_BALLOTS:
            continue
        rate = _rate(r[2] for r in rows)
        med = sum(r[3] for r in rows) / n
        if rate > med + S5_TOLERANCE:
            continue
        legacy = [r for r in rows if r[1]["wb"] == "lines"]
        ex = [r for r in rows if r[1]["wb"] != "lines"]
        ex_rate = _rate(r[2] for r in ex) if ex else None
        ex_med = sum(r[3] for r in ex) / len(ex) if ex else None
        ex_ok = bool(ex) and len(ex) >= MIN_BALLOTS and ex_rate <= ex_med + S5_TOLERANCE
        deviating = sorted((r[0], r[1]["bk"]) for r in rows
                           if (r[2] == "FOR") != (r[3] > 0.5)) or sorted(
            (r[0], r[1]["bk"]) for r in rows)
        ex_ids = deviating[:3]
        out.append({
            "screen": "S5", "entity": ent, "series_id": sid, "series_name": name,
            "theme": ",".join(sorted(set().union(*(r[1]["themes"] for r in rows)))),
            "year": ",".join(str(y) for y in sorted({r[1]["y"] for r in rows if r[1]["y"]})),
            "n_ballots": n, "entity_rate": round(rate, 4), "peer_median": round(med, 4),
            "n_peers": len(a["others"]), "gap_pp": round((rate - med) * 100, 2),
            "score": round((med - rate) * 100 * math.sqrt(n), 2),
            "includes_legacy": bool(legacy), "n_legacy_ballots": len(legacy),
            "n_ballots_ex_legacy": len(ex),
            "entity_rate_ex_legacy": round(ex_rate, 4) if ex else None,
            "peer_median_ex_legacy": round(ex_med, 4) if ex else None,
            "gap_pp_ex_legacy": round((ex_rate - ex_med) * 100, 2) if ex else None,
            "holds_without_legacy": ex_ok,
            "example_proposal_ids": [i for i, _ in ex_ids],
            "example_ballot_keys": [k for _, k in ex_ids],
            "reproduce": [f"glasshouse ask fund_votes proposal_id={i}" for i, _ in ex_ids]})
    out.sort(key=lambda c: (-c["score"], c["entity"], c["series_id"]))
    return {"screen": "S5", "year": year, "candidates": out, "matched_funds": matched}


# ------------------------------------------------------------------------- run

SCREENS = {"S3": s3_peer_outliers, "S5": s5_esg_funds}


def run(eng: engine.Engine, which: str = "all", year: int | None = None) -> dict:
    names = list(SCREENS) if which.lower() == "all" else [which.upper()]
    bad = [n for n in names if n not in SCREENS]
    if bad:
        raise ValueError(f"unknown screen {which!r}; known: {', '.join(SCREENS)}, all")
    res = {}
    for n in names:
        r = SCREENS[n](eng, year=year)
        r["n_candidates"] = len(r["candidates"])
        res[n] = r
    return res


def render(res: dict, top: int | None = None) -> str:
    lines = []
    for n, r in res.items():
        shown = r["candidates"][:top] if top else r["candidates"]
        lines.append(f"== {n}: {r['n_candidates']} candidates (leads, not findings)"
                     f"{'; showing top ' + str(len(shown)) if shown else ''}")
        lines.append(f"{'score':>8} {'entity':<28} {'theme':<16} {'year':<10} {'n':>5} "
                     f"{'rate':>6} {'peers':>6} {'gap_pp':>7} {'np':>3} {'legacy n':>9} "
                     f"{'holds w/o':>9}")
        for c in shown:
            ent = c["entity"] + (f" [{c['series_name']}]" if "series_name" in c else "")
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
