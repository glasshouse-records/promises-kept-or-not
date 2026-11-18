"""The release bundle — the versioned, verifiable artifact the world consumes.

A release must (1) carry ONLY publishable data (the publish.PUBLIC_TABLES
disclosure boundary, inherited), (2) be verifiable WITHOUT trusting us (every
file checksummed in MANIFEST.sha256), and (3) be self-describing (datapackage +
datasheet + coverage). These tests pin all three, plus the dedup/approved-only
filters, on the new surface.
"""

import csv
import gzip
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from glasshouse import engine, ledger, outreach, publish, release, review
from glasshouse.contradictions import ContradictionCandidate
from glasshouse.ledger import EnforcementAction


def _candidate():
    return ContradictionCandidate(
        theme="climate", institution_id="blackrock", doc_label="stewardship",
        doc_version="2026-06-11", doc_sha256="a" * 64, doc_url="https://x/p.pdf",
        commitment_quote="We are committed to climate oversight.",
        accession="ACC-1", issuer_name="AMAZON.COM, INC.", cusip="023135106",
        meeting_date="05/21/2025", vote_description="EMISSIONS PROPOSAL",
        how_voted="AGAINST", management_recommendation="FOR", shares_voted=1000.0)


# Operator-internal secrets that must NEVER surface in a release, anywhere.
SECRET_DRAFT = "TOP SECRET unsent outreach draft"
SECRET_SIGNAL = "internal operator-only signal note"
SECRET_LLM = "raw advisory model output not for publication"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX_DIR", tmp_path / "outbox")
    c = ledger.connect(tmp_path / "work.db")
    c.execute("INSERT INTO institutions (id, display_name, cik) "
              "VALUES ('blackrock','BlackRock Inc.','0001364742')")
    c.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
              "retrieval_date) VALUES ('ACC-1','1','blackrock','N-PX','https://e','2026-06-11')")
    # A vote and its as-filed duplicate; only the deduped one is public.
    for dup in (0, 1):
        c.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, "
                  "is_duplicate) VALUES ('ACC-1','AMAZON','AGAINST',1000,?)", (dup,))
    ledger.insert_enforcement(c, [EnforcementAction(
        agency="SEC", company_name="Oracle", action_date="2020-01-01",
        resolution_type="civil_settlement", primary_ref="LR-1", source_url="https://s")])
    # Operator-internal residue that must NOT leave the working ledger.
    c.execute("INSERT INTO outreach (kind, institution_id, subject, body_path, created_ts) "
              "VALUES ('inquiry','blackrock',?, '/tmp/x','t')", (SECRET_DRAFT,))
    c.execute("INSERT INTO signals (ts, kind, detail) VALUES ('t','citation',?)", (SECRET_SIGNAL,))
    c.execute("INSERT INTO llm_log (ts, model, purpose, prompt_sha, input_key, output) "
              "VALUES ('t','m','p','s','k',?)", (SECRET_LLM,))
    c.commit()
    ledger.dedupe_votes(c)
    return c


REGISTRY = {"blackrock": {
    "display_name": "BlackRock Inc.",
    "voting_scope_notes": ["Some series are voted by an affiliate sub-adviser."],
    "npx_ciks": [
        {"cik": "0000000001", "name": "iShares Trust", "adviser": "BlackRock Fund Advisors",
         "adviser_source": "https://www.sec.gov/Archives/x.htm", "adviser_verified": "2026-11-17",
         "adviser_key": "BIS",
         "series_adviser": {"S000000001": [{"key": "BIS", "until": "2024-12-31"},
                                           {"key": "BAIS", "from": "2025-01-01"}]}},
        {"cik": "0000000002", "name": "No Source Fund", "adviser_key": "BIS"},
    ],
    "commitments": [{"label": "stewardship", "adviser_key": "BIS"}],
}}


