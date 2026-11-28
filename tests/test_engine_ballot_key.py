"""Ballot keys: the same proposal worded or dated slightly differently by two managers
meets under one key; two different proposals never do (precision beats recall)."""

from glasshouse import engine, ledger

LONG = ("Shareholder Proposal Requesting Independent Board Chair Separate From Chief "
        "Executive Officer Role Effective Immediately Policy")


def _build(tmp_path, votes):
    """votes: (institution, description, meeting date mm/dd/yyyy, company, cusip)."""
    led = tmp_path / "l.db"
    c = ledger.connect(led)
    for iid in sorted({v[0] for v in votes}):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"A-{iid}", "1", iid, f"https://sec.example/{iid}"))
    for iid, desc, date, issuer, cusip in votes:
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, is_duplicate) VALUES (?,?,?,?,?,'SECURITY HOLDER','FOR','AGAINST',"
                  "10,0)", (f"A-{iid}", issuer, cusip, date, desc))
    c.commit()
    c.close()
    out = tmp_path / "e.db"
    engine.build(led, out)
    e = engine.Engine(out, led)
    return {(r["institution_id"], r["description"], r["meeting_date"]): r["ballot_key"]
            for r in e.db.execute("SELECT * FROM proposals")}


def test_a_one_word_wording_variant_and_a_next_day_date_share_a_key(tmp_path):
    keys = _build(tmp_path, [
        ("a", LONG, "05/20/2024", "ACME", "000111222"),
        ("b", LONG + " Annually", "05/21/2024", "ACME", "000111222")])
    assert len(set(keys.values())) == 1


def test_two_different_proposals_at_one_meeting_stay_apart(tmp_path):
    other = LONG.replace("Independent Board Chair Separate From Chief Executive Officer Role",
                         "Independent Lead Director Separate From Chief Executive Officer Role")
    keys = _build(tmp_path, [
        ("a", LONG, "05/20/2024", "ACME", "000111222"),
        ("b", other, "05/20/2024", "ACME", "000111222")])
    assert len(set(keys.values())) == 2


def test_near_identical_wording_stays_apart_when_one_manager_voted_both(tmp_path):
    """One manager filing both items at one meeting proves they are two items."""
    keys = _build(tmp_path, [
        ("a", LONG, "05/20/2024", "ACME", "000111222"),
        ("a", LONG + " Annually", "05/20/2024", "ACME", "000111222"),
        ("b", LONG, "05/20/2024", "ACME", "000111222")])
    assert len({k for (i, d, _), k in keys.items() if i == "a"}) == 2


def test_other_company_or_far_date_or_short_titles_never_merge(tmp_path):
    keys = _build(tmp_path, [
        ("a", LONG, "05/20/2024", "ACME", "000111222"),
        ("b", LONG + " Annually", "05/20/2024", "OTHER", "999888777"),
        ("c", LONG + " Annually", "07/20/2024", "ACME", "000111222"),
        ("d", "Report on Lobbying Payments", "05/20/2024", "ACME", "000111222"),
        ("e", "Report on Lobbying Payments and Climate", "05/20/2024", "ACME", "000111222")])
    assert len(set(keys.values())) == 5
