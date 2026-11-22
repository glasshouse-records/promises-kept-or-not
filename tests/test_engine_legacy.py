"""Promoted 2022-23 legacy votes in the engine: deterministic ids, never merged with XML
lines, weight_basis recorded, and mixed-basis comparisons flagged."""

from __future__ import annotations

import pytest

from glasshouse import engine, ledger

POLICY = ("<html><body><p>We expect boards to disclose climate transition plans aligned "
          "with a 1.5 degree pathway. " + "Filler sentence number one is here. " * 8
          + "</p></body></html>")
DESC = "Report on Climate Transition Plan"


def _ledger(tmp_path, legacy: bool):
    led = tmp_path / ("l_legacy.db" if legacy else "l_xml.db")
    c = ledger.connect(led)
    for iid in ("alpha", "beta", "gamma"):
        c.execute("INSERT INTO institutions (id, display_name) VALUES (?,?)", (iid, iid.title()))
        c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
                  " retrieval_date, period_of_report, report_type) VALUES (?,?,?,'N-PX',?,"
                  "'2026-01-01','06/30/2024','FUND VOTING REPORT')",
                  (f"ACC-{iid}", "1", iid, f"https://sec.example/{iid}"))

    def vote(iid, how, date, cusip="30231G102", issuer="EXXON MOBIL", fmt=None, shares=100,
             desc=DESC):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date,"
                  " vote_description, vote_source, how_voted, management_recommendation,"
                  " shares_voted, legacy_format, category_type, is_duplicate)"
                  " VALUES (?,?,?,?,?,'SECURITY HOLDER',?,?,?,?,?,0)",
                  (f"ACC-{iid}", issuer, cusip, date, desc, how,
                   "FOR" if how == "AGAINST" else "AGAINST", shares, fmt,
                   "" if fmt else "SHAREHOLDER PROPOSAL"))

    for iid in ("alpha", "beta", "gamma"):          # XML era, three managers
        vote(iid, "FOR", "05/20/2024")
        vote(iid, "AGAINST", "05/20/2025", cusip="166764100", issuer="CHEVRON")
    vote("alpha", "FOR", "05/20/2025")
    if legacy:
        for iid in ("alpha", "beta", "gamma"):      # 2022-23 season, line-weighted
            vote(iid, "AGAINST", "05/20/2023", fmt="proxyedge", shares=None)
        # same company, meeting and wording as an XML group: must stay a separate group
        vote("alpha", "AGAINST", "05/20/2024", fmt="iss_text", shares=None)
    f = tmp_path / "p.html"
    f.write_text(POLICY)
    c.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, sha256,"
              " content_path, content_type, size_bytes, wayback_timestamp, text_sha256) VALUES"
              " ('alpha','policy','https://a.example/p',"
              "'2026-01-01','s0',?,'text/html',1,'20220101000000','t0')", (str(f),))
    c.commit()
    c.close()
    out = tmp_path / ("e_legacy.db" if legacy else "e_xml.db")
    engine.build(led, out)
    return engine.Engine(out, led)


@pytest.fixture()
def both(tmp_path):
    return _ledger(tmp_path, False), _ledger(tmp_path, True)


def test_xml_group_ids_do_not_change_when_legacy_rows_are_added(both):
    xml, mixed = both
    before = {r["proposal_id"]: (r["institution_id"], r["cusip"], r["meeting_date"])
              for r in xml.db.execute("SELECT * FROM proposals")}
    after = {r["proposal_id"]: (r["institution_id"], r["cusip"], r["meeting_date"], r["weight_basis"])
             for r in mixed.db.execute("SELECT * FROM proposals")}
    assert before
    for pid, key in before.items():
        assert after[pid][:3] == key and after[pid][3] == "shares"
    legacy_ids = [pid for pid, k in after.items() if k[3] == "lines"]
    assert legacy_ids and min(legacy_ids) > max(before)


def test_legacy_and_xml_lines_never_share_a_group(both):
    _, mixed = both
    rows = mixed.db.execute(
        "SELECT weight_basis, n_lines FROM proposals WHERE institution_id='alpha' "
        "AND meeting_date='2024-05-20'").fetchall()
    assert sorted((r["weight_basis"], r["n_lines"]) for r in rows) == [("lines", 1), ("shares", 1)]


def test_weight_basis_is_shares_for_xml_and_lines_for_legacy(both):
    _, mixed = both
    got = {(r["year"], r["weight_basis"]) for r in mixed.db.execute(
        "SELECT year, weight_basis FROM proposals")}
    assert (2023, "lines") in got and (2024, "shares") in got and (2023, "shares") not in got


def _caveat(env):
    return [c for c in env["caveats"] if "WEIGHT BASIS" in c]


def test_period_tools_flag_mixed_weight_bases(both):
    xml, mixed = both
    assert not _caveat(xml.voting_record("alpha", query="climate"))
    calls = {"voting_record": mixed.voting_record("alpha", query="climate"),
             "proposals": mixed.proposals("alpha", query="climate"),
             "peers": mixed.peers(query="climate", min_managers=2),
             "say_vs_do": mixed.say_vs_do("alpha", "climate transition"),
             "reversals": mixed.reversals("alpha", query="climate")}
    for name, env in calls.items():
        assert _caveat(env), name
    assert not _caveat(mixed.voting_record("alpha", query="climate", since="2024-06-01"))


def test_weight_basis_is_exposed_in_outputs(both):
    _, mixed = both
    shown = mixed.proposals("alpha", query="climate")["result"]["shown"]
    assert {p["weight_basis"] for p in shown} == {"lines", "shares"}


def test_director_and_pay_tools_say_2022_23_is_not_categorised(both):
    _, mixed = both
    calls = {"director_record": mixed.director_record("alpha"),
             "pay_record": mixed.pay_record("alpha"),
             "director_votes": mixed.director_votes("alpha"),
             "director_peers": mixed.director_peers(min_managers=2),
             "director_panel": mixed.director_panel(
                 "alpha", "2024-01-01:2024-12-31,2025-01-01:2025-12-31")}
    for name, env in calls.items():
        assert any("2023-07-01" in c and "categor" in c for c in env["caveats"]), name
