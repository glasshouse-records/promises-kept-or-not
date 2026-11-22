"""Regression: the release build was SIGKILLed (exit 137) on an 8 GB machine
because the Parquet writer materialised all ~51M votes as Python lists. Parquet
must be written in bounded batches, and a column that is NULL in the first
batch must still get its real type from later batches."""

import pyarrow.parquet as pq

from glasshouse import release


def test_emit_rows_writes_parquet_in_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "PARQUET_BATCH_ROWS", 2)
    cols = ["id", "name", "shares"]
    rows = [(1, None, None), (2, None, 1.5), (3, "b", None), (4, "c", 2.0), (5, "d", 3.0)]
    _, pq_name = release._emit_rows("t", cols, lambda: iter(rows), len(rows),
                                    tmp_path, with_parquet=True)
    f = pq.ParquetFile(tmp_path / pq_name)
    assert f.metadata.num_row_groups > 1            # bounded batches, not one giant table
    t = f.read()
    assert str(t.schema.field("name").type) == "string"
    assert str(t.schema.field("shares").type) == "double"
    assert [tuple(r.values()) for r in t.to_pylist()] == rows


def test_emit_parquet_ledger_table_batched(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(release, "PARQUET_BATCH_ROWS", 2)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE things (id INTEGER, label TEXT)")
    conn.executemany("INSERT INTO things VALUES (?,?)",
                     [(1, None), (2, None), (3, "x"), (4, "y"), (5, None)])
    name = release._emit_parquet(conn, "things", "", tmp_path)
    f = pq.ParquetFile(tmp_path / name)
    assert f.metadata.num_row_groups > 1
    assert f.read().to_pylist() == [{"id": 1, "label": None}, {"id": 2, "label": None},
                                    {"id": 3, "label": "x"}, {"id": 4, "label": "y"},
                                    {"id": 5, "label": None}]
