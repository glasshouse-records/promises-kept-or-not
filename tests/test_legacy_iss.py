"""Legacy ISS-text N-PX ingestion: two-parser agreement and gate, heading -> series
mapping, contest drop, vote vocabulary, quarantine, idempotent re-ingest."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_iss_blocks, legacy_iss_lines, legacy_pe
from glasshouse.ingest.edgar import Filing

FIX = Path(__file__).parent / "fixtures" / "legacy_iss"
BASIC = "*" * 20 + " FORM N-Px REPORT " + "*" * 20 + "\n" + (FIX / "vanguard_basic.txt").read_text()
CONTEST = (FIX / "contest.txt").read_text()
FUND = "VANGUARD S&P SMALL-CAP 600 GROWTH INDEX FUND"
SID = "S000000001"
HDR = f"<SERIES-ID>{SID}\n<SERIES-NAME>Vanguard S&P Small-Cap 600 Growth Index Fund\n"
ACC = "0001104659-23-095672"
MGMT = ("For", "For", "Management")


def make_doc(heading: str, votes: list[tuple[str, str, str]], rec_label="Mgt Rec") -> str:
    """votes = [(rec, vote, sponsor)]; one meeting, one line per proposal."""
    lines = ["*" * 20 + " FORM N-Px REPORT " + "*" * 20, "",
             f"================= {heading} =================", "", "", "ACME CORP", "",
             "Ticker:       ACME           Security ID:  123456789",
             "Meeting Date: JAN 25, 2023   Meeting Type: Annual",
             "Record Date:  DEC 01, 2022", "",
             f"#     Proposal                                {rec_label:<9} Vote Cast    Sponsor"]
    for i, (rec, vote, sp) in enumerate(votes, 1):
        lines.append(f"{i:<5} {'Proposal number ' + str(i):<39} {rec:<9} {vote:<12} {sp}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vg','Vanguard')")
    return c


def _filing(acc=ACC, period="2023-06-30"):
    return Filing(cik="0000100001", company_name="Vanguard", form_type="N-PX",
                  filing_date="2023-08-30", period_of_report=period, accession_number=acc)


def _ingest(conn, text=BASIC, hdr=HDR, filing=None):
    return legacy_iss.ingest_filing(conn, filing or _filing(), "vg", "2026-11-21",
                                    {"doc.txt": text}, hdr)


def _rows(heading, votes, smap=None, **kw):
    text = make_doc(heading, votes, **kw)
    rows, st = legacy_iss.agreed(text)
    assert st["disagreement_rate"] == 0 and len(rows) == len(votes), st
    return legacy_iss.to_vote_rows(rows, smap if smap is not None else {legacy_pe._norm(FUND): SID})


# -- agreement ---------------------------------------------------------------

def test_agreed_is_the_intersection_of_both_parsers():
    rows, st = legacy_iss.agreed(BASIC)
    assert rows == legacy_iss_blocks.parse(BASIC) and len(rows) == 21
    assert st["agreed"] == 21 and st["a_only"] == st["b_only"] == 0
    assert st["disagreement_rate"] == 0 and st["rows_a"] == st["rows_b"] == 21


def test_agreed_drops_a_row_only_one_parser_produced(monkeypatch):
    real = legacy_iss_lines.parse
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: real(t)[1:])
    rows, st = legacy_iss.agreed(BASIC)
    assert len(rows) == 20 and st["a_only"] == 1 and st["b_only"] == 0
    assert st["disagreement_rate"] == pytest.approx(1 / 21)


def test_a_field_difference_over_all_fields_is_a_disagreement(monkeypatch):
    a = legacy_iss_blocks.parse(BASIC)[:1]
    monkeypatch.setattr(legacy_iss_blocks, "parse", lambda t: a)
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: [{**a[0], "record_date": "x"}])
    rows, st = legacy_iss.agreed(BASIC)
    assert rows == [] and st["a_only"] == st["b_only"] == 1
    assert st["disagreement_rate"] == 1.0


def test_agreed_is_a_multiset_intersection(monkeypatch):
    base = legacy_iss_blocks.parse(BASIC)[0]
    monkeypatch.setattr(legacy_iss_blocks, "parse", lambda t: [base] * 3)
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: [base] * 2)
    rows, st = legacy_iss.agreed(BASIC)
    assert len(rows) == 2 and st["a_only"] == 1


# -- format detection --------------------------------------------------------

def test_detects_iss_proxyedge_and_neither():
    assert legacy_iss.is_iss_text(BASIC)
    assert legacy_iss.is_iss_text(make_doc("X", [MGMT], "Diss Rec"))
    assert not legacy_iss.is_iss_text("Agenda Number: 1\nFORM N-Px REPORT")
    assert legacy_iss.is_iss_text("#     Proposal   Mgt Rec  Vote Cast   Sponsor\nno banner")  # State Street omits it
    assert not legacy_iss.is_iss_text("FORM N-Px REPORT only")
    assert legacy_iss.detect_format({"a": BASIC}) == "iss"
    assert legacy_iss.detect_format({"a": "x Agenda Number: 1"}) == "proxyedge"
    assert legacy_iss.detect_format({"a": "nothing"}) is None
    assert legacy_iss.detect_format({"a": BASIC, "b": "Agenda Number: 1"}) is None  # mixed


# -- heading -> series -------------------------------------------------------

def test_exact_normalised_heading_maps():
    rows, info = _rows("vanguard  s&p small-cap 600 growth INDEX fund ", [MGMT])
    assert [r["vote_series"] for r in rows] == [SID] and info["unmapped"] == {}


@pytest.mark.parametrize("suffix", ["WELLINGTON", "GLASS LEWIS ESG POLICY", "Polen Capital, LLC"])
def test_one_trailing_suffix_is_stripped(suffix):
    rows, info = _rows(f"{FUND} - {suffix}", [MGMT])
    assert [r["vote_series"] for r in rows] == [SID] and info["unmapped"] == {}


def test_only_one_suffix_segment_is_stripped():
    rows, info = _rows(f"{FUND} - A - B", [MGMT])
    assert rows == [] and info["unmapped"] == {f"{FUND} - A - B": 1}


def test_exact_match_beats_stripping():
    smap = {legacy_pe._norm(f"{FUND} - X"): "S000000002", legacy_pe._norm(FUND): SID}
    rows, _ = _rows(f"{FUND} - X", [MGMT], smap=smap)
    assert rows[0]["vote_series"] == "S000000002"


def test_unmatched_heading_is_dropped_and_counted_never_fuzzy():
    rows, info = _rows("VANGUARD S&P SMALL-CAP 600 GROWTH FUND", [MGMT] * 2)
    assert rows == [] and info["unmapped"] == {"VANGUARD S&P SMALL-CAP 600 GROWTH FUND": 2}


def test_ambiguous_name_is_dropped_because_series_map_removes_it():
    h = (f"<SERIES-ID>S000000001\n<SERIES-NAME>{FUND}\n"
         f"<SERIES-ID>S000000002\n<SERIES-NAME>{FUND.lower()}\n")
    smap = legacy_pe.series_map(h)
    rows, info = _rows(FUND, [MGMT], smap=smap)
    assert rows == [] and info["unmapped"] == {FUND: 1}


# -- contests and recommendations -------------------------------------------

def test_contest_rows_are_dropped_and_counted():
    rows, st = legacy_iss.agreed(CONTEST)
    assert len(rows) == 5
    out, info = legacy_iss.to_vote_rows(rows, {"vanguard contest fund": SID})
    assert out == [] and info["contest_rows_dropped"] == 5


def test_a_card_label_alone_drops_the_row():
    (r,) = legacy_iss_blocks.parse(make_doc(FUND, [MGMT]))
    out, info = legacy_iss.to_vote_rows(
        [{**r, "card_label": "White Card"}], {legacy_pe._norm(FUND): SID})
    assert out == [] and info["contest_rows_dropped"] == 1


def test_diss_rec_drops_the_row_even_without_a_card_label():
    rows, info = _rows(FUND, [MGMT], rec_label="Diss Rec")
    assert rows == [] and info["contest_rows_dropped"] == 1


def test_mgt_rec_sets_the_management_recommendation_with_the_vote_mapping():
    rows, _ = _rows(FUND, [("For", "Against", "Management"), ("Against", "Against", "Shareholder"),
                           ("Withhold", "Withheld", "Management")])
    assert [r["management_recommendation"] for r in rows] == ["FOR", "AGAINST", "WITHHOLD"]
    assert [r["how_voted"] for r in rows] == ["AGAINST", "AGAINST", "WITHHOLD"]
    assert all(r["for_against_management"] is None for r in rows)


def test_unmappable_recommendation_leaves_it_empty_but_keeps_the_vote():
    rows, _ = _rows(FUND, [("None", "For", "Management")])
    assert rows[0]["management_recommendation"] == "" and rows[0]["how_voted"] == "FOR"


# -- vote vocabulary ---------------------------------------------------------

@pytest.mark.parametrize("vote,how", [
    ("For", "FOR"), ("FOR", "FOR"), ("Against", "AGAINST"), ("AGAINST", "AGAINST"),
    ("Abstain", "ABSTAIN"), ("Withhold", "WITHHOLD"), ("Withheld", "WITHHOLD"),
    ("1 Year", "1 YEAR"), ("One Year", "1 YEAR"), ("2 Years", "2 YEARS"),
    ("Two Years", "2 YEARS"), ("3 Years", "3 YEARS"), ("Three Years", "3 YEARS"),
    ("Do Not Vote", "DO NOT VOTE"), ("Did Not Vote", "Did Not Vote"),
    ("TNA", "TNA"), ("No Vote", "No Vote")])
def test_vote_vocabulary_maps_to_stored_strings(vote, how):
    rows, info = _rows(FUND, [("For", vote, "Management")])
    assert [r["how_voted"] for r in rows] == [how] and info["dropped_vote"] == 0


@pytest.mark.parametrize("vote", ["None", "N/A", "Take No Action"])
def test_values_without_an_exact_counterpart_are_dropped_and_counted(vote):
    # built from parsed rows: "Take No Action" overflows the 12-column test layout
    base = legacy_iss_blocks.parse(make_doc(FUND, [MGMT, MGMT]))
    rows, info = legacy_iss.to_vote_rows([{**base[0], "vote": vote}, base[1]],
                                         {legacy_pe._norm(FUND): SID})
    assert [r["how_voted"] for r in rows] == ["FOR"] and info["dropped_vote"] == 1


def test_the_vocabulary_tables_cover_the_parsers_closed_vocabulary_exactly():
    for k in legacy_iss_blocks.VOTE_VOCAB:
        assert (k in legacy_iss.HOW_VOTED) != (k in legacy_iss.VOTE_DROPPED), k
    assert set(legacy_iss.HOW_VOTED) | set(legacy_iss.VOTE_DROPPED) == \
        set(legacy_iss_blocks.VOTE_VOCAB)


def test_to_vote_rows_maps_every_field():
    (v,), info = _rows(FUND, [MGMT])
    assert v == {"issuer_name": "ACME CORP", "cusip": "123456789", "isin": None,
                 "meeting_date": "01/25/2023", "vote_description": "Proposal number 1",
                 "category_type": "", "vote_source": "ISSUER", "shares_on_loan": None,
                 "vote_series": SID, "how_voted": "FOR", "shares_voted": None,
                 "management_recommendation": "FOR", "legacy_format": "iss_text",
                 "for_against_management": None}
    assert info["unmapped"] == {} and info["contest_rows_dropped"] == 0


def test_shareholder_is_security_holder():
    rows, _ = _rows(FUND, [("For", "For", "Shareholder")])
    assert rows[0]["vote_source"] == "SECURITY HOLDER"


# -- ledger ------------------------------------------------------------------

def test_ingest_filing_inserts_agreed_votes_and_records_stats(conn):
    assert _ingest(conn) == 21
    f = conn.execute("SELECT report_type, period_of_report FROM filings").fetchone()
    assert tuple(f) == ("LEGACY_ISS", "2023-06-30")
    v = conn.execute("SELECT DISTINCT legacy_format, vote_series, shares_voted, vote_source, "
                     "for_against_management FROM votes").fetchall()
    assert [tuple(x) for x in v] == [("iss_text", SID, None, "ISSUER", None)]
    s = conn.execute("SELECT * FROM legacy_parse").fetchone()
    assert (s["document"], s["agreed"], s["rows_inserted"], s["disagreement_rate"],
            s["meetings"]) == ("doc.txt", 21, 21, 0, 2)


def test_gate_rejects_the_filing_when_parsers_disagree(conn, monkeypatch):
    real = legacy_iss_lines.parse
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: real(t)[1:])   # 1/21 > 0.5%
    assert _ingest(conn) == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS_REJECTED"
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0
    assert tuple(conn.execute("SELECT rows_inserted, a_only FROM legacy_parse").fetchone()) == (0, 1)


def test_gate_boundary_is_inclusive_at_half_a_percent(conn, monkeypatch):
    base = legacy_iss_blocks.parse(BASIC)[0]
    rows = [{**base, "proposal_id": str(i)} for i in range(199)]
    monkeypatch.setattr(legacy_iss_blocks, "parse", lambda t: rows + [base])
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: rows)   # 1 / 200 == 0.005
    assert _ingest(conn) == 199
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS"


def test_gate_rejects_when_nothing_agreed(conn):
    assert _ingest(conn, text="FORM N-Px REPORT\n#  Proposal  Mgt Rec  Vote Cast  Sponsor") == 0
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS_REJECTED"


def test_unmapped_headings_are_not_inserted_and_are_recorded(conn):
    assert _ingest(conn, hdr="<SERIES-ID>S000000009\n<SERIES-NAME>Unrelated\n") == 0
    s = conn.execute("SELECT funds_unmapped, rows_inserted FROM legacy_parse").fetchone()
    assert FUND in s["funds_unmapped"] and s["rows_inserted"] == 0


def test_documents_in_another_format_are_ignored(conn):
    n = legacy_iss.ingest_filing(conn, _filing(), "vg", "2026-11-21",
                                 {"a.txt": BASIC, "b.txt": "Agenda Number: 1"}, HDR)
    assert n == 21 and conn.execute("SELECT COUNT(*) FROM legacy_parse").fetchone()[0] == 1


def test_reingest_replaces_its_own_rows_and_never_touches_xml_rows(conn):
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('XML','1','vg','N-PX','u','2026-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date) VALUES ('XML','X','FOR','ISSUER','05/01/2024')")
    conn.commit()
    assert _ingest(conn) == 21
    assert _ingest(conn) == 21
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE accession=?", (ACC,)).fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM filings WHERE accession=?", (ACC,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM legacy_parse").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM votes WHERE accession='XML'").fetchone()[0] == 1


def test_a_rejected_reingest_removes_the_earlier_accepted_rows(conn, monkeypatch):
    _ingest(conn)
    real = legacy_iss_lines.parse
    monkeypatch.setattr(legacy_iss_lines, "parse", lambda t: real(t)[1:])
    assert _ingest(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0


def test_a_prior_no_cover_record_is_upgraded(conn):
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 f"retrieval_date, report_type) VALUES ('{ACC}','1','vg','N-PX','u',"
                 "'2026-01-01','LEGACY_NO_COVER')")
    assert _ingest(conn) == 21
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 1


def test_candidate_filter_is_legacy_pes():
    assert legacy_iss.is_candidate(_filing())
    assert not legacy_iss.is_candidate(_filing(period="2022-06-30"))


def test_from_sources_uses_the_cache_loader_and_ingests(conn, tmp_path, monkeypatch):
    d = tmp_path / ACC
    d.mkdir()
    (d / "doc.txt.gz").write_bytes(gzip.compress(BASIC.encode()))
    (d / f"{ACC}.hdr.sgml").write_text(HDR)
    monkeypatch.setattr(legacy_pe, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(legacy_pe.http, "get",
                        lambda *a, **k: pytest.fail("network used despite cache"))
    assert legacy_iss.ingest_filing_from_sources(conn, _filing(), "vg", "2026-11-21") == 21


def test_from_sources_returns_none_for_a_non_iss_filing(conn, monkeypatch):
    monkeypatch.setattr(legacy_pe, "load_filing_texts",
                        lambda f, cache_dir=None: ({"a": "Agenda Number: 1"}, HDR))
    assert legacy_iss.ingest_filing_from_sources(conn, _filing(), "vg", "2026-11-21") is None
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0


# -- quarantine --------------------------------------------------------------

def test_rows_are_excluded_by_the_shared_predicate_and_xml_rows_pass(conn):
    _ingest(conn)
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('XML','1','vg','N-PX','u','2026-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date) VALUES ('XML','X','FOR','ISSUER','05/01/2024')")
    conn.commit()
    ledger.dedupe_votes(conn)
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 22
    assert conn.execute(
        f"SELECT COUNT(*) FROM votes WHERE is_duplicate=0 AND {ledger.NON_LEGACY_VOTE_SQL}"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM votes WHERE legacy_format='iss_text' AND "
        f"{ledger.NON_LEGACY_VOTE_SQL}").fetchone()[0] == 0


# -- ingest_npx dispatch -----------------------------------------------------

def _npx_run(conn, monkeypatch, docs, **flags):
    import requests

    from glasshouse.ingest import npx

    def no_cover(url, *a, **k):
        r = requests.Response()
        r.status_code = 404
        raise requests.HTTPError(response=r)

    monkeypatch.setattr(npx, "list_filings", lambda *a, **k: [_filing()])
    monkeypatch.setattr(npx.http, "get", no_cover)
    monkeypatch.setattr(legacy_pe, "load_filing_texts", lambda f, cache_dir=None: (docs, HDR))
    return npx.ingest_npx(conn, "0000100001", institution_id="vg", **flags)


def test_npx_flag_routes_iss_filings(conn, monkeypatch):
    st = _npx_run(conn, monkeypatch, {"a": BASIC}, legacy_iss_text=True)
    assert st["votes"] == 21 and st["filings"] == 1
    assert conn.execute("SELECT report_type FROM filings").fetchone()[0] == "LEGACY_ISS"


def test_npx_iss_flag_alone_never_records_a_proxyedge_or_unknown_filing(conn, monkeypatch):
    for docs in ({"a": "Agenda Number: 1"}, {"a": "nothing"}):
        st = _npx_run(conn, monkeypatch, docs, legacy_iss_text=True)
        assert st.get("no_format") == 1 and st["votes"] == 0
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0


def test_npx_both_flags_send_each_format_to_its_parser(conn, monkeypatch):
    st = _npx_run(conn, monkeypatch, {"a": BASIC}, legacy_iss_text=True, legacy_proxyedge=True)
    assert st["votes"] == 21
    conn.execute("DELETE FROM votes")
    conn.execute("DELETE FROM filings")
    conn.commit()
    assert _npx_run(conn, monkeypatch, {"a": "nothing"}, legacy_iss_text=True,
                    legacy_proxyedge=True).get("no_format") == 1


def test_iss_text_without_the_form_banner_is_detected():
    # State Street's 2023 N-PX documents (e.g. 0001193125-23-286243) carry the ISS meeting
    # blocks and column header but no "FORM N-Px REPORT" banner.
    from glasshouse.ingest import legacy_iss
    body = ("<PRE>\nA.P. MOLLER-MAERSK A/S\n\nTicker:       MAERSK.B       Security ID:  K0514G135\n"
            "#     Proposal                                Mgt Rec   Vote Cast    Sponsor\n")
    assert legacy_iss.is_iss_text(body)
    assert not legacy_iss.is_iss_text("Proposal Vote Cast Sponsor in running prose")


def _record_no_cover(conn, filing):
    conn.execute("""INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                    period_of_report, report_type, source_url, retrieval_date)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (filing.accession_number, filing.cik, "vg", "N-PX", filing.filing_date,
                  filing.period_of_report, "LEGACY_NO_COVER", "https://www.sec.gov/x", "2026-01-01"))
    conn.commit()


