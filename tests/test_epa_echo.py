"""EPA ECHO bulk-case ingester (case_downloads.zip, weekly).

Precision-first rules under test:
  • only defendants exactly matching (normalized) our curated fossil-company
    names — subsidiaries like "BP PRODUCTS NORTH AMERICA" do NOT match "BP plc"
    (conservative undercount, never a parent-attribution guess);
  • only concluded cases with an assessed penalty > 0 and a case-status date —
    excludes open matters and multi-PRP Superfund pileups with no penalty;
  • Judicial → civil_violation; Administrative → administrative_action;
    criminal and anything else → skipped (outcome parsing is ambiguous);
  • company_name is the defendant AS FILED (verbatim provenance);
  • every row carries the ECHO case-report source_url + primary_ref;
  • the parser survives the NUL bytes present in the real CSVs.
"""

import csv
import io
import zipfile

import pytest

from glasshouse.ingest import epa_echo

ENF_COLS = ["ACTIVITY_ID", "ACTIVITY_NAME", "STATE_CODE", "REGION_CODE", "FISCAL_YEAR",
            "CASE_NUMBER", "CASE_NAME", "ACTIVITY_TYPE_CODE", "ACTIVITY_TYPE_DESC",
            "ACTIVITY_STATUS_CODE", "ACTIVITY_STATUS_DESC", "ACTIVITY_STATUS_DATE",
            "LEAD", "CASE_STATUS_DATE", "DOJ_DOCKET_NMBR", "ENF_OUTCOME_CODE",
            "ENF_OUTCOME_DESC", "TOTAL_PENALTY_ASSESSED_AMT", "TOTAL_COST_RECOVERY_AMT",
            "TOTAL_COMP_ACTION_AMT", "HQ_DIVISION", "BRANCH",
            "VOLUNTARY_SELF_DISCLOSURE_FLAG", "MULTIMEDIA_FLAG", "ENF_SUMMARY_TEXT"]
DEF_COLS = ["ACTIVITY_ID", "CASE_NUMBER", "DEFENDANT_NAME",
            "NAMED_IN_COMPLAINT_FLAG", "NAMED_IN_SETTLEMENT_FLAG"]


def _csv(cols, rows):
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue()


def _enf(aid, case, name, typ, penalty, date, status="Final Order Entered"):
    return {"ACTIVITY_ID": aid, "CASE_NUMBER": case, "CASE_NAME": name,
            "ACTIVITY_TYPE_DESC": typ, "ACTIVITY_STATUS_DESC": status,
            "CASE_STATUS_DATE": date, "TOTAL_PENALTY_ASSESSED_AMT": penalty,
            "ENF_SUMMARY_TEXT": f"summary of {name}"}


@pytest.fixture
def fixture_zip(tmp_path):
    enf = _csv(ENF_COLS, [
        _enf("101", "02-2019-0001", "US v Exxon Mobil", "Judicial", "500000", "03/15/2019"),
        _enf("102", "02-2020-0002", "In re Chevron", "Administrative - Formal", "1000", "07/01/2020"),
        _enf("103", "02-2021-0003", "US v Chevron (open)", "Judicial", "", "01/01/2021"),
        _enf("104", "02-2018-0004", "US v Someone (criminal)", "Criminal", "900000", "05/05/2018"),
        _enf("105", "02-2017-0005", "US v BP Products", "Judicial", "250000", "02/02/2017"),
        _enf("106", "02-2016-0006", "US v Smallco", "Judicial", "10000", "06/06/2016"),
    ])
    defendants = _csv(DEF_COLS, [
        {"ACTIVITY_ID": "101", "CASE_NUMBER": "02-2019-0001",
         "DEFENDANT_NAME": "EXXON MOBIL CORP.", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        {"ACTIVITY_ID": "102", "CASE_NUMBER": "02-2020-0002",
         "DEFENDANT_NAME": "CHEVRON CORPORATION", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        {"ACTIVITY_ID": "103", "CASE_NUMBER": "02-2021-0003",
         "DEFENDANT_NAME": "CHEVRON CORPORATION", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        {"ACTIVITY_ID": "104", "CASE_NUMBER": "02-2018-0004",
         "DEFENDANT_NAME": "EXXON MOBIL CORPORATION", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        # Subsidiary — must NOT match BP plc (conservative):
        {"ACTIVITY_ID": "105", "CASE_NUMBER": "02-2017-0005",
         "DEFENDANT_NAME": "BP PRODUCTS NORTH AMERICA INC", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        {"ACTIVITY_ID": "106", "CASE_NUMBER": "02-2016-0006",
         "DEFENDANT_NAME": "SMALLCO LLC", "NAMED_IN_SETTLEMENT_FLAG": "Y"},
        # Named in complaint only (not the settlement) — excluded:
        {"ACTIVITY_ID": "101", "CASE_NUMBER": "02-2019-0001",
         "DEFENDANT_NAME": "CHEVRON CORPORATION", "NAMED_IN_SETTLEMENT_FLAG": "N"},
    ])
    # The real files contain NUL bytes — the parser must survive them.
    enf = enf.replace("summary of In re Chevron", "summary of In re Chev\x00ron")
    p = tmp_path / "case_downloads.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("CASE_ENFORCEMENTS.csv", enf)
        z.writestr("CASE_DEFENDANTS.csv", defendants)
    return p


def test_parse_targets_only_concluded_penalized_exact_matches(fixture_zip):
    actions = epa_echo.parse(fixture_zip)
    by_ref = {a.primary_ref: a for a in actions}
    assert "02-2019-0001" in by_ref              # Exxon judicial, penalty, settled
    assert "02-2020-0002" in by_ref              # Chevron administrative, penalty
    assert "02-2021-0003" not in by_ref          # no penalty assessed (open/PRP)
    assert "02-2018-0004" not in by_ref          # criminal — skipped
    assert "02-2017-0005" not in by_ref          # subsidiary ≠ parent (BP)
    assert "02-2016-0006" not in by_ref          # not a curated company
    assert len(actions) == 2


def test_parsed_fields_carry_provenance(fixture_zip):
    a = {x.primary_ref: x for x in epa_echo.parse(fixture_zip)}["02-2019-0001"]
    assert a.agency == "EPA (ECHO)"
    assert a.company_name == "EXXON MOBIL CORP."          # verbatim, as filed
    assert a.resolution_type == "civil_violation"          # Judicial
    assert a.action_date == "2019-03-15"                   # ISO
    assert a.penalty_usd == 500000
    assert a.source_url == "https://echo.epa.gov/enforcement-case-report?id=101"
    assert not a.is_allegation


def test_administrative_maps_to_administrative_action(fixture_zip):
    a = {x.primary_ref: x for x in epa_echo.parse(fixture_zip)}["02-2020-0002"]
    assert a.resolution_type == "administrative_action"
    assert a.company_name == "CHEVRON CORPORATION"
