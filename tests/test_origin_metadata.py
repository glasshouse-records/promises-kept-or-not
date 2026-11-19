"""Manager-originated dating evidence, extracted from bytes we already hold.

The archive's weakest point is dating: a Wayback capture proves only that the
Internet Archive looked on that day, and Weinhoffer v. Davie Shoring (5th Cir.
2022) held such captures are not self-authenticating. Our own SHA-256 is worse
for this purpose — it is a statement by us, about our own custody, of a file we
fetched.

But 61 of the 62 archived PDFs carry /CreationDate, /ModDate and /Producer
written by the MANAGER'S own software ("Microsoft(R) Word for Office",
"Adobe PDF Library"), several with US Eastern UTC offsets. Every one precedes
its capture date, median lag 79 days, zero inversions. That is independent,
third-party-authored evidence corroborating the whole dating layer, and it was
sitting unextracted in bytes already in custody.

It is deliberately NOT treated as proof of publication — a creation date is when
a file was made, not when it went on a website. Its job is corroboration and,
above all, the inversion check: a document authored AFTER the capture that
supposedly contains it would mean the lineage is wrong.
"""

from __future__ import annotations

import pytest

from glasshouse.ingest import commitments as cm


def _pdf(created: str | None = None, producer: str | None = None) -> bytes:
    """A minimal but genuinely parseable PDF carrying DocInfo."""
    from io import BytesIO

    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    meta = {}
    if created:
        meta["/CreationDate"] = created
    if producer:
        meta["/Producer"] = producer
    if meta:
        w.add_metadata(meta)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_reads_the_managers_own_authoring_date():
    md = cm.origin_metadata(_pdf("D:20201208155441-05'00'", "Microsoft(R) Word for Office"),
                            "application/pdf", "https://x/p.pdf")
    assert md["doc_created_at"] == "2020-12-08T15:54:41-05:00"
    assert "Word" in md["doc_producer"]


def test_missing_date_is_empty_not_invented():
    """A PDF carrying no /CreationDate must yield no date. (The producer field
    is not asserted empty here: pypdf stamps its own /Producer on anything it
    writes, so this fixture cannot express "no producer" — and reporting the
    producer a file really carries is the correct behaviour anyway.)"""
    md = cm.origin_metadata(_pdf(), "application/pdf", "https://x/p.pdf")
    assert md["doc_created_at"] == ""
    assert md["doc_modified_at"] == ""


def test_unparseable_bytes_never_raise():
    md = cm.origin_metadata(b"not a pdf at all", "application/pdf", "https://x/p.pdf")
    assert md == {"doc_created_at": "", "doc_modified_at": "", "doc_producer": ""}


def test_malformed_date_is_dropped_rather_than_guessed():
    """A date we cannot parse is worse than no date — it would be published as
    corroboration of a claim it does not actually support."""
    md = cm.origin_metadata(_pdf("D:BOGUSDATE"), "application/pdf", "https://x/p.pdf")
    assert md["doc_created_at"] == ""


@pytest.mark.parametrize("created,captured,expect", [
    ("2020-12-08T15:54:41-05:00", "20201217000000", True),   # authored before capture
    ("2026-01-05T09:00:00+00:00", "20250101000000", False),  # authored AFTER capture
    ("", "20201217000000", True),                            # unknown = no claim
])
def test_inversion_check(created, captured, expect):
    """The load-bearing check: a document cannot be authored after the capture
    that contains it. An inversion means the lineage is wrong."""
    assert cm.dating_is_consistent(created, captured) is expect