def test_a_no_cover_filing_that_is_not_ingested_keeps_its_record(conn, monkeypatch):
    # Regression: the legacy flags deleted LEGACY_NO_COVER rows up front, so a filing
    # in neither format (or outside the 2023 period) vanished from `filings`.
    _record_no_cover(conn, _filing())
    st = _npx_run(conn, monkeypatch, {"a": "nothing"}, legacy_iss_text=True)
    assert st.get("no_format") == 1
    assert [tuple(r) for r in conn.execute("SELECT report_type FROM filings")] == [("LEGACY_NO_COVER",)]


def test_a_no_cover_filing_in_iss_format_is_upgraded(conn, monkeypatch):
    _record_no_cover(conn, _filing())
    st = _npx_run(conn, monkeypatch, {"a": BASIC}, legacy_iss_text=True)
    assert st["votes"] == 21
    assert [tuple(r) for r in conn.execute("SELECT report_type FROM filings")] == [("LEGACY_ISS",)]


def test_a_no_cover_proxyedge_filing_is_kept_when_only_the_iss_flag_is_on(conn, monkeypatch):
    _record_no_cover(conn, _filing())
    _npx_run(conn, monkeypatch, {"a": "Agenda Number: 1"}, legacy_iss_text=True)
    assert [tuple(r) for r in conn.execute("SELECT report_type FROM filings")] == [("LEGACY_NO_COVER",)]
