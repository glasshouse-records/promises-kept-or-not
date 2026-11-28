"""Share classes of one ballot count once in rate tools (ROADMAP 3b-f ii): proposal rows stay
one per filed security, but a rate counts one ballot per (institution, adviser, CUSIP[:6],
issuer, meeting, wording); classes voted differently make the ballot MIXED."""


from glasshouse import engine, ledger, screens

DESC = "Report on Climate Transition Plan"


def _env(tmp_path, votes, name="sc", insts=("alpha", "beta", "gamma")):
    """votes: (institution, cusip, issuer, how, date, desc, series)"""
    led = tmp_path / f"{name}.db"
    c = ledger.connect(led)
    for n, iid in enumerate(insts):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"A-{iid}", str(n + 1), iid, f"https://sec.example/{iid}"))
    for iid, cusip, issuer, how, date, desc, series in votes:
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, is_duplicate, vote_series, category_type)"
                  " VALUES (?,?,?,?,?,'SECURITY HOLDER',?,'AGAINST',100,0,?,"
                  "'SHAREHOLDER PROPOSAL')",
                  (f"A-{iid}", issuer, cusip, date, desc, how, series))
    c.commit()
    c.close()
    out = tmp_path / f"{name}.engine.db"
    engine.build(led, out, institutions={})
    return engine.Engine(out, led)


def _v(cusip="060505104", issuer="BANK OF AMERICA CORP", how="FOR", date="04/22/2025",
       desc=DESC, iid="alpha", series=None):
    return (iid, cusip, issuer, how, date, desc, series)


FOUR = ["060505104", "060505815", "060505831", "060505849"]    # BofA common + 3 preferreds


def _rec(eng, **kw):
    return eng.voting_record("alpha", theme="climate", **kw)["result"]


def test_four_share_classes_count_as_one_ballot(tmp_path):
    eng = _env(tmp_path, [_v(c) for c in FOUR])
    r = _rec(eng)
    assert r["overall"]["proposals"] == 1 and r["overall"]["for"] == 1
    assert r["share_class_rows_collapsed"] == 3 and r["mixed"] == 0
    assert r["overall"]["support_rate"] == 1.0
    assert any("ONCE" in c for c in eng.voting_record("alpha", theme="climate")["caveats"])


def test_different_positions_make_the_ballot_mixed(tmp_path):
    eng = _env(tmp_path, [_v(FOUR[0], how="FOR"), _v(FOUR[1], how="AGAINST"),
                          _v(FOUR[2], how="AGAINST"), _v(FOUR[3], how="AGAINST"),
                          _v("999999999", "OTHER CO", "AGAINST")])
    o = _rec(eng)["overall"]
    assert _rec(eng)["mixed"] == 1
    assert (o["for"], o["against"], o["mixed"]) == (0, 1, 1)   # MIXED is neither
    assert o["proposals"] == 2 and o["support_rate"] == 0.0     # rate over the one decided


def test_all_mixed_has_no_rate(tmp_path):
    eng = _env(tmp_path, [_v(FOUR[0], how="FOR"), _v(FOUR[1], how="AGAINST")])
    o = _rec(eng)["overall"]
    assert o["mixed"] == 1 and o["support_rate"] is None


def test_different_wording_same_meeting_does_not_collapse(tmp_path):
    eng = _env(tmp_path, [_v(FOUR[0]), _v(FOUR[1], desc="Report on Climate Lobbying Alignment")])
    r = _rec(eng)
    assert r["overall"]["proposals"] == 2 and r["share_class_rows_collapsed"] == 0


def test_different_meeting_does_not_collapse(tmp_path):
    eng = _env(tmp_path, [_v(FOUR[0]), _v(FOUR[1], date="04/23/2025")])
    r = _rec(eng)
    assert r["overall"]["proposals"] == 2 and r["share_class_rows_collapsed"] == 0


def test_same_cusip6_different_issuer_does_not_collapse(tmp_path):
    eng = _env(tmp_path, [_v("060505104", "BANK OF AMERICA CORP"),
                          _v("060505815", "BANCO DIFFERENT SA")])
    r = _rec(eng)
    assert r["overall"]["proposals"] == 2 and r["share_class_rows_collapsed"] == 0


def test_non_us_y_prefix_collapses_only_with_the_same_issuer(tmp_path):
    # Y1594G107 / Y1594G115 share six characters; two issuers must stay two ballots
    eng = _env(tmp_path, [_v("Y1594G107", "GRAND SHIPPING LTD"),
                          _v("Y1594G115", "UNRELATED MINING PLC"),
                          _v("Y1594G123", "GRAND SHIPPING LTD", date="04/23/2025")])
    r = _rec(eng)
    assert r["overall"]["proposals"] == 3 and r["share_class_rows_collapsed"] == 0
    eng2 = _env(tmp_path, [_v("Y1594G107", "GRAND SHIPPING LTD"),
                           _v("Y1594G115", "Grand  Shipping Ltd")], name="sc2")
    r2 = _rec(eng2)                                   # same issuer, normalised: one ballot
    assert r2["overall"]["proposals"] == 1 and r2["share_class_rows_collapsed"] == 1


