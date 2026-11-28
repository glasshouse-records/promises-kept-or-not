"""Screens S3 (peer outlier) and S5 (ESG-labelled funds): leads over the engine."""

from __future__ import annotations

import json
import sqlite3

from glasshouse import engine, ledger, screens


def _ledger(tmp_path, name):
    path = tmp_path / f"{name}.db"
    c = ledger.connect(path)

    def inst(iid, ciks):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid.title()))
        for cik in ciks:
            c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                      " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                      "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                      (f"ACC-{cik}", cik, iid, f"https://sec.example/{cik}"))

    def vote(cik, i, how, date="05/20/2024", series=None, fmt=None, desc=None, pnum=None):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, vote_series, legacy_format, category_type, is_duplicate,"
                  " proposal_number)"
                  " VALUES (?,?,?,?,?,'SECURITY HOLDER',?,'AGAINST',100,?,?,?,0,?)",
                  (f"ACC-{cik}", f"ISSUER {i}", f"CUSIP{i:04d}", date,
                   desc or f"Report on Climate Transition Plan {i}", how, series, fmt,
                   "" if fmt else "SHAREHOLDER PROPOSAL", pnum))

    return c, path, inst, vote


def _build(c, path, tmp_path, registry=None):
    c.commit()
    c.close()
    out = tmp_path / (path.stem + "-engine.db")
    engine.build(path, out, institutions=registry or {})
    return engine.Engine(out, path)


