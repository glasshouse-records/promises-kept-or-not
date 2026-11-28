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

S2 say vs do. For each institution (or institution/ADVISER) and theme, the engine's
`say_vs_do` supplies the policy versions, the sentences matching the theme and each
version's in-force window; nothing here re-matches policy text except one filter: a said
sentence counts as a stated stance only if it mentions the theme (contradictions.THEMES) and
reads "generally ... support / vote for / vote in favor" with no hedge (STANCE_HEDGE). Votes in
the window are the theme's decided ballots (share classes collapsed, MIXED left out). Hit:
a stance, >= 30 decided ballots, support rate <= S2_MAX_RATE; score = (1 - rate) * 100 *
sqrt(n). Windows over GAP_DAYS (no capture for over a year) are never used. An institution
whose advisers differ is only ever paired adviser by adviser; a version without an
adviser there is unpaired and skipped.

S1 walk-back. For consecutive readable versions A -> B of one document (one adviser),
`policy_diff` gives the removed sentences. A removed sentence mentioning theme T
(contradictions.THEMES commitment words) is a removal unless an added sentence is a near
copy (difflib ratio >= S1_REFLOW: a reflow, not a removal). Support on T is measured on
ballots >= 3 firms voted (S3's peer ballots) in the window before B's capture date
(from max(A's capture, 365 days earlier)) and after it (until the next version or 365 days):
`entity_rate` = FOR-rate, `peer_rate` = mean over the same ballots of the FOR share among
the OTHER firms. Hit: both sides >= 30 ballots, the entity fell >= 10 pp and by >= 10 pp
more than its peers moved. The change date is only known to lie between two captures.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import engine
from .contradictions import THEMES as POLICY_THEMES
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
    r"congruen|misalign|third-party"
    r"|retirement plan.*climate|climate.*retirement plan"
    r"|net[\s-]zero.*risk|risk.*net[\s-]zero"
    r"|climate commitments.*impact|impact.*climate commitments", re.IGNORECASE)

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
    collapsed_rows = mixed_ballots = 0     # share-class rows folded into one ballot; MIXED ballots
    for theme in engine.THEMES:
        join, w, p = eng._where(theme=theme, year=year)
        raw = eng.db.execute(
            f"SELECT p.*, {engine._ENTITY.format('p')} ent FROM proposals p {join} "
            f"WHERE {w} ORDER BY p.proposal_id", p).fetchall()
        prefer: dict = defaultdict(set)
        for r in raw:
            prefer[r["ballot_key"]].add(r["ent"])
        cb = engine.collapse_ballots(raw, {k: len(v) for k, v in prefer.items()})
        collapsed_rows += len(raw) - len(cb)
        mixed_ballots += sum(1 for b in cb if b["position"] == "MIXED")
        rows = [{"pid": b["row"]["proposal_id"], "y": b["row"]["year"],
                 "bk": b["row"]["ballot_key"], "d": b["row"]["description"],
                 "ent": b["row"]["ent"], "pos": b["position"],
                 "wb": b["row"]["weight_basis"]}
                for b in cb if b["position"] in ("FOR", "AGAINST")]
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
            "duplicate_firm_entities_dropped": len(dup_dropped),
            "share_class_rows_collapsed": collapsed_rows, "mixed": mixed_ballots}


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


def _dedupe(rows: list) -> tuple[list, int, int]:
    """One row per real ballot, lowest proposal id first: the same item under two proposal
    ids (engine.proposal_key) counts once, and so do the share classes of one ballot
    (engine.share_class_key). A ballot whose classes the series voted differently is MIXED
    and dropped from the rate. Returns (kept, rows removed, MIXED ballots dropped)."""
    seen, first = set(), []
    for r in sorted(rows, key=lambda r: r[0]):
        k = engine.proposal_key(r[1])
        if k not in seen:
            seen.add(k)
            first.append(r)
    classes: dict[tuple, list] = {}
    for r in first:
        classes.setdefault(engine.share_class_key(r[1]), []).append(r)
    kept = [c[0] for c in classes.values() if len({x[2] for x in c}) == 1]
    return kept, len(rows) - len(classes), len(classes) - len(kept)


def _s5_row(*, kind, ent, sid, name, theme, rows, n_peers, compared_with, collapsed,
            by_year=None) -> dict | None:
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
                     + ("" if theme == "pooled" else f" theme={theme}")
                     + ("" if by_year is None else f" year={by_year}"))
    repro += [f"glasshouse ask fund_votes proposal_id={i}" for i, _ in ex_ids]
    return {
        "screen": "S5", "kind": kind, "label": label, "pooled": theme == "pooled",
        "by_year": by_year is not None,
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


def _year_views(rows: list):
    """(by_year, rows) for the all-years view and, when the rows span several years, for
    each year alone: a pooled rate hides dated changes."""
    yield None, rows
    years = sorted({r[1]["year"] for r in rows if r[1]["year"]})
    if len(years) > 1:
        for y in years:
            yield y, [r for r in rows if r[1]["year"] == y]


def _ballots_of(props: dict, pids) -> dict:
    """One entity's ballots: class key (share classes folded, adviser left out so two
    entities of one institution line up) -> (lowest proposal id, position or MIXED).
    The same item under two proposal ids is one ballot too."""
    groups: dict[tuple, list] = {}
    for pid in sorted(pids):
        k = engine.share_class_key(props[pid])
        groups.setdefault(k[:1] + k[2:] if k[0] != "single" else engine.proposal_key(props[pid]),
                          []).append(pid)
    out = {}
    for k, ps in groups.items():
        pos = {props[p]["position"] for p in ps}
        out[k] = (ps[0], pos.pop() if len(pos) == 1 else "MIXED")
    return out


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
    # One series' item is counted once however many adviser keys it was filed under:
    # kept under an ESG adviser group if it has one, else under the lowest key.
    def _pref(ent):
        adv = _split_entity(ent)[1]
        return (0 if adv and ESG_GROUP_KEY.search(adv) else 1 if adv else 2, ent)
    owner: dict[tuple, str] = {}
    for (ent, sid, _name), a in acc.items():
        for r in a["props"]:
            k = (sid, engine.proposal_key(r[1]))
            if k not in owner or _pref(ent) < _pref(owner[k]):
                owner[k] = ent
    out, collapsed_total, mixed_total = [], 0, 0
    for (ent, sid, name), a in acc.items():
        mine_rows = [r for r in a["props"] if owner[(sid, engine.proposal_key(r[1]))] == ent]
        cross = len(a["props"]) - len(mine_rows)
        pooled_collapsed = 0
        for theme in (*ES_THEMES, "pooled"):
            trows = [r for r in mine_rows if theme == "pooled" or theme in r[1]["themes_es"]]
            trows, collapsed, mixed = _dedupe(trows)
            if theme == "pooled":
                pooled_collapsed = collapsed + cross
                mixed_total += mixed
            for by_year, yrows in _year_views(trows):
                row = _s5_row(kind="series", ent=ent, sid=sid, name=name, theme=theme,
                              rows=yrows, n_peers=len(a["others"]), compared_with=ent,
                              collapsed=collapsed, by_year=by_year)
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
        mine = _ballots_of(props, by_ent[g])
        best = None
        for m in sorted(e for e in by_ent if e != g and _split_entity(e)[0] == inst
                        and e not in esg_groups):
            overlap = len(mine.keys() & _ballots_of(props, by_ent[m]).keys())
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, m)
        if not best:
            continue
        main = _ballots_of(props, by_ent[best[1]])
        for theme in (*ES_THEMES, "pooled"):
            rows, kept = [], 0
            for k, (pid, gpos) in sorted(mine.items(), key=lambda kv: kv[1][0]):
                pr, mp = props[pid], main.get(k)
                if theme != "pooled" and theme not in pr["themes_es"]:
                    continue
                kept += 1
                if mp and gpos in ("FOR", "AGAINST") and mp[1] in ("FOR", "AGAINST"):
                    rows.append((pid, pr, gpos, 1.0 if mp[1] == "FOR" else 0.0))
                elif theme == "pooled" and "MIXED" in (gpos, mp[1] if mp else None):
                    mixed_total += 1
            n_dup = sum(1 for p in by_ent[g] if theme == "pooled" or theme in props[p]["themes_es"]) - kept
            for by_year, yrows in _year_views(rows):
                row = _s5_row(kind="group", ent=g, sid="", name=_split_entity(g)[1], theme=theme,
                              rows=yrows, n_peers=1, compared_with=best[1], collapsed=n_dup,
                              by_year=by_year)
                if row:
                    out.append(row)
    out.sort(key=lambda c: (-c["score"], c["entity"], c["series_id"], c["theme"], c["year"]))
    return {"screen": "S5", "year": year, "candidates": out, "matched_funds": matched,
            "summary": _s5_summary(out), "n_collapsed_duplicates": collapsed_total,
            "excluded_catch_all": len(catch_pids),
            "excluded_catch_all_entities": len(catch_ents),
            "n_ambiguous_excluded": len(amb_pids),
            "share_class_rows_collapsed": collapsed_total, "mixed": mixed_total}


