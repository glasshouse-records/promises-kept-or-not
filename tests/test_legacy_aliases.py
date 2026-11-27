"""Trademark-mark normalisation, the reviewed legacy series alias file, and re-ingest of
named legacy filings (ISS and ProxyEdge)."""

from __future__ import annotations

import pytest
import requests
from test_legacy_iss import BASIC, FUND, HDR, SID, make_doc
from test_legacy_pe import BASIC as PE_BASIC
from test_legacy_pe import HDR as PE_HDR

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_pe, npx
from glasshouse.ingest.edgar import Filing

CIK = "0000100001"
ACC = "0001104659-23-095672"


# -- 1. trademark marks --------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("SPDR(R) S&P(R) CHINA ETF", "spdr s&p china etf"),
    ("Invesco PureBeta (SM) FTSE Fund", "invesco purebeta ftse fund"),
    ("Acme (TM) Fund", "acme fund"),
    ("Acme®  Fund™ X℠", "acme fund x"),
    ("Acme (r) Fund", "acme (r) fund"),          # case-sensitive, as printed
    ("Acme (C) Fund [x]", "acme (c) fund [x]"),  # nothing else is stripped
])
def test_norm_strips_only_trademark_marks(raw, want):
    assert legacy_pe._norm(raw) == want


def test_two_header_series_equal_after_stripping_are_both_unmatchable():
    h = ("<SERIES-ID>S000000001\n<SERIES-NAME>Acme(R) Fund\n"
         "<SERIES-ID>S000000002\n<SERIES-NAME>Acme Fund\n"
         "<SERIES-ID>S000000003\n<SERIES-NAME>Other\n")
    assert legacy_pe.series_map(h) == {"other": "S000000003"}


def test_marked_heading_maps_to_the_unmarked_header_name():
    smap = legacy_pe.series_map("<SERIES-ID>S000000001\n<SERIES-NAME>SPDR S&P China ETF\n")
    assert smap.get(legacy_pe._norm("SPDR(R) S&P(R) China ETF")) == "S000000001"


# -- 2. alias file -------------------------------------------------------------

def _csv(tmp_path, *rows):
    p = tmp_path / "a.csv"
    p.write_text("registrant_cik,heading,series_id,rule,note\n" + "".join(r + "\n" for r in rows))
    return p


def test_shipped_alias_file_loads_and_has_the_header():
    first = legacy_pe.ALIAS_PATH.read_text().splitlines()[0]
    assert first == "registrant_cik,heading,series_id,rule,note"
    legacy_pe.load_aliases()


def test_load_pads_cik_and_collapses_heading_whitespace(tmp_path):
    p = _csv(tmp_path, '100001,"My  Printed   Name",S000000009,r1,n')
    assert legacy_pe.load_aliases(p) == {(CIK, "My Printed Name"): "S000000009"}


def test_duplicate_key_with_different_series_raises(tmp_path):
    p = _csv(tmp_path, "100001,Name,S000000009,r,n", "0000100001,Name,S000000008,r,n")
    with pytest.raises(ValueError):
        legacy_pe.load_aliases(p)


def test_duplicate_key_with_same_series_is_fine(tmp_path):
    p = _csv(tmp_path, "100001,Name,S000000009,r,n", "0000100001,Name,S000000009,r,n")
    assert len(legacy_pe.load_aliases(p)) == 1


def _filing(cik=CIK, acc=ACC):
    return Filing(cik=cik, company_name="V", form_type="N-PX", filing_date="2023-08-30",
                  period_of_report="2023-06-30", accession_number=acc)


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vg','Vanguard')")
    return c


ALIAS_HEADING = "Totally Different Printed Name"
DOC = make_doc(ALIAS_HEADING, [("For", "For", "Management")] * 2)
ALIASES = {(CIK, ALIAS_HEADING): SID}


def test_iss_alias_is_used_when_series_is_in_header(conn):
    n = legacy_iss.ingest_filing(conn, _filing(), "vg", "2026-11-21", {"d": DOC}, HDR,
                                 aliases=ALIASES)
    assert n == 2
    assert {r[0] for r in conn.execute("SELECT vote_series FROM votes")} == {SID}


def test_iss_without_alias_is_unmapped(conn):
    assert legacy_iss.ingest_filing(conn, _filing(), "vg", "2026-11-21", {"d": DOC}, HDR) == 0


def test_iss_alias_whose_series_is_not_in_header_is_dropped_and_counted():
    rows, _ = legacy_iss.agreed(DOC)
    out, info = legacy_iss.to_vote_rows(rows, {}, aliases={ALIAS_HEADING: "S000000099"},
                                        header_sids={SID})
    assert out == [] and info["alias_not_in_header"] == 2
    assert sum(info["unmapped"].values()) == 2


