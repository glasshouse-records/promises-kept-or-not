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
from datetime import UTC

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
    from .ingest import courtlistener, doj_fcpa, epa_echo, fed, ofac, ungc, worldbank
    conn = _conn()
    sources = {
        "doj_fcpa": doj_fcpa.fetch,
        "ofac": ofac.fetch,
        "worldbank": worldbank.fetch,
        "ungc": ungc.fetch,
        "fed": fed.fetch,
        "epa_echo": epa_echo.fetch,
        "dockets": lambda: courtlistener.fetch_for(courtlistener.tracked_names(conn)),
    }
    names = list(sources) if args.source == "all" else [args.source]
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
                               max_filings=args.max_filings, max_tables=args.max_tables,
                               legacy=getattr(args, "legacy", False))
        print(f"  CIK {cik}: {stats}")
    return 0


def cmd_ingest_nport(args) -> int:
    from .ingest import nport
    conn = _conn()
    stats = nport.ingest_nport(conn, args.cik, institution_id=args.institution,
                               max_filings=args.max_filings)
    print(f"  {stats}")
    return 0


def cmd_digest(_args) -> int:
    from . import digest
    conn = _conn()
    path = digest.render(conn)
    print(f"  digest rendered → {path}")
    print("  (a human sends it; this tool never does)")
    return 0


def cmd_export(_args) -> int:
    import json as _json
    from datetime import date as _date

    from . import dataset, publish
    from .http import DATA_DIR
    conn = _conn()
    out = DATA_DIR / "exports"
    dest = out / f"glasshouse-public-{_date.today().isoformat()}.db"
    publish.build_public_snapshot(conn, dest)
    # The dataset ships self-describing: datasheet + machine-readable package.
    (out / "DATASHEET.md").write_text(dataset.build_datasheet(conn))
    (out / "datapackage.json").write_text(
        _json.dumps(dataset.build_datapackage(conn), indent=2))
    size = dest.stat().st_size / 1e6
    print(f"  public snapshot → {dest} ({size:.0f} MB)")
    print(f"  datasheet       → {out / 'DATASHEET.md'}")
    print(f"  datapackage     → {out / 'datapackage.json'}")
    print("  publishable data only (no operator tables; approved findings only); "
          "self-describing schema + honest coverage bundled.")
    print(f"  serve with: datasette {dest} -m datasette/metadata.json")
    return 0


def cmd_release(args) -> int:
    from . import release
    conn = _conn()
    info = release.build_release(conn, version=args.version,
                                 with_parquet=not args.no_parquet,
                                 with_sqlite=args.with_sqlite)
    print(f"  release v{info['version']} → {info['dir']}")
    print(f"  {info['file_count']} files · {info['bytes'] / 1e6:.1f} MB · "
          f"formats: {', '.join(info['formats'])}")
    for t, meta in info["tables"].items():
        if meta["rows"]:
            print(f"    {t:<22} {meta['rows']:>10,} rows")
    print("  verify:  cd " + info["dir"] + " && sha256sum -c MANIFEST.sha256")
    print("  publish: upload the vX directory to Zenodo/HF for a citable DOI.")
    if "parquet" not in info["formats"]:
        print("  (CSV only — `pip install glasshouse[release]` to also emit Parquet)")
    return 0


