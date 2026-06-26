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

import pytest

from glasshouse import ledger, outreach, publish, release, review
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
    return c


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
