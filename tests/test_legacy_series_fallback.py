"""SEC series-dataset fallback for legacy fund -> series mapping: it only fills a heading
the filing's own header has no candidate for, within the filing's own registrant CIK, on
an exact match (same normalisation as the header path) to exactly one series."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from test_legacy_iss import MGMT, make_doc
from test_legacy_pe import BASIC as PE_BASIC
from test_legacy_pe import FUND, _filing

from glasshouse import ledger
from glasshouse.ingest import legacy_iss, legacy_pe, sec_series

CIK = "0001217286"
SID = "S000009001"
HDR_OTHER = "<SERIES-ID>S000000001\n<SERIES-NAME>Some Other Fund\n"


def _csv(tmp_path, *rows):
    p = tmp_path / "ds.csv"
    p.write_text("Reporting File Number,CIK Number,Entity Name,Entity Org Type,Series ID,"
                 "Series Name,Class ID,Class Name,Class Ticker\n"
                 + "".join(f"811-1,{c},Trust,30,{s},{n},C000000001,A,XX\n" for c, s, n in rows))
    return p


def _ds(tmp_path, *rows):
    return sec_series.load_dataset([_csv(tmp_path, *rows)])


def _fb(ds, hdr=HDR_OTHER, cik=CIK):
    return legacy_pe.build_fallback(ds, cik, hdr)


def _row(heading=FUND):
    return {"fund_name": heading, "issuer_name": "ACME", "agenda_number": "1",
            "security_id": "123456789", "ticker": "AC", "isin": "", "meeting_type": "Annual",
            "meeting_date": "2023-01-25", "proposal_id": "1", "proposal_text": "x",
            "proposal_type": "Mgmt", "vote": "For", "for_against_management": "For"}


def _map(heading, fb):
    return legacy_pe.to_vote_rows([_row(heading)], {"some other fund": "S000000001"},
                                  fallback=fb)


def test_exact_match_in_own_registrant_maps_and_is_marked(tmp_path):
    fb = _fb(_ds(tmp_path, (CIK, SID, FUND)))
    (v,), info = _map(FUND, fb)
    assert v["vote_series"] == SID
    assert dict(info["series_fallback"]) == {(FUND, SID): 1}


def test_another_registrants_identical_series_name_does_not_map(tmp_path):
    fb = _fb(_ds(tmp_path, ("0000999999", SID, FUND)))
    assert fb is None
    rows, info = _map(FUND, fb)
    assert rows == [] and info["funds_unmapped"] == {FUND: 1}


def test_two_series_with_the_same_name_stay_unmapped(tmp_path):
    ds = _ds(tmp_path, (CIK, SID, FUND), (CIK, "S000009002", FUND.upper()))
    rows, info = _map(FUND, _fb(ds))
    assert rows == [] and info["funds_unmapped"] == {FUND: 1}


def test_same_series_listed_for_many_classes_is_one_match(tmp_path):
    ds = _ds(tmp_path, (CIK, SID, FUND), (CIK, SID, FUND))
    (v,), _ = _map(FUND, _fb(ds))
    assert v["vote_series"] == SID


def test_header_candidate_means_dataset_is_not_consulted(tmp_path):
    ds = _ds(tmp_path, (CIK, SID, FUND))
    # header names the fund under ANOTHER series: header wins
    hdr = f"<SERIES-ID>S000000007\n<SERIES-NAME>{FUND}\n"
    (v,), info = legacy_pe.to_vote_rows(
        [_row()], legacy_pe.series_map(hdr), fallback=_fb(ds, hdr))
    assert v["vote_series"] == "S000000007" and "series_fallback" not in info


def test_ambiguous_header_name_is_still_a_header_candidate(tmp_path):
    ds = _ds(tmp_path, (CIK, SID, FUND))
    hdr = (f"<SERIES-ID>S000000007\n<SERIES-NAME>{FUND}\n"
           f"<SERIES-ID>S000000008\n<SERIES-NAME>{FUND.upper()}\n")
    rows, info = legacy_pe.to_vote_rows([_row()], legacy_pe.series_map(hdr),
                                        fallback=_fb(ds, hdr))
    assert rows == [] and info["funds_unmapped"] == {FUND: 1}


def test_a_reviewed_alias_for_the_heading_blocks_the_dataset(tmp_path):
    ds = _ds(tmp_path, (CIK, SID, FUND))
    rows, _ = legacy_pe.to_vote_rows([_row()], {}, {FUND: "S000000099"}, {"S000000001"},
                                     fallback=_fb(ds))
    assert rows == []


def test_no_fuzzy_matching(tmp_path):
    fb = _fb(_ds(tmp_path, (CIK, SID, FUND)))
    for h in (FUND + " II", FUND[:-1], FUND.replace("Mid", "Midcap")):
        assert fb.lookup(h) is None


def test_iss_suffix_rule_matches_header_path(tmp_path):
    fb = _fb(_ds(tmp_path, (CIK, SID, FUND)))
    assert fb.lookup(FUND + " - CLASS A", suffix=True) == SID
    assert fb.lookup(FUND + " - CLASS A") is None


@given(st.text(max_size=40), st.sampled_from(["", " ", "  ", "(R)", "®", "™", "(SM)"]))
def test_lookup_normalisation_is_the_header_normalisation(name, junk):
    """Whatever spelling-noise _norm removes from the heading, the fallback treats the
    same as the header path does: same key, same answer."""
    if not legacy_pe._norm(name):
        return
    noisy = f"{junk}{name}{junk}"
    smap = legacy_pe.series_map(f"<SERIES-ID>S000000001\n<SERIES-NAME>{name}\n")
    fb = legacy_pe.SeriesFallback({legacy_pe._norm(name): "S000000001"}, set())
    assert (smap.get(legacy_pe._norm(noisy)) is not None) == (fb.lookup(noisy) is not None) \
        or "<" in name or "\n" in name


# -- through ingest_filing, all parsers -----------------------------------------

def _conn(tmp_path):
    c = ledger.connect(tmp_path / "l.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('jpm','JPM')")
    return c


def test_ingest_filing_pe_maps_via_dataset_and_records_provenance(tmp_path):
    c = _conn(tmp_path)
    ds = _ds(tmp_path, (CIK, SID, FUND))
    n = legacy_pe.ingest_filing(c, _filing(), "jpm", "2026-11-27", {"d.txt": PE_BASIC},
                                HDR_OTHER, series_dataset=ds)
    assert n == 12
    assert {r[0] for r in c.execute("SELECT vote_series FROM votes")} == {SID}
    fb = c.execute("SELECT series_fallback FROM legacy_parse").fetchone()[0]
    assert fb == repr([(FUND, SID, 12)])


def test_ingest_filing_without_dataset_is_unchanged(tmp_path):
    c = _conn(tmp_path)
    n = legacy_pe.ingest_filing(c, _filing(), "jpm", "2026-11-27", {"d.txt": PE_BASIC},
                                HDR_OTHER)
    assert n == 0
    assert c.execute("SELECT series_fallback FROM legacy_parse").fetchone()[0] == ""


def test_iss_ingest_maps_via_dataset_for_its_own_registrant_only(tmp_path):
    heading = "ACME GROWTH FUND - INVESTOR SHARES"
    doc = make_doc(heading, [MGMT] * 2)
    iss_cik = "0000100001"
    filing = legacy_iss_filing(iss_cik)
    c = _conn(tmp_path)
    ds = _ds(tmp_path, (iss_cik, SID, "Acme Growth Fund"), ("0000999999", "S000009003",
                                                           "Acme Growth Fund"))
    n = legacy_iss.ingest_filing(c, filing, "jpm", "2026-11-27", {"d": doc}, HDR_OTHER,
                                 series_dataset=ds)
    assert n == 2
    assert {r[0] for r in c.execute("SELECT vote_series FROM votes")} == {SID}
    assert c.execute("SELECT series_fallback FROM legacy_parse").fetchone()[0] == repr(
        [(heading, SID, 2)])


def legacy_iss_filing(cik):
    from glasshouse.ingest.edgar import Filing
    return Filing(cik=cik, company_name="V", form_type="N-PX", filing_date="2023-08-30",
                  period_of_report="2023-06-30", accession_number="0001104659-23-095672")