def test_integrity_check_catches_a_dating_inversion(tmp_path):
    """The inversion guarantee has to be mechanical, not something someone
    verified once. A document authored after the capture that contains it means
    the lineage is wrong, and that must fail the gate rather than sit in a
    published dataset."""
    import hashlib

    from glasshouse import ledger
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock')")
    doc = tmp_path / "p.pdf"
    content = _pdf("D:20260105090000Z")
    doc.write_bytes(content)

    def add(created, wb):
        c.execute(
            "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
            " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
            " text_sha256, doc_created_at) VALUES ('blk','p','https://x/p.pdf',"
            "'2026-01-01',?,?,'application/pdf',?,?,'t',?)",
            (hashlib.sha256(content).hexdigest(), str(doc), len(content), wb, created))
        c.commit()

    add("2020-12-08T15:54:41-05:00", "20201217000000")     # fine
    assert ledger.integrity_check(c)["commitments_dating"] == []
    add("2026-01-05T09:00:00+00:00", "20250101000000")     # authored after capture
    assert len(ledger.integrity_check(c)["commitments_dating"]) == 1


def test_self_dated_count_uses_the_same_denominator_as_versions(tmp_path):
    """Published counts must be comparable to each other.

    First cut counted self-dated CAPTURES against distinct VERSIONS, so coverage
    read "7 self-dated of 5 versions" — a dataset that cannot count its own
    contents invites the reader to discard everything else in the table."""
    import hashlib

    from glasshouse import dataset, ledger
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('blk','BlackRock')")
    doc = tmp_path / "p.pdf"
    doc.write_bytes(b"%PDF-1.4")
    # one policy version captured three times, each capture self-dated
    for i in range(3):
        c.execute(
            "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
            " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
            " text_sha256, identity_sha256, doc_created_at) VALUES ('blk','p','https://x/p.pdf',"
            "'2026-01-01',?,?,'application/pdf',8,?,'SAMETEXT','SAMETEXT','2020-12-08T00:00:00')",
            (hashlib.sha256(f"{i}".encode()).hexdigest(), str(doc), f"2020010{i+1}000000"))
    c.commit()
    row = next(r for r in dataset.coverage(c) if r["institution"] == "BlackRock")
    assert row["policy_versions"] == 1
    assert row["policies_self_dated"] <= row["policy_versions"], (
        f"{row['policies_self_dated']} self-dated cannot exceed "
        f"{row['policy_versions']} versions")


@pytest.mark.parametrize("raw", ["D:00010101000000-04'00'", "D:19700101000000Z",
                                 "D:19920101000000Z"])
def test_placeholder_dates_are_not_authoring_dates(raw):
    """Found 2026-11-19 in two Neuberger Berman captures: their PDF software
    wrote /CreationDate D:00010101 (a null date), and the release shipped
    "authored 0001-01-01" and counted both as self-dated. The PDF format dates
    from 1993; an earlier date is a placeholder, not evidence."""
    md = cm.origin_metadata(_pdf(raw), "application/pdf", "https://x/p.pdf")
    assert md["doc_created_at"] == ""


def test_backfill_clears_a_stored_placeholder_date(tmp_path):
    """Rows captured before the plausibility rule keep their bad date unless
    the backfill re-reads them."""
    import hashlib

    from glasshouse import ledger
    c = ledger.connect(tmp_path / "t.db")
    c.execute("INSERT INTO institutions (id, display_name) VALUES ('nb','NB')")
    doc = tmp_path / "p.pdf"
    content = _pdf("D:00010101000000-04'00'")
    doc.write_bytes(content)
    c.execute(
        "INSERT INTO commitments (institution_id, doc_label, url, retrieval_date,"
        " sha256, content_path, content_type, size_bytes, wayback_timestamp,"
        " text_sha256, doc_created_at, doc_modified_at) VALUES ('nb','p','https://x/p.pdf',"
        "'2026-01-01',?,?,'application/pdf',?,'20251102110612','t',"
        "'0001-01-01T00:00:00-04:00','0001-01-01T00:00:00-04:00')",
        (hashlib.sha256(content).hexdigest(), str(doc), len(content)))
    c.commit()
    cm.backfill_text_hashes(c)
    row = c.execute("SELECT doc_created_at, doc_modified_at FROM commitments").fetchone()
    assert (row[0], row[1]) == ("", "")
