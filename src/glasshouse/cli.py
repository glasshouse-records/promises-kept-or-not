"""Glasshouse CLI.

    glasshouse init-db
    glasshouse seed
    glasshouse ingest enforcement --source all|doj_fcpa|ofac|worldbank|ungc
    glasshouse ingest npx --institution blackrock [--max-filings N] [--max-tables N]
    glasshouse ingest npx --cik 1100663 [...]
    glasshouse report flagged-votes [--shareholder-proposals] [--limit N]
    glasshouse integrity
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import findings, ledger, registry


def _conn():
    conn = ledger.connect()
    registry.sync_to_ledger(conn)
    return conn


def cmd_init_db(_args) -> int:
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
    print(f"ledger ready at {ledger.DB_PATH} ({n} institutions registered)")
    return 0


def cmd_seed(_args) -> int:
    from . import seed
    conn = _conn()
    counts = seed.load_all(conn)
    for src, n in counts.items():
        print(f"  {src:<16} +{n}")
    print(f"curated snapshots loaded (source_kind=curated_snapshot, snapshot {seed.SNAPSHOT_DATE}; "
          f"quarantined until re-verified — see PENDING_VERIFICATION.md)")
    return 0


def cmd_ingest_enforcement(args) -> int:
    from .ingest import doj_fcpa, ofac, ungc, worldbank
    sources = {
        "doj_fcpa": doj_fcpa.fetch,
        "ofac": ofac.fetch,
        "worldbank": worldbank.fetch,
        "ungc": ungc.fetch,
    }
    names = list(sources) if args.source == "all" else [args.source]
    conn = _conn()
    for name in names:
        actions = sources[name]()
        n = ledger.insert_enforcement(conn, actions)
        print(f"  {name:<12} fetched {len(actions):>6}, inserted {n:>6} new")
    return 0


def cmd_ingest_npx(args) -> int:
    from .ingest import npx
    conn = _conn()
    targets: list[tuple[str, str | None]] = []
    if args.cik:
        targets.append((args.cik, args.institution))
    elif args.institution:
        for trust in registry.npx_ciks(args.institution):
            targets.append((trust["cik"], args.institution))
    else:
        print("error: provide --cik or --institution", file=sys.stderr)
        return 2
    for cik, inst_id in targets:
        stats = npx.ingest_npx(conn, cik, institution_id=inst_id,
                               max_filings=args.max_filings, max_tables=args.max_tables)
        print(f"  CIK {cik}: {stats}")
    return 0


def cmd_ingest_commitments(args) -> int:
    from .ingest import commitments
    conn = _conn()
    insts = registry.load()
    new = commitments.fetch_live(conn, insts)
    for key, is_new in new.items():
        print(f"  {key:<56} {'NEW VERSION' if is_new else 'unchanged'}")
    if args.wayback:
        n = commitments.fetch_wayback(conn, insts, max_versions=args.wayback_limit)
        print(f"  wayback: {n} historical versions archived")
    if not new and not args.wayback:
        print("no commitment documents configured (add `commitments:` entries "
              "to config/institutions.yaml)")
    return 0


def cmd_report_policy_edits(_args) -> int:
    from .ingest import commitments
    conn = _conn()
    edits = commitments.policy_edits(conn)
    if not edits:
        print("no documents with multiple versions yet")
        return 0
    for e in edits:
        print(f"\n{e['institution_id']}/{e['doc_label']}: {e['n_versions']} versions "
              f"({e['first_seen']} → {e['last_seen']})")
        for v in e["versions"]:
            when = v["wayback_timestamp"] or v["retrieval_date"]
            print(f"  {when}  sha {v['sha256'][:12]}  {v['content_path']}")
    print("\nEach multi-version document is a potential silent-policy-edit "
          "finding; diff the content paths above.")
    return 0


def cmd_report_vote_divergence(args) -> int:
    conn = _conn()
    rows = findings.vote_divergence(
        conn, shareholder_proposals_only=args.shareholder_proposals, limit=args.limit)
    if not rows:
        print("no vote divergence found (ingest N-PX data first)")
        return 0
    for r in rows:
        split = " vs ".join(f"{how}: {int(n):,} sh" for how, n in sorted(r.ways.items()))
        print(f"\n{r.institution} split at {r.issuer_name} ({r.meeting_date})")
        print(f"  proposal: {r.vote_description}")
        print(f"  {split}  ({r.n_records} vote records)")
    print(f"\n{len(rows)} divergent proposals — the same manager voting both ways "
          f"on identical questions. Finding-grade: internal to one filer's own N-PX.")
    return 0


def cmd_diff(args) -> int:
    from . import diff
    conn = _conn()
    d = diff.compute(conn)
    base = d.since or "ledger creation (first run)"
    print(f"deltas since {base}:")
    print(f"  votes                +{d.new_votes:,}")
    print(f"  enforcement actions  +{d.new_enforcement:,}")
    print(f"  commitment versions  +{d.new_commitment_versions:,}")
    for s in d.enforcement_samples:
        print(f"    new: {s['agency']} | {s['company_name']} | {s['resolution_type']} | {s['primary_ref'] or 'NO REF'}")
    for s in d.commitment_samples:
        print(f"    new: {s['institution_id']}/{s['doc_label']} @ {s['wayback_timestamp'] or s['retrieval_date']}")
    if args.record:
        ts = diff.record_run(conn)
        print(f"run recorded at {ts}")
    return 0


def cmd_report_flagged_votes(args) -> int:
    conn = _conn()
    rows = findings.flagged_votes(
        conn, shareholder_proposals_only=args.shareholder_proposals, limit=args.limit)
    if not rows:
        print("no flagged votes (ingest N-PX data and enforcement sources first)")
        return 0
    for r in rows:
        print(f"\n{r.institution} @ {r.issuer_name} ({r.meeting_date}) [LEAD — {r.join_method} join]")
        print(f"  voted {r.how_voted} (mgmt rec: {r.management_recommendation or '—'})")
        print(f"  proposal: {r.vote_description}")
        print(f"  enforcement: {r.agency} | {r.resolution_type} | {r.primary_ref or 'NO REF'} | {r.action_date}")
    print(f"\n{len(rows)} leads. ALL name-join rows are quarantined until the entity "
          f"match is corroborated by identifier or human review (same name ≠ same "
          f"company — see PENDING_VERIFICATION.md). Resolution types are legally "
          f"distinct (DPA/NPA ≠ conviction); see METHODOLOGY.md.")
    return 0


def cmd_integrity(_args) -> int:
    conn = _conn()
    problems = ledger.integrity_check(conn)
    hard_fail = False
    for check, rows in problems.items():
        status = "OK" if not rows else f"{len(rows)} rows"
        print(f"  {check:<36} {status}")
        if rows and check != "quarantined":
            hard_fail = True
    if problems["quarantined"]:
        print(f"\n  note: {len(problems['quarantined'])} quarantined rows are barred "
              f"from publication (see PENDING_VERIFICATION.md) but valid as leads.")
    return 1 if hard_fail else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="glasshouse")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("seed").set_defaults(func=cmd_seed)

    ing = sub.add_parser("ingest").add_subparsers(dest="what", required=True)
    enf = ing.add_parser("enforcement")
    enf.add_argument("--source", default="all",
                     choices=["all", "doj_fcpa", "ofac", "worldbank", "ungc"])
    enf.set_defaults(func=cmd_ingest_enforcement)
    npx_p = ing.add_parser("npx")
    npx_p.add_argument("--cik")
    npx_p.add_argument("--institution")
    npx_p.add_argument("--max-filings", type=int, default=None)
    npx_p.add_argument("--max-tables", type=int, default=None,
                       help="stop after N proxyTables per exhibit (smoke tests)")
    npx_p.set_defaults(func=cmd_ingest_npx)
    com = ing.add_parser("commitments")
    com.add_argument("--wayback", action="store_true",
                     help="also archive historical versions from the Wayback Machine")
    com.add_argument("--wayback-limit", type=int, default=10)
    com.set_defaults(func=cmd_ingest_commitments)

    rep = sub.add_parser("report").add_subparsers(dest="which", required=True)
    fv = rep.add_parser("flagged-votes")
    fv.add_argument("--shareholder-proposals", action="store_true")
    fv.add_argument("--limit", type=int, default=200)
    fv.set_defaults(func=cmd_report_flagged_votes)
    vd = rep.add_parser("vote-divergence")
    vd.add_argument("--shareholder-proposals", action="store_true")
    vd.add_argument("--limit", type=int, default=100)
    vd.set_defaults(func=cmd_report_vote_divergence)
    rep.add_parser("policy-edits").set_defaults(func=cmd_report_policy_edits)

    df = sub.add_parser("diff")
    df.add_argument("--record", action="store_true",
                    help="record this ledger frontier as the new baseline run")
    df.set_defaults(func=cmd_diff)

    sub.add_parser("integrity").set_defaults(func=cmd_integrity)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