def _s3_engine(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s3")
    for iid, cik in (("alpha", "1"), ("beta", "2"), ("gamma", "3"), ("delta", "4"),
                     ("eps", "5")):
        inst(iid, [cik])
    for i in range(40):                       # voted by four managers; alpha is the outlier
        vote("1", i, "AGAINST")
        for cik in ("2", "3", "4"):
            vote(cik, i, "FOR")
    for i in range(40, 50):                   # only alpha and beta voted: not a peer ballot
        vote("1", i, "FOR")
        vote("2", i, "FOR")
    for i in range(20):                       # eps also deviates, but on 20 ballots only
        vote("5", i, "AGAINST")
    return _build(c, path, tmp_path)


def _s3(eng, **kw):
    return screens.s3_peer_outliers(eng, **kw)["candidates"]


def test_s3_flags_outlier_on_same_ballots_only(tmp_path):
    eng = _s3_engine(tmp_path)
    hits = _s3(eng)
    assert [(h["entity"], h["theme"], h["year"]) for h in hits] == [("alpha", "climate", 2024)]
    h = hits[0]
    # the 10 ballots only beta shared with alpha are not counted: 40, not 50
    assert h["n_ballots"] == 40
    assert h["entity_rate"] == 0.0 and h["peer_median"] == 1.0 and h["n_peers"] >= 2
    assert h["gap_pp"] == -100.0
    assert h["score"] == round(100 * 40 ** 0.5, 2)
    assert len(h["example_proposal_ids"]) == 3 and len(h["example_ballot_keys"]) == 3


def test_s3_floor_drops_entity_under_30_ballots(tmp_path):
    eng = _s3_engine(tmp_path)
    assert all(h["entity"] != "eps" for h in _s3(eng))     # 20 ballots, same deviation


def test_s3_matches_engine_peers_tool(tmp_path):
    eng = _s3_engine(tmp_path)
    h = _s3(eng)[0]
    row = eng.peers(theme="climate", year=2024)["result"]["managers"]["alpha"]
    assert row["shared_proposals"] == h["n_ballots"]
    assert row["support_rate"] == h["entity_rate"]
    assert h["reproduce"] == ["glasshouse ask peers theme=climate year=2024 "
                              "min_managers=3 institution=alpha"]


def test_s3_adviser_separation(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s3adv")
    inst("grp", ["11", "22"])
    inst("beta", ["2"])
    inst("gamma", ["3"])
    for i in range(35):
        vote("11", i, "FOR")                  # adviser AAA: with the peers
        vote("22", i, "AGAINST")              # adviser BBB: against them
        vote("2", i, "FOR")
        vote("3", i, "FOR")
    reg = {"grp": {"npx_ciks": [{"cik": "11", "adviser_key": "AAA"},
                                {"cik": "22", "adviser_key": "BBB"}]}}
    eng = _build(c, path, tmp_path, reg)
    hits = _s3(eng)
    assert [h["entity"] for h in hits] == ["grp/BBB"]      # never pooled as `grp`
    assert hits[0]["reproduce"] == ["glasshouse ask peers theme=climate year=2024 "
                                    "min_managers=3 institution=grp adviser=BBB"]


def test_s3_legacy_split(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s3lg")
    for iid, cik in (("alpha", "1"), ("beta", "2"), ("gamma", "3")):
        inst(iid, [cik])
    for i in range(37):
        legacy = i < 12                       # 12 line-weighted ballots, 25 share-weighted
        date, fmt = ("05/20/2023", "proxyedge") if legacy else ("09/20/2023", None)
        vote("1", i, "AGAINST", date, fmt=fmt)
        vote("2", i, "FOR", date, fmt=fmt)
        vote("3", i, "FOR", date, fmt=fmt)
    h = _s3(_build(c, path, tmp_path))[0]
    assert h["n_ballots"] == 37 and h["includes_legacy"] is True
    assert h["n_legacy_ballots"] == 12 and h["n_ballots_ex_legacy"] == 25
    assert h["holds_without_legacy"] is False             # 25 < 30: rests on legacy rows
    assert h["entity_rate_ex_legacy"] == 0.0


def test_s3_no_legacy_flag_when_none(tmp_path):
    h = _s3(_s3_engine(tmp_path))[0]
    assert h["includes_legacy"] is False and h["n_legacy_ballots"] == 0
    assert h["holds_without_legacy"] is True


# ------------------------------------------------------------------------- S5

def test_esg_name_regex_word_boundaries():
    for name in ("ESG Leaders Index", "Acme Sustainable Equity", "Acme Sustainability Fund",
                 "Low-Carbon Target", "Low Carbon Fund", "Paris-Aligned Equity",
                 "Fossil Fuel Free Core", "Clean Energy", "Global Impact Fund",
                 "Responsible Investing", "Social Choice", "Green Bond", "Climate Action",
                 "esg screened"):
        assert screens.esg_name(name), name
    for name in ("Impactful Growth", "Greenwich Core", "Socialite Fund", "Cleanse Fund",
                 "Acme Core Equity", "Parisian Value", "Irresponsible", None, ""):
        assert not screens.esg_name(name), name


def _s5_engine(tmp_path, other_adviser=False):
    c, path, inst, vote = _ledger(tmp_path, "s5")
    inst("hh", ["11", "22"] if other_adviser else ["11"])
    for cik, sid, name in (("11", "S1", "Acme Sustainable Equity"),
                           ("11", "S2", "Acme Core Equity"),
                           ("11", "S3", "Acme Impactful Growth"),
                           ("22", "S4", "Other Core Equity")):
        if cik == "22" and not other_adviser:
            continue
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, f"ACC-{cik}", name))
    for i in range(35):
        vote("11", i, "AGAINST", series="S1")         # the ESG-named fund votes against
        vote("11", i, "FOR", series="S2")
        vote("11", i, "FOR", series="S3")             # "Impactful": not an ESG name
        if other_adviser:
            vote("22", i, "FOR", series="S4")
    reg = ({"hh": {"npx_ciks": [{"cik": "11", "adviser_key": "AAA"},
                                {"cik": "22", "adviser_key": "BBB"}]}}
           if other_adviser else {})
    return _build(c, path, tmp_path, reg)


def _themed(out):
    """S5 rows for one theme (the pooled summary rows left out)."""
    return [c for c in out["candidates"] if c["theme"] != "pooled"]


def test_s5_flags_esg_named_fund_voting_below_its_siblings(tmp_path):
    out = screens.s5_esg_funds(_s5_engine(tmp_path))
    hits = _themed(out)
    assert len(hits) == 1
    h = hits[0]
    assert (h["series_id"], h["series_name"]) == ("S1", "Acme Sustainable Equity")
    assert h["n_ballots"] == 35 and h["entity_rate"] == 0.0 and h["peer_median"] == 1.0
    assert h["n_peers"] == 2                              # S2 and S3, not S1 itself
    assert h["gap_pp"] == -100.0 and h["score"] == round(100 * 35 ** 0.5, 2)
    assert len(h["example_proposal_ids"]) == 3
    assert h["reproduce"][0] == "glasshouse ask fund_record series_id=S1 theme=climate"
    assert h["reproduce"][1].startswith("glasshouse ask fund_votes proposal_id=")
    assert h["label"] == "with_house" and h["theme"] == "climate"
    assert [m["series_name"] for m in out["matched_funds"]] == ["Acme Sustainable Equity"]


def test_s5_never_compares_with_another_advisers_funds(tmp_path):
    # S4 belongs to adviser BBB: S1 has the same-adviser siblings S2 and S3 only
    hits = _themed(screens.s5_esg_funds(_s5_engine(tmp_path, other_adviser=True)))
    assert len(hits) == 1 and hits[0]["entity"] == "hh/AAA" and hits[0]["n_peers"] == 2


def test_s5_floor_and_both_directions_when_esg_fund_votes_for(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s5b")
    inst("hh", ["11"])
    for sid, name in (("S1", "Acme ESG Fund"), ("S2", "Acme Core")):
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, "ACC-11", name))
    for i in range(29):                                    # 29 shared: under the floor
        vote("11", i, "AGAINST", series="S1")
        vote("11", i, "FOR", series="S2")
    assert screens.s5_esg_funds(_build(c, path, tmp_path))["candidates"] == []   # floor

    c, path, inst, vote = _ledger(tmp_path, "s5c")
    inst("hh", ["11"])
    for sid, name in (("S1", "Acme ESG Fund"), ("S2", "Acme Core")):
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, "ACC-11", name))
    for i in range(35):                                    # ESG fund 20 pp ABOVE siblings
        vote("11", i, "FOR", series="S1")
        vote("11", i, "FOR" if i < 28 else "AGAINST", series="S2")
    rows = _themed(screens.s5_esg_funds(_build(c, path, tmp_path)))
    assert [(r["label"], r["gap_pp"]) for r in rows] == [("differs", 20.0)]   # reported, not hidden