def _s5_summary(cands: list) -> str:
    rows = [c for c in cands if c["kind"] == "series" and c["pooled"] and not c["by_year"]]
    n = {k: sum(1 for c in rows if c["label"] == k) for k in ("with_house", "differs", "between")}
    return (f"{len(rows)} ESG-named series with ≥30 ballots: {n['with_house']} with house "
            f"(±5pp), {n['differs']} differ (+15pp or more), {n['between']} between")


# ------------------------------------------------------------------------- S2 / S1

S2_MAX_RATE = 0.40
S1_MIN_MOVE_PP = 10.0
S1_WINDOW_DAYS = 365
S1_REFLOW = 0.8

# FTS terms that fetch a theme's policy sentences from `say_vs_do` (the tool's own matching),
# each narrowed to sentences that talk about support so its 8-sentence cap is not spent elsewhere.
_SUPPORT_FTS = "(support OR supports OR vote OR favor OR favour)"
S2_FTS = {
    "anti-corruption": "(corruption OR bribery OR ethics)",
    "human-rights": '("human rights")',
    "climate": "(climate OR emissions)",
    "lobbying-disclosure": '(lobbying OR "political spending" OR "political contributions")',
    "board-diversity": "(diversity OR diverse)",
    "nature": "(deforestation OR biodiversity OR water)",
    "labor-rights": '("labor rights" OR "labour rights" OR workforce OR "human capital")',
}

