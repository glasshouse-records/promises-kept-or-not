"""The evidence engine and the desk that checks drafts written from it."""

from __future__ import annotations

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
