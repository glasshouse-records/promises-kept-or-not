"""Review fixes to the legacy ingest: contests, voting-policy sections, no write lock
across loading, format detection, cache completeness, operator counts."""

from __future__ import annotations

import gzip

import pytest
import requests
from test_legacy_iss import BASIC, FUND, HDR, MGMT, SID, make_doc, make_html

from glasshouse import diff, ledger
from glasshouse.ingest import legacy_iss, legacy_pe, npx
from glasshouse.ingest.edgar import Filing

ACC = "0001104659-23-095672"
VG = "VANGUARD RUSSELL 1000 INDEX FUND"


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vg','Vanguard')")
    return c


def _filing(acc=ACC):
    return Filing(cik="0000100001", company_name="Vanguard", form_type="N-PX",
                  filing_date="2023-08-30", period_of_report="2023-06-30", accession_number=acc)


def _row(**kw):
    r = {"fund_heading": FUND, "issuer_name": "ILLUMINA, INC.", "security_id": "452327109",
         "meeting_date": "2023-05-25", "meeting_type": "PROXY CONTEST", "card_label": "",
         "rec_label": "Mgt Rec", "rec": "For", "vote": "For", "sponsor": "Security Holder",
         "proposal_text": "Elect Icahn Nominee Vincent J. Intrieri"}
    return {**r, **kw}


# -- 1. contests ------------------------------------------------------------

def test_contest_meeting_drops_rows_despite_mgt_rec_header_and_no_card_label():
    # 0001683863-23-006011: Icahn nominee printed under "Mgt Rec", no card label.
    out, info = legacy_iss.to_vote_rows(
        [_row(), _row(meeting_type="Proxy Contest", sponsor="Management")],
        {legacy_pe._norm(FUND): SID})
    assert out == [] and info["contest_rows_dropped"] == 2


def test_contest_meeting_dropped_in_text_and_html_style():
    for text, fmt in ((make_doc(FUND, [MGMT]).replace("Annual", "PROXY CONTEST"), "iss"),
                      (make_html().replace("ANNUAL", "PROXY CONTEST"), "iss_html")):
        rows, _ = legacy_iss.agreed(text, legacy_iss.PARSERS[fmt])
        assert len(rows) == 1 and "contest" in rows[0]["meeting_type"].lower()
        out, info = legacy_iss.to_vote_rows(rows, {legacy_pe._norm(FUND): SID}, fmt)
        assert out == [] and info["contest_rows_dropped"] == 1


# -- 2. voting-policy sections -------------------------------------------------

@pytest.mark.parametrize("suffix", ["GLASS LEWIS ESG POLICY", "COMPANY BOARD-ALIGNED POLICY",
                                    "NOT VOTING POLICY", "VANGUARD-ADVISED FUNDS POLICY",
                                    "not  voting   policy"])
def test_policy_sections_do_not_map_and_are_counted_separately(suffix):
    smap = {legacy_pe._norm(VG): SID}
    heading = f"{VG} - {suffix}"
    assert legacy_iss.series_for(heading, smap) is None
    out, info = legacy_iss.to_vote_rows(
        [_row(fund_heading=heading, meeting_type="Annual")], smap)
    assert out == [] and info["policy_section_dropped"] == 1 and info["unmapped"] == {}


def test_policy_sections_do_not_map_by_alias_but_subadviser_suffix_still_maps():
    smap = {legacy_pe._norm(VG): SID}
    h = f"{VG} - GLASS LEWIS ESG POLICY"
    assert legacy_iss.series_for(h, smap, {legacy_pe._heading(h): SID}, {SID}) is None
    assert legacy_iss.series_for(f"{VG} - Subadviser: Acme", smap) == SID


# -- 3 and 5. npx dispatch ---------------------------------------------------

