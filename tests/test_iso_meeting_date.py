"""iso_meeting_date: filer-written meeting dates to ISO, never a guessed date."""
import sqlite3
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from glasshouse.ledger import iso_meeting_date

_DB = sqlite3.connect(":memory:")
_SQL = f"SELECT {iso_meeting_date('d')} FROM (SELECT ? AS d)"


def norm(v):
    return _DB.execute(_SQL, (v,)).fetchone()[0]


@pytest.mark.parametrize("raw,want", [
    ("20240425", "2024-04-25"),
    ("30/07/2023", "2023-07-30"),
    ("30/11/2024", "2024-11-30"),
    ("13/1/2024", "2024-01-13"),
    ("06/30/2025", "2025-06-30"),
    ("9/30/2025", "2025-09-30"),
    ("01/23/24", "2024-01-23"),
    ("12/11/2024", "2024-12-11"),   # A <= 12: month-first, unchanged
    ("2024-04-25", "2024-04-25"),
    # not a real date: returned unchanged
    ("30/24/2024", "30/24/2024"),
    ("00", "00"),
    ("148850", "148850"),
    ("20241325", "20241325"),
    ("20240400", "20240400"),
    ("20240432", "20240432"),
    ("", ""),
])
def test_cases(raw, want):
    assert norm(raw) == want


def test_null_stays_null():
    assert norm(None) is None


@given(st.dates(min_value=date(1990, 1, 1), max_value=date(2099, 12, 31)))
def test_roundtrip(d):
    iso = d.isoformat()
    assert norm(f"{d.month}/{d.day}/{d.year}") == iso
    assert norm(f"{d.month:02d}/{d.day:02d}/{d.year}") == iso
    assert norm(d.strftime("%Y%m%d")) == iso
    if d.day > 12:
        assert norm(f"{d.day}/{d.month}/{d.year}") == iso
        assert norm(f"{d.day:02d}/{d.month:02d}/{d.year}") == iso
