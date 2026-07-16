"""FollowTheMoney export — Glasshouse in the format journalists' tools speak.

FollowTheMoney (followthemoney.tech) is the entity format behind OCCRP Aleph /
OpenAleph; OpenSanctions publishes in it. This module exports Glasshouse's
UNIQUE record as FtM entities (JSON lines, one entity per line) so an
investigator can import it next to the datasets they already use.

Mapping — legal categories are never collapsed:
  • institutions and enforcement defendants → `Company` entities
    (defendant names verbatim, as filed);
  • each enforcement action → an `Event` entity involving its company —
    deliberately NOT `Sanction`, because a DPA, NPA or civil settlement is
    not a sanction; the resolution_type rides in the summary and the
    agency in `description`.

Exclusions on this PUBLIC artifact:
  • `allegation` (pending dockets) and `unverified` rows — quarantined,
    never exported (the publish boundary);
  • OFAC `sanction_designation` rows — OpenSanctions already ships the SDN
    list properly in FtM; we export what is unique to us, not a worse copy
    (and name-only SDN matches are the documented Aldar false-positive class);
  • duplicate-marked rows.

Ids are deterministic (content-derived), so re-imports update, not duplicate.
Reads only; writes a single .ftm.json file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .entities import normalize_name

_EXCLUDED = ("allegation", "unverified", "sanction_designation")


def _cid(name: str) -> str:
    """Deterministic Company id from the normalized name (variants of one
    company collapse to one entity; distinct companies do not)."""
    return "gh-co-" + hashlib.sha1(normalize_name(name).encode()).hexdigest()[:16]


def _entity(eid: str, schema: str, props: dict) -> str:
    clean = {k: [str(v) for v in vs if v not in (None, "")]
             for k, vs in props.items()}
    return json.dumps({"id": eid, "schema": schema,
                       "properties": {k: v for k, v in clean.items() if v}},
                      sort_keys=True, ensure_ascii=False)


def export_ftm(conn: sqlite3.Connection, out_path: Path) -> dict:
    """Write the FtM export; returns counts. Deterministic and read-only."""
    lines: list[str] = []
    companies: dict[str, str] = {}   # id -> line (dedup by id, first name wins)

    def company(name: str, country: str = "") -> str:
        eid = _cid(name)
        if eid not in companies:
            companies[eid] = _entity(eid, "Company",
                                     {"name": [name], "jurisdiction": [country]})
        return eid

    for r in conn.execute("SELECT display_name, country FROM institutions ORDER BY id"):
        company(r["display_name"], r["country"] or "")

    n_events = 0
    rows = conn.execute(
        f"""SELECT agency, company_name, action_date, resolution_type, penalty_usd,
                   primary_ref, description, source_url
            FROM enforcement_actions
            WHERE is_duplicate = 0
              AND resolution_type NOT IN ({",".join("?" * len(_EXCLUDED))})
            ORDER BY agency, action_date, primary_ref, company_name""", _EXCLUDED)
    for r in rows:
        co_id = company(r["company_name"])
        key = f"{r['agency']}|{r['primary_ref']}|{r['company_name']}|{r['action_date']}"
        eid = "gh-enf-" + hashlib.sha1(key.encode()).hexdigest()[:16]
        penalty = f"; penalty USD {r['penalty_usd']:,}" if r["penalty_usd"] else ""
        summary = (f"{r['resolution_type']}: {(r['description'] or '').strip()}"
                   f"{penalty}").strip()
        lines.append(_entity(eid, "Event", {
            "name": [f"{r['agency']} — {r['resolution_type']} — {r['company_name']}"],
            "startDate": [r["action_date"]],
            "summary": [summary],
            "description": [r["agency"]],
            "recordId": [r["primary_ref"]],
            "sourceUrl": [r["source_url"]],
            "involved": [co_id],
        }))
        n_events += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(list(companies.values()) + lines) + "\n")
    return {"companies": len(companies), "events": n_events, "path": str(out_path)}
