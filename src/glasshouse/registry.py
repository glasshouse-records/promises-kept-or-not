"""Institution registry, loaded from config/institutions.yaml.

Adding any filer to Glasshouse = one entry in that file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "institutions.yaml"


def load(path: Path | str = CONFIG_PATH) -> dict[str, dict]:
    with open(path) as fh:
        return yaml.safe_load(fh)["institutions"]


def sync_to_ledger(conn: sqlite3.Connection, institutions: dict[str, dict] | None = None) -> int:
    institutions = institutions or load()
    for inst_id, inst in institutions.items():
        conn.execute(
            "INSERT INTO institutions (id, display_name, cik, type, country) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, "
            "cik=excluded.cik, type=excluded.type, country=excluded.country",
            (inst_id, inst["display_name"], inst.get("cik", ""),
             inst.get("type", ""), inst.get("country", "")),
        )
    conn.commit()
    return len(institutions)


def npx_ciks(inst_id: str, institutions: dict[str, dict] | None = None) -> list[dict]:
    """N-PX filer CIKs for an institution: its fund trusts, falling back to
    the manager CIK itself (some managers file N-PX directly)."""
    institutions = institutions or load()
    inst = institutions[inst_id]
    trusts = inst.get("npx_ciks") or []
    return trusts if trusts else [{"cik": inst["cik"], "name": inst["display_name"]}]
