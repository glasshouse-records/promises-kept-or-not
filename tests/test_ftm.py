"""FollowTheMoney export — Glasshouse in the format journalists' tools speak.

FtM (followthemoney.tech) is the entity format of OCCRP Aleph / OpenAleph;
OpenSanctions ships it. Exporting our UNIQUE record (managers + the curated
enforcement universe) as FtM entities lets investigators import Glasshouse
straight into the tool they already use.

Honesty rules under test:
  • quarantine holds: 'allegation' (dockets) and 'unverified' rows are NEVER
    exported — this is a public artifact;
  • OFAC sanction designations are excluded too — OpenSanctions already ships
    them properly; we export what is unique to us, not a worse copy;
  • enforcement actions are 'Event' entities (an enforcement event involving a
    company) — not 'Sanction', because a DPA or civil settlement is not a
    sanction and legal categories are never collapsed;
  • every Event carries the resolution_type, date, source_url and primary_ref;
  • ids are deterministic (same input → same ids), so re-imports update
    rather than duplicate.
"""

import json

import pytest

from glasshouse import ftm, ledger
from glasshouse.ledger import EnforcementAction


@pytest.fixture
def conn(tmp_path):
    c = ledger.connect(tmp_path / "f.db")
    c.execute("INSERT INTO institutions (id, display_name, type, country) "
              "VALUES ('goldman_sachs','Goldman Sachs Group Inc.','asset_manager','USA')")
    ledger.insert_enforcement(c, [
        EnforcementAction(agency="DOJ/SEC (FCPA)", company_name="The Goldman Sachs Group, Inc.",
                          action_date="2020-10-22", resolution_type="dpa",
                          primary_ref="DOJ 20-1110", penalty_usd=2_900_000_000,
                          description="1MDB FCPA resolution",
                          source_url="https://justice.gov/x"),
        EnforcementAction(agency="EPA (ECHO)", company_name="CHEVRON CORPORATION",
                          action_date="1996-11-13", resolution_type="civil_violation",
                          primary_ref="HQ-1996-0048", penalty_usd=316_000,
                          description="CAA violations", source_url="https://echo.epa.gov/x"),
        # Quarantined classes — must NOT be exported:
        EnforcementAction(agency="Federal docket", company_name="BlackRock Inc.",
                          action_date="2026-01-01", resolution_type="allegation",
                          primary_ref="Docket-1", source_url="https://cl/x", is_allegation=True),
        EnforcementAction(agency="SEC", company_name="Mystery Corp",
                          action_date="2020-01-01", resolution_type="unverified",
                          primary_ref="", source_url="https://sec/x"),
        EnforcementAction(agency="OFAC (SDN)", company_name="ALDAR PROPERTIES",
                          action_date="2010-01-01", resolution_type="sanction_designation",
                          primary_ref="SDN-1", source_url="https://ofac/x"),
    ])
    c.commit()
    return c


def _entities(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_export_shape_and_quarantine(conn, tmp_path):
    out = tmp_path / "glasshouse.ftm.json"
    stats = ftm.export_ftm(conn, out)
    ents = _entities(out)
    schemas = {e["schema"] for e in ents}
    assert schemas <= {"Company", "Event"}
    names = {p for e in ents if e["schema"] == "Company"
             for p in e["properties"]["name"]}
    assert "Goldman Sachs Group Inc." in names          # the manager
    assert "CHEVRON CORPORATION" in names
    # Name VARIANTS of one company collapse to ONE entity: the defendant
    # "The Goldman Sachs Group, Inc." shares the manager's Company id, and the
    # DPA Event links to that same entity (no duplicate Goldmans in Aleph).
    from glasshouse.ftm import _cid
    assert _cid("The Goldman Sachs Group, Inc.") == _cid("Goldman Sachs Group Inc.")
    dpa = next(e for e in ents if e["schema"] == "Event"
               and "DOJ 20-1110" in e["properties"]["recordId"])
    assert dpa["properties"]["involved"] == [_cid("Goldman Sachs Group Inc.")]
    # Quarantine + OFAC exclusions hold on this public artifact:
    blob = out.read_text()
    assert "BlackRock" not in blob        # allegation — never exported
    assert "Mystery Corp" not in blob     # unverified — never exported
    assert "ALDAR" not in blob            # OFAC — OpenSanctions' job, and Aldar-class
    assert stats["events"] == 2


def test_events_carry_legal_character_and_provenance(conn, tmp_path):
    out = tmp_path / "g.ftm.json"
    ftm.export_ftm(conn, out)
    events = [e for e in _entities(out) if e["schema"] == "Event"]
    dpa = next(e for e in events if "DOJ 20-1110" in e["properties"]["recordId"])
    props = dpa["properties"]
    assert any("dpa" in s for s in props["summary"])       # legal category preserved
    assert props["startDate"] == ["2020-10-22"]
    assert props["sourceUrl"] == ["https://justice.gov/x"]
    assert props["involved"], "event not linked to its company entity"


def test_ids_are_deterministic(conn, tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    ftm.export_ftm(conn, a)
    ftm.export_ftm(conn, b)
    assert a.read_text() == b.read_text()