def _build_engine(conn, tmp_path, name="engine.db"):
    path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    ep = tmp_path / name
    if ledger.duplicate_flags_stale(conn):     # a release needs current duplicate flags
        ledger.dedupe_votes(conn)
    engine.build(path, ep, REGISTRY)
    return ep


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch, tmp_path_factory):
    """Old tests mutate the ledger then build; give each build a current engine."""
    orig = release.build_release

    def wrapper(conn, root=None, version=None, **kw):
        if "engine_path" not in kw:
            d = tmp_path_factory.mktemp("eng")
            if ledger.duplicate_flags_stale(conn):
                ledger.dedupe_votes(conn)
            kw["engine_path"] = _build_engine(conn, d)
            kw.setdefault("institutions", REGISTRY)
        return orig(conn, root, version, **kw)
    monkeypatch.setattr(release, "build_release", wrapper)


def _read_csv(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_release_bundle_is_complete_and_self_describing(conn, tmp_path):
    info = release.build_release(conn, root=tmp_path, version="t1",
                                 with_parquet=False, with_sqlite=True)
    d = tmp_path / "vt1"
    assert d.is_dir()
    for required in ("datapackage.json", "DATASHEET.md", "COVERAGE.json",
                     "MANIFEST.sha256", "README.md", "derived/glasshouse.db"):
        assert (d / required).exists(), f"missing {required}"
    # facts/ has a file per public table (the full contract, empty tables included).
    assert (d / "facts" / "votes.csv").exists()
    assert (d / "facts" / "enforcement_actions.csv").exists()
    # datapackage is valid and points at the emitted files.
    pkg = json.loads((d / "datapackage.json").read_text())
    votes_res = next(r for r in pkg["resources"] if r["name"] == "votes")
    assert votes_res["path"] and votes_res["path"][0].startswith("facts/votes.csv")
    assert "sha256" in votes_res and len(votes_res["sha256"]) == 64
    assert info["version"] == "t1"


def test_release_inherits_disclosure_boundary(conn, tmp_path):
    """No operator-internal table, and none of its secrets, may appear anywhere
    in a release — not in facts/, not in the derived db, not in any doc."""
    d = tmp_path / "vt2"
    release.build_release(conn, root=tmp_path, version="t2", with_parquet=False)
    # Default omits the heavy SQLite browse view; CSV/Parquet are canonical.
    assert not (d / "derived" / "glasshouse.db").exists()
    for t in publish.OPERATOR_ONLY:
        assert not (d / "facts" / f"{t}.csv").exists()
        assert not (d / "facts" / f"{t}.csv.gz").exists()
    blob = b""
    for p in d.rglob("*"):
        if p.is_file():
            blob += p.read_bytes()
    for secret in (SECRET_DRAFT, SECRET_SIGNAL, SECRET_LLM):
        assert secret.encode() not in blob, f"leaked: {secret!r}"


def test_release_filters_dupes_and_unapproved_findings(conn, tmp_path, monkeypatch):
    import glasshouse.contradictions as ct
    monkeypatch.setattr(ct, "find_commitment_vote_contradictions", lambda c, **kw: [_candidate()])
    review.sync(conn)  # 1 PENDING finding — must not publish

    d = tmp_path / "vt3"
    release.build_release(conn, root=tmp_path, version="t3", with_parquet=False)
    assert len(_read_csv(d / "facts" / "votes.csv")) == 1            # dup excluded
    assert len(_read_csv(d / "facts" / "findings.csv")) == 0         # pending excluded

    fid = review.queue(conn, "pending")[0]["id"]
    review.decide(conn, fid, "approved", "verified both sources")
    d2 = tmp_path / "vt4"
    release.build_release(conn, root=tmp_path, version="t4", with_parquet=False)
    assert len(_read_csv(d2 / "facts" / "findings.csv")) == 1        # approved included


def test_manifest_verifies_every_file(conn, tmp_path):
    """MANIFEST.sha256 must list every shipped file with a matching hash, and
    must be complete (no unlisted files) — so a consumer can `sha256sum -c` and
    trust the bundle without trusting us."""
    d = tmp_path / "vt5"
    release.build_release(conn, root=tmp_path, version="t5", with_parquet=False)
    manifest = (d / "MANIFEST.sha256").read_text().splitlines()
    listed = {}
    for line in manifest:
        h, rel = line.split("  ", 1)
        listed[rel] = h
    # every listed file exists and hashes correctly
    for rel, h in listed.items():
        f = d / rel
        assert f.exists(), f"manifest lists missing {rel}"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == h, f"hash mismatch {rel}"
    # completeness: every file except the manifest itself is listed
    on_disk = {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}
    assert on_disk - {"MANIFEST.sha256"} == set(listed), "manifest is not complete"


def test_release_quarantines_legacy_html_votes(conn, tmp_path):
    """Pre-2024 legacy-parsed votes (vote_source='legacy_html') are not yet
    validated and must NOT enter a public release."""
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, "
                 "is_duplicate, vote_source) VALUES ('ACC-1','LEGACYCO INC','FOR',0,0,'legacy_html')")
    conn.commit()
    d = tmp_path / "vt7"
    release.build_release(conn, root=tmp_path, version="t7", with_parquet=False)
    rows = _read_csv(d / "facts" / "votes.csv")
    assert all(r.get("vote_source") != "legacy_html" for r in rows)
    assert not any(r["issuer_name"] == "LEGACYCO INC" for r in rows)
    assert len(rows) == 1  # only the structured, deduped vote


