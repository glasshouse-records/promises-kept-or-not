"""The evidence engine and the desk that checks drafts written from it."""

from __future__ import annotations

import sqlite3

import pytest

from glasshouse import desk, engine, ledger

POLICY_2023 = ("<html><body><p>We expect boards to disclose climate transition plans "
               "aligned with a 1.5 degree pathway. " + "Filler sentence number one is here. " * 8
               + "</p></body></html>")
POLICY_2025 = ("<html><body><p>We may consider climate related disclosures where material. "
               + "Filler sentence number one is here. " * 8 + "</p></body></html>")


@pytest.fixture()
def eng(tmp_path):
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    for iid in ("alpha", "beta", "gamma"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)",
                  (iid, iid.title() + " Asset Management"))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{iid}", "1", iid, f"https://sec.example/{iid}"))

    def vote(iid, how, desc="Report on Climate Transition Plan", date="05/20/2024",
             dup=0, issuer="EXXON MOBIL", cusip="30231G102"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, is_duplicate) VALUES (?,?,?,?,?,'SECURITY HOLDER',?,"
                  "?,100,?)", (f"ACC-{iid}", issuer, cusip, date, desc, how,
                               "FOR" if how == "AGAINST" else "AGAINST", dup))

    for _ in range(3):                       # three funds, one proposal
        vote("alpha", "AGAINST")
    vote("alpha", "AGAINST", dup=1)          # flagged duplicate: must not count
    vote("beta", "FOR")
    vote("beta", "AGAINST")                  # beta's funds disagree → SPLIT
    vote("gamma", "FOR")
    vote("alpha", "AGAINST", date="03/01/2023", issuer="CHEVRON", cusip="166764100")
    vote("beta", "FOR", desc="Shareholder Proposal Regarding Climate Transition Plan Report")
    vote("alpha", "FOR", desc="Rescind Climate and Net Zero Emissions Reduction Targets",
         issuer="CHEVRON", cusip="166764100")

    for n, (wb, html) in enumerate((("20230601000000", POLICY_2023),
                                    ("20250115000000", POLICY_2025))):
        f = tmp_path / f"p{n}.html"
        f.write_text(html)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                  " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
                  " text_sha256) VALUES ('alpha','policy','https://alpha.example/p.html',"
                  "'2026-01-01',?,?,'text/html',1,?,?)", (f"sha{n}", str(f), wb, f"t{n}"))
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body></body></html>")
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
              " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
              " text_sha256) VALUES ('alpha','policy','https://alpha.example/p.html',"
              "'2026-01-01','shaE',?,'text/html',1,'20240101000000','')", (str(empty),))
    vote("alpha", "FOR", date="05/20/2025", desc="Report on Climate Transition Plan")

    def director(iid, how, nominee, date="05/20/2024", shares=100, dup=0):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,'EXXON MOBIL','30231G102',?,?,'DIRECTOR ELECTIONS','ISSUER',?,?,?,?)",
                  (f"ACC-{iid}", date, nominee, how, "FOR" if how == "FOR" else "AGAINST",
                   shares, dup))

    for _ in range(2):                       # two funds, two nominees
        director("alpha", "FOR", "Elect Director Jane Roe")
        director("alpha", "WITHHOLD", "Elect Director John Poe")
    director("alpha", "WITHHOLD", "Elect Director Jane Roe", shares=1)   # a sliver
    director("alpha", "WITHHOLD", "Elect Director Jane Roe", dup=1)
    for iid in ("beta", "gamma"):            # another vendor's wording
        director(iid, "FOR", "Election of Directors: Jane Roe")
        director(iid, "FOR", "Election of Directors: John Poe")
    director("alpha", "FOR", "Elect Director Jane Roe", date="05/19/2025")
    director("alpha", "FOR", "Elect Director John Poe", date="05/19/2025")

    def pay(iid, how, desc="Advisory vote to approve named executive officer compensation",
            date="05/20/2024", dup=0, shares=100, cat="SECTION 14A SAY-ON-PAY VOTES"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,'EXXON MOBIL','30231G102',?,?,?,'ISSUER',?,?,?,?)",
                  (f"ACC-{iid}", date, desc, cat, how,
                   "FOR" if how == "FOR" else "AGAINST", shares, dup))

    pay("alpha", "AGAINST")                                    # two funds, one item
    pay("alpha", "AGAINST")
    pay("alpha", "AGAINST", dup=1)                             # duplicate: must not count
    pay("alpha", "FOR", date="05/19/2025")
    pay("alpha", "ONE YEAR", desc="Advisory vote on the frequency of future advisory votes "
        "on executive compensation")                           # frequency: not for/against
    pay("beta", "FOR")
    pay("gamma", "ABSTAIN", date="05/20/2025")
    c.commit()
    c.close()
    out = tmp_path / "engine.db"
    engine.build(led, out)
    return engine.Engine(out, led)


def test_a_proposal_counts_once_however_many_funds_voted(eng):
    """N-PX reports one line per fund. Three funds voting on one proposal is one
    decision, not three — rates over lines weight a proposal by fund count."""
    r = eng.voting_record("alpha", query="climate transition")["result"]["by_year"][2024]
    assert r["proposals"] == 1 and r["against"] == 1


def test_duplicate_lines_never_reach_the_index(eng):
    row = eng.db.execute("SELECT n_lines FROM proposals WHERE institution_id='alpha' "
                         "AND year=2024 AND position='AGAINST'").fetchone()
    assert row["n_lines"] == 3, "the is_duplicate=1 line must be excluded"


def test_funds_voting_both_ways_is_a_split_not_a_side(eng):
    r = eng.voting_record("beta", query="climate transition")["result"]["overall"]
    assert r["split"] == 1


def test_peers_compares_the_same_proposal_across_managers(eng):
    r = eng.peers(query="climate transition", min_managers=2)["result"]
    m = r["managers"]                 # keyed by institution: stable claim paths
    assert m["alpha"]["support_rate"] == 0.0 and m["gamma"]["support_rate"] == 1.0


def test_rollback_proposals_are_not_counted_as_the_theme(eng):
    """A proposal attacking climate commitments is not a climate proposal: a FOR
    there is the opposite stance, and must not raise the support rate."""
    with_rb = eng.voting_record("alpha", theme="climate", include_rollback=True)["result"]
    without = eng.voting_record("alpha", theme="climate")["result"]
    assert with_rb["overall"]["for"] == without["overall"]["for"] + 1


def test_votes_are_only_set_against_the_policy_public_at_the_time(eng):
    """The 2023-03 vote predates the first archived version (captured 2023-06),
    so it may not be attributed to any policy wording."""
    rows = eng.say_vs_do("alpha", "climate", theme="climate")["result"]
    assert [x["did"]["proposals"] for x in rows] == [1, 1]
    assert rows[0]["in_force_until"] == "2025-01-15"


def test_policy_diff_reports_verbatim_removals(eng):
    a, b = _readable(eng)
    d = eng.policy_diff("alpha", a, b, pattern="climate")["result"]
    assert any("1.5 degree pathway" in s for s in d["removed"])
    assert any("may consider" in s for s in d["added"])


def test_sql_is_read_only(eng):
    with pytest.raises(ValueError):
        eng.sql("DELETE FROM proposals")


def _readable(eng):
    return [v["commitment_id"] for v in eng.policy_versions("alpha")["result"]
            if v["readable"]]


def test_an_unreadable_capture_is_never_the_policy_in_force(eng):
    """Found by the first agent to use the engine: an empty capture sat between
    two real versions and was returned as 'the policy', so a whole season of
    votes was attributed to a document with no words in it."""
    got = eng.policy_in_force("alpha", "2024-05-20")["result"]["versions"]
    assert got and all(v["readable"] for v in got)
    assert got[0]["captured"] == "2023-06-01"


def test_a_long_gap_between_captures_is_flagged(eng):
    rows = eng.say_vs_do("alpha", "climate", theme="climate")["result"]
    assert rows[0]["archive_gap"] is True, "593 days with no capture is not continuity"


def test_management_field_means_vote_versus_management(eng):
    """N-PX's field records whether the vote went WITH or AGAINST management,
    not what management recommended. Reading it as the recommendation made
    'voted for where management opposed' equal its own denominator."""
    r = eng.voting_record("alpha", query="climate transition")["result"]
    assert r["against_management"] == {"count": 1, "of": 3}


def test_reversals_finds_the_same_proposal_voted_differently_next_year(eng):
    r = eng.reversals("alpha", query="climate transition")["result"]
    r = r["pairs"]
    assert len(r) == 1 and r[0]["from"]["position"] == "AGAINST" \
        and r[0]["to"]["position"] == "FOR"


def test_filers_shows_how_much_of_the_manager_is_covered(eng):
    r = eng.filers("alpha")["result"]
    assert r["registrants"] == 1


def test_diff_ignores_footnote_renumbering(tmp_path):
    a = {engine.diff_key(s) for s in engine.sentences(
        "We vote against directors where boards lack independence. 3.")}
    b = {engine.diff_key(s) for s in engine.sentences(
        "We vote against directors where boards lack independence. 4.")}
    assert a == b


# ----------------------------------------------------------------- the desk

def _draft(eng, **over):
    a, b = _readable(eng)
    pid = eng.proposals(institution="alpha", year=2024)["result"]["shown"][0]["proposal_id"]
    d = {"slug": "t", "headline": "Alpha's climate wording changed",
         "headline_claims": ["c1", "c2"],
         "standfirst": "What the archived record contains.",
         "body": ("Alpha's 2023 policy said “We expect boards to disclose climate transition "
                  "plans aligned with a 1.5 degree pathway.” [c1]\n\n"
                  "That sentence is not in the version archived in 2025. [c2]\n\n"
                  "Alpha supported 0 such proposals in 2024. [c3]\n\n"
                  "At Exxon Mobil on 2024-05-20 it voted against. [c4]"),
         "claims": [
             {"id": "c1", "text": "quote", "check": {
                 "type": "quote", "commitment_id": a,
                 "text": "We expect boards to disclose climate transition plans aligned "
                         "with a 1.5 degree pathway."}},
             {"id": "c2", "text": "absent", "check": {
                 "type": "absent", "commitment_id": b,
                 "text": "We expect boards to disclose climate transition plans"}},
             {"id": "c3", "text": "rate", "check": {
                 "type": "stat", "tool": "voting_record",
                 "args": {"institution": "alpha", "query": "climate transition"},
                 "path": "by_year.2024.for", "equals": 0}},
             {"id": "c4", "text": "vote", "check": {
                 "type": "proposal", "proposal_id": pid, "institution": "alpha",
                 "position": "AGAINST", "company": "EXXON", "meeting_date": "2024-05-20"}}],
         "limitations": ["One proposal is an anecdote.", "Four funds only."]}
    d.update(over)
    return d