def cmd_investigate(args) -> int:
    from . import investigate
    conn = _conn()

    if args.action == "theme":
        kws = [k.strip() for k in args.keywords.split(",")] if getattr(args, "keywords", None) else None
        recs = investigate.theme_records(conn, args.theme, keywords=kws, label=args.theme)
        committed = [r for r in recs if r.committed and r.n_theme]
        if getattr(args, "export", None):
            hyp = (f"Managers committing to '{args.theme}'"
                   + (f" (keywords: {args.keywords})" if kws else "")
                   + " vote against shareholder proposals advancing it.")
            packs = "\n\n---\n\n".join(
                investigate.evidence_pack(r, hypothesis=hyp) for r in committed) or \
                "# No committed managers with votes on this hypothesis.\n"
            from pathlib import Path as _P
            _P(args.export).write_text(packs)
            print(f"  evidence pack ({len(committed)} managers) → {args.export}")
        kwnote = f" (keywords: {args.keywords})" if kws else ""
        print(f"\nTHEME: {args.theme}{kwnote} — managers that COMMIT to it, vs how they VOTE on it")
        print("against-rate = AGAINST / (FOR+AGAINST) on proposals advancing the theme; "
              "anti-theme proposals and legacy votes excluded.\n")
        if not committed:
            print("  no committed managers with theme votes yet.")
            return 0
        print(f"  {'manager':<26}{'against':>8}{'for':>6}{'rate':>7}   commitment (SAY)")
        for r in committed:
            print(f"  {r.institution_name[:25]:<26}{r.votes_against:>8}{r.votes_for:>6}"
                  f"{r.against_rate*100:>6.0f}%   “{(r.commitment_quote or '')[:46]}…”")
        top = committed[0]
        print(f"\n  ── drill: {top.institution_name} — top AGAINST votes on {args.theme} ──")
        print(f"     SAY [{top.doc_label} @ {top.doc_version}]: “{(top.commitment_quote or '')[:150]}”")
        print(f"     cite: {top.doc_url}")
        for e in top.examples[:args.examples]:
            print(f"     • {e['meeting_date']}  AGAINST  {e['issuer_name'][:30]:<30} "
                  f"{e['shares_voted']:>13,.0f} sh")
            print(f"         “{e['vote_description'][:78]}”")
        print(f"     (filing accession {top.examples[0]['accession'] if top.examples else 'n/a'} → EDGAR)")
        return 0

    if args.action == "matrix":
        if getattr(args, "cache", False):
            investigate.cache_matrix(conn)   # builds + folds in holdings-weighted + writes
            m = investigate.load_matrix()
            print(f"  cached → {investigate.MATRIX_CACHE} (workbench Investigate tab reads this)")
        else:
            m = investigate.build_matrix(conn)
        themes = m["themes"]
        rows = []
        for i in m["institutions"]:
            committed = {t: c["rate"] for t, c in i["cells"].items() if c["committed"] and c["n"]}
            if committed:
                rows.append((i["name"], committed))
        rows.sort(key=lambda r: -max(r[1].values()))
        print("\nHYPOCRISY MATRIX — against-rate (%) on each theme, for managers that "
              "publicly COMMIT to it.\nBlank = no commitment / no votes on that theme.\n")
        print("  " + " " * 22 + "".join(f"{t[:9]:>11}" for t in themes))
        for name, committed in rows:
            cells = "".join((f"{committed[t]*100:>10.0f}%" if t in committed else f"{'·':>11}")
                            for t in themes)
            print(f"  {name[:22]:<22}{cells}")
        print("\n  Read a row for a manager's say-vs-do across themes; a column for who's "
              "worst on a theme.\n  Drill a cell: glasshouse investigate theme <theme>  "
              "(or click it in the workbench Investigate tab).")
        return 0

    if args.action == "refresh":
        from . import agent, timeline
        p = investigate.cache_matrix(conn)
        print(f"  matrix cache → {p}")
        tp = timeline.cache_timelines(conn)
        n_ev = sum(len(d["events"]) for t in timeline.load_timelines()["institutions"].values()
                   for d in t["themes"].values())
        print(f"  timelines cache → {tp} ({n_ev} policy-change events)")
        briefs = agent.investigate_and_draft(conn)
        print(f"  agent drafts → {len(briefs)} leads in data/agent/briefs/ (unverified)")
        print("  workbench Investigate + Drafts tabs now reflect the current ledger.")
        return 0

    if args.action == "holdings":
        kws = [k.strip() for k in args.keywords.split(",")] if getattr(args, "keywords", None) else None
        rows = investigate.holdings_weighted(conn, args.theme, keywords=kws, min_held=args.min_held)
        print(f"\nHOLDINGS-WEIGHTED: do managers vote against '{args.theme}' MORE at their "
              "BIGGEST positions?\n(against-rate at large vs small holdings, split at the "
              "manager's median position size)\n")
        if not rows:
            print(f"  no managers with ≥{args.min_held} held theme votes.")
            return 0
        print(f"  {'manager':<26}{'big pos':>9}{'small pos':>11}{'gap':>8}")
        for r in rows:
            print(f"  {r['institution_name'][:25]:<26}{r['large_rate']*100:>8.0f}%"
                  f"{r['small_rate']*100:>10.0f}%{r['delta']*100:>+7.0f}")
        print("\n  gap > 0 = votes against the theme MORE where it holds the most "
              "(skin-in-the-game). Leads — verify before publishing.")
        return 0

    if args.action == "trend":
        kws = [k.strip() for k in args.keywords.split(",")] if getattr(args, "keywords", None) else None
        tr = investigate.theme_trend(conn, args.theme, keywords=kws)
        years = sorted({y for v in tr.values() for y in v["years"]})
        print(f"\nTREND: against-rate (%) by meeting year on '{args.theme}', committed managers\n")
        if not years:
            print("  no committed managers with dated theme votes.")
            return 0
        print("  " + " " * 24 + "".join(f"{y:>8}" for y in years))
        for iid in sorted(tr, key=lambda k: -max(d["rate"] for d in tr[k]["years"].values())):
            row = "".join((f"{tr[iid]['years'][y]['rate']*100:>7.0f}%" if y in tr[iid]["years"]
                           else f"{'·':>8}") for y in years)
            print(f"  {tr[iid]['name'][:24]:<24}{row}")
        print("\n  A rising row = a manager voting against the theme MORE over time.")
        return 0

    if args.action == "company":
        r = investigate.company_record(conn, args.name)
        rows = [h for h in r["holders"] if h["held_usd"] or h["votes_against"] or h["votes_for"]]
        print(f"\nCOMPANY: {r['company']} — who holds it and how they voted there\n")
        if not rows:
            print(f"  no holdings or votes found matching '{args.name}'.")
            return 0
        print(f"  {'manager':<26}{'held':>12}{'for':>6}{'against':>8}   notable AGAINST vote")
        for h in rows:
            held = f"${h['held_usd']/1e9:.1f}B" if h["held_usd"] else "—"
            ex = h["examples"][0]["vote_description"][:42] if h["examples"] else ""
            print(f"  {h['institution_name'][:25]:<26}{held:>12}{h['votes_for']:>6}"
                  f"{h['votes_against']:>8}   {ex}")
        print("\n  Drill a manager's votes at this company: it's in the row's examples "
              "(date · proposal · shares · N-PX). Leads — verify before publishing.")
        return 0

    if args.action == "institution":
        recs = investigate.institution_record(conn, args.id)
        if not recs:
            print(f"  no record for institution '{args.id}'")
            return 0
        name = next(iter(recs.values())).institution_name
        print(f"\n{name} — say-vs-do across themes\n")
        for theme, r in recs.items():
            say = "committed" if r.committed else "no commitment"
            rate = f"{r.against_rate*100:.0f}% against" if r.n_theme else "no theme votes"
            print(f"  {theme:<20} {say:<14} {rate:<16} (for {r.votes_for}, against {r.votes_against})")
        return 0
    return 2


def cmd_agent(args) -> int:
    from . import agent
    conn = _conn()
    briefs = agent.investigate_and_draft(conn, min_rate=args.min_rate,
                                         min_votes=args.min_votes, top_n=args.top,
                                         llm=getattr(args, "llm", False))
    if not briefs:
        print("  no say-vs-do gaps met the thresholds "
              f"(rate ≥ {args.min_rate}, votes ≥ {args.min_votes}). Nothing drafted.")
        return 0
    from datetime import date as _d
    print(f"\n  {len(briefs)} story drafts → data/agent/briefs/{_d.today().isoformat()}/")
    print("  DRAFTS — unverified leads. A human verifies every source + promotes "
          "via the review gate. Nothing here is published or sent.\n")
    for i, b in enumerate(briefs, 1):
        print(f"  {i:>2}. [score {b['score']}] {b['headline']}")
    return 0