def test_short_or_empty_cusip_never_collapses(tmp_path):
    eng = _env(tmp_path, [_v("ABC12", "SAME CO"), _v("ABC13", "SAME CO"),
                          _v("", "SAME CO"), _v("", "SAME CO", date="04/22/2025 ")])
    assert _rec(eng)["share_class_rows_collapsed"] == 0


def test_institutions_are_never_pooled(tmp_path):
    eng = _env(tmp_path, [_v(FOUR[0]), _v(FOUR[1], iid="beta")])
    assert eng.voting_record("alpha", theme="climate")["result"]["overall"]["proposals"] == 1
    assert eng.voting_record("beta", theme="climate")["result"]["overall"]["proposals"] == 1


def test_listing_tools_still_return_every_row(tmp_path):
    eng = _env(tmp_path, [_v(c) for c in FOUR])
    res = eng.proposals(institution="alpha", theme="climate")["result"]
    assert res["matching"] == 4 and len(res["shown"]) == 4
    assert len(eng.ballot(res["shown"][0]["proposal_id"])["result"]) == 1   # its own key
    assert eng.db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 4


def test_peers_counts_one_ballot_and_excludes_mixed(tmp_path):
    votes = []
    for iid in ("beta", "gamma"):
        votes.append(_v(FOUR[0], iid=iid))                 # peers filed the common class only
    votes += [_v(c, how="FOR", iid="alpha") for c in FOUR]
    votes += [_v(FOUR[0], desc="Report on Climate Lobbying Alignment", iid=i, how="AGAINST")
              for i in ("alpha", "beta", "gamma")]
    votes += [_v(c, iid="alpha", date="05/01/2025", how="FOR" if c == FOUR[0] else "AGAINST")
              for c in FOUR[:2]]                           # alpha MIXED on this one
    votes += [_v(FOUR[0], iid=i, date="05/01/2025") for i in ("beta", "gamma", "delta")]
    res = _env(tmp_path, votes, insts=("alpha", "beta", "gamma", "delta")).peers(theme="climate", min_managers=3)["result"]
    a = res["managers"]["alpha"]
    assert a["shared_proposals"] == 2 and a["for"] == 1       # 4 classes -> 1; MIXED not counted
    assert a["mixed_not_counted"] == 1
    assert res["share_class_rows_collapsed"] == 4 - 1 + 1 and res["mixed"] == 1


def test_fund_record_collapses_share_classes_and_reports_mixed(tmp_path):
    votes = [_v(c, series="S000000001") for c in FOUR]
    votes += [_v(c, series="S000000001", date="05/01/2025",
                 how="FOR" if c == FOUR[0] else "AGAINST") for c in FOUR[:2]]
    votes += [_v(FOUR[0], series="S000000001", date="06/01/2025")]
    res = _env(tmp_path, votes).fund_record(series_id="S000000001", theme="climate")["result"]
    t = res["series"][0]["themes"]["climate"]
    assert t["ballots"] == 3 and t["for"] == 2 and t["mixed"] == 1 and t["against"] == 0
    assert t["share_class_rows_collapsed"] == 3 + 1
    assert any(len(p.get("class_proposal_ids", [])) == 4 for p in t["proposals"])


def test_s3_counts_one_ballot_per_class_group(tmp_path):
    votes = []
    for i in range(35):
        d = f"Report on Climate Transition Plan {i}"
        votes += [_v(c, how="AGAINST", desc=d, iid="alpha") for c in FOUR]
        votes += [_v(FOUR[0], how="FOR", desc=d, iid=x) for x in ("beta", "gamma")]
    eng = _env(tmp_path, votes, insts=("alpha", "beta", "gamma", "delta"))
    res = screens.s3_peer_outliers(eng)
    assert res["share_class_rows_collapsed"] == 35 * 3 and res["mixed"] == 0
    assert "SHARE" not in res        # shape guard; candidates need 3 peers, none here
    assert eng.voting_record("alpha", theme="climate")["result"]["overall"]["proposals"] == 35


def test_s5_dedupe_collapses_classes_and_drops_mixed():
    def pr(pid, cusip, pos):
        return {"proposal_id": pid, "institution_id": "a", "adviser": None, "cusip": cusip,
                "issuer_name": "BofA", "meeting_date": "2025-04-22", "description": DESC,
                "weight_basis": "shares", "position": pos}
    rows = [(1, pr(1, "060505104", "FOR"), "FOR", 0.0), (2, pr(2, "060505815", "FOR"), "FOR", 0.0),
            (3, pr(3, "11111Y104", "FOR"), "FOR", 0.0)]
    rows[2][1]["issuer_name"] = "Other"
    kept, collapsed, mixed = screens._dedupe(rows)
    assert [r[0] for r in kept] == [1, 3] and collapsed == 1 and mixed == 0
    rows[1] = (2, pr(2, "060505815", "AGAINST"), "AGAINST", 0.0)
    kept, collapsed, mixed = screens._dedupe(rows)
    assert [r[0] for r in kept] == [3] and mixed == 1
