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
    got = eng.policy_in_force("alpha", "2024-05-20")["result"]
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
    for ok in ("a majority vote standard.", "majority voting.", "a majority-vote rule.",
               "a majority of votes cast.", "a supermajority."):
        assert not any("vague" in p for p in _problems(eng, base + tail.format(ok))), ok
    for bad in ("the majority of proposals.", "a majority of managers."):
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