_STANCE = re.compile(
    r"\bgenerally\b(?:\s+\w+){0,2}?\s+(?:support|supports|vote\s+for|votes\s+for"
    r"|vote\s+in\s+favou?r|votes\s+in\s+favou?r)\b", re.IGNORECASE)
# A hedge anywhere in the sentence means it is not an unconditional stance: precision first.
STANCE_HEDGE = re.compile(
    r"\b(?:against|oppose[sd]?|not|unless|except|case[\s-]by[\s-]case|only\s+if|provided"
    r"|rarely|but|however)\b", re.IGNORECASE)


def stated_support(theme: str, sentence: str) -> bool:
    """A policy sentence that says the manager 'generally supports' the theme: it mentions
    the theme, reads generally + support/vote for/vote in favor, and carries no hedge."""
    rx = "|".join(POLICY_THEMES[theme]["commitment"])
    return bool(re.search(rx, sentence, re.IGNORECASE) and _STANCE.search(sentence)
                and not STANCE_HEDGE.search(sentence))


def _snippet(rx, text: str, width: int = 90) -> str:
    """The stretch of a (possibly very long) policy sentence around the first match, so a
    reader sees WHY it matched the theme."""
    m = re.search(getattr(rx, "pattern", rx), text, re.IGNORECASE)
    if not m:
        return text[:2 * width]
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


def _decided_rate(ballots) -> float | None:
    f = sum(1 for b in ballots if b["position"] == "FOR")
    a = sum(1 for b in ballots if b["position"] == "AGAINST")
    return f / (f + a) if f + a else None


def _version_groups(eng: engine.Engine):
    """(institution, adviser-or-None, scope) for every policy document owner; None scope
    for an institution whose advisers do not differ. A multi-adviser institution's version
    without a (real) adviser key cannot be paired with votes and is yielded as unpaired."""
    unpaired = 0
    out = []
    for r in eng.db.execute("SELECT DISTINCT institution_id, adviser FROM policy_versions "
                            "WHERE n_sentences >= ? ORDER BY 1, 2", (engine.READABLE_MIN,)):
        iid, adv = r["institution_id"], r["adviser"]
        if eng.advisers_of(iid)["multi"]:
            if adv is None or adv in CATCH_ALL:
                unpaired += 1
                continue
            out.append((iid, adv, adv))
        else:
            out.append((iid, adv, None))
    return out, unpaired


