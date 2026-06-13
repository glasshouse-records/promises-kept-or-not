"""Tests for N-PORT parsing, Fed CSV mapping, CourtListener allegation
invariant, and the digest renderer."""


from glasshouse import digest, ledger
from glasshouse.ingest import fed
from glasshouse.ingest.nport import iter_positions

NPORT_FIXTURE = """<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/nport">
  <!-- comment nodes must not break parsing -->
  <formData><invstOrSecs>
    <invstOrSec>
      <name>ORACLE CORP</name>
      <lei>1Z4GXXU7ZHVWFCD8TV52</lei>
      <title>Oracle Corporation</title>
      <cusip>68389X105</cusip>
      <identifiers><isin value="US68389X1054"/></identifiers>
      <balance>41000000.00</balance>
      <valUSD>7100000000.00</valUSD>
      <pctVal>2.41</pctVal>
    </invstOrSec>
  </invstOrSecs></formData>
</edgarSubmission>"""

FED_CSV = (
    '"Effective Date","Termination Date","Banking Organization","Action","URL","Note"\n'
    '"01/15/2025","","Examplebank Corp","Written Agreement",'
    '"https://www.federalreserve.gov/x.pdf","Capital plan deficiencies"\n'
)


def test_nport_streaming_parser(tmp_path):
    p = tmp_path / "primary_doc.xml"
    p.write_text(NPORT_FIXTURE)
    rows = list(iter_positions(p))
    assert len(rows) == 1
    r = rows[0]
    assert r["cusip"] == "68389X105" and r["isin"] == "US68389X1054"
    assert r["lei"] == "1Z4GXXU7ZHVWFCD8TV52"
    assert r["value_usd"] == 7_100_000_000 and r["shares"] == 41_000_000.0


def test_fed_csv_mapping(monkeypatch):
    class Resp:
        text = FED_CSV
    monkeypatch.setattr(fed.http, "get", lambda *a, **k: Resp())
    actions = fed.fetch()
    assert len(actions) == 1
    a = actions[0]
    assert a.agency == "Federal Reserve"
    assert a.company_name == "Examplebank Corp"
    assert a.action_date == "2025-01-15"
    assert a.resolution_type == "administrative_action"
    assert "Written Agreement" in a.description
    assert a.source_url.endswith(".pdf")


def test_courtlistener_rows_are_always_allegations(monkeypatch):
    from glasshouse.ingest import courtlistener as cl
    monkeypatch.setattr(cl.http, "get_json", lambda *a, **k: {"results": [{
        "caseName": "Doe v. Examplebank", "docketNumber": "1:26-cv-001",
        "court": "S.D.N.Y.", "dateFiled": "2026-01-02", "absolute_url": "/d/1/"}]})
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    rows = cl.fetch_for(["Examplebank"])
    assert len(rows) == 1
    assert rows[0].resolution_type == "allegation"
    assert rows[0].is_allegation
    assert "PENDING MATTER" in rows[0].description
    # Allegations score zero in the concern index — the invariant that
    # keeps dockets from ever moving a number.
    from glasshouse.scoring import concern_index
    s = concern_index([{"resolution_type": "allegation", "action_date": "2026-01-02"}])
    assert s["raw"] == 0.0 and s["n_scored_actions"] == 0


def test_digest_renders_to_outbox(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "DIGEST_DIR", tmp_path / "outbox")
    conn = ledger.connect(tmp_path / "test.db")
    from glasshouse.ledger import EnforcementAction
    ledger.insert_enforcement(conn, [EnforcementAction(
        agency="SEC", company_name="Oracle Corporation", action_date="2012-08-16",
        resolution_type="civil_settlement", primary_ref="SEC Rel. 34-67574",
        source_url="https://www.sec.gov/x")])
    path = digest.render(conn)
    body = open(path).read()
    assert "Glasshouse digest" in body
    assert "1 new enforcement actions" in body
    assert "pending human review" in body