def test_a_sound_draft_verifies(eng):
    rep = desk.verify(_draft(eng), eng)
    assert rep["verified"], rep["problems"]


def test_a_wrong_number_fails(eng):
    d = _draft(eng)
    d["claims"][2]["check"]["equals"] = 1
    assert not desk.verify(d, eng)["verified"]


def test_a_misquote_fails(eng):
    d = _draft(eng)
    d["claims"][0]["check"]["text"] = "We require boards to disclose climate transition plans"
    assert not desk.verify(d, eng)["verified"]


def test_a_figure_without_a_claim_fails(eng):
    d = _draft(eng)
    d["body"] += "\n\nAlpha manages 9 trillion dollars."
    assert any("no claim" in p for p in desk.verify(d, eng)["problems"])


def test_motive_and_accusation_are_rejected(eng):
    """The record shows what was said and done. It cannot show intent, and for
    an uninsured publisher that word is the whole legal exposure."""
    d = _draft(eng, headline="Alpha abandoned its climate promise")
    assert any("characterisation" in p for p in desk.verify(d, eng)["problems"])


def test_a_quotation_must_be_a_verified_quote(eng):
    d = _draft(eng)
    d["body"] += "\n\nIt also said “climate risk is the defining issue of our era.” [c1]"
    assert any("not backed" in p for p in desk.verify(d, eng)["problems"])


def test_a_draft_must_state_its_limits(eng):
    assert not desk.verify(_draft(eng, limitations=[]), eng)["verified"]


def test_every_paragraph_needs_a_claim_not_just_numeric_ones(eng):
    d = _draft(eng)
    d["body"] += "\n\nAlpha opposed nearly all such resolutions."
    assert any("no claim" in p for p in desk.verify(d, eng)["problems"])


def test_a_number_must_come_from_a_claim_cited_in_its_paragraph(eng):
    """A marker in the paragraph is not enough: the figure itself has to be one
    the cited claims actually establish."""
    d = _draft(eng)
    d["body"] = d["body"].replace("supported 0 such proposals in 2024",
                                  "supported 0 of 37 such proposals in 2024")
    assert any("37" in p for p in desk.verify(d, eng)["problems"])


def test_a_vote_claim_checks_the_company_and_date_in_the_prose(eng):
    d = _draft(eng)
    d["claims"][3]["check"]["meeting_date"] = "2024-06-20"
    assert not desk.verify(d, eng)["verified"]


def test_the_headline_must_rest_on_claims(eng):
    d = _draft(eng)
    del d["headline_claims"]
    assert any("headline" in p for p in desk.verify(d, eng)["problems"])


def test_insinuation_is_rejected_like_accusation(eng):
    d = _draft(eng, standfirst="Alpha quietly walked back its wording. [c1]")
    assert any("characterisation" in p for p in desk.verify(d, eng)["problems"])


def test_a_sliver_of_shares_the_other_way_is_not_a_split(tmp_path):
    """Second trial run: State Street showed 801 'split' proposals because each
    fund files a tiny second line (0.2-2.5% of its shares) the other way. Counting
    lines called that an even split and dropped the proposal from every rate."""
    assert engine.position_from_shares(4997.6, 1_040_000.0, 0) == "AGAINST"
    assert engine.position_from_shares(600.0, 400.0, 0) == "SPLIT"
    assert engine.position_from_shares(0, 0, 3) == "ABSTAIN"


def test_rollback_wording_the_shared_detector_misses():
    assert engine.is_rollback("Remove Emissions Reduction Targets")
    assert engine.is_rollback("Revisit Executive Pay Incentives for GHG Emission Reductions")
    # As You Sow's retirement-plan proposal ASKS for climate-risk reporting
    assert not engine.is_rollback("Report on Climate Risks to Retirement Plan Beneficiaries")


def test_fund_votes_shows_each_series_behind_a_position(eng):
    pid = eng.proposals(institution="alpha", year=2024)["result"]["shown"][0]["proposal_id"]
    r = eng.fund_votes(pid)["result"]
    assert len(r["lines"]) == 3 and r["shares"]["against"] == 300


def test_reversals_reports_direction_counts(eng):
    r = eng.reversals("alpha", query="climate transition")["result"]
    assert r["summary"] == {"pairs": 1, "for_to_against": 0, "against_to_for": 1}


def test_internal_ids_do_not_back_a_number_in_prose(eng):
    """A proposal_id of 7 must not make a stray '7' in the prose look sourced."""
    d = _draft(eng)
    pid = d["claims"][3]["check"]["proposal_id"]
    d["body"] = d["body"].replace("it voted against. [c4]",
                                  f"it voted against, one of {pid + 900} such votes. [c4]")
    assert any(str(pid + 900) in p for p in desk.verify(d, eng)["problems"])


# ---------------------------------------------------------------- directors

def test_director_votes_count_per_nominee_not_per_fund(eng):
    """Two funds withholding from one nominee is one decision; a sliver the
    other way does not turn a FOR into a split; duplicates never count."""
    r = eng.director_record("alpha")["result"]["by_year"]
    assert r[2024]["nominees"] == 2 and r[2024]["opposed"] == 1 and r[2024]["for"] == 1
    assert r[2024]["opposition_rate"] == 0.5
    assert r[2024]["meetings"] == 1 and r[2024]["meetings_with_opposition"] == 1
    assert r[2025]["opposed"] == 0 and r[2025]["meetings_with_opposition"] == 0


def test_director_elections_stay_out_of_the_proposal_index(eng):
    n = eng.db.execute("SELECT COUNT(*) FROM proposals WHERE description LIKE '%Roe%'")
    assert n.fetchone()[0] == 0


def test_director_peers_compares_the_same_meetings(eng):
    """Vendors word nominees differently, so managers are compared on the
    meetings they all voted at, not on nominee strings."""
    r = eng.director_peers(year=2024)["result"]
    assert r["shared_meetings"] == 1
    assert r["managers"]["alpha"]["meetings_with_opposition"] == 1
    assert r["managers"]["beta"]["meetings_with_opposition"] == 0
    assert r["managers"]["alpha"]["opposition_rate"] == 0.5


def test_director_votes_lists_the_nominees_with_their_source(eng):
    rows = eng.director_votes("alpha", company="exxon", position="AGAINST")["result"]
    assert len(rows) == 1 and rows[0]["nominee_item"] == "Elect Director John Poe"
    assert rows[0]["source_url"] == "https://sec.example/alpha"


def test_a_director_claim_checks_who_where_and_when(eng):
    row = eng.director_votes("alpha", company="exxon", position="AGAINST")["result"][0]
    check = {"type": "director", "director_id": row["director_id"], "institution": "alpha",
             "position": "AGAINST", "company": "Exxon", "meeting_date": "2024-05-20",
             "nominee": "John Poe"}
    assert desk._check(eng, check)[0]
    assert not desk._check(eng, {**check, "nominee": "Jane Roe"})[0]
    assert not desk._check(eng, {**check, "meeting_date": "2025-05-19"})[0]
    assert not desk._check(eng, {k: v for k, v in check.items() if k != "nominee"})[0]


def test_a_number_spelled_out_is_still_a_number(eng):
    """"Three of four" slipped past a check that only looked for digits."""
    d = _draft(eng)
    d["body"] += "\n\nAlpha opposed three such proposals. [c3]"
    assert any("digits" in p for p in desk.verify(d, eng)["problems"])


def test_a_vague_quantity_is_not_a_fact(eng):
    """"Nearly all" beside a valid claim asserts a proportion no claim checks."""
    d = _draft(eng)
    d["body"] += "\n\nAlpha opposed nearly all such resolutions. [c3]"
    assert any("count" in p for p in desk.verify(d, eng)["problems"])
    d = _draft(eng, headline="Alpha's climate support fell sharply")
    assert any("count" in p for p in desk.verify(d, eng)["problems"])


def test_figures_in_the_limitations_are_checked_too(eng):
    d = _draft(eng, limitations=["Only 9 funds are on file.", "One proposal is an anecdote."])
    assert any("limitation" in p for p in desk.verify(d, eng)["problems"])
    d = _draft(eng, limitations=["Alpha backed 0 such proposals in 2024, a single item. [c3]",
                                 "One proposal is an anecdote."])
    assert desk.verify(d, eng)["verified"], desk.verify(d, eng)["problems"]


def test_coverage_shows_filings_per_season_so_a_partial_season_is_visible(eng):
    """One filing of a season's dozen looks like a collapse in every rate unless
    the count of filings on file is shown next to it."""
    c = eng.ledger
    row = next(i for i in eng.coverage()["result"]["institutions"]
               if i["institution"] == "alpha")
    assert row["vote_filings_by_season"] == {2024: 1}
    assert row["director_items_by_year"] == {2024: 2, 2025: 2}
    assert c.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 3


# ------------------------------------------- faults reported by the third trial

@pytest.mark.parametrize("bad", ["", "2024-01-01 2024-06-30", "garbage", "2024-13-01", "01/01/2024"])
def test_a_malformed_date_is_refused_not_ignored(eng, bad):
    """An empty `until` was silently dropped and a two-date `since` matched
    everything after it, under an echoed args block that looked right."""
    for call in (lambda: eng.director_record("alpha", since="2024-01-01", until=bad),
                 lambda: eng.director_peers(since=bad),
                 lambda: eng.peers(theme="climate", since=bad),
                 lambda: eng.voting_record("alpha", theme="climate", until=bad)):
        with pytest.raises(ValueError, match="ISO date"):
            call()


def test_director_panel_holds_the_companies_constant(eng):
    """'Different companies each year' is the first dull explanation for a
    moving rate; the control must be citable, not hand SQL."""
    r = eng.director_panel("alpha", windows="2024-01-01:2024-06-30,2025-01-01:2025-06-30")
    r = r["result"]
    assert r["companies_in_every_window"] == 1
    w24, w25 = r["windows"]
    assert w24["companies_with_opposition"] == 1 and w25["companies_with_opposition"] == 0
    assert w24["opposed"] == 1 and w24["nominees"] == 2
    assert r["opposed_in_first_and_last"] == 0