def test_s5_legacy_counts(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s5lg")
    inst("hh", ["11"])
    for sid, name in (("S1", "Acme ESG Fund"), ("S2", "Acme Core")):
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, "ACC-11", name))
    for i in range(36):
        legacy = i < 8
        date, fmt = ("05/20/2023", "proxyedge") if legacy else ("09/20/2023", None)
        vote("11", i, "AGAINST", date, series="S1", fmt=fmt)
        vote("11", i, "FOR", date, series="S2", fmt=fmt)
    h = _themed(screens.s5_esg_funds(_build(c, path, tmp_path)))[0]
    assert h["n_ballots"] == 36 and h["n_legacy_ballots"] == 8 and h["includes_legacy"]
    assert h["n_ballots_ex_legacy"] == 28 and h["holds_without_legacy"] is False


def test_screens_are_read_only_and_json_serialisable(tmp_path):
    eng = _s3_engine(tmp_path)
    before = {p: (tmp_path / p).stat().st_mtime_ns for p in ("s3-engine.db", "s3.db")}
    res = screens.run(eng, "all")
    json.dumps(res)
    assert {p: (tmp_path / p).stat().st_mtime_ns for p in before} == before
    try:
        eng.db.execute("CREATE TABLE x (a)")
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("engine db must be read-only")


def test_s5_bulk_lines_agree_with_fund_votes(tmp_path):
    eng = _s5_engine(tmp_path, other_adviser=True)
    names = screens._series_names(eng)
    pids = [r[0] for r in eng.db.execute("SELECT proposal_id FROM proposals")]
    bulk = screens._bulk_lines(eng, {p: {} for p in pids}, names)
    assert pids
    for pid in pids:
        slow = sorted((x["fund_series"], x["fund_series_name"], x["how_voted"])
                      for x in eng.fund_votes(pid)["result"]["lines"])
        fast = sorted((x["fund_series"], x["fund_series_name"], x["how_voted"])
                      for x in bulk[pid])
        assert fast == slow and fast