def test_release_drops_operator_columns_and_non_votes(conn, tmp_path):
    """The public release must not ship content_path (a local operator path),
    and must exclude administrative N-PX rows with no cast vote."""
    conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                 "sha256, content_path, content_type, size_bytes) VALUES "
                 "('blackrock','principles','https://x/p.pdf','2025-01-01',?,?, 'application/pdf',9)",
                 ("b" * 64, "/Users/op/glasshouse/data/commitments/x.pdf"))
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, is_duplicate) "
                 "VALUES ('ACC-1','POSTAL NOTICE CO','',0,0)")   # non-vote (empty how_voted)
    conn.commit()
    d = tmp_path / "vt8"
    release.build_release(conn, root=tmp_path, version="t8", with_parquet=False)
    com_cols = next(csv.reader(open(d / "facts" / "commitments.csv")))
    assert "content_path" not in com_cols          # local path not leaked
    assert "url" in com_cols and "sha256" in com_cols   # real provenance kept
    votes = _read_csv(d / "facts" / "votes.csv")
    assert all(r["issuer_name"] != "POSTAL NOTICE CO" for r in votes)  # non-vote excluded
    assert all(r["how_voted"] for r in votes)      # every public vote is a cast vote


def test_release_version_cannot_escape_root(conn, tmp_path):
    """version becomes a dir name we rmtree — separators/traversal are rejected."""
    for bad in ("../../etc", "a/b", ".."):
        with pytest.raises(ValueError):
            release.build_release(conn, root=tmp_path, version=bad, with_parquet=False)


