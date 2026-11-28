"""Engine: two legacy items with identical text at one meeting stay two decisions
(proposal_number is part of the legacy group key); XML grouping is unchanged."""

from glasshouse import engine, ledger

DESC = "Instructions if Meeting is Held on Second Call"


def _build(tmp_path, xml_same_day=False):
    led = tmp_path / "l.db"
    c = ledger.connect(led)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('alpha','Alpha')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
              " retrieval_date, period_of_report, report_type) VALUES ('A','1','alpha','N-PX',"
              "'https://sec.example/a','2026-01-01','06/30/2023','FUND VOTING REPORT')")

    def vote(pn, how, fmt="issueno", date="04/26/2023", series="S1"):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, legacy_format, category_type, vote_series, proposal_number,"
                  " is_duplicate) VALUES ('A','ACME','123456789',?,?,'SECURITY HOLDER',?,'',"
                  "?,?,'',?,?,0)", (date, DESC, how, None if fmt else 10, fmt, series, pn))

    vote("4", "FOR")
    vote("33", "AGAINST")
    vote("33", "AGAINST", series="S2")
    vote(None, "FOR", fmt=None, date="05/01/2024")        # XML: NULL number, one group
    vote(None, "AGAINST", fmt=None, date="05/01/2024", series="S2")
    if xml_same_day:                                     # an XML line at the legacy meeting
        vote(None, "ABSTAIN", fmt=None, series="S3")
    c.commit()
    c.close()
    out = tmp_path / "e.db"
    engine.build(led, out)
    return engine.Engine(out, led), out


def test_distinct_legacy_items_are_separate_decisions_and_xml_is_unchanged(tmp_path):
    eng, _ = _build(tmp_path)
    rows = eng.db.execute("SELECT proposal_id, meeting_date, position, n_lines, weight_basis "
                          "FROM proposals ORDER BY proposal_id").fetchall()
    xml = [r for r in rows if r["weight_basis"] != "lines"]
    leg = [r for r in rows if r["weight_basis"] == "lines"]
    assert len(xml) == 1 and xml[0]["n_lines"] == 2 and xml[0]["position"] == "SPLIT"
    assert sorted((r["position"], r["n_lines"]) for r in leg) == [("AGAINST", 2), ("FOR", 1)]
    assert xml[0]["proposal_id"] not in {r["proposal_id"] for r in leg}


def test_fund_votes_for_a_legacy_item_returns_only_that_item(tmp_path):
    eng, _ = _build(tmp_path)
    for r in eng.db.execute("SELECT proposal_id, n_lines FROM proposals "
                            "WHERE weight_basis = 'lines'").fetchall():
        got = eng.fund_votes(r["proposal_id"])["result"]["lines"]
        assert len(got) == r["n_lines"]


def test_fund_votes_never_mixes_eras(tmp_path):
    eng, _ = _build(tmp_path, xml_same_day=True)
    for r in eng.db.execute("SELECT proposal_id, n_lines FROM proposals").fetchall():
        got = eng.fund_votes(r["proposal_id"])["result"]["lines"]
        assert len(got) == r["n_lines"], r["proposal_id"]
