"""Phase 4 — the public evidence site, built straight from the ledger.

Not a database dump: a guided reading experience. Every page answers three
reader questions in order — what is this, what did we find, how do I verify
it myself. Visual synthesis (vote-behavior bars, enforcement landscape,
policy timelines) is generated as dependency-free HTML/CSS from ledger
queries; claim cards show SAY and DID side by side with the full citation
chain. Static output, GitHub-Pages-ready, no build toolchain.
"""

from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .http import DATA_DIR

SITE_DIR = DATA_DIR / "_site"

# ── design system ────────────────────────────────────────────────────────────

_CSS = """
:root{
  --bg:#faf9f7; --panel:#ffffff; --ink:#1c1b19; --muted:#6b675f;
  --line:#e6e2da; --accent:#0e6e6e; --accent-ink:#0a5252;
  --warn-bg:#fdf3d7; --warn-ink:#7a5a00; --warn-line:#ecd9a0;
  --for:#2e7d54; --against:#b4452f; --abstain:#b08c2e; --other:#8a8a8a;
  --serif:Georgia,'Times New Roman',serif;
  --sans:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#171614; --panel:#201f1c; --ink:#ece9e2; --muted:#a39d92;
  --line:#36332d; --accent:#5fc4c4; --accent-ink:#8fd8d8;
  --warn-bg:#332a10; --warn-ink:#e8c96a; --warn-line:#5a4a1a;
}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.55 var(--sans)}
a{color:var(--accent-ink);text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:68rem;margin:0 auto;padding:0 1.25rem}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
  z-index:9;backdrop-filter:blur(6px)}
nav .wrap{display:flex;gap:1.4rem;align-items:baseline;padding:.7rem 1.25rem;flex-wrap:wrap}
.wordmark{font:700 1.05rem var(--serif);letter-spacing:.14em;color:var(--ink)}
nav a{color:var(--muted);font-size:.92rem} nav a.on{color:var(--ink);font-weight:600}
h1{font:700 2.1rem/1.15 var(--serif);margin:1.6rem 0 .4rem}
h2{font:700 1.35rem/1.2 var(--serif);margin:2.4rem 0 .8rem}
h3{font:600 1.05rem var(--sans);margin:1.2rem 0 .5rem}
.lede{font-size:1.12rem;color:var(--muted);max-width:46rem}
.statband{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));
  gap:.8rem;margin:1.6rem 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.9rem 1rem}
.stat b{display:block;font:700 1.7rem var(--serif)}
.stat span{color:var(--muted);font-size:.85rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:1.1rem 1.25rem;margin:.9rem 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.saydid{border-left:4px solid var(--accent);padding-left:.9rem}
.saydid.did{border-color:var(--against)}
.saydid .tag{font:700 .72rem var(--sans);letter-spacing:.12em;color:var(--muted)}
blockquote{margin:.4rem 0;font:italic 1.05rem/1.5 var(--serif)}
.cite{font-size:.8rem;color:var(--muted);word-break:break-word}
.ribbon{display:inline-block;background:var(--warn-bg);color:var(--warn-ink);
  border:1px solid var(--warn-line);border-radius:6px;padding:.15rem .55rem;
  font-size:.78rem;font-weight:600;margin-bottom:.5rem}
.bar{display:flex;height:1.05rem;border-radius:6px;overflow:hidden;margin:.35rem 0 .2rem}
.bar i{display:block;height:100%}
.legend{display:flex;gap:1rem;flex-wrap:wrap;font-size:.8rem;color:var(--muted)}
.legend i{display:inline-block;width:.7rem;height:.7rem;border-radius:3px;
  margin-right:.3rem;vertical-align:-1px}
.hrow{display:grid;grid-template-columns:11rem 1fr 4.5rem;gap:.6rem;align-items:center;
  font-size:.88rem;margin:.3rem 0}
.hrow .track{background:var(--line);border-radius:5px;height:.8rem}
.hrow .fill{background:var(--accent);height:100%;border-radius:5px}
.hrow b{text-align:right;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:.92rem}
td,th{border-bottom:1px solid var(--line);padding:.5rem .4rem;text-align:left;vertical-align:top}
th{font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.meta{color:var(--muted);font-size:.85rem}
input.filter{width:100%;padding:.55rem .8rem;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink);font:inherit;margin:.6rem 0}
.timeline{border-left:2px solid var(--line);margin:.6rem 0 .6rem .4rem;padding-left:1.1rem}
.tl{position:relative;margin:.7rem 0}
.tl::before{content:'';position:absolute;left:-1.45rem;top:.35rem;width:.6rem;height:.6rem;
  border-radius:50%;background:var(--accent)}
.tl b{font-variant-numeric:tabular-nums}
footer{margin:3.5rem 0 2rem;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);
  padding-top:1.2rem}
.steps{counter-reset:s;display:grid;gap:.8rem;margin:1rem 0;padding:0;list-style:none}
.steps li{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:.9rem 1rem .9rem 3.2rem;position:relative}
.steps li::before{counter-increment:s;content:counter(s);position:absolute;left:1rem;top:.85rem;
  width:1.5rem;height:1.5rem;border-radius:50%;background:var(--accent);color:#fff;
  font-weight:700;font-size:.85rem;display:flex;align-items:center;justify-content:center}
"""