def cmd_detectors(args) -> int:
    from . import detectors
    conn = _conn()
    if args.action == "list":
        print("\n  THE DETECTOR LIBRARY — each is a tool that asks one question of the record:\n")
        for d in detectors.registry().values():
            t = detectors.TECHNIQUES[d.technique]
            print(f"  ● {d.id}  [{t['family']}]")
            print(f"      {d.question}")
            print(f"      reads: {t['reads']}")
            print(f"      trust: {d.validation}\n")
        return 0
    if args.action == "run":
        reg = detectors.registry()
        chosen = [reg[args.detector]] if args.detector else list(reg.values())
        if args.detector and args.detector not in reg:
            print(f"  no detector {args.detector!r}. See: glasshouse detectors list")
            return 2
        for d in chosen:
            leads = d.run(conn, min_rate=args.min_rate, min_votes=args.min_votes)
            print(f"\n  {d.id} — {len(leads)} cited leads (unverified; a human confirms before publication):\n")
            for ld in leads[:20]:
                flag = " ⚠ small sample" if ld.evidence.get("low_confidence") else ""
                print(f"   [{ld.strength:.0%}] {ld.headline}{flag}")
        return 0
    return 2


def cmd_promise(args) -> int:
    """The systemic finding: does a published commitment predict how a manager
    votes? Paired (each manager against itself), so house voting philosophy
    cannot manufacture the answer."""
    from . import investigate, systemic
    conn = _conn()
    matrix = investigate.load_matrix() or investigate.build_matrix(conn)
    print(systemic.summary_markdown(systemic.industry_summary(matrix, min_votes=args.min_votes)))
    return 0


def cmd_ftm(args) -> int:
    """Export the unique Glasshouse record as FollowTheMoney entities, ready to
    import into OCCRP Aleph / OpenAleph next to OpenSanctions et al."""
    from pathlib import Path

    from . import ftm
    conn = _conn()
    out = Path(args.out) if args.out else (ledger.DATA_DIR / "export" / "glasshouse.ftm.json")
    stats = ftm.export_ftm(conn, out)
    print(f"  {stats['companies']} Company + {stats['events']} Event entities → {stats['path']}")
    print("  Quarantine held: allegations/unverified/OFAC excluded from this public artifact.")
    print("  Import into Aleph/OpenAleph alongside OpenSanctions (same FtM format).")
    return 0


def cmd_cases(args) -> int:
    """Case files: every independent footprint converging on one manager × theme,
    ranked by strong corroboration. What a human publisher reads before signing."""
    from . import casefile, investigate, timeline
    conn = _conn()
    kw = {"matrix": investigate.load_matrix(), "timelines": timeline.load_timelines()}
    cases = casefile.build_cases(conn, **kw)
    if args.action == "show":
        match = [c for c in cases if c.institution_id == args.institution
                 and c.subject == args.theme]
        if not match:
            print(f"  no case for {args.institution} × {args.theme}. Try: glasshouse cases list")
            return 2
        print(casefile.case_markdown(match[0]))
        return 0
    print(f"\n  {len(cases)} corroborated cases — each needs at least one STRONG footprint.")
    print("  Ranked by INDEPENDENT strong corroboration. All are leads; a human "
          "verifies before publication.\n")
    for c in cases:
        bits = f"{c.n_strong} strong"
        if c.n_supporting:
            bits += f" + {c.n_supporting} supporting"
        if c.n_descriptive:
            bits += f" + {c.n_descriptive} descriptive"
        print(f"   [{bits:36s}] {c.institution_name} × {c.subject}")
        print(f"       {' · '.join(f.detector_id for f in c.footprints)}")
    print("\n  Read one: glasshouse cases show <institution_id> <theme>")
    return 0


def cmd_firststone(args) -> int:
    from . import firststone
    if args.action == "run":
        conn = _conn()
        stories = firststone.run(conn, min_rate=args.min_rate, min_votes=args.min_votes,
                                 top_n=args.top, llm=getattr(args, "llm", False))
        filed = [s for s in stories if s["state"] == "awaiting_publisher"]
        spiked = [s for s in stories if s["state"] == "spiked"]
        print(f"\n  FIRST STONE — edition cycle complete: {len(filed)} filed, "
              f"{len(spiked)} spiked by the desks → data/newsroom/runs/")
        for s in filed:
            print(f"   ⏳ {s['slug']}: {s['headline']}")
        for s in spiked:
            print(f"   ✗ {s['slug']}: spiked — {s['trail'][-1]['note'][:80]}")
        print("\n  Stories await the PUBLISHER — that chair is human. Review in the "
              "workbench (First Stone tab)\n  or: glasshouse firststone publish <slug> "
              "--note '<what you verified>'")
        return 0
    if args.action == "list":
        run = firststone.load_run()
        if not run:
            print("  no newsroom run on file — run: glasshouse firststone run")
            return 0
        print(f"\n  run of {run['generated'][:10]}:")
        for s in run["stories"]:
            print(f"   {s['state']:<20} {s['slug']}")
        for p in firststone.load_published():
            print(f"   published {p['published'][:10]}    {p['slug']} — note: {p['publisher_note'][:60]}")
        return 0
    if args.action == "publish":
        rec = firststone.publish(args.slug, note=args.note or "", human_confirmed=True)
        print(f"  published under the First Stone masthead: {rec['slug']}\n"
              f"  rebuild the site to ship it: glasshouse site")
        return 0
    if args.action == "spike":
        firststone.spike(args.slug, note=args.note or "")
        print(f"  spiked: {args.slug}")
        return 0
    return 2


def cmd_ingest_commitments(args) -> int:
    from .ingest import commitments
    conn = _conn()
    if args.purge_errors:
        n = commitments.purge_error_pages(conn)
        print(f"  purged {n} error-page rows masquerading as policy versions")
        return 0
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


def cmd_report_contradictions(args) -> int:
    from . import contradictions
    conn = _conn()
    rows = contradictions.find_commitment_vote_contradictions(
        conn, limit_per_theme=args.limit_per_theme)
    if args.theme:
        rows = [r for r in rows if r.theme == args.theme]
    if not rows:
        print("no commitment-vote contradiction candidates "
              "(need ingested commitments AND N-PX votes for the same institution)")
        return 0
    for r in rows:
        print(f"\n[{r.theme}] {r.institution_id} — CANDIDATE (quarantined; human review required)")
        print(f"  SAYS ({r.doc_label} @ {r.doc_version}, sha {r.doc_sha256[:12]}):")
        print(f"    \"{r.commitment_quote}\"")
        print(f"    source: {r.doc_url}")
        print(f"  DID  (N-PX {r.accession}, {r.issuer_name}, meeting {r.meeting_date}):")
        print(f"    voted {r.how_voted} ({int(r.shares_voted):,} sh; mgmt rec {r.management_recommendation})")
        print(f"    proposal: {r.vote_description}")
    print(f"\n{len(rows)} candidates. None is a finding until a human reads the "
          f"commitment and the proposal together (see PENDING_VERIFICATION.md).")
    return 0