def test_release_parquet_when_pyarrow_available(conn, tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    d = tmp_path / "vt6"
    info = release.build_release(conn, root=tmp_path, version="t6", with_parquet=True)
    assert "parquet" in info["formats"]
    pf = d / "facts" / "votes.parquet"
    assert pf.exists()
    assert pq.read_table(pf).num_rows == 1  # deduped


def _commitment(conn):
    conn.execute("INSERT INTO commitments (institution_id, doc_label, url, retrieval_date, "
                 "sha256, text_sha256, content_path, content_type, size_bytes, "
                 "wayback_timestamp, doc_created_at) VALUES ('blackrock','stewardship',"
                 "'https://x/p.pdf','2025-01-01',?,?,'/Users/op/secret/path.pdf',"
                 "'application/pdf',9,'20250102030405','2024-12-20T00:00:00')",
                 ("b" * 64, "c" * 64))
    conn.commit()


def test_new_tables_present_with_expected_rows(conn, tmp_path):
    _commitment(conn)
    ep = _build_engine(conn, tmp_path)
    release.build_release(conn, root=tmp_path, version="n1", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY)
    d = tmp_path / "vn1" / "facts"
    va = _read_csv(d / "voting_advisers.csv")
    # default + 2 series rules for the sourced registrant; the unsourced one is omitted
    assert [(r["series_id"], r["adviser_key"], r["from"], r["until"]) for r in va] == [
        ("", "BIS", "", ""), ("S000000001", "BIS", "", "2024-12-31"),
        ("S000000001", "BAIS", "2025-01-01", "")]
    assert all(r["adviser_source"].startswith("https://") for r in va)
    assert va[0]["adviser"] == "BlackRock Fund Advisors" and va[2]["adviser"] == ""
    assert _read_csv(d / "voting_scope_notes.csv") == [
        {"institution": "blackrock",
         "note": "Some series are voted by an affiliate sub-adviser."}]
    pv = _read_csv(d / "policy_versions.csv")
    assert len(pv) == 1
    assert pv[0]["adviser_key"] == "BIS" and pv[0]["captured"] == "2025-01-02"
    assert pv[0]["authored"] == "2024-12-20" and pv[0]["text_sha256"] == "c" * 64
    assert pv[0]["wayback_timestamp"] == "20250102030405" and pv[0]["source_url"] == "https://x/p.pdf"
    pkg = json.loads((tmp_path / "vn1" / "datapackage.json").read_text())
    names = {r["name"]: r for r in pkg["resources"]}
    for n in ("voting_advisers", "voting_scope_notes", "policy_versions",
              "proposal_decisions", "director_decisions"):
        assert n in names and len(names[n]["sha256"]) == 64
        assert names[n]["rowCount"] == len(_read_csv(d / f"{n}.csv"))
    assert names["proposal_decisions"]["derived"] and names["director_decisions"]["derived"]
    assert not names["policy_versions"].get("derived")
    assert pkg["engine"]["ledger_max_vote_id"] == conn.execute(
        "SELECT MAX(id) FROM votes").fetchone()[0]
    sheet = (tmp_path / "vn1" / "DATASHEET.md").read_text()
    assert "Before you compare a policy with votes" in sheet
    assert sheet.index("Before you compare") < sheet.index("## Provenance guarantees")
    assert "UNRESOLVED" in sheet and "EXTERNAL" in sheet and "UNDATED" in sheet
    assert "issued the ISIN" in sheet.replace("ISSUED", "issued")
    assert "DERIVED" in sheet and "src/glasshouse/engine.py" in sheet
    assert "1 voting rule(s) have no source URL" in sheet     # computed, not hardcoded


def test_derived_tables_carry_adviser_key_and_provenance(conn, tmp_path):
    conn.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                 "vote_description, how_voted, shares_voted, is_duplicate, vote_source, "
                 "category_type) VALUES ('ACC-1','TESLA','88160R101','2025-06-01',"
                 "'REPORT ON CLIMATE','FOR',5,0,'SECURITY HOLDER','x')")
    conn.commit()
    ep = _build_engine(conn, tmp_path)
    release.build_release(conn, root=tmp_path, version="n2", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY)
    rows = _read_csv(tmp_path / "vn2" / "facts" / "proposal_decisions.csv")
    assert rows and "adviser_key" in rows[0] and "adviser" not in rows[0]
    assert all(r["accession"] and r["source_url"] for r in rows)


def test_policy_versions_ships_no_text_or_paths(conn, tmp_path):
    _commitment(conn)
    ep = _build_engine(conn, tmp_path)
    release.build_release(conn, root=tmp_path, version="n3", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY)
    cols = next(csv.reader(open(tmp_path / "vn3" / "facts" / "policy_versions.csv")))
    assert not {"text", "content_path", "path", "sentences"} & set(cols)
    blob = b"".join(p.read_bytes() for p in (tmp_path / "vn3").rglob("*") if p.is_file())
    assert b"/Users/op/secret" not in blob


def test_stale_engine_is_refused_and_no_derived_overrides(conn, tmp_path):
    ep = _build_engine(conn, tmp_path)
    conn.execute("INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, "
                 "is_duplicate) VALUES ('ACC-1','NEWER','FOR',1,0)")
    conn.commit()
    with pytest.raises(release.StaleEngineError, match="stale"):
        release.build_release(conn, root=tmp_path, version="n4", with_parquet=False,
                              engine_path=ep, institutions=REGISTRY)
    assert not (tmp_path / "vn4").exists()
    ledger.dedupe_votes(conn)
    release.build_release(conn, root=tmp_path, version="n4", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY, no_derived=True)
    d = tmp_path / "vn4"
    assert not list((d / "facts").glob("proposal_decisions*"))
    assert not list((d / "facts").glob("director_decisions*"))
    assert (d / "facts" / "policy_versions.csv").exists()
    assert "built with `--no-derived`" in (d / "DATASHEET.md").read_text()
    pkg = json.loads((d / "datapackage.json").read_text())
    assert pkg["derived_tables_included"] is False
    assert "proposal_decisions" not in {r["name"] for r in pkg["resources"]}