_FILTER_JS = """<script>
function ghFilter(inp){const q=inp.value.toLowerCase();
  document.querySelectorAll(inp.dataset.target+' tbody tr, '+inp.dataset.target+' .card')
  .forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'})}
</script>"""

_VOTE_COLORS = {"FOR": "var(--for)", "AGAINST": "var(--against)",
                "ABSTAIN": "var(--abstain)"}


def _e(s) -> str:
    return html.escape(str(s or ""))


def _page(title: str, body: str, active: str = "") -> str:
    links = [("index.html", "Overview", "home"), ("institutions.html", "Institutions", "inst"),
             ("candidates.html", "Candidates", "cand"), ("how-to-read.html", "How to read", "how"),
             ("feed.xml", "Feed", "feed")]
    nav = "".join(f"<a href='{h}'{' class=on' if k == active else ''}>{t}</a>"
                  for h, t, k in links)
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)} — Glasshouse</title><style>{_CSS}</style></head><body>"
            f"<nav><div class=wrap><span class=wordmark>GLASSHOUSE</span>{nav}</div></nav>"
            f"<div class=wrap>{body}"
            f"<footer>Every claim traces to a primary source with a reference number and "
            f"retrieval date. Resolution types are legally distinct — a DPA or NPA is not a "
            f"conviction; a docket is an allegation. Items marked <b>quarantined</b> are "
            f"unverified leads, never findings. <a href='how-to-read.html'>How to read "
            f"Glasshouse</a>.</footer></div>{_FILTER_JS}</body></html>")


# ── visual components ────────────────────────────────────────────────────────

def _stacked_bar(parts: list[tuple[str, int]]) -> str:
    total = sum(v for _, v in parts) or 1
    segs = "".join(
        f"<i style='width:{100*v/total:.2f}%;background:{_VOTE_COLORS.get(k, 'var(--other)')}'"
        f" title='{_e(k)}: {v:,}'></i>" for k, v in parts if v)
    leg = "".join(
        f"<span><i style='background:{_VOTE_COLORS.get(k, 'var(--other)')}'></i>"
        f"{_e(k or 'OTHER')} {v:,} ({100*v/total:.0f}%)</span>" for k, v in parts if v)
    return f"<div class=bar>{segs}</div><div class=legend>{leg}</div>"


def _hbars(items: list[tuple[str, int]]) -> str:
    mx = max((v for _, v in items), default=1) or 1
    return "".join(
        f"<div class=hrow><span>{_e(k)}</span><span class=track>"
        f"<span class=fill style='width:{100*v/mx:.1f}%'></span></span><b>{v:,}</b></div>"
        for k, v in items)


def _stat(value: str, label: str) -> str:
    return f"<div class=stat><b>{value}</b><span>{_e(label)}</span></div>"


