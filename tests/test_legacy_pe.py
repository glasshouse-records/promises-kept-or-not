"""Legacy (2022-23) ProxyEdge N-PX: two-parser agreement, series mapping, ledger rows,
the release/analysis quarantine, and dedupe."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from glasshouse import engine, ledger, publish
from glasshouse.ingest import legacy_pe, legacy_pe_blocks, legacy_pe_lines
from glasshouse.ingest.edgar import Filing

FIX = Path(__file__).parent / "fixtures" / "legacy_pe"
BASIC = (FIX / "basic.txt").read_text()
FUND = "JPMorgan Mid Cap Value Fund"
HDR = ("<SERIES>\n<OWNER-CIK>0001217286\n<SERIES-ID>S000001447\n"
       f"<SERIES-NAME>{FUND}\n<CLASS-CONTRACT>\n</SERIES>\n")


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('jpm','JPM')")
    return c


def _filing(acc="0001438934-23-000402", period="2023-06-30"):
    return Filing(cik="0001217286", company_name="JPMorgan Trust I", form_type="N-PX",
                  filing_date="2023-08-31", period_of_report=period, accession_number=acc)


# -- agreement ---------------------------------------------------------------

def test_agreed_is_the_intersection_of_both_parsers():
    rows, st = legacy_pe.agreed(BASIC)
    assert rows == legacy_pe_blocks.parse(BASIC) and len(rows) == 12
    assert st["agreed"] == 12 and st["a_only"] == st["b_only"] == 0
    assert st["disagreement_rate"] == 0 and st["rows_a"] == st["rows_b"] == 12


def test_agreed_drops_a_row_only_one_parser_produced(monkeypatch):
    real = legacy_pe_lines.parse
    monkeypatch.setattr(legacy_pe_lines, "parse", lambda t: real(t)[1:])
    rows, st = legacy_pe.agreed(BASIC)
    first = legacy_pe_blocks.parse(BASIC)
    same = sum(legacy_pe.meeting_key(r) == legacy_pe.meeting_key(first[0]) for r in first)
    assert same > 1 and len(rows) == 12 - same and st["rows_dropped_disputed"] == same - 1
    assert st["a_only"] == 1 and st["b_only"] == 0
    assert st["disagreement_rate"] == pytest.approx(1 / 12)


def test_agreed_is_a_multiset_intersection(monkeypatch):
    base = legacy_pe_blocks.parse(BASIC)[0]
    other = {**base, "issuer_name": "ZZ OTHER MEETING INC."}   # surplus copy in its own meeting
    monkeypatch.setattr(legacy_pe_blocks, "parse", lambda t: [base, base, other, other])
    monkeypatch.setattr(legacy_pe_lines, "parse", lambda t: [base, base, other])
    rows, st = legacy_pe.agreed(BASIC)
    assert len(rows) == 2 and st["a_only"] == 1


def test_a_field_difference_is_a_disagreement(monkeypatch):
    a = legacy_pe_blocks.parse(BASIC)[:1]
    monkeypatch.setattr(legacy_pe_blocks, "parse", lambda t: a)
    monkeypatch.setattr(legacy_pe_lines, "parse", lambda t: [{**a[0], "vote": "Against"}])
    rows, st = legacy_pe.agreed(BASIC)
    assert rows == [] and st["a_only"] == 1 and st["b_only"] == 1
    assert st["disagreement_rate"] == 1.0


# -- series map --------------------------------------------------------------

def test_series_map_from_sgml_header():
    assert legacy_pe.series_map(HDR) == {FUND.casefold(): "S000001447"}


def test_series_map_normalises_names_and_reads_plain_text_form():
    txt = "S000001447\n  JPMorgan   Mid Cap  Value Fund \nS000009999 Other Fund\n"
    assert legacy_pe.series_map(txt) == {FUND.casefold(): "S000001447",
                                         "other fund": "S000009999"}


def test_series_map_removes_a_name_mapping_to_two_series():
    h = ("<SERIES-ID>S000000001\n<SERIES-NAME>Same Fund\n"
         "<SERIES-ID>S000000002\n<SERIES-NAME>same  FUND\n"
         "<SERIES-ID>S000000003\n<SERIES-NAME>Other\n")
    assert legacy_pe.series_map(h) == {"other": "S000000003"}


def test_series_map_same_series_listed_twice_is_not_ambiguous():
    h = "<SERIES-ID>S000000001\n<SERIES-NAME>A\n<SERIES-ID>S000000001\n<SERIES-NAME>a\n"
    assert legacy_pe.series_map(h) == {"a": "S000000001"}


# -- vote rows ---------------------------------------------------------------

def _row(**kw):
    r = {"fund_name": FUND, "issuer_name": "ACME", "agenda_number": "1",
         "security_id": "123456789", "ticker": "AC", "isin": "US1234567890",
         "meeting_type": "Annual", "meeting_date": "2023-01-25", "proposal_id": "1",
         "proposal_text": "Elect X", "proposal_type": "Mgmt", "vote": "For",
         "for_against_management": "For"}
    r.update(kw)
    return r


SMAP = {FUND.casefold(): "S000001447"}


def test_to_vote_rows_maps_every_field():
    (v,), info = legacy_pe.to_vote_rows([_row()], SMAP)
    assert v == {"issuer_name": "ACME", "cusip": "", "isin": "",  # was "123456789"/"US1234567890": both fail their check digit
                 "meeting_date": "01/25/2023", "vote_description": "Elect X",
                 "category_type": "", "vote_source": "ISSUER", "shares_on_loan": None,
                 "vote_series": "S000001447", "how_voted": "FOR", "shares_voted": None,
                 "management_recommendation": "FOR", "legacy_format": "proxyedge",
                 "for_against_management": "For", "proposal_number": "1"}
    assert info["funds_unmapped"] == {}


def test_shr_is_security_holder_other_types_dropped_and_counted():
    rows, info = legacy_pe.to_vote_rows(
        [_row(proposal_type="Shr"), _row(proposal_type="Other")], SMAP)
    assert [r["vote_source"] for r in rows] == ["SECURITY HOLDER"]
    assert info["dropped_type"] == 1


@pytest.mark.parametrize("vote,how", [("Withheld", "WITHHOLD"), ("Withhold", "WITHHOLD"),
                                      ("Abstain", "ABSTAIN"), ("Against", "AGAINST"),
                                      ("1 Year", "1 YEAR")])
def test_how_voted_closed_mapping(vote, how):
    (v,), _ = legacy_pe.to_vote_rows([_row(vote=vote, for_against_management="")], SMAP)
    assert v["how_voted"] == how


def test_unknown_vote_is_dropped_and_counted():
    rows, info = legacy_pe.to_vote_rows([_row(vote="Take No Action"), _row(vote="Banana")], SMAP)
    assert rows == [] and info["dropped_vote"] == 2


@pytest.mark.parametrize("vote,fa,rec", [("For", "For", "FOR"), ("Against", "For", "FOR"),
                                         ("For", "Against", "AGAINST"),
                                         ("Against", "Against", "AGAINST"),
                                         ("Abstain", "For", "FOR"), ("Withheld", "Against", "AGAINST"),
                                         ("For", "", ""), ("1 Year", "For", "FOR")])
def test_management_recommendation_is_the_printed_for_against_management(vote, fa, rec):
    (v,), _ = legacy_pe.to_vote_rows([_row(vote=vote, for_against_management=fa)], SMAP)
    assert v["management_recommendation"] == rec and v["for_against_management"] == fa


def test_funds_not_in_this_filings_header_are_dropped_and_counted_by_name():
    rows, info = legacy_pe.to_vote_rows(
        [_row(), _row(fund_name="Other Registrant Fund"),
         _row(fund_name="Other Registrant Fund")], SMAP)
    assert len(rows) == 1 and info["funds_unmapped"] == {"Other Registrant Fund": 2}


def test_fund_name_matching_is_normalised():
    rows, _ = legacy_pe.to_vote_rows([_row(fund_name="jpmorgan  MID cap value fund ")], SMAP)
    assert len(rows) == 1


# -- ledger ------------------------------------------------------------------

def test_migration_adds_columns_idempotently(tmp_path):
    p = tmp_path / "old.db"
    c = ledger.connect(p)
    c.execute("ALTER TABLE votes DROP COLUMN legacy_format")
    c.execute("ALTER TABLE votes DROP COLUMN for_against_management")
    c.execute("DROP TABLE legacy_parse")
    c.commit()
    c.close()
    for _ in range(2):
        c = ledger.connect(p)
    cols = {r[1] for r in c.execute("PRAGMA table_info(votes)")}
    assert {"legacy_format", "for_against_management"} <= cols
    assert {r[1] for r in c.execute("PRAGMA table_info(legacy_parse)")} >= {
        "accession", "document", "disagreement_rate", "funds_unmapped", "rows_inserted"}


def _ingest(conn, text=BASIC, hdr=HDR, filing=None):
    return legacy_pe.ingest_filing(conn, filing or _filing(), "jpm", "2026-11-21",
                                   {"doc.txt": text}, hdr)


def test_ingest_filing_inserts_agreed_votes_and_records_stats(conn):
    n = _ingest(conn)
    assert n == 12
    f = conn.execute("SELECT report_type, period_of_report FROM filings").fetchone()
    assert tuple(f) == ("LEGACY_PROXYEDGE", "2023-06-30")
    v = conn.execute("SELECT DISTINCT legacy_format, vote_series, shares_voted, vote_source "
                     "FROM votes").fetchall()
    assert [tuple(x) for x in v] == [("proxyedge", "S000001447", None, "ISSUER")]
    s = conn.execute("SELECT * FROM legacy_parse").fetchone()
    assert (s["document"], s["agreed"], s["rows_inserted"], s["disagreement_rate"]) == (
        "doc.txt", 12, 12, 0)


def test_gate_rejects_the_filing_when_parsers_disagree(conn, monkeypatch):
    real = legacy_pe_lines.parse
    monkeypatch.setattr(legacy_pe_lines, "parse", lambda t: real(t)[1:])   # 1/12 > 0.5%
    assert _ingest(conn) == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == \
        "LEGACY_PROXYEDGE_REJECTED"
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0
    s = conn.execute("SELECT rows_inserted, a_only FROM legacy_parse").fetchone()
    assert tuple(s) == (0, 1)


def test_gate_rejects_when_nothing_agreed(conn):
    assert _ingest(conn, text="Agenda Number: nothing parseable") == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == \
        "LEGACY_PROXYEDGE_REJECTED"


def test_unmapped_funds_are_not_inserted(conn):
    assert _ingest(conn, hdr="<SERIES-ID>S000000009\n<SERIES-NAME>Unrelated\n") == 0
    s = conn.execute("SELECT funds_unmapped, rows_inserted FROM legacy_parse").fetchone()
    assert FUND in s["funds_unmapped"] and s["rows_inserted"] == 0


def test_a_prior_no_cover_record_is_upgraded(conn):
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date, report_type) VALUES ('0001438934-23-000402','1','jpm','N-PX',"
                 "'u','2026-01-01','LEGACY_NO_COVER')")
    assert _ingest(conn) == 12
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 1


def test_candidate_filter_period_and_form():
    assert legacy_pe.is_candidate(_filing())
    assert legacy_pe.is_candidate(Filing("1", "x", "N-PX/A", "d", "2023-06-30", "a"))
    assert not legacy_pe.is_candidate(_filing(period="2022-06-30"))
    assert not legacy_pe.is_candidate(Filing("1", "x", "13F-HR", "d", "2023-06-30", "a"))


def test_cache_is_used_before_the_network(tmp_path, monkeypatch):
    acc = "0001438934-23-000402"
    d = tmp_path / acc
    d.mkdir()
    (d / "doc.txt.gz").write_bytes(gzip.compress(BASIC.encode()))
    (d / f"{acc}.hdr.sgml").write_text(HDR)
    monkeypatch.setattr(legacy_pe.http, "get",
                        lambda *a, **k: pytest.fail("network used despite cache"))
    monkeypatch.setattr(legacy_pe, "list_documents", lambda f: ["doc.txt"])
    docs, hdr = legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert docs == {"doc.txt": BASIC} and hdr == HDR


# -- quarantine --------------------------------------------------------------

def test_unpromoted_legacy_rows_are_not_published_and_not_analysed(conn):
    _ingest(conn)
    conn.execute("UPDATE votes SET vote_source='SECURITY HOLDER', category_type='X', "
                 "legacy_format='not_yet_promoted'")
    conn.commit()
    ledger.dedupe_votes(conn)
    assert conn.execute(
        f"SELECT COUNT(*) FROM votes {publish.PUBLIC_TABLES['votes']}").fetchone()[0] == 0
    assert conn.execute(
        f"SELECT COUNT(*) FROM votes WHERE is_duplicate=0 AND {ledger.NON_LEGACY_VOTE_SQL}"
    ).fetchone()[0] == 0
    assert engine._grouped(conn, "v.vote_source = 'SECURITY HOLDER'") == {}


def test_xml_rows_still_pass_the_shared_predicate(conn):
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('A','1','jpm','N-PX','u','2026-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date) VALUES ('A','X','FOR','SECURITY HOLDER','05/01/2024')")
    conn.commit()
    assert conn.execute(
        f"SELECT COUNT(*) FROM votes {publish.PUBLIC_TABLES['votes']}").fetchone()[0] == 1
    assert len(engine._grouped(conn, "v.vote_source = 'SECURITY HOLDER'")) == 1


def test_legacy_identifying_columns_ship_with_the_promoted_rows(conn):
    assert {"legacy_format", "for_against_management"} <= set(
        publish.public_columns(conn, "votes"))


def test_dedupe_marks_two_identical_legacy_rows_once(conn):
    _ingest(conn)
    conn.execute("INSERT INTO votes (accession, issuer_name, cusip, isin, meeting_date, "
                 "vote_description, category_type, vote_source, vote_series, how_voted, "
                 "management_recommendation, legacy_format, for_against_management, "
                 "proposal_number) SELECT accession, issuer_name, cusip, isin, meeting_date, vote_description, "
                 "category_type, vote_source, vote_series, how_voted, management_recommendation, "
                 "legacy_format, for_against_management, proposal_number FROM votes ORDER BY id LIMIT 1")
    conn.commit()
    ledger.dedupe_votes(conn)
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE is_duplicate=1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE is_duplicate=0").fetchone()[0] == 12