def test_missing_engine_is_refused(conn, tmp_path):
    with pytest.raises(release.StaleEngineError, match="not found"):
        release.build_release(conn, root=tmp_path, version="n5", with_parquet=False,
                              engine_path=tmp_path / "nope.db", institutions=REGISTRY)


def test_manifest_covers_new_files(conn, tmp_path):
    release.build_release(conn, root=tmp_path, version="n6", with_parquet=False)
    d = tmp_path / "vn6"
    listed = {ln.split("  ", 1)[1] for ln in (d / "MANIFEST.sha256").read_text().splitlines()}
    for n in ("voting_advisers", "voting_scope_notes", "policy_versions",
              "proposal_decisions", "director_decisions"):
        assert f"facts/{n}.csv" in listed


def test_release_does_not_write_ledger(conn, tmp_path):
    before = conn.total_changes
    release.build_release(conn, root=tmp_path, version="n7", with_parquet=False)
    assert conn.total_changes == before


def test_methodology_excerpts_are_verbatim():
    doc = re.sub(r"\s+", " ", (Path(__file__).parent.parent / "METHODOLOGY.md").read_text())
    for t in release.METHODOLOGY_PROPOSALS + release.METHODOLOGY_DIRECTORS:
        assert re.sub(r"\s+", " ", t) in doc, t


def _coverage_fixture(conn):
    """Rows the release filter EXCLUDES, plus two institutions with different
    kinds of votes held, so the coverage must describe the shipped rows."""
    conn.execute("INSERT INTO institutions (id, display_name, cik) "
                 "VALUES ('ubs','UBS Group','0000000009')")
    conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                 "retrieval_date) VALUES ('ACC-U','9','ubs','N-PX','https://e','2026-06-11')")

    def vote(acc, src, cat, how, md, dup=0):
        conn.execute(
            "INSERT INTO votes (accession, issuer_name, how_voted, shares_voted, is_duplicate, "
            "vote_source, category_type, meeting_date) VALUES (?,?,?,?,?,?,?,?)",
            (acc, "CO", how, 10, dup, src, cat, md))
    # shipped for BlackRock: a shareholder proposal and a director election
    vote("ACC-1", "SECURITY HOLDER", "ENVIRONMENT OR CLIMATE", "FOR", "2025-05-01")
    vote("ACC-1", "ISSUER", "DIRECTOR ELECTIONS", "FOR", "2025-06-01")
    # excluded: unvalidated legacy row, administrative no-vote row (both with EARLY dates)
    vote("ACC-1", "legacy_html", "COMPENSATION", "FOR", "2019-01-01")
    vote("ACC-1", "ISSUER", "COMPENSATION", "", "2018-01-01")
    # UBS: say-on-pay only, plus an excluded legacy row
    vote("ACC-U", "", "SECTION 14A SAY-ON-PAY VOTES", "FOR", "2025-03-01")
    vote("ACC-U", "legacy_html", "DIRECTOR ELECTIONS", "FOR", "2017-01-01")
    conn.commit()


def test_coverage_counts_describe_shipped_rows_not_ledger_rows(conn, tmp_path):
    _coverage_fixture(conn)
    release.build_release(conn, root=tmp_path, version="cov",
                          with_parquet=False, with_sqlite=False)
    d = tmp_path / "vcov"
    shipped = _read_csv(d / "facts" / "votes.csv")
    filings = {r["accession"]: r["institution_id"] for r in _read_csv(d / "facts" / "filings.csv")}
    per: dict = {}
    for r in shipped:
        per[filings[r["accession"]]] = per.get(filings[r["accession"]], 0) + 1
    cov = {r["institution"]: r for r in json.loads((d / "COVERAGE.json").read_text())}
    assert cov["BlackRock Inc."]["votes"] == per["blackrock"] == 3   # 1 fixture + 2 above
    assert cov["UBS Group"]["votes"] == per["ubs"] == 1
    # the excluded rows' dates must not leak into the published range
    assert cov["BlackRock Inc."]["vote_dates"].startswith("2025-05-01")
    assert cov["UBS Group"]["vote_dates"] == "2025-03-01 → 2025-03-01"
    sheet = (d / "DATASHEET.md").read_text()
    assert "| BlackRock Inc. | 1 | 3 |" in sheet
    assert "2018" not in cov["BlackRock Inc."]["vote_dates"]


