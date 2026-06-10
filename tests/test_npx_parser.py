from pathlib import Path

from glasshouse.ingest.npx import iter_vote_rows, parse_cover

FIXTURES = Path(__file__).parent / "fixtures"


def test_streaming_parser_yields_one_row_per_vote_record():
    rows = list(iter_vote_rows(FIXTURES / "npx_sample.xml"))
    # 2 voteRecords in table 1 + 1 in table 2 + 1 notes-only table = 4 rows
    assert len(rows) == 4

    oracle = [r for r in rows if r.issuer_name == "ORACLE CORP"]
    assert len(oracle) == 2, "MULTIPLE voteRecord elements must all be parsed"
    assert {r.how_voted for r in oracle} == {"AGAINST", "FOR"}
    assert all(r.cusip == "68389X105" for r in oracle)
    assert all(r.management_recommendation == "AGAINST" for r in oracle)
    assert oracle[0].vote_description.startswith("Shareholder proposal")

    msft = [r for r in rows if r.issuer_name == "MICROSOFT CORP"][0]
    assert msft.shares_voted == 9_000_000
    assert msft.shares_on_loan == 120.5
    assert msft.category_type == "DIRECTOR ELECTIONS"
    assert msft.vote_series == "S000004358"


def test_notes_only_proxy_table_still_recorded():
    rows = list(iter_vote_rows(FIXTURES / "npx_sample.xml"))
    notes = [r for r in rows if r.issuer_name == "NOTES ONLY HOLDINGS PLC"]
    assert len(notes) == 1
    assert notes[0].how_voted == ""


def test_max_tables_limits_work():
    rows = list(iter_vote_rows(FIXTURES / "npx_sample.xml", max_tables=1))
    assert {r.issuer_name for r in rows} == {"ORACLE CORP"}


def test_cover_parse_detects_notice_and_series_leis():
    cover = parse_cover((FIXTURES / "npx_cover_notice.xml").read_bytes())
    assert cover.is_notice_only
    assert cover.reporting_person == "iShares Trust"
    assert cover.period_of_report == "06/30/2025"
    assert len(cover.series) == 2
    assert cover.series[0] == {
        "series_id": "S000004357",
        "name": "iShares 1-3 Year Treasury Bond ETF",
        "lei": "549300W0WX9TL4G6HM56",
    }
