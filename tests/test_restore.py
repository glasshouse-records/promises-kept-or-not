"""`glasshouse restore`: a ledger from a release bundle, so the engine builds without
a full SEC ingest. Pins: the manifest is verified, a non-empty ledger is never
overwritten, restored votes are is_duplicate=0 and equal the shipped rows, the
ledger says it was restored, and the engine says so when policy text is absent."""

import hashlib
import sqlite3

import pytest

from glasshouse import engine, ledger, release, restore
from glasshouse.ledger import EnforcementAction

REGISTRY = {"vanguard": {
    "display_name": "Vanguard",
    "npx_ciks": [{"cik": "0000000001", "name": "Vanguard Trust", "adviser_key": "VCM"}],
    "commitments": [{"label": "policy", "adviser_key": "VCM"}],
}}


@pytest.fixture
def bundle(tmp_path):
    src = ledger.connect(tmp_path / "src.db")
    src.execute("INSERT INTO institutions (id, display_name, cik) "
                "VALUES ('vanguard','Vanguard','0000102909')")
    src.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                "retrieval_date) VALUES ('ACC-1','1','vanguard','N-PX','https://e','2026-06-11')")
    for desc, dup in (("ELECT A", 0), ("ELECT A", 1), ("CLIMATE REPORT", 0)):
        src.execute(
            "INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
            "category_type, vote_source, how_voted, shares_voted, management_recommendation, "
            "is_duplicate) VALUES ('ACC-1','ACME','000000001','2025-05-01',?,"
            "'SHAREHOLDER PROPOSALS','SECURITY HOLDER','AGAINST',500,'AGAINST',?)", (desc, dup))
    src.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                "sha256, content_path, text_sha256, wayback_timestamp) VALUES "
                "('vanguard','policy','https://v/p.pdf','2026-06-11','aa','/maintainer/p.pdf',"
                "'tt','20240101000000')")
    src.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                "sha256, content_path, text_sha256, wayback_timestamp) VALUES "
                "('vanguard','policy','https://v/p.pdf','2026-06-12','bb','/maintainer/q.pdf',"
                "'uu','20250101000000')")
    ledger.insert_enforcement(src, [EnforcementAction(
        agency="SEC", company_name="Oracle", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="LR-1", source_url="https://s")])
    src.commit()
    ledger.dedupe_votes(src)
    eng = tmp_path / "eng.db"
    engine.build(tmp_path / "src.db", eng, REGISTRY)
    info = release.build_release(src, root=tmp_path / "rel", version="T", no_derived=True,
                                 engine_path=eng, institutions=REGISTRY)
    src.close()
    return tmp_path / "rel" / "vT", info


def test_restore_roundtrips_the_shipped_rows(bundle, tmp_path):
    d, _ = bundle
    out = restore.restore(d, tmp_path / "out" / "glasshouse.db")
    assert out["counts"]["votes"] == 2 and out["votes_is_duplicate"] == 0
    c = ledger.connect(tmp_path / "out" / "glasshouse.db")
    votes = c.execute("SELECT is_duplicate, shares_voted, how_voted FROM votes").fetchall()
    assert [tuple(v) for v in votes] == [(0, 500.0, "AGAINST")] * 2
    assert c.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM enforcement_actions").fetchone()[0] == 1
    com = c.execute("SELECT url, text_sha256, wayback_timestamp, content_path "
                    "FROM commitments").fetchone()
    assert tuple(com) == ("https://v/p.pdf", "tt", "20240101000000", "")
    assert c.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 2
    assert ledger.integrity_check(c) is not None


def test_restore_records_where_it_came_from(bundle, tmp_path):
    d, _ = bundle
    out = restore.restore(d, tmp_path / "o.db")
    c = ledger.connect(tmp_path / "o.db")
    row = c.execute("SELECT source, ok FROM ingest_runs").fetchall()
    assert len(row) == 1 and row[0]["ok"] == 1
    assert row[0]["source"] == f"restore:vT:{out['manifest_sha256'][:12]}"
    # no live source name can be satisfied by it
    assert not c.execute("SELECT 1 FROM ingest_runs WHERE source NOT LIKE 'restore:%'").fetchone()


def test_tampered_bundle_is_refused_and_nothing_is_written(bundle, tmp_path):
    d, _ = bundle
    f = d / "facts" / "institutions.csv"
    f.write_text(f.read_text() + "x,y,z,w,v\n")
    dest = tmp_path / "o.db"
    with pytest.raises(restore.RestoreError, match="checksum mismatch"):
        restore.restore(d, dest)
    assert not dest.exists()