def test_a_claim_id_of_the_wrong_shape_is_named_as_such(eng):
    d = _draft(eng)
    d["claims"][2]["id"] = "rate"
    d["body"] = d["body"].replace("[c3]", "[rate]")
    assert any("claim id 'rate'" in p for p in desk.verify(d, eng)["problems"])


def test_a_date_in_the_prose_must_be_a_date_the_claims_carry(eng):
    """'2024-05-20' was checked as the loose numbers 2024, 5 and 20."""
    d = _draft(eng)
    d["body"] = d["body"].replace("on 2024-05-20 it voted", "on 2024-05-02 it voted")
    d["claims"][2]["check"]["args"]["since"] = "2024-01-02"     # a stray 2 to borrow
    assert any("date 2024-05-02" in p for p in desk.verify(d, eng)["problems"])


def test_thousands_separators_are_read_as_one_number(eng):
    assert desk._numbers("opposed 3,229 of 12,400.5 items, then 4, 5") == [
        "3229", "12400.5", "4", "5"]


def test_limitations_may_not_characterise_either(eng):
    d = _draft(eng, limitations=["Alpha misled nobody on record.", "One proposal only."])
    assert any("characterisation" in p for p in desk.verify(d, eng)["problems"])


def test_a_filtered_diff_says_what_the_filter_can_hide(eng):
    a, b = _readable(eng)
    cav = " ".join(eng.policy_diff("alpha", a, b, pattern="1\\.5")["caveats"])
    assert "replacement" in cav


# ------------------------------------------------- country of the issuer's ISIN

@pytest.fixture()
def iso(tmp_path):
    """Director items at US, non-US, no-ISIN and conflicting-ISIN companies."""
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    for iid in ("alpha", "beta"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)",
                  (iid, iid.title() + " Asset Management"))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{iid}", "1", iid, f"https://sec.example/{iid}"))

    def d(iid, how, company, cusip, isin, nominee, date="05/20/2024"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, isin, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,?,?,?,?,?,'DIRECTOR ELECTIONS','ISSUER',?,?,100,0)",
                  (f"ACC-{iid}", company, cusip, isin, date, nominee, how,
                   "FOR" if how == "FOR" else "AGAINST"))

    for iid in ("alpha", "beta"):
        for date in ("05/20/2024", "05/20/2025"):
            d(iid, "FOR", "ACME", "000000001", "US0000000010", "Elect Ann", date)
            d(iid, "AGAINST" if iid == "alpha" else "FOR", "ACME", "000000001",
              "US0000000010", "Elect Bob", date)
            d(iid, "AGAINST" if iid == "alpha" else "FOR", "NIPPON", "000000002",
              "JP0000000020", "Elect Chi", date)
        d(iid, "FOR", "CAYCO", "000000003", "KY0000000030", "Elect Dee")
        d(iid, "FOR", "NOISIN", "000000004", None, "Elect Eve")
        d(iid, "AGAINST", "NOISIN", "000000004", "", "Elect Fay")
        d(iid, "FOR", "BADISIN", "000000006", "12XYZ", "Elect Hal")
    # one item whose fund lines disagree on the country: stored as unknown
    d("alpha", "FOR", "CONFLICT", "000000005", "US0000000050", "Elect Gus")
    d("alpha", "FOR", "CONFLICT", "000000005", "CA0000000050", "Elect Gus")
    c.commit()
    c.close()
    out = tmp_path / "engine.db"
    engine.build(led, out)
    return engine.Engine(out, led)


def _country_of(iso, company):
    return {r[0] for r in iso.db.execute(
        "SELECT isin_country FROM director_votes WHERE issuer_name=?", (company,))}


def test_isin_country_is_two_letters_or_unknown(iso):
    assert _country_of(iso, "ACME") == {"US"}
    assert _country_of(iso, "NIPPON") == {"JP"}
    assert _country_of(iso, "CAYCO") == {"KY"}
    assert _country_of(iso, "NOISIN") == {None}
    assert _country_of(iso, "BADISIN") == {None}       # "12" is not a country
    assert _country_of(iso, "CONFLICT") == {None}      # US and CA on one item


@pytest.mark.parametrize("bad", ["", "USA", "u", "US,", "US,non-US", "nonUS", "non-us,CA", "1S",
                                 "US CA", "everything"])
def test_an_unrecognised_country_is_refused_not_ignored(iso, bad):
    for call in (lambda: iso.director_record("alpha", country=bad),
                 lambda: iso.director_votes("alpha", country=bad),
                 lambda: iso.director_peers(country=bad),
                 lambda: iso.director_panel("alpha", windows="2024-01-01:2024-12-31,"
                                            "2025-01-01:2025-12-31", country=bad)):
        with pytest.raises(ValueError, match="country"):
            call()


def test_country_filters_and_counts_what_it_excluded(iso):
    us = iso.director_record("alpha", country="US")
    assert us["result"]["overall"]["nominees"] == 4     # ACME: two nominees, two years
    assert us["args"] == {"institution": "alpha", "country": "US"}
    excluded = [c for c in us["caveats"] if "lacking an ISIN" in c]
    assert len(excluded) == 1
    # NOISIN x2, BADISIN, CONFLICT: four items with no usable country
    assert excluded[0].startswith("4 nominee items were excluded")
    assert any("country that issued the ISIN" in c and "not where the company is run" in c
               for c in us["caveats"])
    non = iso.director_record("alpha", country="non-US")["result"]["overall"]
    assert non["nominees"] == 3                          # NIPPON x2, CAYCO x1 (KY counts)
    both = iso.director_record("alpha", country="jp,KY")["result"]["overall"]
    assert both["nominees"] == 3


def test_the_excluded_count_follows_the_other_filters(iso):
    r = iso.director_record("alpha", country="US", since="2025-01-01")
    assert any(c.startswith("0 nominee items were excluded") for c in r["caveats"])


def test_no_country_means_no_country_caveat(iso):
    r = iso.director_record("alpha")
    assert not any("lacking an ISIN" in c for c in r["caveats"])


def test_by_country_adds_up_to_the_overall_block(iso):
    r = iso.director_record("alpha")["result"]
    bc = r["by_country"]
    assert set(bc) == {"US", "non-US", "unknown"}
    for k in ("nominees", "opposed"):
        assert sum(bc[b][k] for b in bc) == r["overall"][k]
    assert bc["US"]["nominees"] == 4 and bc["US"]["opposed"] == 2
    assert bc["US"]["opposition_rate"] == 0.5
    assert bc["non-US"]["nominees"] == 3 and bc["non-US"]["opposed"] == 2
    assert bc["unknown"]["nominees"] == 4
    assert "by_country" not in iso.director_record("alpha", country="US")["result"]


def test_country_args_round_trip(iso):
    env = iso.director_record("alpha", country="non-US", since="2024-01-01")
    assert env["args"]["country"] == "non-US"
    assert iso.director_record(**env["args"])["result"] == env["result"]
    env = iso.director_votes("alpha", country="US,CA")
    assert iso.director_votes(**env["args"])["result"] == env["result"]
    env = iso.director_peers(country="US", min_managers=2)
    assert iso.director_peers(**env["args"])["result"] == env["result"]
    env = iso.director_panel("alpha", windows="2024-01-01:2024-12-31,2025-01-01:2025-12-31",
                             country="US")
    assert iso.director_panel(**env["args"])["result"] == env["result"]


def test_director_votes_with_country_lists_only_those_items(iso):
    rows = iso.director_votes("alpha", country="non-US", limit=100)["result"]
    assert {r["company"] for r in rows} == {"NIPPON", "CAYCO"}


def test_director_peers_with_country(iso):
    r = iso.director_peers(country="non-US", min_managers=2)["result"]
    assert r["shared_meetings"] == 3                     # NIPPON 2024, 2025 and CAYCO 2024
    assert r["managers"]["alpha"]["opposed"] == 2
    us = iso.director_peers(country="US", min_managers=2)["result"]
    assert us["shared_meetings"] == 2


def test_director_panel_with_country(iso):
    w = "2024-01-01:2024-12-31,2025-01-01:2025-12-31"
    r = iso.director_panel("alpha", windows=w, country="non-US")
    assert r["result"]["companies_in_every_window"] == 1     # NIPPON; CAYCO only in 2024
    assert r["result"]["windows"][0]["nominees"] == 1
    assert any("lacking an ISIN" in c for c in r["caveats"])
    allc = iso.director_panel("alpha", windows=w)["result"]
    assert allc["companies_in_every_window"] == 2


# ------------------------------------------------ instrument fixes (2026-11-17)

def test_country_matching_nothing_in_the_index_says_so(iso):
    eng = iso
    """UK is well-formed but the ISIN prefix is GB: an empty answer needs a hint."""
    env = eng.director_votes("alpha", country="UK")
    assert any("UK" in c and "matches no item" in c and "GB, not UK" in c
               for c in env["caveats"])
    ok = eng.director_votes("alpha", country="US")
    assert not any("matches no item" in c for c in ok["caveats"])
    # one known code among unknown ones: no warning
    assert not any("matches no item" in c
                   for c in eng.director_votes("alpha", country="US,UK")["caveats"])


def test_filers_names_come_from_the_registry_and_unknown_is_null(eng, monkeypatch):
    monkeypatch.setattr(engine, "_registry_names", lambda iid: {"1": "Alpha Funds Trust"})
    env = eng.filers("alpha")
    assert env["result"]["filers"][0]["registrant_name"] == "Alpha Funds Trust"
    assert "institutions.yaml" in env["result"]["name_source"]
    monkeypatch.setattr(engine, "_registry_names", lambda iid: {})
    assert eng.filers("alpha")["result"]["filers"][0]["registrant_name"] is None


def _ledger_rw(eng):
    path = eng.ledger.execute("PRAGMA database_list").fetchone()[2]
    return sqlite3.connect(path)