def s2_say_vs_do(eng: engine.Engine, year: int | None = None,
                 include_ambiguous: bool = False) -> dict:
    out, amb_pids, catch_pids = [], set(), set()
    n_gap = n_stance = collapsed_rows = mixed_ballots = 0
    groups, unpaired = _version_groups(eng)
    for iid, adv, sc in groups:
        ent = f"{iid}/{adv}" if adv else iid
        for theme in S2_FTS:
            try:
                env = eng.say_vs_do(iid, f"{S2_FTS[theme]} AND {_SUPPORT_FTS}", theme=theme,
                                    adviser=sc)
            except ValueError:
                unpaired += 1
                break
            stances = [(v, [s for s in v["said"] if stated_support(theme, s)])
                       for v in env["result"]]
            stances = [(v, s) for v, s in stances if s]
            if not stances:
                continue
            join, w, p = eng._where(institution=iid, theme=theme, adviser=sc, year=year)
            rows = eng.db.execute(
                f"SELECT p.*, {engine._ENTITY.format('p')} ent FROM proposals p {join} "
                f"WHERE {w} ORDER BY p.proposal_id", p).fetchall()
            for v, said in stances:
                n_stance += 1
                if v["archive_gap"]:
                    n_gap += 1
                    continue
                until = v["in_force_until"] or "9999-12-31"
                win = []
                for r in rows:
                    if not v["in_force_from"] <= r["meeting_date"] < until:
                        continue
                    if is_catch_all(r["ent"]):
                        catch_pids.add(r["proposal_id"])
                    elif not include_ambiguous and AMBIGUOUS_POLARITY.search(r["description"] or ""):
                        amb_pids.add(r["proposal_id"])
                    else:
                        win.append(r)
                bl = engine.collapse_ballots(win)
                collapsed_rows += len(win) - len(bl)
                mixed_ballots += sum(1 for b in bl if b["position"] == "MIXED")
                n_for = sum(1 for b in bl if b["position"] == "FOR")
                n_against = sum(1 for b in bl if b["position"] == "AGAINST")
                n = n_for + n_against
                if n < MIN_BALLOTS:
                    continue
                rate = n_for / n
                if rate > S2_MAX_RATE:
                    continue
                dec = [b for b in bl if b["position"] in ("FOR", "AGAINST")]
                ex = [b for b in dec if b["row"]["weight_basis"] != "lines"]
                ex_rate = _decided_rate(ex)
                legacy = len(dec) - len(ex)
                ex_ids = sorted(b["row"]["proposal_id"] for b in dec if b["position"] == "AGAINST")[:3]
                out.append({
                    "screen": "S2", "entity": ent, "theme": theme,
                    "year": f"{v['in_force_from']}..{v['in_force_until'] or 'latest'}",
                    "version_id": v["commitment_id"], "doc_label": v["doc_label"],
                    "in_force_from": v["in_force_from"], "in_force_until": v["in_force_until"],
                    "window_days": v["window_days"], "said": said[:3],
                    "said_context": [_snippet(_STANCE, t) for t in said[:3]],
                    "n_ballots": n, "for": n_for, "against": n_against,
                    "mixed": sum(1 for b in bl if b["position"] == "MIXED"),
                    "entity_rate": round(rate, 4), "gap_pp": round((rate - 1) * 100, 2),
                    "score": round((1 - rate) * 100 * math.sqrt(n), 2),
                    "includes_legacy": bool(legacy), "n_legacy_ballots": legacy,
                    "n_ballots_ex_legacy": len(ex),
                    "entity_rate_ex_legacy": round(ex_rate, 4) if ex_rate is not None else None,
                    "holds_without_legacy": bool(
                        ex_rate is not None and len(ex) >= MIN_BALLOTS and ex_rate <= S2_MAX_RATE),
                    "example_proposal_ids": ex_ids,
                    "reproduce": [f"glasshouse ask say_vs_do institution={iid} "
                                  f"query={S2_FTS[theme]!r} theme={theme}"
                                  + (f" adviser={sc}" if sc else "")]})
    out.sort(key=lambda c: (-c["score"], c["entity"], c["theme"], c["version_id"]))
    return {"screen": "S2", "year": year, "candidates": out, "matched_funds": [],
            "n_stance_versions": n_stance, "n_archive_gap_excluded": n_gap,
            "n_unpaired_skipped": unpaired,
            "excluded_catch_all": len(catch_pids), "excluded_catch_all_entities": 0,
            "n_ambiguous_excluded": len(amb_pids),
            "share_class_rows_collapsed": collapsed_rows, "mixed": mixed_ballots}