def cmd_ingest_13f(args) -> int:
    from .ingest import thirteenf
    conn = _conn()
    insts = registry.load()
    cik = args.cik or insts[args.institution]["cik"]
    stats = thirteenf.ingest_13f(conn, cik, institution_id=args.institution,
                                 max_filings=args.max_filings)
    print(f"  {stats}")
    return 0


def cmd_scan_events(args) -> int:
    from . import events
    conn = _conn()
    stats = events.scan(conn, sources=args.source)
    if getattr(args, "news", False):
        stats["news_triggers"] = events.news_scan(conn)
    print(f"  {stats} — alert packs in {events.ALERTS_DIR}/")
    return 0


def cmd_site(_args) -> int:
    from . import site
    conn = _conn()
    stats = site.build(conn)
    print(f"  built {stats['pages']} pages, {stats['findings']} published findings → {site.SITE_DIR}/")
    print(f"  preview: python -m http.server -d {site.SITE_DIR}")
    return 0


def cmd_outreach_draft(args) -> int:
    from . import contradictions, outreach
    conn = _conn()
    cands = contradictions.find_commitment_vote_contradictions(conn, limit_per_theme=10)
    cands = [c for c in cands
             if (not args.institution or c.institution_id == args.institution)
             and (not args.theme or c.theme == args.theme)]
    if not cands:
        print("no matching contradiction candidates to draft from")
        return 1
    c = max(cands, key=lambda x: x.shares_voted)
    oid = outreach.draft_from_candidate(conn, c, kind=args.kind)
    row = conn.execute("SELECT body_path FROM outreach WHERE id=?", (oid,)).fetchone()
    print(f"  draft #{oid} ({args.kind}) → {row['body_path']}")
    print("  NOTHING IS SENT. Review, send manually, then: "
          f"glasshouse outreach mark-sent {oid} --i-sent-this")
    return 0


def cmd_outreach_list(_args) -> int:
    conn = _conn()
    for r in conn.execute("SELECT id, kind, institution_id, subject, status, sent_date, "
                          "response_date FROM outreach ORDER BY id"):
        print(f"  #{r['id']} [{r['status']:<8}] {r['kind']:<12} {r['institution_id']} — "
              f"{r['subject']} (sent: {r['sent_date'] or '—'}; response: {r['response_date'] or '—'})")
    return 0


def cmd_outreach_mark_sent(args) -> int:
    from . import outreach
    outreach.mark_sent(_conn(), args.id, human_confirmed=args.i_sent_this)
    print(f"  #{args.id} marked sent {'' if args.i_sent_this else '(refused)'}")
    return 0


def cmd_outreach_record_response(args) -> int:
    from . import outreach
    outreach.record_response(_conn(), args.id, args.summary)
    print(f"  #{args.id} response recorded")
    return 0


def cmd_report_non_response(_args) -> int:
    from . import outreach
    rows = outreach.non_response_ledger(_conn())
    if not rows:
        print("non-response ledger is empty")
        return 0
    for r in rows:
        print(f"  Asked {r['institution_id']} on {r['sent_date']} about "
              f"\"{r['subject']}\". Day {r['days_without_response']}: no response.")
    return 0