# ------------------------------------------------------- fund_record (engine tool)

def test_fund_record_counts_each_theme_and_lists_the_ballots(tmp_path):
    eng = _s5_engine(tmp_path)
    env = eng.fund_record(series_id="S1")
    assert env["tool"] == "fund_record" and env["args"] == {"series_id": "S1"}
    [row] = env["result"]["series"]
    assert (row["series_id"], row["series_name"], row["institution"]) == (
        "S1", "Acme Sustainable Equity", "hh")
    t = row["themes"]["climate"]
    assert (t["for"], t["against"], t["split"], t["other"], t["ballots"]) == (0, 35, 0, 0, 35)
    assert len(t["proposals"]) == 35
    pid = t["proposals"][0]["proposal_id"]
    assert t["proposals"][0]["ballot_key"] == eng.db.execute(
        "SELECT ballot_key FROM proposals WHERE proposal_id=?", (pid,)).fetchone()[0]
    assert {x["how_voted"] for x in eng.fund_votes(pid)["result"]["lines"]
            if x["fund_series"] == "S1"} == {"AGAINST"}
    assert env["caveats"]
    # the same series by name, and narrowed by theme/year
    assert eng.fund_record(fund="sustainable equity")["result"]["series"] == env["result"]["series"]
    assert eng.fund_record(series_id="S1", theme="nature")["result"]["series"][0]["themes"] == {}
    assert eng.fund_record(series_id="S1", year=2023)["result"]["series"][0]["themes"] == {}
    got = eng.fund_record(series_id="S1", since="2024-05-01", until="2024-05-31")
    assert got["result"]["series"][0]["themes"]["climate"]["ballots"] == 35
    json.dumps(env)


def test_fund_record_split_other_and_rollback(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "fr")
    inst("hh", ["11"])
    c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES ('S1','ACC-11','Acme')")
    vote("11", 0, "FOR", series="S1")
    vote("11", 1, "AGAINST", series="S1")
    vote("11", 2, "FOR", series="S1")
    vote("11", 2, "AGAINST", series="S1")               # one series, both ways: SPLIT
    vote("11", 3, "ABSTAIN", series="S1")
    vote("11", 4, "AGAINST", series="S1", desc="Remove climate change targets")   # roll-back
    eng = _build(c, path, tmp_path)
    t = eng.fund_record(series_id="S1")["result"]["series"][0]["themes"]["climate"]
    assert (t["for"], t["against"], t["split"], t["other"], t["ballots"]) == (1, 1, 1, 1, 4)


def test_fund_record_refuses_vague_or_unknown_requests(tmp_path):
    eng = _s5_engine(tmp_path)
    for kw in ({}, {"series_id": "NOPE"}, {"fund": "no such fund"}, {"series_id": "S1", "theme": "x"}):
        try:
            eng.fund_record(**kw)
        except ValueError:
            continue
        raise AssertionError(f"{kw} should have been refused")


def test_fund_record_is_registered_everywhere_tools_are_listed():
    assert "fund_record" in engine.TOOLS
    import inspect
    assert list(inspect.signature(engine.Engine.fund_record).parameters)[1:] == [
        "series_id", "fund", "theme", "year", "since", "until"]


def _dup_ledger(tmp_path, name="dup"):
    """Each issuer's item sits under TWO proposal ids (legacy printed item numbers 1 and 2,
    same company, meeting and wording)."""
    c, path, inst, vote = _ledger(tmp_path, name)
    inst("hh", ["11"])
    for sid, nm in (("S1", "Acme ESG Fund"), ("S2", "Acme Core")):
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, "ACC-11", nm))
    for i in range(35):
        for pn in ("1", "2"):
            vote("11", i, "AGAINST", "05/20/2023", series="S1", fmt="proxyedge", pnum=pn)
            vote("11", i, "FOR", "05/20/2023", series="S2", fmt="proxyedge", pnum=pn)
    return c, path