def _theme_ballots(eng: engine.Engine, theme: str, include_ambiguous: bool, stats: dict) -> dict:
    """bk -> {entity: ballot} for the theme's decided, non catch-all, non ambiguous ballots
    (share classes collapsed as S3 does); each ballot is a dict of position/date/legacy/pid."""
    join, w, p = eng._where(theme=theme)
    raw = eng.db.execute(
        f"SELECT p.*, {engine._ENTITY.format('p')} ent FROM proposals p {join} "
        f"WHERE {w} ORDER BY p.proposal_id", p).fetchall()
    prefer: dict = defaultdict(set)
    for r in raw:
        prefer[r["ballot_key"]].add(r["ent"])
    cb = engine.collapse_ballots(raw, {k: len(v) for k, v in prefer.items()})
    stats["collapsed"] += len(raw) - len(cb)
    stats["mixed"] += sum(1 for b in cb if b["position"] == "MIXED")
    by_bk: dict = defaultdict(dict)
    for b in cb:
        r = b["row"]
        if b["position"] not in ("FOR", "AGAINST") or r["ballot_key"] is None:
            continue
        if is_catch_all(r["ent"]):
            stats["catch"].add(r["proposal_id"])
            continue
        if not include_ambiguous and AMBIGUOUS_POLARITY.search(r["description"] or ""):
            stats["amb"].add(r["proposal_id"])
            continue
        by_bk[r["ballot_key"]][r["ent"]] = {
            "bk": r["ballot_key"], "pos": b["position"], "date": r["meeting_date"],
            "legacy": r["weight_basis"] == "lines", "pid": r["proposal_id"],
            "inst": r["institution_id"], "adv": r["adviser"], "ent": r["ent"]}
    return by_bk


def _side(mine: list, by_bk: dict, firm: str, firm_keys: dict, start: str, end: str,
          with_legacy: bool) -> dict:
    """The entity's FOR-rate on peer ballots (>= 3 managers) dated [start, end), and the
    mean, over those same ballots, of the FOR share among the other firms."""
    own, peer, pids = [], [], []
    for b in mine:
        if not start <= b["date"] < end or (b["legacy"] and not with_legacy):
            continue
        others = [x["pos"] for e, x in by_bk[b["bk"]].items()
                  if firm_of(e, firm_keys) != firm]
        if len(others) < MIN_MANAGERS - 1:
            continue
        own.append(b["pos"] == "FOR")
        peer.append(sum(1 for o in others if o == "FOR") / len(others))
        pids.append(b["pid"])
    n = len(own)
    return {"n": n, "rate": sum(own) / n if n else None,
            "peer": sum(peer) / n if n else None, "pids": pids,
            "n_legacy": sum(1 for b in mine if b["legacy"] and start <= b["date"] < end)}


