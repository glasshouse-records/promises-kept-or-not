"""Promotion of the reviewed 2022-23 legacy votes: the stale-data gate (release + integrity),
the public contract (columns shipped, data dictionary), and the datasheet's per-season
coverage and known gaps."""
from __future__ import annotations

import sqlite3

import pytest
from test_legacy_pe import BASIC, HDR, _filing

from glasshouse import cli, dataset, ledger, publish, release
from glasshouse.ingest import legacy_pe


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('jpm','JPM')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url,"
              " retrieval_date) VALUES ('XML','1','jpm','N-PX','u','2026-01-01')")
    return c


def _vote(conn, fmt, how="FOR", date="05/01/2023", src="ISSUER", shares=None, acc="XML"):
    conn.execute(
        "INSERT INTO votes (accession, issuer_name, meeting_date, vote_description, vote_source,"
        " how_voted, shares_voted, management_recommendation, legacy_format,"
        " for_against_management, is_duplicate) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
        (acc, "X", date, "p", src, how, shares, "FOR", fmt, "For" if fmt else None))
    conn.commit()


# -- the stale-data gate ---------------------------------------------------------------------

def _stale(conn):
    legacy_pe.ingest_filing(conn, _filing(), "jpm", "2026-11-22", {"doc.txt": BASIC}, HDR)
    conn.execute("UPDATE legacy_parse SET parser_version = 'old'")
    conn.commit()


def test_promotion_blockers_name_stale_filings_and_bad_management(conn):
    assert ledger.promotion_blockers(conn) == []
    _stale(conn)
    assert any("stale" in b and _filing().accession_number in b
               for b in ledger.promotion_blockers(conn))


def test_promotion_blockers_flag_bad_management_recommendation(conn):
    _vote(conn, "proxyedge")
    conn.execute("UPDATE votes SET management_recommendation='ABSTAIN'")
    conn.commit()
    assert any("management_recommendation" in b for b in ledger.promotion_blockers(conn))


def test_release_refuses_stale_legacy_data(conn, tmp_path):
    _stale(conn)
    with pytest.raises(release.PromotionBlockedError):
        release.build_release(conn, root=tmp_path / "rel", version="x", no_derived=True,
                              engine_path=tmp_path / "none.db", institutions={})
    assert not (tmp_path / "rel" / "vx").exists()


def test_integrity_command_fails_on_stale_legacy_data(conn, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_conn", lambda: conn)
    assert cli.cmd_integrity(None) == 0
    _stale(conn)
    assert cli.cmd_integrity(None) == 1
    assert "stale" in capsys.readouterr().out


# -- what ships -------------------------------------------------------------------------------

def test_promoted_rows_ship_with_their_identifying_columns(conn, tmp_path):
    _vote(conn, None, shares=5)
    _vote(conn, "proxyedge")
    _vote(conn, "iss_html")
    _vote(conn, None, src="legacy_html")             # single-parser: stays out
    _vote(conn, "something_new")                      # unknown format: stays out
    cols = publish.public_columns(conn, "votes")
    assert "legacy_format" in cols and "for_against_management" in cols
    dest = publish.build_public_snapshot(conn, tmp_path / "pub.db")
    rows = sqlite3.connect(dest).execute(
        "SELECT legacy_format, for_against_management FROM votes ORDER BY id").fetchall()
    assert rows == [(None, None), ("proxyedge", "For"), ("iss_html", "For")]


def test_data_dictionary_documents_the_legacy_columns():
    v = dataset.DATA_DICTIONARY["votes"]
    assert "proxyedge" in v["legacy_format"] and "iss_text" in v["legacy_format"]
    assert "NULL" in v["legacy_format"] and "METHODOLOGY" in v["legacy_format"]
    assert "Against Management" in v["for_against_management"] or "For/Against" in \
        v["for_against_management"]
    assert "NULL on legacy" in v["shares_voted"] or "NULL on 2022-23" in v["shares_voted"]
    for col, needle in (("management_recommendation", "ProxyEdge"), ("how_voted", "normalised"),
                        ("vote_source", "sponsor"), ("category_type", "legacy"),
                        ("cusip", "check digit"), ("isin", "check digit")):
        assert needle in v[col], col


def test_every_shipped_votes_column_is_documented(conn):
    cols = set(publish.public_columns(conn, "votes"))
    assert cols <= set(dataset.DATA_DICTIONARY["votes"]) | {"_"}


# -- datasheet: per-season coverage and known gaps ---------------------------------------------

def test_datasheet_has_season_coverage_and_known_gaps_computed_from_data(conn):
    for _ in range(3):
        _vote(conn, "proxyedge", date="12/01/2022")
    _vote(conn, None, shares=9, date="08/01/2023")
    _vote(conn, None, shares=9, date="05/01/2023")
    _vote(conn, "future_fmt", date="12/01/2022")          # unpromoted: not counted anywhere
    seasons = {s["season"]: s for s in dataset.season_coverage(conn)}
    assert seasons["2022-23"]["legacy_lines"] == 3 and seasons["2022-23"]["xml_lines"] == 1
    assert seasons["2023-24"]["legacy_lines"] == 0 and seasons["2023-24"]["xml_lines"] == 1
    sheet = dataset.build_datasheet(conn)
    assert "## Coverage by N-PX season" in sheet and "| 2022-23 | 3 | 1 |" in sheet
    assert "## Known gaps" in sheet
    for needle in ("Fidelity", "Federated", "Issue No.", "Diamond Hill", "Dodge & Cox",
                   "unmapped", "Proxy contests", "Vanguard", "share counts", "categor",
                   "same-direction"):
        assert needle in sheet, needle


def test_season_coverage_never_invents_a_season_from_an_unreadable_date(conn):
    # As filed: YYYYMMDD is read; day-first-looking values (a minute in one filing), month 00,
    # impossible months and trailing junk may not be cut into a fake season: one honest label.
    for d in ("20240425", "30/07/2023", "30/24/2024", "11/7/2023x", "00/24/2024"):
        _vote(conn, None, shares=1, date=d)
    _vote(conn, None, shares=1, date="08/01/2023")
    seasons = {s["season"]: s for s in dataset.season_coverage(conn)}
    assert set(seasons) == {"2023-24", dataset.UNREADABLE_DATE_SEASON}
    assert seasons[dataset.UNREADABLE_DATE_SEASON]["xml_lines"] == 4
    assert seasons["2023-24"]["xml_lines"] == 2