def test_fund_votes_names_the_series_by_its_latest_filing(eng):
    w = _ledger_rw(eng)
    w.execute("UPDATE filings SET filing_date='2024-08-01' WHERE accession='ACC-alpha'")
    w.execute("INSERT INTO filings (accession, cik, institution_id, form_type,"
              " filing_date, source_url, retrieval_date) VALUES ('ACC-alpha-2','1',"
              "'alpha','N-PX','2025-08-01','https://sec.example/a2','2026-01-01')")
    w.execute("UPDATE votes SET vote_series='S1' WHERE accession='ACC-alpha'")
    w.executemany("INSERT INTO fund_series (series_id, accession, name) VALUES (?,?,?)",
                  [("S1", "ACC-alpha", "Old Name Fund"), ("S1", "ACC-alpha-2", "New Name Fund")])
    w.commit()
    pid = eng.proposals(institution="alpha", year=2024)["result"]["shown"][0]["proposal_id"]
    lines = eng.fund_votes(pid)["result"]["lines"]
    assert {ln["fund_series"] for ln in lines} == {"S1"}
    assert {ln["fund_series_name"] for ln in lines} == {"New Name Fund"}
    w.execute("DELETE FROM fund_series")
    w.commit()
    assert {ln["fund_series_name"]
            for ln in eng.fund_votes(pid)["result"]["lines"]} == {None}


def _problems(eng, body, **over):
    d = _draft(eng, body=body, **over)
    return desk.verify(d, eng)["problems"]


def test_majority_governance_terms_of_art_are_not_vague(eng):
    base = ("Alpha's 2023 policy said “We expect boards to disclose climate transition "
            "plans aligned with a 1.5 degree pathway.” [c1]\n\n"
            "That sentence is not in the version archived in 2025. [c2]\n\n"
            "Alpha supported 0 such proposals in 2024. [c3]\n\n")
    tail = "At Exxon Mobil on 2024-05-20 it voted against {} [c4]"
    for ok in ("a majority vote standard.", "a majority-vote standard.",
               "a majority voting standard.", "a majority voting policy.",
               "a majority voting requirement.", "a majority of votes cast standard.",
               "a supermajority."):
        assert not any("vague" in p for p in _problems(eng, base + tail.format(ok))), ok
    for bad in ("the majority of proposals.", "a majority of managers.",
                "it after a majority of votes cast by its funds opposed the proposal.",
                "it after the majority vote of its funds went against it.",
                "majority voting.", "a majority-vote rule."):
        assert any("vague" in p for p in _problems(eng, base + tail.format(bad))), bad


def test_straight_quote_with_a_stray_inch_mark_is_checked_not_mispaired(eng):
    q = ("We expect boards to disclose climate transition plans aligned with a 1.5 "
         "degree pathway.")
    body = ('Alpha\'s 2023 policy said "' + q + '" [c1]\n\n'
            "That sentence is not in the version archived in 2025. [c2]\n\n"
            "Alpha supported 0 such proposals in 2024. [c3]\n\n"
            "At Exxon Mobil on 2024-05-20 it voted against. [c4]")
    assert _problems(eng, body) == []
    # an inch mark makes the straight quotes odd: refuse to guess a pairing, so a
    # fabricated quote cannot hide behind it and a genuine one is not misread
    stray = body.replace("Alpha's", 'A 6" gap: Alpha\'s', 1)
    probs = _problems(eng, stray)
    assert any("odd number of straight" in p for p in probs)
    assert not any("not backed" in p for p in probs)
    # mixed curly and straight in one paragraph: each kind pairs with its own
    mixed = body.replace(f'"{q}"', f'“{q}” and, as the "short phrase" shows,')
    assert _problems(eng, mixed) == []


def test_a_quotation_must_be_backed_by_a_claim_that_paragraph_cites(eng):
    q = ("We expect boards to disclose climate transition plans aligned with a 1.5 "
         "degree pathway.")
    body = ("Alpha's 2023 policy said something. [c1]\n\n"
            f"The wording “{q}” appears elsewhere. [c3]\n\n"
            "That sentence is not in the version archived in 2025. [c2]\n\n"
            "At Exxon Mobil on 2024-05-20 it voted against. [c4]")
    assert any("not backed" in p for p in _problems(eng, body))


def test_standing_limitations_say_paragraph_relevance_is_unchecked():
    assert any("relevan" in s.lower() for s in desk.STANDING_LIMITATIONS)


# ------------------------------------------------------------ which adviser votes

TEXT_A = ("<html><body><p>Adviser A will support board diversity proposals always. "
          + "Filler sentence number one is here. " * 8 + "</p></body></html>")
TEXT_B = ("<html><body><p>Adviser B will oppose board diversity proposals always. "
          + "Filler sentence number one is here. " * 8 + "</p></body></html>")

REGISTRY = {
    "delta": {"npx_ciks": [
        {"cik": "11", "adviser": "Alpha Advisers LLC", "adviser_key": "AAA",
         "adviser_source": "https://sec.example/11"},
        {"cik": "22", "adviser": "Beta Investment Mgmt", "adviser_key": "BBB",
         "adviser_source": "https://sec.example/22"}],
        "commitments": [{"label": "policy-aaa", "adviser_key": "AAA"},
                        {"label": "policy-bbb", "adviser_key": "BBB"}]},
    "solo": {"npx_ciks": [{"cik": "33", "adviser_key": "AAA"},
                          {"cik": "44", "adviser_key": "AAA"}]},
}


def _duo_ledger(tmp_path):
    led = tmp_path / "duo.db"
    c = ledger.connect(led)
    for iid, ciks in (("delta", ("0000000011", "22")), ("solo", ("33", "44")),
                      ("other", ("55",))):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)",
                  (iid, iid.title() + " Group"))
        for cik in ciks:
            c.execute("INSERT INTO filings (accession, cik, institution_id, form_type,"
                      " source_url, retrieval_date, period_of_report, report_type) VALUES"
                      " (?,?,?,'N-PX',?,'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                      (f"ACC-{cik}", cik, iid, f"https://sec.example/{cik}"))

    def vote(cik, how, desc="Report on Board Diversity", nominee=False):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,'EXXON MOBIL','30231G102','05/20/2024',?,?,?,?,'FOR',100,0)",
                  (f"ACC-{cik}", desc, "DIRECTOR ELECTIONS" if nominee else "",
                   "ISSUER" if nominee else "SECURITY HOLDER", how))

    vote("0000000011", "FOR")
    vote("22", "AGAINST")
    vote("33", "FOR")
    vote("44", "FOR")
    vote("55", "FOR")
    for cik, how in (("0000000011", "FOR"), ("22", "WITHHOLD"), ("33", "FOR"),
                     ("44", "FOR"), ("55", "FOR")):
        vote(cik, how, desc="Elect Director Jane Roe", nominee=True)
    for cik, how in (("0000000011", "FOR"), ("22", "AGAINST"), ("33", "FOR")):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,'EXXON MOBIL','30231G102','05/20/2024',"
                  "'Advisory vote to approve executive compensation',"
                  "'SECTION 14A SAY-ON-PAY VOTES','ISSUER',?,?,100,0)",
                  (f"ACC-{cik}", how, "FOR" if how == "FOR" else "AGAINST"))
    for n, (label, text, iid) in enumerate((("policy-aaa", TEXT_A, "delta"),
                                            ("policy-bbb", TEXT_B, "delta"))):
        f = tmp_path / f"d{n}.html"
        f.write_text(text)
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                  " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
                  " text_sha256) VALUES (?,?,'https://delta.example/p.html','2026-01-01',?,?,"
                  "'text/html',1,'20240101000000',?)", (iid, label, f"s{n}", str(f), f"t{n}"))
    c.commit()
    c.close()
    return led


@pytest.fixture()
def duo(tmp_path):
    led = _duo_ledger(tmp_path)
    out = tmp_path / "duo-engine.db"
    engine.build(led, out, institutions=REGISTRY)
    return engine.Engine(out, led)


def test_advisers_voting_one_ballot_item_are_separate_rows(duo):
    rows = duo.db.execute("SELECT adviser, position FROM proposals "
                          "WHERE institution_id='delta' ORDER BY adviser").fetchall()
    assert [(r["adviser"], r["position"]) for r in rows] == [("AAA", "FOR"), ("BBB", "AGAINST")]
    d = duo.db.execute("SELECT adviser, position FROM director_votes "
                       "WHERE institution_id='delta' ORDER BY adviser").fetchall()
    assert [(r["adviser"], r["position"]) for r in d] == [("AAA", "FOR"), ("BBB", "AGAINST")]


def test_an_institution_with_one_known_adviser_builds_exactly_as_before(tmp_path):
    led = _duo_ledger(tmp_path)
    plain = tmp_path / "plain.db"
    labelled = tmp_path / "labelled.db"
    engine.build(led, plain, institutions={})
    engine.build(led, labelled, institutions=REGISTRY)
    for path in (plain, labelled):
        e = engine.Engine(path, led)
        assert e.db.execute("SELECT COUNT(*) FROM proposals WHERE institution_id='solo'"
                            ).fetchone()[0] == 1
        assert e.db.execute("SELECT n_lines, position, adviser FROM proposals WHERE "
                            "institution_id='solo'").fetchone()[:2] == (2, "FOR")
        assert e.db.execute("SELECT COUNT(*) FROM director_votes WHERE institution_id='solo'"
                            ).fetchone()[0] == 1
    ids = [engine.Engine(path, led).db.execute(
        "SELECT institution_id, proposal_id FROM proposals WHERE institution_id != 'delta' "
        "ORDER BY institution_id").fetchall() for path in (plain, labelled)]
    assert [tuple(r) for r in ids[0]] == [tuple(r) for r in ids[1]]   # drafts cite these ids
    # with no registry at all, even delta pools exactly as it always did
    e = engine.Engine(plain, led)
    assert e.db.execute("SELECT COUNT(*) FROM proposals WHERE institution_id='delta'"
                        ).fetchone()[0] == 1


def test_a_pooled_multi_adviser_answer_carries_a_caveat(duo):
    for env in (duo.voting_record("delta", query="board diversity"),
                duo.director_record("delta"), duo.director_votes("delta"),
                duo.proposals(institution="delta"), duo.reversals("delta"),
                duo.filers("delta")):
        text = " ".join(env["caveats"])
        assert "AAA" in text and "BBB" in text and "pool" in text, env["tool"]
    assert not any("pool separately" in c for c in duo.director_record("solo")["caveats"])


