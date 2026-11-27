"""Dry run of the SEC series-dataset fallback over the unmapped headings already recorded
in data/glasshouse.db (opened READ-ONLY; nothing is written there). For every legacy
filing it asks the same question the parser would ask (`legacy_pe.build_fallback` +
`SeriesFallback.lookup`) and reports, per institution, headings and rows that WOULD map,
plus random examples.

    .venv/bin/python scripts/series_fallback_dryrun.py [out_path]
"""

from __future__ import annotations

import ast
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from glasshouse.ingest import legacy_iss, legacy_pe, sec_series

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "glasshouse.db"
OUT = ROOT / "data" / "research" / "series_fallback_dryrun.txt"


def main(out: Path = OUT) -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    ds = sec_series.load_dataset()
    names = {}  # series id -> normalised name, for display only
    for per_cik in ds.values():
        for n, ids in per_cik.items():
            for i in ids:
                names.setdefault(i, n)
    aliases = legacy_pe.load_aliases()
    rows = conn.execute(
        "SELECT p.accession, p.funds_unmapped, f.cik, f.report_type, "
        "COALESCE(i.display_name, f.cik) AS inst FROM legacy_parse p "
        "JOIN filings f ON f.accession = p.accession "
        "LEFT JOIN institutions i ON i.id = f.institution_id "
        "WHERE IFNULL(p.funds_unmapped,'') != ''").fetchall()
    per = defaultdict(lambda: {"headings": 0, "rows": 0, "unmapped_headings": 0,
                               "unmapped_rows": 0})
    examples: list[tuple[str, str, str, str, int]] = []
    for r in rows:
        hp = ROOT / "data" / "legacy_cache" / r["accession"] / f"{r['accession']}.hdr.sgml"
        hdr = hp.read_text("utf-8", "replace") if hp.exists() else ""
        fb = legacy_pe.build_fallback(ds, r["cik"], hdr)
        fa = legacy_pe.filing_aliases(aliases, r["cik"])
        suffix = r["report_type"] != "LEGACY_PROXYEDGE_REJECTED" and \
            not r["report_type"].startswith("LEGACY_PROXYEDGE")
        for heading, n in ast.literal_eval(r["funds_unmapped"]):
            p = per[r["inst"]]
            p["unmapped_headings"] += 1
            p["unmapped_rows"] += n
            if fb is None or legacy_pe._heading(heading) in fa:
                continue
            if suffix and legacy_iss.is_policy_section(heading):
                continue
            sid = fb.lookup(heading, suffix=suffix)
            if sid:
                p["headings"] += 1
                p["rows"] += n
                examples.append((heading, r["accession"], sid, names.get(sid, ""), n))
    lines = ["Dry run: SEC series-dataset fallback over data/glasshouse.db (read-only)",
             f"files: {', '.join(sec_series.FILES)}",
             "Counts are (accession, heading) pairs and parsed rows already counted as unmapped.",
             "", f"{'institution':44} {'headings':>9} {'rows':>9}   (of unmapped: headings, rows)"]
    tot = [0, 0, 0, 0]
    for inst, p in sorted(per.items(), key=lambda kv: -kv[1]["rows"]):
        if p["rows"]:
            lines.append(f"{inst[:44]:44} {p['headings']:>9,} {p['rows']:>9,}   "
                         f"({p['unmapped_headings']:,}, {p['unmapped_rows']:,})")
        for i, k in enumerate(("headings", "rows", "unmapped_headings", "unmapped_rows")):
            tot[i] += p[k]
    lines += [f"{'TOTAL':44} {tot[0]:>9,} {tot[1]:>9,}   ({tot[2]:,}, {tot[3]:,})", "",
              "25 random examples (heading | accession | series id | dataset series name "
              "(normalised) | rows):"]
    random.Random(2026).shuffle(examples)
    for h, acc, sid, nm, n in examples[:25]:
        lines.append(f"  {h} | {acc} | {sid} | {nm} | {n}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