def _candidate_card(c) -> str:
    return f"""<div class=card>
  <span class=ribbon>QUARANTINED CANDIDATE — human review required</span>
  <h3>{_e(c.institution_id)} · {_e(c.theme)} · {_e(c.issuer_name)}</h3>
  <div class=grid2>
    <div class=saydid><div class=tag>WHAT IT SAYS</div>
      <blockquote>“{_e(c.commitment_quote)}”</blockquote>
      <div class=cite>{_e(c.doc_label)}, version {_e(c.doc_version)}, sha256
      {_e(c.doc_sha256[:16])}… · <a href='{_e(c.doc_url)}'>source document</a></div></div>
    <div class='saydid did'><div class=tag>WHAT IT DID</div>
      <blockquote>Voted <b>{_e(c.how_voted)}</b> with {int(c.shares_voted):,} shares
      (management recommendation: {_e(c.management_recommendation or '—')})</blockquote>
      <div class=cite>“{_e(c.vote_description)}” — {_e(c.issuer_name)},
      meeting {_e(c.meeting_date)} · SEC Form N-PX {_e(c.accession)}</div></div>
  </div></div>"""


# ── data synthesis queries ───────────────────────────────────────────────────

def _vote_split(conn, inst_id: str | None = None) -> list[tuple[str, int]]:
    where, args = "", ()
    if inst_id:
        where, args = "AND f.institution_id = ?", (inst_id,)
    rows = conn.execute(
        f"""SELECT v.how_voted, COUNT(*) FROM votes v
            JOIN filings f ON f.accession = v.accession
            WHERE v.how_voted != '' {where}
            GROUP BY v.how_voted ORDER BY 2 DESC""", args).fetchall()
    main = [(k, n) for k, n in rows if k in _VOTE_COLORS]
    other = sum(n for k, n in rows if k not in _VOTE_COLORS)
    return main + ([("OTHER", other)] if other else [])


def _theme_stances(conn, inst_id: str) -> list[dict]:
    """One pass over the institution's votes: per theme, how often its funds
    voted FOR vs AGAINST proposals mentioning that theme."""
    from .contradictions import THEMES
    kw = {"climate": "climate", "human-rights": "human rights",
          "lobbying-disclosure": "lobbying", "board-diversity": "diversity",
          "anti-corruption": "corruption"}
    cases = ", ".join(
        f"SUM(CASE WHEN instr(lower(v.vote_description), '{kw[t]}') > 0 "
        f"AND v.how_voted='FOR' THEN 1 ELSE 0 END) AS \"{t}_for\", "
        f"SUM(CASE WHEN instr(lower(v.vote_description), '{kw[t]}') > 0 "
        f"AND v.how_voted='AGAINST' THEN 1 ELSE 0 END) AS \"{t}_against\""
        for t in THEMES if t in kw)
    row = conn.execute(
        f"SELECT {cases} FROM votes v JOIN filings f ON f.accession=v.accession "
        f"WHERE f.institution_id = ?", (inst_id,)).fetchone()
    out = []
    for t in kw:
        f_, a_ = row[f"{t}_for"], row[f"{t}_against"]
        if f_ or a_:
            out.append({"theme": t, "for": f_, "against": a_})
    return sorted(out, key=lambda d: -(d["for"] + d["against"]))


# ── pages ────────────────────────────────────────────────────────────────────