def test_coverage_states_which_kinds_of_votes_are_shipped(conn, tmp_path):
    _coverage_fixture(conn)
    release.build_release(conn, root=tmp_path, version="kinds",
                          with_parquet=False, with_sqlite=False)
    d = tmp_path / "vkinds"
    cov = {r["institution"]: r for r in json.loads((d / "COVERAGE.json").read_text())}
    assert cov["UBS Group"]["vote_kinds"] == ["say_on_pay"]
    assert cov["UBS Group"]["vote_kinds_note"].startswith("say-on-pay votes only")
    br = cov["BlackRock Inc."]
    assert br["vote_kinds"] == ["shareholder_proposals", "director_elections", "management_other"]
    assert "only" not in br["vote_kinds_note"]
    assert br["votes_by_kind"]["shareholder_proposals"] == 1
    sheet = (d / "DATASHEET.md").read_text()
    assert "say-on-pay votes only" in sheet


# ---------------------------------------------------------------- documentation gaps

def _add_vote(c, acc, series, md, desc, how="FOR", cat="DIRECTOR ELECTIONS", src="ISSUER"):
    c.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, vote_description, "
              "category_type, vote_source, vote_series, how_voted, shares_voted, is_duplicate) "
              "VALUES (?, 'ACME', '000000001', ?, ?, ?, ?, ?, ?, 10, 0)",
              (acc, md, desc, cat, src, series, how))


def _adviser_ledger(conn):
    """BlackRock (multi-adviser: BIS to 2024, BAIS from 2025 on one series), one filing from
    a registrant the registry does not list, and UBS (no keys at all)."""
    conn.execute("INSERT INTO institutions (id, display_name, cik) VALUES ('ubs','UBS','9')")
    for acc, cik, iid in (("ACC-2", "9", "ubs"), ("ACC-3", "77", "blackrock")):
        conn.execute("INSERT INTO filings (accession, cik, institution_id, form_type, source_url, "
                     "retrieval_date) VALUES (?,?,?,'N-PX','https://e','2026-06-11')",
                     (acc, cik, iid))
    _add_vote(conn, "ACC-1", "S000000001", "06/01/2024", "ELECT A")          # BIS
    _add_vote(conn, "ACC-1", "S000000001", "6/1/2025", "ELECT B", how="WITHHOLD")  # BAIS
    _add_vote(conn, "ACC-1", "S000000002", "06/01/2025", "ELECT C")          # default BIS
    _add_vote(conn, "ACC-1", "S000000001", "not a date", "ELECT D")          # UNDATED
    _add_vote(conn, "ACC-3", "S000000001", "06/01/2025", "ELECT E")          # unlisted registrant
    _add_vote(conn, "ACC-2", "S000000001", "06/01/2025", "ELECT F")          # UBS: no keys
    _add_vote(conn, "ACC-1", "S000000001", "6/1/2025", "ELECT G", how="")    # not shipped
    conn.commit()