def test_the_adviser_filter_scopes_every_vote_tool(duo):
    aaa = duo.director_record("delta", adviser="AAA")
    bbb = duo.director_record("delta", adviser="BBB")
    assert aaa["args"]["adviser"] == "AAA"
    assert (aaa["result"]["overall"]["for"], aaa["result"]["overall"]["opposed"]) == (1, 0)
    assert (bbb["result"]["overall"]["for"], bbb["result"]["overall"]["opposed"]) == (0, 1)
    assert not any("pool separately" in c for c in aaa["caveats"])
    v = duo.voting_record("delta", query="board diversity", adviser="BBB")
    assert v["result"]["overall"]["against"] == 1 and v["result"]["overall"]["for"] == 0
    assert [p["adviser"] for p in duo.proposals(institution="delta",
                                               adviser="AAA")["result"]["shown"]] == ["AAA"]
    assert [d["adviser"] for d in duo.director_votes("delta", adviser="BBB")["result"]] == ["BBB"]
    panel = duo.director_panel("delta", "2024-01-01:2024-06-30,2024-07-01:2024-12-31",
                               adviser="AAA")
    assert panel["args"]["adviser"] == "AAA"
    assert duo.reversals("delta", adviser="AAA")["args"]["adviser"] == "AAA"


def test_an_unknown_adviser_is_refused_naming_the_valid_ones(duo):
    with pytest.raises(ValueError, match="AAA.*BBB"):
        duo.director_record("delta", adviser="CCC")
    with pytest.raises(ValueError, match="no adviser"):
        duo.director_record("other", adviser="AAA")
    with pytest.raises(ValueError, match="institution"):
        duo.proposals(adviser="AAA")


def test_filers_names_each_registrants_adviser_and_source(duo):
    by = {r["cik"].lstrip("0"): r for r in duo.filers("delta")["result"]["filers"]}
    assert by["11"]["adviser"] == "AAA" and by["11"]["adviser_source"] == "https://sec.example/11"
    assert by["22"]["adviser"] == "BBB"
    only = duo.filers("delta", adviser="BBB")["result"]["filers"]
    assert [r["cik"] for r in only] == ["22"]


def test_say_vs_do_refuses_a_multi_adviser_institution_without_adviser(duo):
    with pytest.raises(ValueError, match="adviser"):
        duo.say_vs_do("delta", "board diversity")


def test_say_vs_do_uses_only_the_matching_advisers_policy(duo):
    r = duo.say_vs_do("delta", "board diversity", adviser="BBB")["result"]
    assert [x["doc_label"] for x in r] == ["policy-bbb"]
    assert r[0]["did"]["against"] == 1 and r[0]["did"]["for"] == 0
    assert all("oppose" in s for s in r[0]["said"])


def test_policy_tools_return_the_documents_adviser(duo):
    vs = {v["doc_label"]: v["adviser"] for v in duo.policy_versions("delta")["result"]}
    assert vs == {"policy-aaa": "AAA", "policy-bbb": "BBB"}
    hits = duo.policy_search("diversity", institution="delta")["result"]
    assert {h["adviser"] for h in hits} == {"AAA", "BBB"}
    assert {h["adviser"] for h in duo.policy_search("diversity", institution="delta",
                                                    adviser="AAA")["result"]} == {"AAA"}


def test_policy_in_force_needs_a_document_or_adviser_for_a_multi_adviser_institution(duo):
    with pytest.raises(ValueError, match="adviser"):
        duo.policy_in_force("delta", "2025-01-01")
    one = duo.policy_in_force("delta", "2025-01-01", adviser="AAA")["result"]["versions"]
    assert [r["doc_label"] for r in one] == ["policy-aaa"]
    one = duo.policy_in_force("delta", "2025-01-01", doc_label="policy-bbb")["result"]["versions"]
    assert [r["adviser"] for r in one] == ["BBB"]


def test_peers_list_each_adviser_as_its_own_manager(duo):
    m = duo.director_peers(min_managers=2)["result"]["managers"]
    assert {"delta/AAA", "delta/BBB", "solo", "other"} <= set(m)
    assert "delta" not in m
    p = duo.peers(query="board diversity", min_managers=2)["result"]["managers"]
    assert {"delta/AAA", "delta/BBB"} <= set(p) and "delta" not in p


def test_fund_votes_for_one_advisers_item_shows_only_that_advisers_funds(duo):
    pid = duo.proposals(institution="delta", adviser="BBB")["result"]["shown"][0]["proposal_id"]
    lines = duo.fund_votes(pid)["result"]["lines"]
    assert [ln["registrant_cik"].lstrip("0") for ln in lines] == ["22"]


def test_args_roundtrip_through_call(duo, monkeypatch):
    env = duo.director_record("delta", adviser="AAA")
    monkeypatch.setattr(engine, "Engine", lambda: duo)
    assert engine.call("director_record", **env["args"])["result"] == env["result"]


def test_a_draft_stat_on_a_multi_adviser_institution_must_name_the_adviser(duo):
    unscoped = {"type": "stat", "tool": "director_record", "path": "overall.for",
                "args": {"institution": "delta"}, "equals": 1}
    ok, why = desk._check(duo, unscoped)
    assert not ok and "adviser" in why
    scoped = {**unscoped, "args": {"institution": "delta", "adviser": "AAA"}}
    assert desk._check(duo, scoped)[0]
    refused = {**scoped, "tool": "say_vs_do", "path": "0", "args": {"institution": "delta",
                                                                     "query": "diversity"}}
    ok, why = desk._check(duo, refused)
    assert not ok and "adviser" in why


def test_a_draft_vote_claim_must_name_the_adviser_of_the_item(duo):
    pid = duo.proposals(institution="delta", adviser="BBB")["result"]["shown"][0]["proposal_id"]
    claim = {"type": "proposal", "proposal_id": pid, "institution": "delta",
             "position": "AGAINST", "company": "EXXON", "meeting_date": "2024-05-20"}
    ok, why = desk._check(duo, claim)
    assert not ok and "adviser" in why
    assert desk._check(duo, {**claim, "adviser": "BBB"})[0]
    assert not desk._check(duo, {**claim, "adviser": "AAA"})[0]


def test_a_free_text_adviser_label_alone_never_splits_a_group(tmp_path):
    led = _duo_ledger(tmp_path)
    out = tmp_path / "lbl.db"
    labels = {"delta": {"npx_ciks": [{"cik": "11", "adviser": "Alpha Advisers LLC"},
                                     {"cik": "22", "adviser": "Beta Investment Mgmt"}]}}
    engine.build(led, out, institutions=labels)
    e = engine.Engine(out, led)
    assert not e.advisers_of("delta")["multi"]
    assert e.db.execute("SELECT COUNT(*) FROM proposals WHERE institution_id='delta'"
                        ).fetchone()[0] == 1


# ------------------------------------------------- series / dated / document keys

def _lines_ledger(tmp_path, iid, lines, docs=(), name="grp"):
    """One institution; `lines` = (cik, series, 'M/D/YYYY', how); `docs` = (label, text)."""
    led = tmp_path / f"{name}.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid.title()))
    for cik in sorted({ln[0] for ln in lines}):
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES"
                  " (?,?,?,'N-PX',?,'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{cik}", cik, iid, f"https://sec.example/{cik}"))
    for cik, series, date, how in lines:
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate, vote_series) VALUES"
                  " (?,'EXXON MOBIL','30231G102',?,'Report on Board Diversity','',"
                  "'SECURITY HOLDER',?,'FOR',100,0,?)", (f"ACC-{cik}", date, how, series))
    for n, (label, text, *more) in enumerate(docs):
        f = tmp_path / f"{name}{n}.html"
        f.write_text(text)
        wb, created = more or ["20240101000000", ""]
        c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
                  " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
                  " text_sha256, doc_created_at) VALUES (?,?,'https://x.example/p.html',"
                  "'2026-01-01',?,?,'text/html',1,?,?,?)",
                  (iid, label, f"s{name}{n}", str(f), wb, f"t{name}{n}", created))
    c.commit()
    c.close()
    return led


def _build(tmp_path, led, registry, name="e"):
    out = tmp_path / f"{name}-engine.db"
    engine.build(led, out, institutions=registry)
    return engine.Engine(out, led)


def _advs(e, iid="g"):
    return [(r["adviser"], r["position"]) for r in e.db.execute(
        "SELECT adviser, position FROM proposals WHERE institution_id=? ORDER BY adviser",
        (iid,))]


def test_a_series_override_splits_a_registrants_lines(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S000001", "05/20/2024", "FOR"),
                                        ("71", "S000002", "05/20/2024", "AGAINST")])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "P", "series_adviser": {
        "S000002": {"key": "Q"}}}]}}
    e = _build(tmp_path, led, reg)
    assert _advs(e) == [("P", "FOR"), ("Q", "AGAINST")]
    assert e.advisers_of("g")["multi"]
    f = e.filers("g")["result"]["filers"][0]
    assert f["adviser"] == "P" and f["series_overrides"] == 1 and set(f["advisers"]) == {"P", "Q"}
    assert [r["cik"] for r in e.filers("g", adviser="Q")["result"]["filers"]] == ["71"]
    pid = e.proposals(institution="g", adviser="Q")["result"]["shown"][0]["proposal_id"]
    assert [ln["fund_series"] for ln in e.fund_votes(pid)["result"]["lines"]] == ["S000002"]


def test_dated_history_switches_on_the_boundary_days_inclusive(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "12/31/2025", "FOR"),
                                        ("71", "S1", "1/1/2026", "AGAINST")])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key_history": [
        {"key": "A", "until": "2025-12-31"}, {"key": "B", "from": "2026-01-01"}]}]}}
    e = _build(tmp_path, led, reg)
    got = {r["meeting_date"]: r["adviser"] for r in e.db.execute(
        "SELECT meeting_date, adviser FROM proposals")}
    assert got == {"2025-12-31": "A", "2026-01-01": "B"}


def test_resolution_order_and_undated_rules():
    entry = {"adviser_key": "D", "adviser_key_history": [{"key": "H", "until": "2024-12-31"}],
             "series_adviser": {"s9": [{"key": "S", "from": "2024-06-01", "until": "2024-06-30"}],
                                "S8": {"key": "U"}}}
    r = engine.normalize_rules(entry)
    f = engine.resolve_key
    assert f(r, "S9", "2024-06-15") == "S"        # series rule first (case-insensitive id)
    assert f(r, "S9", "2024-07-01") == "H"        # series window over: registrant history
    assert f(r, "S9", "2025-01-01") == "D"        # then the default
    assert f(r, "S9", "garbage") == "UNDATED"     # a dated series rule cannot place it
    assert f(r, "S9", None) == "UNDATED"
    assert f(r, "S8", "garbage") == "U"           # an unbounded series rule applies undated
    assert f(r, "", "2024-01-01") == "H"
    assert f(engine.normalize_rules({"cik": "1"}), "S", "2024-01-01") is None