def test_iss_alias_for_another_cik_is_ignored(conn):
    other = {("0000999999", ALIAS_HEADING): SID}
    assert legacy_iss.ingest_filing(conn, _filing(), "vg", "2026-11-21", {"d": DOC}, HDR,
                                    aliases=other) == 0


def test_exact_match_beats_alias():
    rows, _ = legacy_iss.agreed(make_doc(FUND, [("For", "For", "Management")]))
    out, _ = legacy_iss.to_vote_rows(rows, {legacy_pe._norm(FUND): SID},
                                     aliases={FUND: "S000000077"},
                                     header_sids={SID, "S000000077"})
    assert out[0]["vote_series"] == SID


def test_filing_aliases_selects_by_padded_cik():
    al = {(CIK, "A"): "S1", ("0000000002", "B"): "S2"}
    assert legacy_pe.filing_aliases(al, "100001") == {"A": "S1"}
    assert legacy_pe.filing_aliases(al, "2") == {"B": "S2"}


def _pe_row(fund):
    return {"fund_name": fund, "issuer_name": "ACME", "agenda_number": "1",
            "security_id": "123456789", "ticker": "AC", "isin": "US1234567890",
            "meeting_type": "Annual", "meeting_date": "2023-01-25", "proposal_id": "1",
            "proposal_text": "Elect X", "proposal_type": "Mgmt", "vote": "For",
            "for_against_management": "For"}


def test_proxyedge_alias_used_only_if_in_header():
    (v,), info = legacy_pe.to_vote_rows([_pe_row("Odd  Name")], {}, {"Odd Name": SID}, {SID})
    assert v["vote_series"] == SID and info["alias_not_in_header"] == 0
    out, info = legacy_pe.to_vote_rows([_pe_row("Odd Name")], {}, {"Odd Name": "S000000099"},
                                       {SID})
    assert out == [] and info["alias_not_in_header"] == 1
    assert info["funds_unmapped"] == {"Odd Name": 1}


def test_proxyedge_alias_for_another_cik_ignored_via_filing_aliases():
    fa = legacy_pe.filing_aliases({("0000999999", "Odd Name"): SID}, CIK)
    out, _ = legacy_pe.to_vote_rows([_pe_row("Odd Name")], {}, fa, {SID})
    assert out == []


# -- 3. re-ingest of named legacy filings ---------------------------------------