def test_shipped_votes_carry_institution_and_the_engines_adviser_key(conn, tmp_path):
    _adviser_ledger(conn)
    ep = _build_engine(conn, tmp_path)
    release.build_release(conn, root=tmp_path, version="a1", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY)
    votes = _read_csv(tmp_path / "va1" / "facts" / "votes.csv")
    assert list(votes[0])[-2:] == ["institution_id", "adviser_key"]
    by_desc = {r["vote_description"]: r for r in votes if r["vote_description"]}
    got = {k: (v["institution_id"], v["adviser_key"]) for k, v in by_desc.items()}
    assert got == {"ELECT A": ("blackrock", "BIS"), "ELECT B": ("blackrock", "BAIS"),
                   "ELECT C": ("blackrock", "BIS"), "ELECT D": ("blackrock", "UNDATED"),
                   "ELECT E": ("blackrock", "unlabelled"), "ELECT F": ("ubs", "")}
    # ...and it is the engine's own resolution, line for line: per (institution, key) the
    # shipped director lines equal what the engine folded into director_decisions.
    eng = sqlite3.connect(ep)
    eng_n = {(i, a): n for i, a, n in eng.execute(
        "SELECT institution_id, adviser, SUM(n_lines) FROM director_votes GROUP BY 1,2")}
    ship_n: dict = {}
    for r in votes:
        if r["category_type"] == "DIRECTOR ELECTIONS" and r["vote_source"] == "ISSUER":
            k = (r["institution_id"], r["adviser_key"] or None)
            ship_n[k] = ship_n.get(k, 0) + 1
    # the engine also counts a line filed with an empty how_voted (not shipped): the one
    # documented difference, here one BAIS line
    assert {k: n + (1 if k == ("blackrock", "BAIS") else 0) for k, n in ship_n.items()} == eng_n
    pkg = json.loads((tmp_path / "va1" / "datapackage.json").read_text())
    vres = next(r for r in pkg["resources"] if r["name"] == "votes")
    assert [f["name"] for f in vres["schema"]["fields"]][-2:] == ["institution_id", "adviser_key"]
    assert vres["rowCount"] == len(votes)


def _shipped_columns(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def test_every_shipped_column_of_every_shipped_table_is_defined(conn, tmp_path):
    """A new column cannot ship undocumented: the descriptor must define, in the
    one dictionary, exactly the columns the CSV carries; the datasheet repeats them."""
    release.build_release(conn, root=tmp_path, version="d1", with_parquet=False)
    d = tmp_path / "vd1"
    pkg = json.loads((d / "datapackage.json").read_text())
    sheet = (d / "DATASHEET.md").read_text()
    assert {r["name"] for r in pkg["resources"]} == {
        p.name.split(".")[0] for p in (d / "facts").iterdir()}
    for res in pkg["resources"]:
        cols = _shipped_columns(d / res["path"][0])
        assert [f["name"] for f in res["schema"]["fields"]] == cols, res["name"]
        for f in res["schema"]["fields"]:
            assert len(f["description"].strip()) > 8, (res["name"], f["name"])
            assert f"- **{f['name']}** — {f['description']}" in sheet, (res["name"], f["name"])
            assert release.COLUMN_DICTIONARY[res["name"]][f["name"]] == f["description"]
    for table, col in (("votes", "id"), ("votes", "category_type"), ("votes", "vote_source"),
                       ("votes", "shares_on_loan"), ("votes", "vote_series"),
                       ("filings", "report_type"), ("filings", "notes")):
        assert col in release.COLUMN_DICTIONARY[table]


def test_datasheet_defines_code_lists_joins_and_manifest(conn, tmp_path):
    release.build_release(conn, root=tmp_path, version="d2", with_parquet=False)
    sheet = (tmp_path / "vd2" / "DATASHEET.md").read_text()
    flat = " ".join(sheet.split())
    for needle in ("## Code lists", "`FOR`", "`AGAINST`", "WITHHOLD", "`ABSTAIN`", "`SPLIT`",
                   "5%", "`NONE`", "ISSUER", "SECURITY HOLDER", "legacy_html",
                   "shareholder_proposals", "director_elections", "say_on_pay",
                   "management_other", "`UNRESOLVED`", "`EXTERNAL`", "`UNDATED`",
                   "`unlabelled`", "`NULL` = no adviser key recorded",
                   "votes.accession = filings.accession",
                   "votes.vote_series = fund_series.series_id",
                   "neither numerator nor denominator",
                   "MANIFEST.sha256 covers every file in the bundle except itself",
                   "nothing signs it"):
        assert needle in flat, needle
    # the sentence that overstated provenance is gone: votes carry it via filings
    assert "Every record carries source_url + retrieval_date." not in sheet
    assert "`votes` rows carry no `source_url`" in flat


def test_bundle_readme_has_no_placeholder_citation(conn, tmp_path):
    release.build_release(conn, root=tmp_path, version="d3", with_parquet=False)
    readme = (tmp_path / "vd3" / "README.md").read_text()
    assert "add release/DOI URL" not in readme and "https://github.com/" not in readme
    # True before and after the Zenodo deposit: the bundle cannot know its DOI.
    assert "not yet published" not in readme
    assert "DOI on the Zenodo record" in readme and "unpublished build" in readme


def test_git_state_names_the_checked_out_commit_and_flags_a_dirty_tree(tmp_path):
    import subprocess

    from glasshouse import dataset

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *a],
                              cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    git("init", "-q")
    (tmp_path / "f.txt").write_text("1")
    git("add", "f.txt")
    git("commit", "-q", "-m", "c")
    head = git("rev-parse", "HEAD").strip()
    st = dataset.git_state(tmp_path)
    assert st == {"commit": head, "dirty": False}
    (tmp_path / "f.txt").write_text("2")
    assert dataset.git_state(tmp_path) == {"commit": head, "dirty": True}
    (tmp_path / "f.txt").write_text("1")
    (tmp_path / "new.txt").write_text("x")           # an untracked file is a dirty tree too
    assert dataset.git_state(tmp_path)["dirty"] is True
    assert dataset.git_state(tmp_path / "missing") == {"commit": "unknown", "dirty": None}