DOC_REG = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "D1"}],
                 "commitments": [{"label": "pol-x", "adviser_key": "D2"}]}}


def test_a_document_key_that_no_registrant_has_makes_a_multi_group_institution(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR")],
                        docs=[("pol-x", TEXT_B)])
    e = _build(tmp_path, led, DOC_REG)
    info = e.advisers_of("g")
    assert info["multi"] and info["known"] == ["D1", "D2"]
    assert _advs(e) == [("D1", "FOR")]
    with pytest.raises(ValueError, match="adviser"):
        e.say_vs_do("g", "board diversity")
    with pytest.raises(ValueError, match="no archived policy for the adviser that cast these votes"):
        e.say_vs_do("g", "board diversity", adviser="D1")
    with pytest.raises(ValueError, match="no archived policy for the adviser that cast these votes"):
        e.policy_in_force("g", "2025-01-01", adviser="D1")
    ok = e.say_vs_do("g", "board diversity", adviser="D2")["result"]
    assert [x["doc_label"] for x in ok] == ["pol-x"]


def test_two_documents_with_different_keys_pair_only_with_their_own(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR")],
                        docs=[("pol-a", TEXT_A), ("pol-b", TEXT_B)])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "D1"}],
                 "commitments": [{"label": "pol-a", "adviser_key": "D1"},
                                 {"label": "pol-b", "adviser_key": "D2"}]}}
    e = _build(tmp_path, led, reg)
    assert e.advisers_of("g")["multi"]
    r = e.say_vs_do("g", "board diversity", adviser="D1")["result"]
    assert [x["doc_label"] for x in r] == ["pol-a"] and r[0]["did"]["for"] == 1
    assert [x["doc_label"] for x in
            e.policy_in_force("g", "2025-01-01", adviser="D1")["result"]["versions"]] == ["pol-a"]


def test_external_is_a_group_but_never_pairs_with_a_policy(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("71", "S9", "05/20/2024", "AGAINST")],
                        docs=[("pol-a", TEXT_A)])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "A", "series_adviser": {
        "S9": {"key": "EXTERNAL"}}}], "commitments": [{"label": "pol-a", "adviser_key": "A"}]}}
    e = _build(tmp_path, led, reg)
    assert _advs(e) == [("A", "FOR"), ("EXTERNAL", "AGAINST")]
    assert e.voting_record("g", query="board diversity", adviser="EXTERNAL"
                           )["result"]["overall"]["against"] == 1
    assert any("EXTERNAL" in c and "never" in c for c in e.voting_record("g")["caveats"])
    for call in (lambda: e.say_vs_do("g", "board diversity", adviser="EXTERNAL"),
                 lambda: e.policy_in_force("g", "2025-01-01", adviser="EXTERNAL")):
        with pytest.raises(ValueError, match="EXTERNAL"):
            call()
    assert e.say_vs_do("g", "board diversity", adviser="A")["result"]


def test_voting_scope_notes_ride_on_every_vote_and_policy_tool(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("72", "S2", "05/20/2024", "AGAINST")],
                        docs=[("pol-a", TEXT_A), ("pol-b", TEXT_B)])
    note = "NOTE: the DWS letter does not govern these US trusts."
    reg = {"g": {"voting_scope_notes": [note],
                 "npx_ciks": [{"cik": "71", "adviser_key": "A"}, {"cik": "72", "adviser_key": "B"}],
                 "commitments": [{"label": "pol-a", "adviser_key": "A"},
                                 {"label": "pol-b", "adviser_key": "B"}]}}
    e = _build(tmp_path, led, reg)
    envs = [e.voting_record("g"), e.voting_record("g", adviser="A"), e.proposals(institution="g"),
            e.reversals("g"), e.filers("g"), e.policy_versions("g"),
            e.policy_search("diversity", institution="g"), e.policy_in_force("g", "2025-01-01",
                                                                           adviser="A"),
            e.say_vs_do("g", "board diversity", adviser="A")]
    for env in envs:
        assert note in env["caveats"], env["tool"]
    pid = e.proposals(institution="g", adviser="A")["result"]["shown"][0]["proposal_id"]
    assert note in e.fund_votes(pid)["caveats"]


def test_an_institution_without_keys_builds_identically_with_or_without_notes(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("72", "S2", "05/20/2024", "AGAINST")],
                        docs=[("pol-a", TEXT_A)])
    bare = _build(tmp_path, led, {}, "bare")
    cfg = _build(tmp_path, led, {"g": {"npx_ciks": [{"cik": "71"}, {"cik": "72"}],
                                       "commitments": [{"label": "pol-a"}]}}, "cfg")
    for q in ("SELECT * FROM proposals ORDER BY proposal_id",
              "SELECT * FROM director_votes ORDER BY director_id",
              "SELECT commitment_id, adviser FROM policy_versions"):
        assert [tuple(r) for r in bare.db.execute(q)] == [tuple(r) for r in cfg.db.execute(q)]
    assert not cfg.advisers_of("g")["multi"]
    assert not any("POOLED" in c for c in cfg.voting_record("g")["caveats"])


def test_split_off_items_are_numbered_after_every_pooled_item(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("71", "S2", "05/20/2024", "AGAINST"),
                                        ("71", "S1", "05/21/2024", "FOR")])
    plain = _build(tmp_path, led, {}, "plain")
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "P",
                               "series_adviser": {"S2": {"key": "Q"}}}]}}
    split = _build(tmp_path, led, reg, "split")
    old = {r["meeting_date"]: r["proposal_id"] for r in plain.db.execute(
        "SELECT meeting_date, proposal_id FROM proposals")}
    new = {(r["meeting_date"], r["adviser"]): r["proposal_id"] for r in split.db.execute(
        "SELECT meeting_date, adviser, proposal_id FROM proposals")}
    assert new[("2024-05-20", "P")] == old["2024-05-20"]
    assert new[("2024-05-21", "P")] == old["2024-05-21"]
    assert new[("2024-05-20", "Q")] > max(old.values())


# ------------------------------------------- review batch 2026-11-17 (items 1-8)

SPLIT_HIST = [{"key": "OLD", "until": "2026-01-11"}, {"key": "NEW", "from": "2026-01-12"}]


def _split_registry(doc_hist=SPLIT_HIST):
    return {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "NEW",
                                "adviser_key_history": SPLIT_HIST}],
                  "commitments": [{"label": "pol", "adviser_key": "NEW",
                                   "adviser_key_history": doc_hist}]}}


def _split_engine(tmp_path, doc_hist=SPLIT_HIST):
    led = _lines_ledger(
        tmp_path, "g", [("71", "S1", "5/20/2025", "FOR"), ("71", "S1", "3/10/2026", "AGAINST")],
        docs=[("pol", TEXT_A, "20220117000000", ""),
              ("pol", TEXT_B, "20260716000000", "2026-01-06T09:00:00")])
    return _build(tmp_path, led, _split_registry(doc_hist))


def test_a_documents_key_comes_from_its_history_on_the_capture_date(tmp_path):
    """Vanguard: the 2022 capture of the VPM-keyed document is the unified pre-split text."""
    e = _split_engine(tmp_path)
    rows = e.policy_versions("g")["result"]
    assert [(r["captured"], r["adviser"]) for r in rows] == [
        ("2022-01-17", "OLD"), ("2026-07-16", "NEW")]
    # authored 2026-01-06 is BEFORE the split, yet the text is the NEW adviser's:
    # the key is dated by the day the text was demonstrably public, and says so
    assert all(r["adviser_key_date"] == r["captured"] for r in rows)
    assert any("captured" in c and "key" in c.lower()
               for c in e.policy_versions("g")["caveats"])
    old = e.say_vs_do("g", "board diversity", adviser="OLD")["result"]
    assert [x["in_force_from"] for x in old] == ["2022-01-17"]
    assert old[0]["did"]["for"] == 1                       # the 2025 vote, not the 2026 one
    new = e.say_vs_do("g", "board diversity", adviser="NEW")
    assert [x["in_force_from"] for x in new["result"]] == ["2026-07-16"]
    assert new["result"][0]["did"]["proposals"] == 0


def test_a_policy_authored_long_before_capture_and_uncovered_votes_are_said(tmp_path):
    e = _split_engine(tmp_path)
    cav = e.say_vs_do("g", "board diversity", adviser="NEW")["caveats"]
    assert any("authored 2026-01-06" in c and "first captured 2026-07-16" in c
               and "not covered" in c for c in cav)
    assert any("1 proposal" in c and "before the first archived text" in c for c in cav)
    inf = e.policy_in_force("g", "2026-08-01", adviser="NEW")
    assert [v["captured"] for v in inf["result"]["versions"]] == ["2026-07-16"]
    assert any("authored 2026-01-06" in c and "not covered" in c for c in inf["caveats"])
    # within 30 days of capture: nothing to say
    near = e.policy_in_force("g", "2023-01-01", adviser="OLD")
    assert not any("authored" in c for c in near["caveats"])


def test_a_document_without_history_still_takes_its_default_key(tmp_path):
    e = _split_engine(tmp_path, doc_hist=None)
    assert {r["adviser"] for r in e.policy_versions("g")["result"]} == {"NEW"}


def test_policy_in_force_with_nothing_in_force_is_citable(tmp_path):
    e = _split_engine(tmp_path)
    r = e.policy_in_force("g", "2025-01-01", adviser="NEW")["result"]
    assert r["versions"] == [] and r["none_in_force"] is True and r["reason"]
    full = e.policy_in_force("g", "2025-01-01", adviser="OLD")["result"]
    assert full["none_in_force"] is False and len(full["versions"]) == 1
    stat = {"type": "stat", "tool": "policy_in_force", "path": "none_in_force", "equals": True,
            "args": {"institution": "g", "date": "2025-01-01", "adviser": "NEW"}}
    assert desk._check(e, stat)[0]


# -- item 3: unlabelled lines are a group of their own