def test_unlisted_fact_file_is_refused(bundle, tmp_path):
    d, _ = bundle
    (d / "facts" / "extra.csv").write_text("a\n1\n")
    with pytest.raises(restore.RestoreError, match="does not list"):
        restore.restore(d, tmp_path / "o.db")


def test_missing_manifest_is_refused(bundle, tmp_path):
    d, _ = bundle
    (d / "MANIFEST.sha256").unlink()
    with pytest.raises(restore.RestoreError, match="MANIFEST"):
        restore.restore(d, tmp_path / "o.db")


def test_existing_nonempty_ledger_is_never_overwritten(bundle, tmp_path):
    d, _ = bundle
    dest = tmp_path / "live.db"
    c = ledger.connect(dest)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('x','X')")
    c.execute("INSERT INTO filings (accession, cik, form_type, source_url, retrieval_date) "
              "VALUES ('A','1','N-PX','u','2026-01-01')")
    c.commit()
    c.close()
    before = hashlib.sha256(dest.read_bytes()).hexdigest()
    with pytest.raises(restore.RestoreError, match="refusing to overwrite"):
        restore.restore(d, dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == before


def test_seeded_but_factless_ledger_may_be_restored_over(bundle, tmp_path):
    d, _ = bundle
    dest = tmp_path / "seeded.db"
    c = ledger.connect(dest)
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('vanguard','Vanguard')")
    c.commit()
    c.close()
    restore.restore(d, dest)
    c = sqlite3.connect(dest)
    assert c.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 2


def test_engine_builds_from_a_restored_ledger_and_says_policy_text_is_absent(bundle, tmp_path):
    d, _ = bundle
    led, eng_path = tmp_path / "r.db", tmp_path / "re.db"
    restore.restore(d, led)
    stats = engine.build(led, eng_path, REGISTRY)
    assert stats["proposals"] >= 1
    assert stats["policy_versions"] == 2 and stats["policy_sentences"] == 0
    e = engine.Engine(eng_path, ledger_path=led) if _takes_ledger() else engine.Engine(eng_path)
    versions = e.db.execute("SELECT n_sentences FROM policy_versions").fetchall()
    assert [r[0] for r in versions] == [0, 0]
    env = e.policy_search("climate", institution="vanguard")
    assert env["result"] == []
    text = " ".join(env["caveats"])
    assert "no policy text" in text and "ingest commitments --wayback" in text
    assert "restored from" in text and "vT" in text
    a, b = [r[0] for r in e.db.execute(
        "SELECT commitment_id FROM policy_versions ORDER BY commitment_id")]
    diff = e.policy_diff("vanguard", a, b)
    assert "no policy text" in " ".join(diff["caveats"])


def _takes_ledger() -> bool:
    import inspect
    return "ledger_path" in inspect.signature(engine.Engine.__init__).parameters


def test_doctor_says_a_restored_ledger_is_not_live(bundle, tmp_path, monkeypatch):
    from datetime import date

    from glasshouse import doctor
    d, _ = bundle
    restore.restore(d, tmp_path / "o.db")
    c = ledger.connect(tmp_path / "o.db")
    monkeypatch.setattr(doctor, "_today", lambda: date(2026, 11, 17))
    monkeypatch.setattr("glasshouse.registry.load", lambda: REGISTRY)
    checks = doctor.diagnose(c)["checks"]
    first = checks[0]
    assert first["name"] == "ledger:restored" and first["ok"]
    assert "restore of bundle vT" in first["detail"] and "NOT a live ingest" in first["detail"]
    for ch in checks:
        if ch["name"].startswith(("source:", "commitment-live:")):
            assert ch["ok"] and ch["severity"] == "info", ch
            assert "restored, not live" in ch["detail"]
            assert "last successful ingest" not in ch["detail"]
    # a live ingest after the restore is judged live again
    c.execute("INSERT INTO ingest_runs (source, run_at, fetched, inserted, ok) VALUES ('ofac','2026-11-16T00:00:00',0,0,1)")
    c.commit()
    ofac = next(x for x in doctor.diagnose(c)["checks"] if x["name"] == "source:OFAC (SDN)")
    assert "last successful ingest 2026-11-16" in ofac["detail"]


def test_doctor_on_a_live_ledger_has_no_restore_line(tmp_path, monkeypatch):
    from glasshouse import doctor
    c = ledger.connect(tmp_path / "live.db")
    monkeypatch.setattr("glasshouse.registry.load", dict)
    names = [x["name"] for x in doctor.diagnose(c)["checks"]]
    assert "ledger:restored" not in names
