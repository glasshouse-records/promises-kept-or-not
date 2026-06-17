"""The dataset-as-product layer: self-describing schema, honest coverage, and
a machine-readable package — generated from the data so it can't drift. Core
deliverable per the 2026-06-15 decision (the dataset is the product)."""

import pytest

from glasshouse import dataset, ledger
from glasshouse.ledger import EnforcementAction
from glasshouse.publish import OPERATOR_ONLY, PUBLIC_TABLES


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blackrock','BlackRock Inc.')")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('empty_co','Empty Co.')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('A1','1','blackrock','N-PX','u','d')")
    for dup in (0, 1):
        c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                  "how_voted, shares_voted, is_duplicate) VALUES "
                  "('A1','AMAZON','C','05/21/2025','AGAINST',1000,?)", (dup,))
    ledger.insert_enforcement(c, [EnforcementAction(
        agency="SEC", company_name="Oracle", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="LR-1", source_url="https://s")])
    c.commit()
    return c


def test_data_dictionary_covers_public_tables_only():
    # Every public table is documented; no operator table is.
    for t in PUBLIC_TABLES:
        assert t in dataset.DATA_DICTIONARY, f"{t} undocumented"
    for t in OPERATOR_ONLY:
        assert t not in dataset.DATA_DICTIONARY, f"{t} must not be in the public dictionary"


def test_coverage_is_honest(conn):
    cov = dataset.coverage(conn)
    names = {r["institution"] for r in cov}
    assert "BlackRock Inc." in names
    assert "Empty Co." not in names           # registered-but-empty omitted, not faked
    bl = next(r for r in cov if r["institution"] == "BlackRock Inc.")
    assert bl["votes"] == 1                    # dedup applied (2 rows, 1 real)


def test_datapackage_is_machine_describing(conn):
    pkg = dataset.build_datapackage(conn)
    assert pkg["name"] == "glasshouse-evidence"
    assert pkg["licenses"][0]["name"] == "CC-BY-4.0"
    assert any("is_duplicate = 0" in g for g in pkg["provenance_guarantees"])
    votes = next(r for r in pkg["resources"] if r["name"] == "votes")
    assert votes["rowCount"] == 1             # deduped count, matches the snapshot
    assert any(f["name"] == "is_duplicate" for f in votes["schema"]["fields"])


def test_datasheet_states_provenance_and_coverage(conn):
    sheet = dataset.build_datasheet(conn)
    assert "Provenance guarantees" in sheet
    assert "in force at the vote date" in sheet      # temporal guarantee advertised
    assert "BlackRock Inc." in sheet                  # coverage table
    assert "partial" in sheet.lower()                 # honest about boundaries