def test_lines_with_no_key_are_never_pooled_with_a_keyed_adviser(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("72", "S2", "05/20/2024", "AGAINST")],
                        docs=[("pol-a", TEXT_A)])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "A"}],       # 72 is not in config
                 "commitments": [{"label": "pol-a", "adviser_key": "A"}]}}
    e = _build(tmp_path, led, reg)
    assert _advs(e) == [("A", "FOR"), ("unlabelled", "AGAINST")]
    info = e.advisers_of("g")
    assert info["multi"] and info["known"] == ["A"] and info["unlabelled"] == 1
    a = e.say_vs_do("g", "board diversity", adviser="A")["result"]
    assert a[0]["did"]["for"] == 1 and a[0]["did"]["against"] == 0
    with pytest.raises(ValueError, match="no archived policy"):
        e.say_vs_do("g", "board diversity", adviser="unlabelled")


def test_a_keyed_document_alone_makes_unkeyed_votes_a_separate_group(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR")],
                        docs=[("pol-a", TEXT_A)])
    reg = {"g": {"npx_ciks": [{"cik": "71"}],
                 "commitments": [{"label": "pol-a", "adviser_key": "A"}]}}
    e = _build(tmp_path, led, reg)
    assert _advs(e) == [("unlabelled", "FOR")]
    assert e.advisers_of("g")["multi"]
    with pytest.raises(ValueError, match="adviser"):
        e.say_vs_do("g", "board diversity")
    assert e.say_vs_do("g", "board diversity", adviser="A")["result"][0]["did"]["proposals"] == 0


# -- item 4: rule bounds validated; undated lines are UNDATED

@pytest.mark.parametrize("hist,series,needle", [
    ([{"key": "A", "from": "2025-1-1"}], {}, "CIK 71"),
    ([{"key": "A", "from": "soon"}], {}, "ISO"),
    ([{"key": "A", "from": "2025-06-01", "until": "2025-01-01"}], {}, "before"),
    ([{"key": "A", "until": "2025-06-30"}, {"key": "B", "from": "2025-06-30"}], {}, "overlap"),
    ([], {"S000009": [{"key": "A", "until": "2025-06-30"},
                      {"key": "B", "from": "2025-01-01"}]}, "S000009"),
    ([{"key": "A"}, {"key": "B", "from": "2025-01-01"}], {}, "overlap"),
])
def test_bad_rule_bounds_stop_the_build_naming_the_registrant(tmp_path, hist, series, needle):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR")])
    entry = {"cik": "71", "adviser_key": "D", "adviser_key_history": hist,
             "series_adviser": series}
    with pytest.raises(ValueError, match="g") as ei:
        _build(tmp_path, led, {"g": {"npx_ciks": [entry]}})
    assert "71" in str(ei.value) and needle in str(ei.value)


def test_bad_document_rule_bounds_stop_the_build_naming_the_document(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR")])
    reg = {"g": {"npx_ciks": [{"cik": "71", "adviser_key": "A"}],
                 "commitments": [{"label": "pol-a", "adviser_key": "A",
                                  "adviser_key_history": [{"key": "A", "from": "2025/01/01"}]}]}}
    with pytest.raises(ValueError, match="pol-a"):
        _build(tmp_path, led, reg)


def test_a_line_with_no_parsable_date_on_a_dated_rule_is_undated_and_never_pairs(tmp_path):
    led = _lines_ledger(tmp_path, "g", [("71", "S1", "05/20/2024", "FOR"),
                                        ("71", "S1", "TBD", "AGAINST"),
                                        ("72", "S2", "TBD", "FOR")],
                        docs=[("pol-a", TEXT_A)])
    reg = {"g": {"npx_ciks": [
        {"cik": "71", "adviser_key": "A", "adviser_key_history": [
            {"key": "A", "until": "2024-12-31"}, {"key": "B", "from": "2025-01-01"}]},
        {"cik": "72", "adviser_key": "A"}],                     # no dated rule: default holds
        "commitments": [{"label": "pol-a", "adviser_key": "A"}]}}
    e = _build(tmp_path, led, reg)
    got = {(r["adviser"], r["position"]) for r in e.db.execute(
        "SELECT adviser, position FROM proposals")}
    assert got == {("A", "FOR"), ("UNDATED", "AGAINST")}      # 72's undated line stays A
    with pytest.raises(ValueError, match="UNDATED"):
        e.say_vs_do("g", "board diversity", adviser="UNDATED")


def test_resolve_key_undated_rule_table():
    r = engine.normalize_rules({"adviser_key": "D", "adviser_key_history": [
        {"key": "H", "until": "2024-12-31"}],
        "series_adviser": {"S9": [{"key": "S", "from": "2024-06-01", "until": "2024-06-30"}],
                           "S8": {"key": "U"}}})
    f = engine.resolve_key
    assert f(r, "S9", "garbage") == engine.UNDATED
    assert f(r, "S1", None) == engine.UNDATED                # registrant history is dated
    assert f(r, "S8", "garbage") == "U"                      # an unbounded rule needs no date
    assert f(engine.normalize_rules({"adviser_key": "D"}), "S", "garbage") == "D"
    assert f(r, "S1", "2024-13-45") == engine.UNDATED        # shaped like a date, not one


# -- item 5: director_peers count, ISO country codes

def test_peers_excluded_count_is_only_items_peers_would_have_used(tmp_path):
    led = tmp_path / "l.db"
    c = ledger.connect(led)
    for iid in ("a", "b"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{iid}", "1", iid, f"https://sec.example/{iid}"))
        for company, cusip, isin in (("ACME", "000000001", "US0000000010"),
                                     ("NOISIN", "000000002", None),
                                     ("NOCUSIP", "", None)):
            c.execute("INSERT INTO votes (accession, issuer_name, cusip, isin, meeting_date,"
                      " vote_description, category_type, vote_source, how_voted,"
                      " management_recommendation, shares_voted, is_duplicate) VALUES"
                      " (?,?,?,?,'05/20/2024','Elect Ann','DIRECTOR ELECTIONS','ISSUER',"
                      "'FOR','FOR',100,0)", (f"ACC-{iid}", company, cusip, isin))
    c.commit()
    c.close()
    e = _build(tmp_path, led, {})
    cav = e.director_peers(country="US", min_managers=2)["caveats"]
    assert any(x.startswith("2 nominee items were excluded") for x in cav), cav
    # director_record has no meeting-key restriction: a's NOISIN and NOCUSIP both count
    assert any(x.startswith("2 nominee items were excluded")
               for x in e.director_record("a", country="US")["caveats"])


def test_isin_country_accepts_only_real_iso_codes():
    assert len(engine.ISO_3166_ALPHA2) == 249
    for ok in ("US", "GB", "KY", "JP", "DE"):
        assert engine.isin_country([ok + "0000000010"]) == ok
    for notcountry in ("XS", "EU", "ZZ", "AN", "QQ", "CS"):
        assert engine.isin_country([notcountry + "0000000010"]) is None, notcountry


# -- items 6, 7: desk

def test_an_unclosed_curly_quote_is_a_problem_like_an_odd_straight_quote(eng):
    quotes, rest, ok = desk._quotations("He wrote “a long sentence that never closes here.")
    assert ok is False
    assert desk._quotations("He wrote “short” and “another one that is long enough to count.”"
                            )[2] is True
    body = ("Alpha's 2023 policy said “We expect boards to disclose climate transition plans "
            "aligned with a 1.5 degree pathway. [c1]\n\n"
            "That sentence is not in the version archived in 2025. [c2]\n\n"
            "Alpha supported 0 such proposals in 2024. [c3]\n\n"
            "At Exxon Mobil on 2024-05-20 it voted against. [c4]")
    assert any("unclosed curly" in p for p in _problems(eng, body))


def test_a_claim_cannot_point_at_a_list_row_by_position(eng):
    ballot = eng.ballot(eng.proposals(institution="alpha", year=2024
                                      )["result"]["shown"][0]["proposal_id"])["result"]
    pid = ballot[0]["proposal_id"]
    stat = {"type": "stat", "tool": "ballot", "args": {"proposal_id": pid},
            "equals": ballot[0]["position"]}
    with pytest.raises(KeyError, match=r"Select the row by key"):
        desk._check(eng, {**stat, "path": "0.position"})
    row = next(r for r in ballot if r["institution"] == "alpha")
    ok, detail = desk._check(eng, {**stat, "path": "[institution=alpha].position",
                                   "equals": row["position"]})
    assert ok, detail
    # a key that matches no row, or several, is refused rather than guessed
    with pytest.raises(KeyError, match="no row"):
        desk._check(eng, {**stat, "path": "[institution=nobody].position"})
    # and verify() reports a positional claim as a failed claim, not a crash
    d = _draft(eng)
    d["claims"][2]["check"] = {**stat, "path": "0.position"}
    assert any(p.startswith("claim c3 failed") and "Select the row by key" in p
               for p in desk.verify(d, eng)["problems"])


def test_dig_selects_list_rows_by_key_and_still_walks_dicts_and_scalar_lists():
    obj = {"rows": [{"institution": "a", "adviser": "X", "v": 1},
                    {"institution": "a", "adviser": "Y", "v": 2},
                    {"institution": "b", "adviser": "X", "v": 3}],
           "by_year": {2024: {"for": 5}}, "words": ["p", "q"], "dotted": [{"k": "1.5", "v": 9}]}
    assert desk._dig(obj, "rows.[institution=a,adviser=Y].v") == 2
    assert desk._dig(obj, "rows[institution=b].v") == 3
    assert desk._dig(obj, "by_year.2024.for") == 5
    assert desk._dig(obj, "words.1") == "q"
    assert desk._dig(obj, "dotted.[k=1.5].v") == 9
    with pytest.raises(KeyError, match="2 rows"):
        desk._dig(obj, "rows.[institution=a].v")
    with pytest.raises(KeyError, match="key"):
        desk._dig(obj, "rows.0.v")


# ------------------------------------------------- coding shift: withhold vs abstain

@pytest.fixture()
def shifted(tmp_path):
    """One manager whose withheld votes are filed as WITHHOLD in 2024 and as
    ABSTAIN in 2025 (a new filing agent), over the same 40 companies; a second
    manager that never changes."""
    led = tmp_path / "ledger.db"
    c = ledger.connect(led)
    for iid in ("alpha", "beta"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)",
                  (iid, iid.title() + " Asset Management"))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{iid}", "1", iid, f"https://sec.example/{iid}"))

    def director(iid, how, n, date, person=None):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, category_type, vote_source, how_voted,"
                  " management_recommendation, shares_voted, is_duplicate) VALUES"
                  " (?,?,?,?,?,'DIRECTOR ELECTIONS','ISSUER',?,'FOR',100,0)",
                  (f"ACC-{iid}", f"CO {n}", f"{n:09d}", date,
                   f"Elect Director Person {person or n}", how))

    for n in range(40):
        for year, how in ((2024, "WITHHOLD"), (2025, "ABSTAIN")):
            director("alpha", how, n, f"05/20/{year}")
            director("alpha", "FOR", n, f"05/20/{year}", person=n + 100)
            director("beta", "WITHHOLD", n, f"05/20/{year}")
            director("beta", "FOR", n, f"05/20/{year}", person=n + 100)
            for how in ("AGAINST" if year == 2024 else "ABSTAIN",):
                c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                          " vote_description, category_type, vote_source, how_voted,"
                          " management_recommendation, shares_voted, is_duplicate) VALUES"
                          " (?,?,?,?,'Advisory vote on executive compensation',"
                          "'SECTION 14A SAY-ON-PAY VOTES','ISSUER',?,'FOR',100,0)",
                          ("ACC-alpha", f"CO {n}", f"{n:09d}", f"05/20/{year}", how))
    c.commit()
    c.close()
    out = tmp_path / "engine.db"
    engine.build(led, out)
    return engine.Engine(out, led)