def build(conn: sqlite3.Connection, out_dir: Path = SITE_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    from .contradictions import find_commitment_vote_contradictions
    cands = find_commitment_vote_contradictions(conn, limit_per_theme=10)

    stats = {r[0]: r[1] for r in conn.execute(
        "SELECT 'votes', COUNT(*) FROM votes UNION ALL "
        "SELECT 'enforcement', COUNT(*) FROM enforcement_actions UNION ALL "
        "SELECT 'holdings', COUNT(*) FROM holdings UNION ALL "
        "SELECT 'commitments', COUNT(*) FROM commitments UNION ALL "
        "SELECT 'issuers', COUNT(DISTINCT issuer_name) FROM votes")}

    insts = conn.execute(
        """SELECT i.id, i.display_name, i.type, i.country,
                  (SELECT COUNT(*) FROM votes v JOIN filings f ON f.accession=v.accession
                   WHERE f.institution_id=i.id) AS n_votes,
                  (SELECT COUNT(*) FROM commitments c WHERE c.institution_id=i.id) AS n_docs,
                  (SELECT COUNT(*) FROM holdings h JOIN filings f ON f.accession=h.accession
                   WHERE f.institution_id=i.id) AS n_holdings
           FROM institutions i ORDER BY n_votes DESC, i.display_name""").fetchall()

    _build_index(conn, out_dir, stats, insts, cands)
    _build_institutions_index(out_dir, insts)
    n_inst_pages = sum(_build_institution(conn, out_dir, r, cands) for r in insts)
    _build_candidates(out_dir, cands)
    _build_how_to_read(out_dir)
    _write_feed(conn, out_dir)
    return {"pages": 4 + n_inst_pages, "candidates": len(cands)}


def _build_index(conn, out_dir, stats, insts, cands) -> None:
    enf = conn.execute(
        "SELECT agency, COUNT(*) FROM enforcement_actions GROUP BY agency "
        "ORDER BY 2 DESC LIMIT 8").fetchall()
    split = _vote_split(conn)
    featured = max(cands, key=lambda c: c.shares_voted) if cands else None

    body = f"""
<h1>The gap between what institutions say and what they do</h1>
<p class=lede>Glasshouse joins the published commitments of major financial
institutions with their actual proxy votes, holdings, and the documented
enforcement records of the companies they fund. Every clause of every claim
traces to a public primary source. <a href='how-to-read.html'>Start here if
you're new</a>.</p>
<div class=statband>
{_stat(f"{stats.get('votes',0):,}", 'proxy votes on record (SEC N-PX)')}
{_stat(f"{stats.get('issuers',0):,}", 'companies voted on')}
{_stat(f"{stats.get('holdings',0):,}", '13-F holdings')}
{_stat(f"{stats.get('enforcement',0):,}", 'enforcement actions indexed')}
{_stat(f"{stats.get('commitments',0):,}", 'archived policy versions')}
</div>"""

    if featured:
        body += f"<h2>Latest contradiction candidate</h2>{_candidate_card(featured)}" \
                f"<p class=meta><a href='candidates.html'>All candidates →</a></p>"

    body += f"""
<h2>How the tracked institutions vote</h2>
<div class=card>{_stacked_bar(split)}
<p class=meta>Every vote is an active choice — the “passive index” defense
does not apply to voting. Distribution across all ingested N-PX records.</p></div>

<h2>The enforcement universe</h2>
<div class=card>{_hbars([(a, n) for a, n in enf])}
<p class=meta>Actions indexed per agency. Resolution types are preserved and
legally distinct — see <a href='how-to-read.html'>how to read Glasshouse</a>.
Query everything yourself via the Datasette interface or the raw SQLite ledger.</p></div>

<h2>Institutions</h2>
{_inst_cards(insts[:6])}
<p class=meta><a href='institutions.html'>All {len(insts)} institutions →</a></p>"""
    (out_dir / "index.html").write_text(_page("Glasshouse", body, "home"))


def _inst_cards(insts) -> str:
    cards = ""
    for r in insts:
        cards += f"""<div class=card><h3><a href='institution-{_e(r['id'])}.html'>
{_e(r['display_name'])}</a></h3>
<div class=meta>{_e(r['type'] or '')} · {_e(r['country'] or '')}</div>
<div class=statband style='margin:.6rem 0 0'>
{_stat(f"{r['n_votes']:,}", 'votes')}{_stat(f"{r['n_holdings']:,}", 'holdings')}
{_stat(str(r['n_docs']), 'policy versions')}</div></div>"""
    return cards


def _build_institutions_index(out_dir, insts) -> None:
    body = (f"<h1>Institutions</h1><p class=lede>One entry in the registry adds any "
            f"SEC 13-F filer. Counts reflect what has been ingested so far — an empty "
            f"row means not-yet-ingested, not innocence.</p>{_inst_cards(insts)}")
    (out_dir / "institutions.html").write_text(_page("Institutions", body, "inst"))


def _build_institution(conn, out_dir, r, cands) -> int:
    inst_id = r["id"]
    body = f"""<h1>{_e(r['display_name'])}</h1>
<p class=meta>{_e(r['type'] or '')} · {_e(r['country'] or '')}</p>
<div class=statband>
{_stat(f"{r['n_votes']:,}", 'proxy votes on record')}
{_stat(f"{r['n_holdings']:,}", '13-F holdings')}
{_stat(str(r['n_docs']), 'archived policy versions')}</div>"""

    if r["n_votes"]:
        body += f"<h2>Voting behavior</h2><div class=card>{_stacked_bar(_vote_split(conn, inst_id))}</div>"
        stances = _theme_stances(conn, inst_id)
        if stances:
            rows = "".join(
                f"<tr><td>{_e(s['theme'])}</td><td>{s['for']:,}</td><td>{s['against']:,}</td>"
                f"<td><div class=bar style='max-width:14rem'>"
                f"<i style='width:{100*s['for']/(s['for']+s['against']):.0f}%;background:var(--for)'></i>"
                f"<i style='width:{100*s['against']/(s['for']+s['against']):.0f}%;background:var(--against)'></i>"
                f"</div></td></tr>" for s in stances)
            body += (f"<h2>Votes on proposals mentioning…</h2><div class=card><table>"
                     f"<tr><th>Theme</th><th>For</th><th>Against</th><th>Split</th></tr>{rows}</table>"
                     f"<p class=meta>Keyword match on proposal text — context varies; verify any "
                     f"individual vote before citing it.</p></div>")

    docs = conn.execute(
        """SELECT doc_label, sha256, content_path,
                  COALESCE(NULLIF(wayback_timestamp,''), retrieval_date) AS version
           FROM commitments WHERE institution_id=? GROUP BY sha256 ORDER BY version""",
        (inst_id,)).fetchall()
    if docs:
        items = ""
        for d in docs:
            v = d["version"]
            pretty = f"{v[:4]}-{v[4:6]}-{v[6:8]}" if re.fullmatch(r"\d{14}", v) else v
            items += (f"<div class=tl><b>{_e(pretty)}</b> — {_e(d['doc_label'])} "
                      f"<span class=meta>sha {_e(d['sha256'][:10])}</span></div>")
        body += (f"<h2>Policy paper trail</h2><div class=card><div class=timeline>{items}</div>"
                 f"<p class=meta>Each dot is a distinct archived version of the institution's own "
                 f"document (live fetch or Wayback Machine). Differences between versions are "
                 f"silent edits — findings in themselves.</p></div>")

    mine = [c for c in cands if c.institution_id == inst_id]
    if mine:
        body += f"<h2>Contradiction candidates</h2>" + "".join(_candidate_card(c) for c in mine[:5])

    if r["n_votes"]:
        div = conn.execute(
            """SELECT v.issuer_name, v.meeting_date, v.vote_description,
                      COUNT(DISTINCT v.how_voted) AS ways, COUNT(*) AS n
               FROM votes v JOIN filings f ON f.accession=v.accession
               WHERE f.institution_id=? AND v.how_voted != ''
               GROUP BY v.cusip, v.meeting_date, v.vote_description HAVING ways > 1
               ORDER BY n DESC LIMIT 40""", (inst_id,)).fetchall()
        if div:
            rows = "".join(
                f"<tr><td>{_e(d['issuer_name'])}</td><td>{_e(d['meeting_date'])}</td>"
                f"<td>{_e((d['vote_description'] or '')[:170])}</td><td>{d['ways']}</td></tr>"
                for d in div)
            body += (f"<h2>Split votes — its own funds disagreeing</h2>"
                     f"<p class=meta>The same manager voting multiple ways on the identical "
                     f"proposal. Finding-grade: the contradiction is internal to one filer's "
                     f"own N-PX report.</p>"
                     f"<input class=filter placeholder='Filter by company or proposal…' "
                     f"data-target='#split' oninput='ghFilter(this)'>"
                     f"<table id=split><thead><tr><th>Issuer</th><th>Meeting</th><th>Proposal</th>"
                     f"<th>Ways</th></tr></thead><tbody>{rows}</tbody></table>")

    (out_dir / f"institution-{inst_id}.html").write_text(_page(r["display_name"], body, "inst"))
    return 1


def _build_candidates(out_dir, cands) -> None:
    cards = "".join(_candidate_card(c) for c in cands) or \
        "<p class=meta>No candidates yet — ingest commitments and votes for the same institution.</p>"
    body = f"""<h1>Contradiction candidates</h1>
<p class=lede>Each card pairs an institution's own archived policy language with a
vote its funds actually cast on a proposal touching the same theme. The match is
lexical: <b>every card is a quarantined lead</b> until a human reads the policy and
the proposal together and confirms they speak to each other.</p>
<input class=filter placeholder='Filter by institution, company, or theme…'
 data-target='#cands' oninput='ghFilter(this)'><div id=cands>{cards}</div>"""
    (out_dir / "candidates.html").write_text(_page("Contradiction candidates", body, "cand"))


def _build_how_to_read(out_dir) -> None:
    body = """<h1>How to read Glasshouse</h1>
<p class=lede>Glasshouse exists to make one gap visible: the distance between what
financial institutions publicly commit to and what they actually do. Here is how to
use it without being misled — by us or by anyone.</p>

<h2>The anatomy of a claim</h2>
<ol class=steps>
<li><b>SAY</b> — a verbatim sentence from the institution's own published policy,
pinned to a dated, content-hashed archived version. We never paraphrase commitments.</li>
<li><b>DO</b> — an act from a regulatory filing: a proxy vote (SEC Form N-PX, with
accession number), a holding (SEC Form 13-F), or a documented silence.</li>
<li><b>The join</b> — what connects them: the same institution, the same theme, the
same company. The strength of every claim lives or dies on this join.</li>
</ol>

<h2>Leads vs. findings</h2>
<div class=card><p>Anything marked <span class=ribbon>QUARANTINED</span> is a
<b>lead</b>: a machine-generated candidate awaiting human verification. We publish
the distinction because the failure mode is real — on our first live run, a sanctions
entry for “Aldar Properties” (a Sudan-based entity) matched the name of Aldar
Properties PJSC, an unrelated Abu Dhabi-listed developer. Same normalized name,
different company. <b>Name matches are never findings.</b> A lead is promoted only
when corroborated by an identifier (CUSIP, LEI, CIK) or human review of the primary
source.</p></div>

<h2>Resolution types are not interchangeable</h2>
<table>
<tr><th>Resolution</th><th>Criminal conviction?</th><th>Admission of guilt?</th></tr>
<tr><td><b>Guilty plea</b></td><td>Yes</td><td>Yes</td></tr>
<tr><td><b>DPA</b> (deferred prosecution)</td><td>No — dismissed if compliant</td><td>No</td></tr>
<tr><td><b>NPA</b> (non-prosecution)</td><td>No — no charges filed</td><td>No</td></tr>
<tr><td><b>Civil settlement</b></td><td>No (civil only)</td><td>Typically no</td></tr>
<tr><td><b>Debarment / sanction / expulsion</b></td><td>No (administrative)</td><td>N/A</td></tr>
<tr><td><b>Docket / pending matter</b></td><td><b>Allegation only — never a finding</b></td><td>—</td></tr>
</table>
<p class=meta>Every enforcement record in the ledger carries its resolution type, the
agency's own reference number, the source URL, and the retrieval date.</p>

<h2>Why votes, not just holdings</h2>
<div class=card><p>Holding a stock through an index fund supports a credible “we just
track the index” defense. <b>Voting does not.</b> Every proxy vote is an active choice
by the institution's stewardship team — which is why N-PX voting records are the spine
of this project, and holdings-only claims are explicitly labeled as the weakest class.</p></div>

<h2>Verify everything yourself</h2>
<ol class=steps>
<li>Every vote cites its SEC accession number — open the filing directly on EDGAR.</li>
<li>Every policy quote links the source document and its content hash — fetch and hash it.</li>
<li>The full SQLite ledger ships with the project; run any SQL you like via Datasette.</li>
</ol>
<p>If you find an error, we want it: discarding almost-right findings is the discipline
this project is built on.</p>"""
    (out_dir / "how-to-read.html").write_text(_page("How to read", body, "how"))


def _write_feed(conn, out_dir) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entries = []
    for r in conn.execute(
            "SELECT agency, company_name, resolution_type, primary_ref, retrieval_date "
            "FROM enforcement_actions WHERE source_kind='live' ORDER BY id DESC LIMIT 25"):
        title = f"{r['agency']}: {r['company_name']} ({r['resolution_type']})"
        entries.append(
            f"<entry><title>{_e(title)}</title><id>urn:glasshouse:enf:{_e(r['primary_ref'])}"
            f"</id><updated>{_e(r['retrieval_date'])}T00:00:00Z</updated>"
            f"<content type='text'>{_e(r['primary_ref'])}</content></entry>")
    feed = (f"<?xml version='1.0' encoding='utf-8'?>"
            f"<feed xmlns='http://www.w3.org/2005/Atom'>"
            f"<title>Glasshouse — ledger updates</title><id>urn:glasshouse:feed</id>"
            f"<updated>{now}</updated>{''.join(entries)}</feed>")
    (out_dir / "feed.xml").write_text(feed)