def _record(conn, report_type, acc=ACC):
    conn.execute("""INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                    period_of_report, report_type, source_url, retrieval_date)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (acc, CIK, "vg", "N-PX", "2023-08-30", "2023-06-30", report_type,
                  "https://www.sec.gov/x", "2026-01-01"))
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date, legacy_format) VALUES (?,'OLD','FOR','ISSUER','01/01/2023',"
                 "'iss_text')", (acc,))
    conn.commit()


def _run(conn, monkeypatch, docs, reingest, hdr=HDR, filings=None, **flags):
    def no_cover(url, *a, **k):
        r = requests.Response()
        r.status_code = 404
        raise requests.HTTPError(response=r)

    monkeypatch.setattr(npx, "list_filings", lambda *a, **k: filings or [_filing()])
    monkeypatch.setattr(npx.http, "get", no_cover)
    monkeypatch.setattr(legacy_pe, "load_filing_texts", lambda f, cache_dir=None: (docs, hdr))
    return npx.ingest_npx(conn, CIK, institution_id="vg", reingest=set(reingest),
                          reingest_reason="t", **flags)


def _votes(conn, acc=ACC):
    return conn.execute("SELECT COUNT(*) FROM votes WHERE accession=?", (acc,)).fetchone()[0]


@pytest.mark.parametrize("rt", ["LEGACY_ISS", "LEGACY_ISS_REJECTED"])
def test_named_iss_filing_is_reparsed_with_the_iss_flag(conn, monkeypatch, rt):
    _record(conn, rt)
    st = _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy_iss_text=True)
    assert st["votes"] == 21 and _votes(conn) == 21
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS"


def test_named_iss_filing_is_skipped_without_the_flag(conn, monkeypatch):
    _record(conn, "LEGACY_ISS")
    st = _run(conn, monkeypatch, {"a": BASIC}, [ACC])
    assert st["skipped"] == 1 and _votes(conn) == 1
    _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy_proxyedge=True)
    assert _votes(conn) == 1


def test_named_proxyedge_filing_needs_the_proxyedge_flag(conn, monkeypatch):
    _record(conn, "LEGACY_PROXYEDGE")
    _run(conn, monkeypatch, {"a": PE_BASIC}, [ACC], hdr=PE_HDR, legacy_iss_text=True)
    assert _votes(conn) == 1                      # the ISS flag does not cover ProxyEdge
    st = _run(conn, monkeypatch, {"a": PE_BASIC}, [ACC], hdr=PE_HDR, legacy_proxyedge=True)
    assert st["filings"] == 1 and _votes(conn) > 1
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_PROXYEDGE"


def test_unnamed_legacy_filing_is_never_touched(conn, monkeypatch):
    other_acc = "0001104659-23-000002"
    _record(conn, "LEGACY_ISS")
    _record(conn, "LEGACY_NO_COVER", acc=other_acc)
    _run(conn, monkeypatch, {"a": BASIC}, [ACC], filings=[_filing(acc=other_acc)],
         legacy_iss_text=True, legacy_proxyedge=True)
    assert _votes(conn) == 1 and _votes(conn, other_acc) == 1
    assert conn.execute("SELECT report_type FROM filings WHERE accession=?",
                        (other_acc,)).fetchone()[0] == "LEGACY_NO_COVER"


def test_named_legacy_reingest_never_deletes_xml_votes(conn, monkeypatch):
    _record(conn, "LEGACY_ISS")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('XML',?, 'vg','N-PX','u','2026-01-01')", (CIK,))
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date) VALUES ('XML','X','FOR','ISSUER','05/01/2024')")
    conn.commit()
    _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy_iss_text=True)
    assert _votes(conn, "XML") == 1


def _record_single_parser(conn):
    """A LEGACY_PARSED record: rows of the old single HTML parser (vote_source legacy_html,
    legacy_format NULL), quarantined from every release."""
    conn.execute("""INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                    period_of_report, report_type, source_url, retrieval_date)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (ACC, CIK, "vg", "N-PX", "2023-08-30", "2023-06-30", "LEGACY_PARSED",
                  "https://www.sec.gov/x", "2026-01-01"))
    conn.executemany("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                     "meeting_date) VALUES (?,'OLD','FOR','legacy_html','01/01/2023')",
                     [(ACC,), (ACC,)])
    conn.commit()


def test_legacy_parsed_is_skipped_unless_named(conn, monkeypatch):
    _record_single_parser(conn)
    _run(conn, monkeypatch, {"a": BASIC}, [], legacy=True, legacy_iss_text=True,
         legacy_proxyedge=True)
    assert _votes(conn) == 2
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_PARSED"


def test_legacy_parsed_needs_a_two_parser_flag(conn, monkeypatch):
    _record_single_parser(conn)
    st = _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy=True)
    assert st["skipped"] == 1 and _votes(conn) == 2


def test_named_legacy_parsed_is_replaced_by_the_two_parser_reading(conn, monkeypatch):
    """2026-11-27: three Fidelity filings (26,135 single-parser rows, never released) are in
    the ISS HTML layout both agreeing parsers read; a named re-ingest upgrades them and the
    single-parser rows go, so nothing is counted twice."""
    _record_single_parser(conn)
    st = _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy_iss_text=True)
    assert st["filings"] == 1 and _votes(conn) == 21
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE vote_source='legacy_html'"
                        ).fetchone()[0] == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS"


def test_legacy_parsed_in_another_format_keeps_its_rows(conn, monkeypatch):
    _record_single_parser(conn)
    _run(conn, monkeypatch, {"a": "nothing"}, [ACC], legacy_iss_text=True)
    assert _votes(conn) == 2
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_PARSED"


def test_named_legacy_no_cover_takes_the_upgrade_path_under_a_legacy_flag(conn, monkeypatch):
    """Was asserted skipped (the (b4)(4) bug); a plain legacy run upgrades it, so must this."""
    _record(conn, "LEGACY_NO_COVER")
    st = _run(conn, monkeypatch, {"a": BASIC}, [ACC], legacy_iss_text=True)
    assert st["skipped"] == 0 and st["filings"] == 1
    assert conn.execute("SELECT report_type FROM filings WHERE accession=?",
                        (ACC,)).fetchone()[0] != "LEGACY_NO_COVER"


def test_reingest_with_a_wrong_format_keeps_the_old_rows(conn, monkeypatch):
    _record(conn, "LEGACY_ISS")
    st = _run(conn, monkeypatch, {"a": "nothing"}, [ACC], legacy_iss_text=True)
    assert st.get("no_format") == 1 and _votes(conn) == 1