def _record_no_cover(conn, filing):
    conn.execute("""INSERT INTO filings (accession, cik, institution_id, form_type, filing_date,
                    period_of_report, report_type, source_url, retrieval_date)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (filing.accession_number, filing.cik, "vg", "N-PX", filing.filing_date,
                  filing.period_of_report, "LEGACY_NO_COVER", "https://www.sec.gov/x", "2026-01-01"))
    conn.commit()


def test_no_write_lock_is_held_while_documents_are_loaded(conn, monkeypatch):
    for docs in ({"a": BASIC}, {"a": "Agenda Number: 1"}):
        _record_no_cover(conn, _filing())
        seen = []

        def loader(f, cache_dir=None, docs=docs, seen=seen):
            seen.append(conn.in_transaction)
            return docs, HDR

        def get(url, *a, seen=seen, **k):
            seen.append(conn.in_transaction)
            r = requests.Response()
            r.status_code = 404
            raise requests.HTTPError(response=r)
        monkeypatch.setattr(npx, "list_filings", lambda *a, **k: [_filing()])
        monkeypatch.setattr(npx.http, "get", get)
        monkeypatch.setattr(legacy_pe, "load_filing_texts", loader)
        npx.ingest_npx(conn, "0000100001", institution_id="vg",
                       legacy_iss_text=True, legacy_proxyedge=True)
        assert len(seen) >= 2 and not any(seen), seen
        conn.execute("DELETE FROM votes")
        conn.execute("DELETE FROM filings")
        conn.commit()


def test_a_proxyedge_only_run_never_records_an_iss_filing_as_rejected(conn, monkeypatch):
    def get(url, *a, **k):
        r = requests.Response()
        r.status_code = 404
        raise requests.HTTPError(response=r)
    monkeypatch.setattr(npx, "list_filings", lambda *a, **k: [_filing()])
    monkeypatch.setattr(npx.http, "get", get)
    monkeypatch.setattr(legacy_pe, "load_filing_texts", lambda f, cache_dir=None: ({"a": BASIC}, HDR))
    st = npx.ingest_npx(conn, "0000100001", institution_id="vg", legacy_proxyedge=True)
    assert st.get("no_format") == 1 and st["votes"] == 0
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0


# -- 4. cache completeness -----------------------------------------------------

PE_HDR = HDR


class _Resp:
    def __init__(self, raw):
        self.content = raw
        self.text = raw.decode()


def _fake_net(monkeypatch, names, fail_on=None, calls=None):
    def get(url, *a, **k):
        if calls is not None:
            calls.append(url)
        if fail_on and url.endswith(fail_on):
            raise RuntimeError("download failed")
        return _Resp(PE_HDR.encode() if url.endswith(".hdr.sgml") else BASIC.encode())
    monkeypatch.setattr(legacy_pe.http, "get", get)
    monkeypatch.setattr(legacy_pe, "list_documents", lambda f: list(names))


def test_failed_download_leaves_no_marker_and_is_refetched(tmp_path, monkeypatch):
    _fake_net(monkeypatch, ["a.txt", "b.txt"], fail_on="b.txt")
    with pytest.raises(RuntimeError):
        legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert not (tmp_path / ACC / legacy_pe.COMPLETE_MARKER).exists()
    calls = []
    _fake_net(monkeypatch, ["a.txt", "b.txt"], calls=calls)
    docs, hdr = legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert set(docs) == {"a.txt", "b.txt"} and hdr == PE_HDR
    assert any(u.endswith("b.txt") for u in calls)
    assert (tmp_path / ACC / legacy_pe.COMPLETE_MARKER).exists()


def test_marked_cache_is_used_without_network(tmp_path, monkeypatch):
    _fake_net(monkeypatch, ["a.txt"])
    legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    monkeypatch.setattr(legacy_pe.http, "get", lambda *a, **k: pytest.fail("network"))
    monkeypatch.setattr(legacy_pe, "list_documents", lambda f: pytest.fail("network"))
    docs, _ = legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert set(docs) == {"a.txt"}


def _old_cache(tmp_path, names, hdr=True):
    d = tmp_path / ACC
    d.mkdir()
    for n in names:
        (d / f"{n}.gz").write_bytes(gzip.compress(BASIC.encode()))
    if hdr:
        (d / f"{ACC}.hdr.sgml").write_text(PE_HDR)
    return d


def test_unmarked_cache_matching_the_listing_is_adopted_and_marked(tmp_path, monkeypatch):
    d = _old_cache(tmp_path, ["a.txt"])
    calls = []
    _fake_net(monkeypatch, ["a.txt"], calls=calls)
    legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert calls == [] and (d / legacy_pe.COMPLETE_MARKER).exists()


def test_unmarked_partial_cache_is_refetched(tmp_path, monkeypatch):
    d = _old_cache(tmp_path, ["a.txt"])
    _fake_net(monkeypatch, ["a.txt", "b.txt"])
    docs, _ = legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert set(docs) == {"a.txt", "b.txt"} and (d / legacy_pe.COMPLETE_MARKER).exists()


def test_unmarked_cache_without_header_is_refetched(tmp_path, monkeypatch):
    _old_cache(tmp_path, ["a.txt"], hdr=False)
    calls = []
    _fake_net(monkeypatch, ["a.txt"], calls=calls)
    legacy_pe.load_filing_texts(_filing(), cache_dir=tmp_path)
    assert any(u.endswith("a.txt") for u in calls)


# -- 6. operator counts --------------------------------------------------------

def _vote(conn, legacy_format):
    conn.execute("INSERT OR IGNORE INTO filings (accession, cik, institution_id, form_type, "
                 "source_url, retrieval_date) VALUES ('A','1','vg','N-PX','u','2026-01-01')")
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, vote_source, "
                 "meeting_date, legacy_format) VALUES ('A','X','FOR','ISSUER','05/01/2023',?)",
                 (legacy_format,))
    conn.commit()


def test_diff_new_votes_exclude_quarantined_legacy_rows(conn):
    _vote(conn, None)
    _vote(conn, "iss_text")
    assert diff.compute(conn).new_votes == 1            # no prior run
    diff.record_run(conn)
    _vote(conn, None)
    _vote(conn, "iss_text")
    assert diff.compute(conn).new_votes == 1


def test_dedupe_command_total_excludes_quarantined_legacy_rows(conn, monkeypatch, capsys):
    from glasshouse import cli
    _vote(conn, None)
    _vote(conn, "iss_text")
    monkeypatch.setattr(cli, "_conn", lambda: conn)
    cli.cmd_dedupe(None)
    assert " of 1 " in capsys.readouterr().out