def _iso_add(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def _is_hit(before: dict, after: dict) -> bool:
    if before["n"] < MIN_BALLOTS or after["n"] < MIN_BALLOTS:
        return False
    change = (after["rate"] - before["rate"]) * 100
    peer = (after["peer"] - before["peer"]) * 100
    return change <= -S1_MIN_MOVE_PP and change - peer <= -S1_MIN_MOVE_PP


def s1_walk_back(eng: engine.Engine, year: int | None = None,
                 include_ambiguous: bool = False) -> dict:
    stats = {"collapsed": 0, "mixed": 0, "catch": set(), "amb": set()}
    firm_keys = _firm_keys(eng)
    themes: dict = {}
    out, n_pairs, n_gap, n_unpaired, n_reflow = [], 0, 0, 0, 0
    vers: dict = defaultdict(list)
    for r in eng.db.execute("SELECT * FROM policy_versions WHERE n_sentences >= ? "
                            "ORDER BY institution_id, doc_label, captured, commitment_id",
                            (engine.READABLE_MIN,)):
        vers[(r["institution_id"], r["doc_label"])].append(dict(r))
    multi = {}
    for (iid, _label), vs in sorted(vers.items()):
        for i in range(len(vs) - 1):
            a, b = vs[i], vs[i + 1]
            if a["adviser"] != b["adviser"]:
                n_unpaired += 1
                continue
            multi.setdefault(iid, eng.advisers_of(iid)["multi"])
            if multi[iid] and (b["adviser"] is None or b["adviser"] in CATCH_ALL):
                n_unpaired += 1
                continue
            sc = b["adviser"] if multi[iid] else None
            n_pairs += 1
            if year and int(b["captured"][:4]) != year:
                continue
            d = eng.policy_diff(iid, a["commitment_id"], b["commitment_id"])["result"]
            added = [t.lower() for t in d["added"]]
            for theme in S2_FTS:
                rx = re.compile("|".join(POLICY_THEMES[theme]["commitment"]), re.IGNORECASE)
                removed = []
                for t in d["removed"]:
                    if not rx.search(t):
                        continue
                    low = t.lower()
                    if any(difflib.SequenceMatcher(None, low, x).ratio() >= S1_REFLOW
                           for x in added):
                        n_reflow += 1
                    else:
                        removed.append(t)
                if not removed:
                    continue
                days = (date.fromisoformat(b["captured"])
                        - date.fromisoformat(a["captured"])).days
                if days > engine.GAP_DAYS:
                    n_gap += 1
                    continue
                if theme not in themes:
                    themes[theme] = _theme_ballots(eng, theme, include_ambiguous, stats)
                by_bk = themes[theme]
                mine = {}
                for bk, ents in by_bk.items():
                    for e in sorted(ents):
                        x = ents[e]
                        if x["inst"] == iid and (sc is None or x["adv"] == sc):
                            mine.setdefault(bk, x)
                mine = sorted(mine.values(), key=lambda x: (x["date"], x["pid"]))
                if not mine:
                    continue
                firm = firm_of(mine[0]["ent"], firm_keys)
                nxt = [x["captured"] for x in vs[i + 2:]]
                a_end = min([_iso_add(b["captured"], S1_WINDOW_DAYS), *nxt[:1]])
                b_start = max(a["captured"], _iso_add(b["captured"], -S1_WINDOW_DAYS))
                bef = _side(mine, by_bk, firm, firm_keys, b_start, b["captured"], True)
                aft = _side(mine, by_bk, firm, firm_keys, b["captured"], a_end, True)
                if not _is_hit(bef, aft):
                    continue
                bx = _side(mine, by_bk, firm, firm_keys, b_start, b["captured"], False)
                ax = _side(mine, by_bk, firm, firm_keys, b["captured"], a_end, False)
                change = (aft["rate"] - bef["rate"]) * 100
                peer_change = (aft["peer"] - bef["peer"]) * 100
                gap = change - peer_change
                n_min = min(bef["n"], aft["n"])
                ent = mine[0]["ent"]
                out.append({
                    "screen": "S1", "entity": ent, "theme": theme, "year": b["captured"],
                    "doc_label": a["doc_label"],
                    "from_version": a["commitment_id"], "to_version": b["commitment_id"],
                    "from_captured": a["captured"], "to_captured": b["captured"],
                    "removed": removed, "n_removed": len(removed),
                    "removed_context": [_snippet(rx, t) for t in removed],
                    "window_before": [b_start, b["captured"]], "window_after": [b["captured"], a_end],
                    "n_before": bef["n"], "n_after": aft["n"],
                    "rate_before": round(bef["rate"], 4), "rate_after": round(aft["rate"], 4),
                    "peer_before": round(bef["peer"], 4), "peer_after": round(aft["peer"], 4),
                    "change_pp": round(change, 2), "peer_change_pp": round(peer_change, 2),
                    "gap_pp": round(gap, 2), "n_ballots": n_min,
                    "entity_rate": round(aft["rate"], 4), "peer_median": round(aft["peer"], 4),
                    "score": round(-gap * math.sqrt(n_min), 2),
                    "includes_legacy": bool(bef["n_legacy"] or aft["n_legacy"]),
                    "n_legacy_ballots": bef["n_legacy"] + aft["n_legacy"],
                    "n_before_ex_legacy": bx["n"], "n_after_ex_legacy": ax["n"],
                    "holds_without_legacy": _is_hit(bx, ax),
                    "example_proposal_ids": sorted(aft["pids"])[:3],
                    "reproduce": [
                        f"glasshouse ask policy_diff institution={iid} "
                        f"from_id={a['commitment_id']} to_id={b['commitment_id']}",
                        f"glasshouse ask peers theme={theme} since={b_start} until={a_end} "
                        f"min_managers={MIN_MANAGERS} institution={iid}"
                        + (f" adviser={sc}" if sc else "")]})
    out.sort(key=lambda c: (-c["score"], c["entity"], c["theme"], c["to_version"]))
    return {"screen": "S1", "year": year, "candidates": out, "matched_funds": [],
            "n_version_pairs": n_pairs, "n_archive_gap_excluded": n_gap,
            "n_unpaired_skipped": n_unpaired, "n_reflowed_not_removed": n_reflow,
            "excluded_catch_all": len(stats["catch"]), "excluded_catch_all_entities": 0,
            "n_ambiguous_excluded": len(stats["amb"]),
            "share_class_rows_collapsed": stats["collapsed"], "mixed": stats["mixed"]}


# ------------------------------------------------------------------------- run

SCREENS = {"S3": s3_peer_outliers, "S5": s5_esg_funds, "S2": s2_say_vs_do,
           "S1": s1_walk_back}


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


def _render_policy(n: str, r: dict, shown: list) -> list[str]:
    lines = []
    if n == "S2":
        lines.append(f"{r['n_stance_versions']} policy versions state support for a theme; "
                     f"{r['n_archive_gap_excluded']} dropped for an archive gap, "
                     f"{r['n_unpaired_skipped']} adviser-unpaired skipped")
        lines.append(f"{'score':>8} {'entity':<24} {'theme':<14} {'ver':>7} {'in force':<23} "
                     f"{'n':>4} {'FOR':>4} {'AGN':>4} {'MIX':>4} {'rate':>6} {'leg':>4} {'w/o':>5}")
        for c in shown:
            lines.append(f"{c['score']:>8.1f} {c['entity'][:24]:<24} {c['theme'][:14]:<14} "
                         f"{c['version_id']:>7} {c['year']:<23} {c['n_ballots']:>4} {c['for']:>4} "
                         f"{c['against']:>4} {c['mixed']:>4} {c['entity_rate']:>6.3f} "
                         f"{c['n_legacy_ballots']:>4} {str(c['holds_without_legacy']):>5}")
            lines.append(f"{'':>8} said: {c['said_context'][0]}")
            lines.append(f"{'':>8} ids {c['example_proposal_ids']}  {c['reproduce'][0]}")
        return lines
    lines.append(f"{r['n_version_pairs']} consecutive version pairs; "
                 f"{r['n_archive_gap_excluded']} dropped for an archive gap, "
                 f"{r['n_reflowed_not_removed']} removed-looking sentences were reflows, "
                 f"{r['n_unpaired_skipped']} adviser-unpaired skipped")
    lines.append(f"{'score':>8} {'entity':<24} {'theme':<14} {'from>to':<15} {'changed':<10} "
                 f"{'before':>13} {'after':>13} {'peer chg':>8} {'gap_pp':>7} {'leg':>4} {'w/o':>5}")
    for c in shown:
        lines.append(f"{c['score']:>8.1f} {c['entity'][:24]:<24} {c['theme'][:14]:<14} "
                     f"{c['from_version']}>{c['to_version']:<8} {c['to_captured']:<10} "
                     f"{c['rate_before']:>6.3f} n={c['n_before']:<4} {c['rate_after']:>6.3f} "
                     f"n={c['n_after']:<4} {c['peer_change_pp']:>8.1f} {c['gap_pp']:>7.1f} "
                     f"{c['n_legacy_ballots']:>4} {str(c['holds_without_legacy']):>5}")
        for t in c["removed_context"][:2]:
            lines.append(f"{'':>8} removed: {t}")
        lines.append(f"{'':>8} {c['reproduce'][0]}")
    return lines


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
                     + f"; {r.get('share_class_rows_collapsed', 0)} share-class rows folded "
                       f"into their ballot, {r.get('mixed', 0)} MIXED ballots left out "
                       "(classes voted differently)"
                     + (f"; {len(r['low_match'])} rows under the {MIN_MATCH_RATE:.0%} "
                        f"match guard held out as low_match" if "low_match" in r else ""))
        if n in ("S1", "S2"):
            lines += _render_policy(n, r, shown)
            continue
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