def _shift(env):
    return [c for c in env["caveats"] if c.startswith(engine.CODING_SHIFT)]


def test_director_record_reports_non_support_beside_opposed(shifted):
    r = shifted.director_record("alpha")["result"]["by_year"]
    assert r[2024]["opposed"] == 40 and r[2024]["abstain"] == 0
    assert r[2025]["opposed"] == 0 and r[2025]["abstain"] == 40
    for y in (2024, 2025):
        assert r[y]["not_supported"] == 40 and r[y]["non_support_rate"] == 0.5
    assert r[2024]["opposition_rate"] == 0.5 and r[2025]["opposition_rate"] == 0.0


def test_a_change_of_coding_across_years_is_flagged_with_the_counts(shifted):
    env = shifted.director_record("alpha")
    (msg,) = _shift(env)
    assert "40" in msg and "not_supported" in msg and "NOT comparable" in msg
    assert not _shift(shifted.director_record("beta"))
    assert not _shift(shifted.director_record("alpha", since="2025-01-01"))   # one period


def test_few_abstentions_do_not_trip_the_coding_guard(eng):
    assert not _shift(eng.director_record("alpha"))


def test_the_abstain_caveat_names_the_us_plurality_point(shifted):
    text = " ".join(shifted.director_record("beta")["caveats"])
    assert "only way to oppose" in text and "plurality" in text and "withhold" in text.lower()


def test_director_panel_reports_non_support_and_flags_the_shift(shifted):
    env = shifted.director_panel("alpha", windows="2024-01-01:2024-06-30,2025-01-01:2025-06-30")
    r = env["result"]
    w24, w25 = r["windows"]
    assert w24["opposed"] == 40 and w25["opposed"] == 0
    assert w24["not_supported"] == w25["not_supported"] == 40
    assert w24["non_support_rate"] == w25["non_support_rate"] == 0.5
    assert w24["companies_with_non_support"] == w25["companies_with_non_support"] == 40
    assert r["non_support_in_first_and_last"] == 40
    assert _shift(env)


def test_director_peers_reports_non_support_and_scopes_to_one_group(shifted):
    r = shifted.director_peers(year=2025, min_managers=2)["result"]["managers"]
    assert r["alpha"]["opposed"] == 0 and r["alpha"]["not_supported"] == 40
    assert r["alpha"]["non_support_rate"] == 0.5 and r["beta"]["non_support_rate"] == 0.5
    one = shifted.director_peers(year=2025, min_managers=2, institution="alpha")["result"]
    assert list(one["managers"]) == ["alpha"] and one["shared_meetings"] == 40


def test_director_peers_adviser_is_strict(shifted):
    for kw in ({"adviser": "BIS"}, {"institution": "alpha", "adviser": "BIS"}):
        with pytest.raises(ValueError):
            shifted.director_peers(**kw)
    with pytest.raises(ValueError):
        shifted.peers(adviser="BIS")


def test_peers_scopes_to_one_institution(eng):
    one = eng.peers(query="climate transition", min_managers=2, institution="gamma")["result"]
    assert list(one["managers"]) == ["gamma"]


def test_the_desk_requires_non_support_beside_opposed_when_coding_shifted(shifted):
    def claim(cid, path, eq):
        return {"id": cid, "text": "x", "check": {
            "type": "stat", "tool": "director_record", "args": {"institution": "alpha"},
            "path": path, "equals": eq}}
    base = {"slug": "t", "headline": "Alpha 2024 opposed 40 nominees", "headline_claims": ["c1"],
            "standfirst": "The record.",
            "claims": [claim("c1", "by_year.2024.opposed", 40),
                       claim("c2", "by_year.2024.not_supported", 40)],
            "limitations": ["One filer.", "Two years."]}
    bad = desk.verify({**base, "body": "Alpha opposed 40 nominees in 2024. [c1]\n\n"
                       "Alpha did not support 40 nominees in 2024. [c2]"}, shifted)
    assert any("c1" in p and "not_supported" in p for p in bad["problems"])
    good = desk.verify({**base, "body": "Alpha opposed 40 nominees in 2024, and did not "
                        "support 40. [c1] [c2]"}, shifted)
    assert not any("not_supported" in p for p in good["problems"])


def test_coding_shift_flags_abstain_that_disappears_even_when_its_share_is_small():
    # JPMorgan: abstain 60 -> 40 -> 0 out of ~1,000 not_supported. The share moves
    # only 6 points, but a category that vanishes entirely is a recording change.
    parts = {"2023": (60, 1000), "2024": (40, 900), "2025": (0, 800)}
    assert engine.Engine._coding_shift(parts)[0].startswith(engine.CODING_SHIFT)


def test_coding_shift_stays_quiet_on_small_steady_abstain():
    assert engine.Engine._coding_shift({"2023": (60, 1000), "2024": (45, 900)}) == []
    # too few abstain items anywhere to read a recording change into
    assert engine.Engine._coding_shift({"2023": (5, 1000), "2024": (0, 900)}) == []


def test_policy_counts_gives_a_citable_count_per_document(eng):
    rows = eng.policy_counts("alpha")["result"]
    vs = eng.policy_versions("alpha")["result"]
    by = {r["doc_label"]: r for r in rows}
    assert set(by) == {v["doc_label"] for v in vs}
    for label, r in by.items():
        mine = [v for v in vs if v["doc_label"] == label]
        assert r["versions"] == len(mine)
        assert r["readable_versions"] == sum(v["readable"] for v in mine)
        assert r["first_captured"] == min(v["captured"] for v in mine)
        assert r["last_captured"] == max(v["captured"] for v in mine)
    assert "policy_counts" in engine.TOOLS


def test_policy_counts_respects_adviser(duo):
    rows = duo.policy_counts("delta", adviser="BBB")["result"]
    assert [r["doc_label"] for r in rows] == ["policy-bbb"]


# ---------------------------------------------------------------- say-on-pay

def test_pay_votes_count_per_item_not_per_fund_and_skip_duplicates(eng):
    r = eng.pay_record("alpha")["result"]["by_year"]
    assert r[2024]["items"] == 1 and r[2024]["opposed"] == 1 and r[2024]["for"] == 0
    assert r[2024]["opposition_rate"] == 1.0
    assert r[2025]["for"] == 1 and r[2025]["opposed"] == 0


def test_pay_frequency_items_are_reported_apart_from_for_against(eng):
    out = eng.pay_record("alpha")
    assert out["result"]["overall"]["items"] == 2            # frequency not among them
    assert out["result"]["frequency_items"] == 1
    assert any("frequency" in c.lower() for c in out["caveats"])


def test_pay_votes_stay_out_of_director_and_proposal_indexes(eng):
    assert eng.director_record("alpha")["result"]["by_year"][2024]["nominees"] == 2
    n = eng.db.execute("SELECT COUNT(*) FROM proposals WHERE description LIKE '%compensation%'")
    assert n.fetchone()[0] == 0


def test_pay_record_is_registered_as_a_vote_tool():
    assert "pay_record" in engine.TOOLS and "pay_record" in engine.VOTE_TOOLS


def test_pay_record_filters_by_year_and_replays_from_its_args(eng):
    env = eng.pay_record("alpha", year=2025)
    assert list(env["result"]["by_year"]) == [2025]
    assert eng.pay_record(**env["args"])["result"] == env["result"]


def test_pay_votes_scope_by_adviser(duo):
    assert [(r["adviser"], r["position"]) for r in duo.db.execute(
        "SELECT adviser, position FROM pay_votes WHERE institution_id='delta' "
        "ORDER BY adviser")] == [("AAA", "FOR"), ("BBB", "AGAINST")]
    assert duo.pay_record("delta", adviser="AAA")["result"]["overall"]["opposed"] == 0
    assert duo.pay_record("delta", adviser="BBB")["result"]["overall"]["opposed"] == 1
    assert any("POOLED ADVISERS" in c for c in duo.pay_record("delta")["caveats"])
    with pytest.raises(ValueError, match="no adviser"):
        duo.pay_record("delta", adviser="CCC")


def test_pay_record_warns_when_abstain_replaces_against(shifted):
    env = shifted.pay_record("alpha")
    assert _shift(env), "abstain recording changed between years: must be flagged"
    r = env["result"]["by_year"]
    assert r[2024]["opposed"] == 40 and r[2025]["abstain"] == 40


@pytest.mark.parametrize("desc", [
    "Advisory vote on holding the say-on-pay vote for executive officers every year",
    "Whether shareholders would prefer an advisory vote every one, two or three years",
    "Advisory vote every two (2) years",
    "Approve the frequency of future advisory votes",
])
def test_pay_frequency_items_are_recognised_in_every_wording(desc):
    """Review of e19ce3a: Constellium put its frequency question as three yes/no
    items; 'every year' was counted as a pay approval."""
    assert engine._FREQ_DESC.search(desc)


def test_an_ordinary_say_on_pay_item_is_not_a_frequency_item():
    assert not engine._FREQ_DESC.search(
        "Advisory vote to approve the compensation of named executive officers")
