"""The meeting-date reading is expensive; every query must build it once per row.
A release stalled ~5 h in the datasheet (2026-11-23): the season table pasted the
reading 9 times and each reading pasted the candidate date 3 times (27 per row)."""
from glasshouse import dataset
from glasshouse.ledger import iso_meeting_date

ONE = iso_meeting_date("c").count("printf(")   # copies inside a single candidate


def test_reading_builds_the_candidate_once():
    assert ONE == 4                    # 2 M/D/YYYY + 2 M/D/YY branches, one candidate


def test_season_query_reads_each_date_once():
    assert dataset.season_coverage_sql().count("printf(") == ONE


def test_coverage_bounds_read_each_date_once():
    assert dataset.coverage_vote_sql()[0].count("printf(") == ONE


def test_datasheet_examples_of_unreadable_dates_are_unreadable():
    # v2026-11-22's first build cited `20240425`, which IS read (as 2024-04-25).
    import sqlite3
    db = sqlite3.connect(":memory:")
    assert dataset.UNREADABLE_DATE_EXAMPLES
    for raw in dataset.UNREADABLE_DATE_EXAMPLES:
        out = db.execute(f"SELECT {iso_meeting_date('d')} FROM (SELECT ? AS d)", (raw,)).fetchone()[0]
        assert out == raw, raw
