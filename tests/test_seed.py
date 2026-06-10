import pytest

from glasshouse import ledger, seed
from glasshouse.seed import infer_resolution_type


@pytest.fixture
def conn(tmp_path):
    return ledger.connect(tmp_path / "test.db")


def test_infer_resolution_type_is_conservative():
    assert infer_resolution_type(
        "Siemens AG (parent) entered DPA; three subsidiaries pleaded guilty") == "dpa"
    assert infer_resolution_type("XYZ Corp pleaded guilty to price fixing") == "guilty_plea"
    assert infer_resolution_type("resolved via non-prosecution agreement") == "npa"
    assert infer_resolution_type("SEC charged the company; civil penalty paid") == "civil_settlement"
    # Anything ambiguous goes to quarantine, never to a guess.
    assert infer_resolution_type("the company paid a fine") == "unverified"


def test_seed_load_all_inserts_and_is_idempotent(conn):
    counts = seed.load_all(conn)
    total = sum(counts.values())
    assert total > 200, f"expected substantial curated coverage, got {counts}"
    # Idempotent: second load inserts nothing.
    counts2 = seed.load_all(conn)
    assert sum(counts2.values()) == 0

    # Every seeded row must satisfy ledger invariants.
    problems = ledger.integrity_check(conn)
    assert problems["enforcement_missing_provenance"] == []
    assert problems["enforcement_bad_resolution_type"] == []

    # And all seeded rows must be marked as curated snapshots.
    n_live = conn.execute(
        "SELECT COUNT(*) FROM enforcement_actions WHERE source_kind != 'curated_snapshot'"
    ).fetchone()[0]
    assert n_live == 0