def test_a_proposal_under_two_ids_is_counted_once(tmp_path):
    c, path = _dup_ledger(tmp_path)
    eng = _build(c, path, tmp_path)
    assert eng.db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 70
    t = eng.fund_record(series_id="S1")["result"]["series"][0]["themes"]["climate"]
    assert t["ballots"] == 35 and t["against"] == 35 and len(t["proposals"]) == 35
    assert t["collapsed_duplicates"] == 35
    out = screens.s5_esg_funds(eng)
    [h] = _themed(out)
    assert h["n_ballots"] == 35 and h["n_collapsed_duplicates"] == 35
    assert out["n_collapsed_duplicates"] == 35


def test_s5_per_theme_rows_pooled_summary_labels_and_summary_line(tmp_path):
    c, path, inst, vote = _ledger(tmp_path, "s5t")
    inst("hh", ["11"])
    for sid, nm in (("E1", "Acme ESG Leaders"), ("E2", "Acme Sustainable Core"),
                    ("E3", "Acme Climate Mid"), ("S2", "Acme Core Equity")):
        c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  (sid, "ACC-11", nm))
    hr = "Report on Human Rights Impact Assessment"
    for i in range(35):                  # climate: core votes FOR on 20 of 35
        core = "FOR" if i < 20 else "AGAINST"
        vote("11", i, core, series="S2")
        vote("11", i, "FOR", series="E1")                  # +42.9 pp: differs
        vote("11", i, core, series="E2")                   # 0 pp: with_house
        vote("11", i, "FOR" if i < 25 else "AGAINST", series="E3")   # +14.3 pp: between
    for i in range(100, 110):            # ten human-rights ballots: under the per-theme floor
        vote("11", i, "AGAINST", series="S2", desc=hr)
        vote("11", i, "AGAINST", series="E1", desc=hr)
    out = screens.s5_esg_funds(_build(c, path, tmp_path))
    rows = {(r["series_id"], r["theme"]): r for r in out["candidates"]}
    assert rows[("E1", "climate")]["label"] == "differs"
    assert rows[("E2", "climate")]["label"] == "with_house"
    assert rows[("E3", "climate")]["label"] == "between"
    assert ("E1", "human-rights") not in rows                 # 10 ballots: per-row floor
    p = rows[("E1", "pooled")]
    assert p["n_ballots"] == 45 and p["pooled"] is True and rows[("E1", "climate")]["pooled"] is False
    assert out["summary"] == ("3 ESG-named series with ≥30 ballots: 1 with house (±5pp), "
                              "1 differ (+15pp or more), 1 between")
    assert out["summary"] in screens.render({"S5": out | {"n_candidates": 0}})


def test_s5_esg_adviser_group_is_compared_with_the_main_group(tmp_path):
    for n, esg_key in enumerate(("MAIN_SUSTAINABILITY", "ZZ")):   # suffix; all-series-ESG
        c, path, inst, vote = _ledger(tmp_path, f"s5g{n}")
        inst("hh", ["11", "22"])
        for cik, sid, nm in (("11", "S1", "Acme Core Equity"), ("22", "S9", "Acme Sustainable Fund")):
            c.execute("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                      (sid, f"ACC-{cik}", nm))
        for i in range(35):
            vote("11", i, "AGAINST", series="S1")
            vote("22", i, "FOR", series="S9")
        reg = {"hh": {"npx_ciks": [{"cik": "11", "adviser_key": "MAIN"},
                                   {"cik": "22", "adviser_key": esg_key}]}}
        out = screens.s5_esg_funds(_build(c, path, tmp_path, reg))
        groups = [r for r in _themed(out) if r["kind"] == "group"]
        assert [(g["entity"], g["compared_with"], g["label"], g["n_ballots"], g["gap_pp"])
                for g in groups] == [(f"hh/{esg_key}", "hh/MAIN", "differs", 35, 100.0)], esg_key