def test_datapackage_records_git_state(conn, tmp_path, monkeypatch):
    from glasshouse import dataset
    monkeypatch.setattr(dataset, "git_state", lambda *a: {"commit": "f" * 40, "dirty": True})
    release.build_release(conn, root=tmp_path, version="d4", with_parquet=False)
    d = tmp_path / "vd4"
    pkg = json.loads((d / "datapackage.json").read_text())
    assert pkg["git"] == {"commit": "f" * 40, "dirty": True}
    assert pkg["git_commit"] == "f" * 7
    assert "dirty" in (d / "DATASHEET.md").read_text().split("\n")[2]
    assert "working tree was dirty" in (d / "README.md").read_text()


def test_pay_decisions_ships_both_kinds_with_every_column_defined(conn, tmp_path):
    for desc, how in (("ADVISORY VOTE ON EXECUTIVE COMPENSATION", "FOR"),
                      ("FREQUENCY OF ADVISORY VOTE ON EXECUTIVE COMPENSATION", "ONE YEAR")):
        conn.execute("INSERT INTO votes (accession, issuer_name, cusip, meeting_date, "
                     "vote_description, how_voted, shares_voted, is_duplicate, vote_source, "
                     "category_type) VALUES ('ACC-1','TESLA','88160R101','2025-06-01',?,?,5,0,"
                     "'ISSUER','SECTION 14A SAY-ON-PAY VOTES')", (desc, how))
    conn.commit()
    ep = _build_engine(conn, tmp_path)
    release.build_release(conn, root=tmp_path, version="n8", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY)
    d = tmp_path / "vn8"
    rows = _read_csv(d / "facts" / "pay_decisions.csv")
    assert {r["kind"] for r in rows} == {"approval", "frequency"}
    assert all(r["accession"] and r["source_url"] for r in rows)
    pkg = json.loads((d / "datapackage.json").read_text())
    res = next(r for r in pkg["resources"] if r["name"] == "pay_decisions")
    assert res["derived"] and res["rowCount"] == len(rows)
    assert {f["name"] for f in res["schema"]["fields"]} == set(release.PAY_COLS)
    assert "frequency" in res["description"] and "opposition" in res["description"]
    assert "pay_decisions" in (d / "DATASHEET.md").read_text()
    assert "facts/pay_decisions.csv" in (d / "MANIFEST.sha256").read_text()
    release.build_release(conn, root=tmp_path, version="n9", with_parquet=False,
                          engine_path=ep, institutions=REGISTRY, no_derived=True)
    assert not list((tmp_path / "vn9" / "facts").glob("pay_decisions*"))


def test_policy_versions_docs_name_sai_filing_dates():
    """SAI-printed versions are dated by the EDGAR filing date, not a Wayback
    capture or our fetch; the datasheet must say so or readers misread them."""
    from glasshouse.release import NEW_TABLES
    cols = NEW_TABLES["policy_versions"]
    assert "filing date" in cols["captured"]
    assert "SAI" in cols["captured"]
    assert "live fetch" not in cols["wayback_timestamp"] or "SAI" in cols["wayback_timestamp"]