def cmd_report_awards(_args) -> int:
    from . import contradictions, outreach
    conn = _conn()
    cands = contradictions.find_commitment_vote_contradictions(conn, limit_per_theme=25)
    by_inst: dict[str, dict] = {}
    for c in cands:
        d = by_inst.setdefault(c.institution_id, {"n": 0, "shares": 0.0})
        d["n"] += 1
        d["shares"] += c.shares_voted
    print("ANNUAL RANKED AWARDS (draft — candidates only, all quarantined)\n")
    print("Most votes against own stated policy themes:")
    for inst, d in sorted(by_inst.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {inst}: {d['n']} candidate votes")
    print("\nLargest say–do gap (shares-weighted candidates):")
    for inst, d in sorted(by_inst.items(), key=lambda kv: -kv[1]["shares"]):
        print(f"  {inst}: {int(d['shares']):,} shares voted against own themes")
    nr = outreach.non_response_ledger(conn)
    if nr:
        print("\nLongest non-response:")
        for r in sorted(nr, key=lambda x: -x["days_without_response"])[:5]:
            print(f"  {r['institution_id']}: day {r['days_without_response']} — {r['subject']}")
    return 0


def cmd_enrich_lei(args) -> int:
    from .ingest import gleif
    conn = _conn()
    stats = gleif.enrich_from_votes(conn, limit=args.limit)
    print(f"  GLEIF enrichment: {stats}")
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
        if r.issuer_lei:
            print(f"  issuer identity (GLEIF): LEI {r.issuer_lei}, country {r.issuer_country or '?'}")
        print(f"  voted {r.how_voted} (mgmt rec: {r.management_recommendation or '—'})")
        print(f"  proposal: {r.vote_description}")
        print(f"  enforcement: {r.agency} | {r.resolution_type} | {r.primary_ref or 'NO REF'} | {r.action_date}")
    print(f"\n{len(rows)} leads. ALL name-join rows are quarantined until the entity "
          f"match is corroborated by identifier or human review (same name ≠ same "
          f"company — see PENDING_VERIFICATION.md). Resolution types are legally "
          f"distinct (DPA/NPA ≠ conviction); see METHODOLOGY.md.")
    return 0


def cmd_workbench(args) -> int:
    from . import workbench
    server = workbench.serve(port=args.port)
    print(f"  workbench → http://127.0.0.1:{args.port}  (local only; Ctrl-C to stop)")
    print("  review candidates, label leads (grows the eval gold set), manage")
    print("  outreach, record signals — all through the same gates as the CLI.")
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def cmd_discover_npx(args) -> int:
    from .ingest.discover import discover_npx_filers
    cands = discover_npx_filers(args.name, max_candidates=args.limit)
    if not cands:
        print(f"  no N-PX-filing candidates for {args.name!r}")
        return 0
    print(f"  candidate N-PX filers for {args.name!r} "
          f"(PROPOSALS — verify before adding to the registry; wrong attribution "
          f"puts another fund's votes in this manager's mouth):")
    for c in cands:
        print(f"   CIK {c['cik']:>9}  N-PX={c['npx_filings']:>3}  latest={c['latest']}  {c['name']}")
    print("  add confirmed trust(s) under the institution's npx_ciks in "
          "config/institutions.yaml, then `glasshouse ingest npx --institution <id>`.")
    return 0


def cmd_improve(args) -> int:
    from . import improve, metrics
    conn = _conn()
    if args.apply_safe:
        res = improve.apply_safe(conn)
        for name, what in res["ran"].items():
            print(f"  [auto] {name}: {what}")
        print(f"  balanced index {res['index_before']} → {res['index_after']} "
              f"({res['delta']:+})")
    else:
        metrics.snapshot(conn)
    a = improve.assess(conn)
    d = metrics.delta(conn)
    print(f"\n  BALANCED INDEX: {a['balanced_index']}/100"
          + (f" ({d:+} since last run)" if d is not None else ""))
    print("  components: " + ", ".join(f"{k} {v}" for k, v in a["components"].items()))
    print("  highest-leverage next moves (tool self-improves; data/publish stay yours):")
    for x in a["agenda"]:
        tag = "AUTO" if x["auto_safe"] else x["executor"]
        print(f"   P{x['priority']} [{tag}] {x['area']}: {x['action']}")
    path = improve.write_brief(conn)
    print(f"\n  agenda → {path}")
    return 0


def cmd_doctor(args) -> int:
    from . import doctor
    conn = _conn()
    report_path, task_path = doctor.emit(conn)
    import json as _json
    report = _json.loads(open(report_path).read())
    for c in report["checks"]:
        mark = "ok " if c["ok"] else ("ERR" if c["severity"] == "error" else "WRN")
        print(f"  [{mark}] {c['name']}: {c['detail']}")
    print(f"\n  report → {report_path}")
    if task_path:
        print(f"  repair task → {task_path}")
        print("  hand it to the repair loop: claude --agent source-medic "
              f"-p \"$(cat {task_path})\"")
    return 0 if report["healthy"] else 1


def cmd_triage(args) -> int:
    from . import triage
    from .llm import NotConfigured
    conn = _conn()
    try:
        if args.what == "leads":
            stats = triage.triage_leads(conn, limit=args.limit)
        else:
            stats = triage.classify_proposals(conn, limit=args.limit)
        print(f"  {stats} (ADVISORY — stored in triage table, gate unchanged)")
        return 0
    except NotConfigured as exc:
        print(f"  {exc}")
        return 2


def cmd_eval(args) -> int:
    from . import evals
    from .llm import NotConfigured
    conn = _conn()
    try:
        r = evals.run_matcher_eval(conn)
    except NotConfigured as exc:
        print(f"  {exc}")
        return 2
    print(f"  model {r['model']} on {r['n']} gold pairs: "
          f"precision(match)={r['precision_on_match']} recall={r['recall_on_match']} "
          f"unsure={r['unsure']}")
    print(f"  bar: precision ≥ {r['bar']} with zero false matches → "
          f"{'PASSES — triage may be trusted' if r['passes_bar'] else 'FAILS — do not trust triage output'}")
    for f in r["failures"]:
        print(f"    MISS [{f['label']} judged {f['verdict']}] {f['why']} — {f['rationale']}")
    return 0 if r["passes_bar"] else 1


def cmd_review_council(args) -> int:
    from . import council
    from .llm import NotConfigured
    conn = _conn()
    try:
        tally = council.evaluate_pending(conn, limit=args.limit)
    except NotConfigured as exc:
        print(f"  {exc}")
        return 2
    print(f"  council tiers (advisory; your approval still required): {tally}")
    print("  per-candidate reasoning is in the workbench Review tab.")
    return 0


def cmd_review(args) -> int:
    from . import review
    conn = _conn()
    if args.action == "council":
        return cmd_review_council(args)
    if args.action == "dossier":
        path = review.dossier(conn, args.id)
        print(f"  dossier → {path}")
        return 0
    if args.action == "sync":
        r = review.sync(conn)
        print(f"  +{r['added']} new, -{r['pruned']} pruned (no longer generated); "
              f"{r['pending']} live candidates. totals: {review.stats(conn)}")
    elif args.action == "list":
        for f in review.queue(conn, args.status):
            p = f["payload"]
            print(f"\n#{f['id']} [{f['status']}] {f['theme']} | {f['institution_id']} "
                  f"@ {p['issuer_name']} ({p['meeting_date']})")
            print(f"   says: \"{p['commitment_quote'][:110]}\"")
            print(f"   did:  {p['how_voted']} {int(float(p['shares_voted'])):,} sh — "
                  f"{p['vote_description'][:110]}")
            if f["reviewer_note"]:
                print(f"   note: {f['reviewer_note']} ({f['reviewed_date']})")
    else:  # approve / reject
        from . import review as rv
        rv.decide(conn, args.id, "approved" if args.action == "approve" else "rejected",
                  args.note or "")
        print(f"  #{args.id} {args.action}d; totals: {rv.stats(conn)}")
    return 0


def cmd_report_own_record(_args) -> int:
    conn = _conn()
    rows = findings.own_record(conn)
    if not rows:
        print("no enforcement records matching tracked institutions' names")
        return 0
    for r in rows:
        print(f"\n{r.institution} [LEAD — name join; confirm corporate relationship]")
        print(f"  {r.agency} | {r.resolution_type} | {r.primary_ref or 'NO REF'} | "
              f"{r.action_date} | ${r.penalty_usd or 0:,}")
        print(f"  {(r.description or '')[:180]}")
    print(f"\n{len(rows)} records. An institution's own record vs its marketing is a "
          f"first-class finding class — after human verification.")
    return 0


def cmd_report_holdings_diff(args) -> int:
    from . import diff
    conn = _conn()
    d = diff.holdings_changes(conn, args.institution)
    if len(d["periods"]) < 2:
        print(f"need two 13-F periods for {args.institution}; have {d['periods']}")
        return 1
    print(f"{args.institution}: {d['periods'][1]} → {d['periods'][0]} "
          f"(positions ≥ $10M)")
    for label in ("opened", "closed"):
        print(f"\n  {label.upper()} ({len(d[label])}):")
        for p in d[label][:10]:
            print(f"    {p['issuer_name']:<45} ${p['value_usd']:,}")
    print(f"\n  CHANGED ≥10% ({len(d['changed'])}):")
    for p in d["changed"][:10]:
        print(f"    {p['issuer_name']:<45} {p['pct']:+.0f}% shares")
    return 0


def cmd_report_concern(args) -> int:
    from . import scoring
    conn = _conn()
    if args.company:
        rows = conn.execute(
            "SELECT company_name, resolution_type, action_date FROM enforcement_actions "
            "WHERE is_duplicate=0 AND company_name LIKE ?", (f"%{args.company}%",)).fetchall()
        s = scoring.concern_index([dict(r) for r in rows])
        print(f"{args.company}: score {s['score']}/100 (raw {s['raw']}, "
              f"{s['n_scored_actions']} scored actions, ×{s['recidivism_multiplier']})")
        for p in s["breakdown"]:
            print(f"  {p['action_date']:<12} {p['resolution_type']:<18} "
                  f"sev {p['severity']} × decay {p['decay']} = {p['contribution']:.2f}")
    else:
        for s in scoring.company_scores(conn, limit=args.limit):
            print(f"  {s['score']:>5}/100  {s['company']:<50} "
                  f"({s['n_scored_actions']} actions)")
    print("\nFormula: severity × 0.5^(age/5y), recidivism ×(1+0.15(n−1)) cap 2.0; "
          "allegations and unverified rows score zero. See METHODOLOGY.md.")
    return 0


def cmd_report_ladder(_args) -> int:
    from . import outreach
    conn = _conn()
    rows = outreach.ladder(conn)
    if not rows:
        print("no outreach tied to findings yet")
        return 0
    for r in rows:
        steps = ", ".join(f"{k}:{v}" for k, v in r["steps"].items())
        print(f"  {r['fingerprint']}: {steps} → next: {r['next'] or 'ladder complete'}")
    return 0


def cmd_signal(args) -> int:
    from datetime import datetime
    conn = _conn()
    if args.action == "record":
        conn.execute("INSERT INTO signals (ts, kind, detail, source_url) VALUES (?,?,?,?)",
                     (datetime.now(UTC).isoformat(timespec="seconds"),
                      args.kind, args.detail, args.url or ""))
        conn.commit()
        print("  recorded")
    else:
        for r in conn.execute("SELECT ts, kind, detail, source_url FROM signals ORDER BY id"):
            print(f"  {r['ts']} [{r['kind']}] {r['detail']} {r['source_url']}")
    return 0


def cmd_dedupe(_args) -> int:
    conn = _conn()
    n = ledger.dedupe_votes(conn)
    total = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    print(f"  marked {n:,} duplicate vote rows of {total:,} "
          f"(kept in ledger as filed; excluded from analytics)")
    ne = ledger.dedupe_enforcement(conn)
    print(f"  marked {ne:,} live enforcement rows superseded by curated records")
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
                     choices=["all", "doj_fcpa", "ofac", "worldbank", "ungc",
                              "fed", "epa_echo", "dockets"])
    enf.set_defaults(func=cmd_ingest_enforcement)
    np = ing.add_parser("nport")
    np.add_argument("--cik", required=True)
    np.add_argument("--institution")
    np.add_argument("--max-filings", type=int, default=1)
    np.set_defaults(func=cmd_ingest_nport)
    npx_p = ing.add_parser("npx")
    npx_p.add_argument("--cik")
    npx_p.add_argument("--institution")
    npx_p.add_argument("--max-filings", type=int, default=None)
    npx_p.add_argument("--max-tables", type=int, default=None,
                       help="stop after N proxyTables per exhibit (smoke tests)")
    npx_p.add_argument("--legacy", action="store_true",
                       help="parse pre-2024 legacy HTML N-PX (historical depth); "
                            "votes tagged legacy_html and quarantined from releases")
    npx_p.set_defaults(func=cmd_ingest_npx)
    com = ing.add_parser("commitments")
    com.add_argument("--wayback", action="store_true",
                     help="also archive historical versions from the Wayback Machine")
    com.add_argument("--wayback-limit", type=int, default=10)
    com.add_argument("--purge-errors", action="store_true",
                     help="remove already-ingested error pages (rotted-URL 404s) "
                          "that masquerade as policy versions")
    com.set_defaults(func=cmd_ingest_commitments)
    t13 = ing.add_parser("13f")
    t13.add_argument("--cik")
    t13.add_argument("--institution")
    t13.add_argument("--max-filings", type=int, default=1)
    t13.set_defaults(func=cmd_ingest_13f)

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
    from .contradictions import THEMES
    ct = rep.add_parser("contradictions")
    ct.add_argument("--theme", choices=sorted(THEMES))
    ct.add_argument("--limit-per-theme", type=int, default=25)
    ct.set_defaults(func=cmd_report_contradictions)

    enr = sub.add_parser("enrich").add_subparsers(dest="how", required=True)
    lei = enr.add_parser("lei", help="resolve voted issuers' ISINs via GLEIF (LEI, legal name, country)")
    lei.add_argument("--limit", type=int, default=None)
    lei.set_defaults(func=cmd_enrich_lei)

    df = sub.add_parser("diff")
    df.add_argument("--record", action="store_true",
                    help="record this ledger frontier as the new baseline run")
    df.set_defaults(func=cmd_diff)

    rep.add_parser("non-response").set_defaults(func=cmd_report_non_response)
    rep.add_parser("awards").set_defaults(func=cmd_report_awards)
    rep.add_parser("own-record").set_defaults(func=cmd_report_own_record)
    hd = rep.add_parser("holdings-diff")
    hd.add_argument("--institution", required=True)
    hd.set_defaults(func=cmd_report_holdings_diff)
    cc = rep.add_parser("concern")
    cc.add_argument("--company")
    cc.add_argument("--limit", type=int, default=20)
    cc.set_defaults(func=cmd_report_concern)
    rep.add_parser("ladder").set_defaults(func=cmd_report_ladder)

    rv = sub.add_parser("review").add_subparsers(dest="action", required=True)
    rv.add_parser("sync").set_defaults(func=cmd_review)
    rl = rv.add_parser("list")
    rl.add_argument("--status", choices=["pending", "approved", "rejected"])
    rl.set_defaults(func=cmd_review)
    for act in ("approve", "reject"):
        ra = rv.add_parser(act)
        ra.add_argument("id", type=int)
        ra.add_argument("--note", required=True,
                        help="why — every decision is documented")
        ra.set_defaults(func=cmd_review)
    rc = rv.add_parser("council", help="run the advisory AI review council over the "
                       "pending queue (tiers candidates; never auto-approves)")
    rc.add_argument("--limit", type=int, default=50)
    rc.set_defaults(func=cmd_review)
    rd = rv.add_parser("dossier", help="assemble the verification dossier for one candidate")
    rd.add_argument("id", type=int)
    rd.set_defaults(func=cmd_review)

    sub.add_parser("doctor", help="self-diagnosis: source freshness, integrity, "
                   "queues; emits a repair task for the source-medic agent"
                   ).set_defaults(func=cmd_doctor)

    dn = sub.add_parser("discover-npx", help="find a manager's N-PX-filing fund-trust "
                        "CIKs (proposals to verify, never auto-attributed)")
    dn.add_argument("name", help="manager name to search, e.g. 'Invesco'")
    dn.add_argument("--limit", type=int, default=12)
    dn.set_defaults(func=cmd_discover_npx)

    imp = sub.add_parser("improve", help="self-improvement loop: score the balanced "
                         "index, rank highest-leverage moves, auto-apply safe hygiene")
    imp.add_argument("--apply-safe", action="store_true",
                     help="run the safe, idempotent hygiene allowlist (dedupe, purge "
                          "error pages, reconcile review) — never touches data decisions")
    imp.set_defaults(func=cmd_improve)

    wb = sub.add_parser("workbench", help="local operator desk: review candidates, "
                        "label leads, manage outreach, record signals")
    wb.add_argument("--port", type=int, default=8010)
    wb.set_defaults(func=cmd_workbench)

    tr = sub.add_parser("triage").add_subparsers(dest="what", required=True)
    for what, hlp in (("leads", "LLM-adjudicate quarantined name-join leads (advisory)"),
                      ("proposals", "LLM theme-classification of AGAINST proposals (cached)")):
        tp = tr.add_parser(what, help=hlp)
        tp.add_argument("--limit", type=int, default=20)
        tp.set_defaults(func=cmd_triage)

    ev = sub.add_parser("eval").add_subparsers(dest="which2", required=True)
    ev.add_parser("matcher", help="gold-set gate for the match adjudicator"
                  ).set_defaults(func=cmd_eval)

    sg = sub.add_parser("signal").add_subparsers(dest="action", required=True)
    sr = sg.add_parser("record")
    sr.add_argument("kind", choices=["pitch_reply", "citation", "subscriber",
                                     "inquiry_response", "other"])
    sr.add_argument("detail")
    sr.add_argument("--url")
    sr.set_defaults(func=cmd_signal)
    sg.add_parser("list").set_defaults(func=cmd_signal)

    sc = sub.add_parser("scan-events")
    sc.add_argument("--source", action="append", default=None,
                    choices=["doj_fcpa", "ofac", "worldbank", "ungc"])
    sc.add_argument("--news", action="store_true",
                    help="also run the GDELT news-trigger pass (never citable)")
    sc.set_defaults(func=cmd_scan_events)

    sub.add_parser("site").set_defaults(func=cmd_site)
    sub.add_parser("digest", help="render the weekly digest body to the outbox "
                   "(a human sends it)").set_defaults(func=cmd_digest)
    sub.add_parser("export", help="VACUUM a dated public snapshot of the ledger "
                   "for Datasette/mirrors").set_defaults(func=cmd_export)
    rel = sub.add_parser("release", help="build a versioned, checksummed, "
                         "self-describing release bundle (CSV/Parquet + manifest "
                         "+ datapackage) — the citable artifact for the world")
    rel.add_argument("--version", default=None,
                     help="release version label (default: today's date)")
    rel.add_argument("--no-parquet", action="store_true",
                     help="emit CSV only (skip Parquet even if pyarrow is installed)")
    rel.add_argument("--with-sqlite", action="store_true",
                     help="also bundle a SQLite browse view (≈doubles size; "
                          "CSV/Parquet are the canonical formats)")
    rel.set_defaults(func=cmd_release)

    inv = sub.add_parser("investigate", help="connect SAY↔DO: find managers that "
                         "commit to a theme but vote against it (the finding engine)")
    inv_sub = inv.add_subparsers(dest="action", required=True)
    it = inv_sub.add_parser("theme", help="one theme: leaderboard of committed managers by against-rate + drill")
    it.add_argument("theme", help="a built-in theme (climate | anti-corruption | human-rights | "
                    "lobbying-disclosure | board-diversity) OR any label when using --keywords")
    it.add_argument("--keywords", help="comma-separated keywords to test your OWN hypothesis "
                    "(e.g. 'weapon,firearm,defense'); matches commitment + proposal text")
    it.add_argument("--export", help="write a cited Markdown evidence pack to this file")
    it.add_argument("--examples", type=int, default=8)
    it.set_defaults(func=cmd_investigate)
    im = inv_sub.add_parser("matrix", help="themes × managers against-rate grid (the hypocrisy matrix)")
    im.add_argument("--cache", action="store_true",
                    help="persist the matrix to data/investigate/matrix.json for the workbench")
    im.set_defaults(func=cmd_investigate)
    ii = inv_sub.add_parser("institution", help="one manager's say-vs-do across all themes")
    ii.add_argument("id")
    ii.set_defaults(func=cmd_investigate)
    ic = inv_sub.add_parser("company", help="who holds a company (13-F) and how they voted there")
    ic.add_argument("name", help="company name or fragment, e.g. 'Exxon'")
    ic.set_defaults(func=cmd_investigate)
    itr = inv_sub.add_parser("trend", help="against-rate by meeting year (did a manager shift over time?)")
    itr.add_argument("theme", help="a built-in theme, or any label with --keywords")
    itr.add_argument("--keywords", help="comma-separated keywords for a custom hypothesis")
    itr.set_defaults(func=cmd_investigate)
    ih = inv_sub.add_parser("holdings", help="does a manager vote against a theme more at its "
                            "biggest positions? (skin-in-the-game test)")
    ih.add_argument("theme", help="a built-in theme, or any label with --keywords")
    ih.add_argument("--keywords", help="comma-separated keywords for a custom hypothesis")
    ih.add_argument("--min-held", type=int, default=8, help="min held theme votes per manager")
    ih.set_defaults(func=cmd_investigate)
    inv_sub.add_parser("refresh", help="rebuild the matrix cache + agent drafts so the "
                       "workbench reflects the current ledger (run after ingests)"
                       ).set_defaults(func=cmd_investigate)

    ag = sub.add_parser("agent", help="the findings agent: investigates and drafts cited "
                        "story leads for human review (never publishes/sends)")
    ag_sub = ag.add_subparsers(dest="action", required=True)
    agr = ag_sub.add_parser("run", help="scan, rank, and draft the strongest say-vs-do leads")
    agr.add_argument("--min-rate", type=float, default=0.6, help="min against-rate (default 0.6)")
    agr.add_argument("--min-votes", type=int, default=10, help="min theme votes for confidence (default 10)")
    agr.add_argument("--top", type=int, default=12, help="how many drafts to write (default 12)")
    agr.add_argument("--llm", action="store_true", help="advisory LLM prose-polish of "
                     "headline/standfirst (needs ANTHROPIC_API_KEY; cited evidence stays "
                     "deterministic; falls back if unconfigured)")
    agr.set_defaults(func=cmd_agent)

    pr = sub.add_parser("promise", help="the systemic finding: does a published "
                        "commitment predict how a manager votes? (paired test)")
    pr.add_argument("--min-votes", type=int, default=20,
                    help="min votes on BOTH sides for a manager to be compared")
    pr.set_defaults(func=cmd_promise)

    fm = sub.add_parser("ftm", help="export the unique record as FollowTheMoney entities "
                        "(imports into OCCRP Aleph / OpenAleph)")
    fm.add_argument("--out", help="output path (default data/export/glasshouse.ftm.json)")
    fm.set_defaults(func=cmd_ftm)

    cs = sub.add_parser("cases", help="case files: independent footprints converging on one "
                        "manager × theme, ranked by strong corroboration")
    cs_sub = cs.add_subparsers(dest="action", required=True)
    csl = cs_sub.add_parser("list", help="ranked corroborated cases")
    csl.set_defaults(func=cmd_cases)
    css = cs_sub.add_parser("show", help="the full cited case file")
    css.add_argument("institution")
    css.add_argument("theme")
    css.set_defaults(func=cmd_cases)

    dt = sub.add_parser("detectors", help="the detector library: each accountability pattern "
                        "is a tool that emits cited leads (say-vs-do is the first)")
    dt_sub = dt.add_subparsers(dest="action", required=True)
    dtl = dt_sub.add_parser("list", help="the catalogue: every detector, its technique, and how it's validated")
    dtl.set_defaults(func=cmd_detectors)
    dtr = dt_sub.add_parser("run", help="run one detector (or all) and print cited leads")
    dtr.add_argument("detector", nargs="?", help="detector id (omit for all); see 'detectors list'")
    dtr.add_argument("--min-rate", type=float, default=0.6)
    dtr.add_argument("--min-votes", type=int, default=10)
    dtr.set_defaults(func=cmd_detectors)

    fs = sub.add_parser("firststone", help="First Stone — the AI newsroom on the registrar: "
                        "desks draft, fact-check and edit; only a HUMAN publishes")
    fs_sub = fs.add_subparsers(dest="action", required=True)
    fsr = fs_sub.add_parser("run", help="one edition cycle: assignment → records → ledger "
                            "(recount) → copy → standards → editor")
    fsr.add_argument("--min-rate", type=float, default=0.5)
    fsr.add_argument("--min-votes", type=int, default=10)
    fsr.add_argument("--top", type=int, default=8)
    fsr.add_argument("--llm", action="store_true", help="advisory copy-desk polish (logged; "
                     "falls back if unconfigured)")
    fsr.set_defaults(func=cmd_firststone)
    fsl = fs_sub.add_parser("list", help="stories in the latest run + published")
    fsl.set_defaults(func=cmd_firststone)
    fsp = fs_sub.add_parser("publish", help="the publisher's act (yours): requires a written note")
    fsp.add_argument("slug")
    fsp.add_argument("--note", required=True, help="what you verified in both primary sources")
    fsp.set_defaults(func=cmd_firststone)
    fsk = fs_sub.add_parser("spike", help="kill a story, with the reason on the record")
    fsk.add_argument("slug")
    fsk.add_argument("--note", required=True)
    fsk.set_defaults(func=cmd_firststone)

    out = sub.add_parser("outreach").add_subparsers(dest="action", required=True)
    od = out.add_parser("draft")
    od.add_argument("--kind", default="inquiry",
                    choices=["inquiry", "social_post", "pitch", "fiduciary", "data_offer"])
    od.add_argument("--institution")
    od.add_argument("--theme")
    od.set_defaults(func=cmd_outreach_draft)
    out.add_parser("list").set_defaults(func=cmd_outreach_list)
    oms = out.add_parser("mark-sent")
    oms.add_argument("id", type=int)
    oms.add_argument("--i-sent-this", action="store_true",
                     help="explicit human confirmation that YOU sent it")
    oms.set_defaults(func=cmd_outreach_mark_sent)
    orr = out.add_parser("record-response")
    orr.add_argument("id", type=int)
    orr.add_argument("summary")
    orr.set_defaults(func=cmd_outreach_record_response)

    sub.add_parser("integrity").set_defaults(func=cmd_integrity)
    sub.add_parser("dedupe", help="mark exact-duplicate vote rows so analytics "
                   "never sum the same shares twice").set_defaults(func=cmd_dedupe)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
