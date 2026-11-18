"""Phase 4 — the public evidence site: an editorial, visual reading
experience generated straight from the ledger.

Design principle: one visual idiom per story, never a generic table.
  - scale            → waffle grid (100 squares = all votes)
  - theme opposition → butterfly chart (AGAINST pulls left, FOR pulls right)
  - one claim        → editorial SAY|DID card + donut gauge of shares
  - policy history   → SVG timeline with a year axis (drift made visible)
  - enforcement mix  → mosaic tiles (a landscape, not a ranking)
  - internal splits  → tug-of-war bars from a center spine

Static output, no build toolchain, no external assets; dark-mode aware;
tiny inline vanilla JS for scroll-reveal, count-up and filtering only.
"""

from __future__ import annotations

import html
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from . import timeline
from .http import DATA_DIR

SITE_DIR = DATA_DIR / "_site"

# ── design tokens: "Through glass, stamped" ─────────────────────────────────
# Direction (see commit message): cool glass-white paper, registrar-blue
# stamp ink, condensed-caps display over a reading serif, monospace for
# every machine-verifiable identifier, and the rubber stamp as the one
# signature element. Deliberately NOT the cream/serif/terracotta default.

_CSS = """
:root{
  --bg:#eff3f2; --panel:#fdfefe; --ink:#0d1f26; --muted:#5b6e74;
  --line:#d7e0df; --edge:#c3d2d0; --accent:#2547d0; --accent-soft:#e7ecfb;
  --for:#1e7a5a; --against:#bc3f2e; --abstain:#9a6a00; --other:#8295a0;
  --hold:#9a6a00; --hold-bg:#f6ecd4;
  --shadow:0 1px 0 rgba(13,31,38,.04),0 10px 32px -14px rgba(13,31,38,.22);
  --display:'Avenir Next Condensed','HelveticaNeue-CondensedBold','Arial Narrow',
    'Roboto Condensed',ui-sans-serif,sans-serif;
  --serif:'Iowan Old Style',Palatino,'Palatino Linotype',Georgia,serif;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0d181c; --panel:#13242a; --ink:#e6efed; --muted:#92a8ab;
  --line:#23393e; --edge:#2d474d; --accent:#8aa6ff; --accent-soft:#1b2a4d;
  --for:#46ab84; --against:#e06a52; --abstain:#d9b04a;
  --hold:#e3b855; --hold-bg:#33290f;
  --shadow:0 1px 0 rgba(0,0,0,.35),0 12px 34px -14px rgba(0,0,0,.6);
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.62 var(--serif)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
.wrap{max-width:72rem;margin:0 auto;padding:0 1.4rem}
nav{position:sticky;top:0;background:color-mix(in srgb,var(--bg) 86%,transparent);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--edge);z-index:9}
nav .wrap{display:flex;gap:1.5rem;align-items:baseline;padding:.8rem 1.4rem;flex-wrap:wrap}
.wordmark{font:600 1.05rem/1 var(--display);letter-spacing:.34em;color:var(--ink);
  text-transform:uppercase}
.wordmark em{font-style:normal;color:var(--accent);border-left:2px solid var(--accent);
  padding-left:.34em;margin-left:.12em}
nav a{color:var(--muted);font:500 .82rem var(--mono);letter-spacing:.04em}
nav a.on{color:var(--accent);font-weight:700}

h1{font:600 clamp(2.6rem,7vw,4.6rem)/.98 var(--display);text-transform:uppercase;
  letter-spacing:.015em;margin:2.8rem 0 1.1rem;max-width:54rem}
h2{font:600 clamp(1.5rem,3vw,2rem)/1.05 var(--display);text-transform:uppercase;
  letter-spacing:.03em;margin:3.4rem 0 .4rem}
h3{font:600 1.02rem var(--sans);margin:1rem 0 .4rem}
.kicker{display:flex;align-items:center;gap:.7rem;font:700 .72rem var(--mono);
  letter-spacing:.22em;color:var(--accent);text-transform:uppercase;
  margin:3.4rem 0 -3.1rem}
.kicker::after{content:'';flex:1;height:1px;background:var(--edge)}
.lede{font-size:1.16rem;color:var(--muted);max-width:46rem;line-height:1.65}
.secnote{color:var(--muted);max-width:44rem;margin:.1rem 0 1.2rem;font-size:.95rem}

/* ledger lines, not stat cards: numbers live on rules */
.statband{margin:2.2rem 0;border-top:2px solid var(--ink)}
.stat{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;
  padding:.55rem .1rem;border-bottom:1px solid var(--line)}
.stat b{font:600 clamp(1.3rem,2.6vw,1.9rem)/1 var(--mono);order:2;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.stat span{color:var(--muted);font:400 .9rem var(--serif);order:1}

.card{background:var(--panel);border:1px solid var(--edge);border-radius:10px;
  padding:1.4rem 1.5rem;margin:1rem 0;box-shadow:var(--shadow);position:relative}
.card.flat{box-shadow:none}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem}
.grid3{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:1rem}
@media(max-width:780px){.grid2{grid-template-columns:1fr}
  .stat b{font-size:1.25rem}}

/* exhibit (claim) card: a filed document */
.claim{padding-top:1.1rem}
.claim::before{content:'';position:absolute;inset:0 0 auto 0;height:6px;
  border-radius:10px 10px 0 0;
  background:linear-gradient(90deg,var(--accent) 0 50%,var(--against) 50% 100%)}
/* the stamp — the signature element. Rotated, inked, slightly imperfect. */
.ribbon{display:inline-block;transform:rotate(-3deg);color:var(--hold);
  border:2.5px solid currentColor;border-radius:4px;padding:.22rem .65rem;
  font:700 .72rem var(--mono);letter-spacing:.16em;text-transform:uppercase;
  margin:.2rem 0 .9rem;background:
    radial-gradient(ellipse at 30% 40%,transparent 58%,var(--hold-bg) 59%) ,
    color-mix(in srgb,var(--hold-bg) 55%,transparent);
  box-shadow:inset 0 0 0 1px color-mix(in srgb,currentColor 25%,transparent)}
.ribbon.ok{color:var(--accent)}
.r.in .ribbon{animation:stamp .38s cubic-bezier(.2,1.6,.4,1) backwards}
@keyframes stamp{from{transform:rotate(-9deg) scale(1.7);opacity:0}
  to{transform:rotate(-3deg) scale(1);opacity:1}}
/* the record: say-vs-do matrix */
table.rc{border-collapse:collapse;width:100%;font:400 .9rem var(--sans)}
.rc th,.rc td{border:1px solid var(--line);padding:.45rem .5rem;text-align:center}
.rc thead th{font:700 .66rem var(--mono);letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted)}
.rc tbody th{text-align:left;font:600 .92rem var(--sans)}
.rc td b{font:700 .95rem var(--mono);font-variant-numeric:tabular-nums}
.rc td span{display:block;font:400 .66rem var(--mono);color:var(--muted)}
.rc td.dot{color:var(--muted);font-size:1.1rem}
/* change log: verbatim language differences between archived versions */
ul.chg{margin:.4rem 0 1rem;padding-left:1.1rem}
.chg li{margin:.5rem 0}
.chg q{font:italic 500 1.02rem/1.5 var(--serif);quotes:'“' '”'}
.saydid .tag{font:700 .7rem var(--mono);letter-spacing:.2em;text-transform:uppercase}
.saydid.say .tag{color:var(--accent)} .saydid.did .tag{color:var(--against)}
blockquote{margin:.5rem 0;font:italic 500 1.22rem/1.45 var(--serif)}
.did blockquote{font-style:normal}
.cite{font:400 .76rem/1.6 var(--mono);color:var(--muted);word-break:break-word;
  margin-top:.45rem;padding-top:.5rem;border-top:1px dotted var(--edge)}
.vs{display:flex;align-items:center;justify-content:center}
.vs span{font:700 .78rem var(--mono);letter-spacing:.1em;color:var(--muted);
  border:1px solid var(--edge);border-radius:999px;padding:.3rem .7rem;background:var(--bg)}

/* waffle */
.waffle{display:grid;grid-template-columns:repeat(20,1fr);gap:4px;max-width:34rem}
.waffle i{aspect-ratio:1;border-radius:2px;display:block;transition:transform .15s}
.waffle i:hover{transform:scale(1.35)}
.legend{display:flex;gap:1.2rem;flex-wrap:wrap;font:400 .78rem var(--mono);
  color:var(--muted);margin-top:.9rem}
.legend i{display:inline-block;width:.72rem;height:.72rem;border-radius:2px;
  margin-right:.35rem;vertical-align:-1px}

/* donut */
.donut{display:flex;align-items:center;gap:1.1rem}
.donut svg{flex:0 0 auto}
.dval{font:600 1.4rem var(--mono);fill:var(--ink)}
.dlab{font:600 .6rem var(--mono);fill:var(--muted);letter-spacing:.1em;text-transform:uppercase}

/* butterfly */
.bf{display:grid;grid-template-columns:1fr 9.5rem 1fr;align-items:center;
  gap:.7rem;margin:.65rem 0}
.bfl,.bfr{display:grid;align-items:center;gap:.5rem;min-height:1.5rem}
.bfl{grid-template-columns:auto 1fr}
.bfr{grid-template-columns:1fr auto}
.trk{display:block;width:100%}
.bfl .trk i,.bfr .trk i{display:block;height:1.5rem;border-radius:4px;min-width:2px}
.bfl .trk i{background:var(--against);border-radius:6px 2px 2px 6px;margin-left:auto}
.bfr .trk i{background:var(--for);border-radius:2px 6px 6px 2px}
.bf b{font:500 .8rem var(--mono);font-variant-numeric:tabular-nums;color:var(--muted);
  white-space:nowrap}
.bfc{text-align:center;font:600 .84rem var(--sans)}
.bfhead{display:grid;grid-template-columns:1fr 9.5rem 1fr;font:700 .66rem var(--mono);
  letter-spacing:.14em;color:var(--muted);text-transform:uppercase;margin-bottom:.4rem}
.bfhead :first-child{text-align:right;color:var(--against)}
.bfhead :last-child{color:var(--for)}

/* mosaic */
.mosaic{display:flex;flex-wrap:wrap;gap:5px;border-radius:14px;overflow:hidden}
.mosaic a{display:flex;flex-direction:column;justify-content:end;color:#fff;
  padding:.7rem .8rem;border-radius:8px;min-height:5.2rem;text-decoration:none;
  transition:filter .15s} .mosaic a:hover{filter:brightness(1.12)}
.mosaic b{font:600 1.25rem var(--mono)} .mosaic span{font:400 .72rem var(--mono);opacity:.85}

/* tug of war */
.tug{padding:.9rem 0;border-bottom:1px solid var(--line)}
.tug:last-child{border-bottom:none}
.tugmeta{font-size:.88rem;margin-bottom:.45rem}
.tugmeta b{font:600 1rem var(--sans)}
.tugbar{display:grid;grid-template-columns:1fr 1fr;gap:0;align-items:start}
.tugL{border-right:2px solid var(--ink);text-align:right}
.tugR{text-align:left}
.tugL .trk i{background:var(--against);border-radius:6px 0 0 6px;margin-left:auto}
.tugR .trk i{background:var(--for);border-radius:0 6px 6px 0}
.tugbar .trk i{display:block;height:1.15rem;min-width:2px}
.tugbar b{display:block;font:400 .72rem var(--mono);color:var(--muted);
  font-variant-numeric:tabular-nums;margin-top:.25rem;padding:0 .4rem}

/* timeline */
.tlwrap{overflow-x:auto}
.tl-axis{stroke:var(--line);stroke-width:2}
.tl-node{fill:var(--accent)} .tl-node.live{fill:var(--against)}
.tl-year{font:600 .68rem var(--mono);fill:var(--muted)}
.tl-sha{font:.62rem ui-monospace,monospace;fill:var(--muted)}

table{border-collapse:collapse;width:100%;font-size:.92rem}
td,th{border-bottom:1px solid var(--line);padding:.55rem .4rem;text-align:left;vertical-align:top}
table{font-family:var(--sans)}
th{font:700 .7rem var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.meta{color:var(--muted);font-size:.85rem;font-family:var(--sans)}
input.filter{width:100%;padding:.65rem .95rem;border:1px solid var(--edge);border-radius:8px;
  background:var(--panel);color:var(--ink);font:400 .92rem var(--sans);margin:.7rem 0}

.steps{counter-reset:s;display:grid;gap:.85rem;margin:1.2rem 0;padding:0;list-style:none}
.steps li{background:var(--panel);border:1px solid var(--edge);border-radius:8px;font-family:var(--sans);
  padding:1rem 1.1rem 1rem 3.4rem;position:relative;box-shadow:var(--shadow)}
.steps li::before{counter-increment:s;content:counter(s);position:absolute;left:1rem;top:.95rem;
  width:1.6rem;height:1.6rem;border-radius:3px;background:var(--accent);color:#fff;
  font:700 .8rem var(--mono);display:flex;align-items:center;justify-content:center}

.r{opacity:0;transform:translateY(14px);transition:opacity .6s,transform .6s}
.r.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){.r{opacity:1;transform:none;transition:none}
  .r.in .ribbon{animation:none}}
footer{margin:4rem 0 2.2rem;color:var(--muted);font:400 .84rem/1.6 var(--sans);
  border-top:2px solid var(--ink);padding-top:1.2rem;max-width:50rem}
"""

_JS = """<script>
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.12});
document.querySelectorAll('.r').forEach(el=>io.observe(el));
document.querySelectorAll('[data-count]').forEach(el=>{
  const end=+el.dataset.count, t0=performance.now(), d=900;
  const f=t=>{const p=Math.min(1,(t-t0)/d), v=Math.round(end*(1-Math.pow(1-p,3)));
    el.textContent=v.toLocaleString(); if(p<1)requestAnimationFrame(f)};
  requestAnimationFrame(f)});
function ghFilter(inp){const q=inp.value.toLowerCase();
  document.querySelectorAll(inp.dataset.target+' .fitem')
  .forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'})}
</script>"""

_VOTE_COLORS = {"FOR": "var(--for)", "AGAINST": "var(--against)",
                "ABSTAIN": "var(--abstain)", "OTHER": "var(--other)"}
_MOSAIC_COLORS = ["#0d6b6b", "#bb4430", "#c39a2e", "#46598a", "#2c7a52",
                  "#8a4674", "#9b958a", "#5b7c99"]


def _e(s) -> str:
    return html.escape(str(s or ""))


def _page(title: str, body: str, active: str = "") -> str:
    # First Stone earns its place in the nav only once a HUMAN has published a
    # story. With an empty newsroom, leading the public face with an AI masthead
    # invites "AI accuses BlackRock" as the first impression, which is a worse
    # front door than the registrar and a needless launch risk. The pages are
    # always built and reachable; the nav item appears when there is real,
    # human-approved journalism behind it.
    from .firststone import load_published
    links = [("index.html", "Overview", "home"),
             ("promise.html", "Does a promise predict?", "promise"),
             ("record.html", "The record", "record"),
             ("detectors.html", "What we check", "detect"),
             ("institutions.html", "Institutions", "inst"),
             ("findings.html", "Findings", "find"),
             ("how-to-read.html", "How to read", "how")]
    if load_published():
        links.append(("firststone.html", "First Stone", "fs"))
    links.append(("feed.xml", "Feed", "feed"))
    nav = "".join(f"<a href='{h}'{' class=on' if k == active else ''}>{t}</a>"
                  for h, t, k in links)
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)} — Glasshouse</title><style>{_CSS}</style></head><body>"
            f"<nav><div class=wrap><span class=wordmark>GLASS<em>HOUSE</em></span>{nav}</div></nav>"
            f"<div class=wrap>{body}"
            f"<footer>Every claim traces to a primary source with a reference number and "
            f"retrieval date. Resolution types are legally distinct — a DPA or NPA is not a "
            f"conviction; a docket is an allegation. Items marked <b>quarantined</b> are "
            f"unverified leads, never findings. <a href='how-to-read.html'>How to read "
            f"Glasshouse</a>.</footer></div>{_JS}</body></html>")


# ── visual components ────────────────────────────────────────────────────────

def _stat(value: int | str, label: str) -> str:
    if isinstance(value, int):
        return (f"<div class=stat><b data-count={value}>0</b>"
                f"<span>{_e(label)}</span></div>")
    return f"<div class=stat><b>{_e(value)}</b><span>{_e(label)}</span></div>"


def _waffle(parts: list[tuple[str, int]], cells: int = 200) -> str:
    """Each square ≈ total/cells records. Scale you can feel, not read."""
    total = sum(v for _, v in parts) or 1
    sq, acc = [], 0.0
    for name, v in parts:
        acc += v / total * cells
        while len(sq) < min(cells, round(acc)):
            sq.append(name)
    while len(sq) < cells:
        sq.append(parts[-1][0] if parts else "OTHER")
    cs = "".join(f"<i style='background:{_VOTE_COLORS.get(n, 'var(--other)')}' "
                 f"title='{_e(n)}'></i>" for n in sq)
    leg = "".join(f"<span><i style='background:{_VOTE_COLORS.get(k, 'var(--other)')}'></i>"
                  f"{_e(k)} {v:,} ({100*v/total:.0f}%)</span>" for k, v in parts if v)
    per = f"{total // cells:,}"
    return (f"<div class=waffle>{cs}</div><div class=legend>{leg}</div>"
            f"<p class=meta>One square ≈ {per} votes.</p>")


def _donut(pct: float, label: str, color: str = "var(--against)", sub: str = "") -> str:
    dash = max(0.0, min(100.0, pct)) * 3.0159  # r=48 → C≈301.59
    return f"""<div class=donut><svg width=110 height=110 viewBox='0 0 110 110'>
<circle cx=55 cy=55 r=48 fill=none stroke=var(--line) stroke-width=11/>
<circle cx=55 cy=55 r=48 fill=none stroke={color} stroke-width=11 stroke-linecap=round
 stroke-dasharray='{dash:.1f} 301.6' transform='rotate(-90 55 55)'/>
<text x=55 y=53 text-anchor=middle class=dval>{pct:.0f}%</text>
<text x=55 y=70 text-anchor=middle class=dlab>{_e(label)}</text></svg>
<div class=meta style='max-width:13rem'>{sub}</div></div>"""


def _butterfly(rows: list[dict]) -> str:
    """rows: {label, against, for} — opposition pulls left, support right."""
    mx = max((max(r["against"], r["for"]) for r in rows), default=1) or 1
    body = "".join(
        f"<div class='bf r'><div class=bfl><b>{r['against']:,}</b>"
        f"<span class=trk><i style='width:{96*r['against']/mx:.1f}%'></i></span></div>"
        f"<div class=bfc>{_e(r['label'])}</div>"
        f"<div class=bfr><span class=trk><i style='width:{96*r['for']/mx:.1f}%'></i></span>"
        f"<b>{r['for']:,}</b></div></div>"
        for r in rows)
    return (f"<div class=bfhead><span>voted against ←</span><span></span>"
            f"<span>→ voted for</span></div>{body}")


def _mosaic(items: list[tuple[str, int, str]]) -> str:
    """(label, value, href) tiles sized by share — a landscape, not a ranking."""
    total = sum(v for _, v, _ in items) or 1
    tiles = ""
    for i, (label, v, href) in enumerate(items):
        share = v / total
        grow = max(share * 100, 6)
        tiles += (f"<a href='{_e(href)}' style='flex:{grow:.1f} 1 "
                  f"{max(share*38, 9):.0f}rem;background:{_MOSAIC_COLORS[i % len(_MOSAIC_COLORS)]}'>"
                  f"<b>{v:,}</b><span>{_e(label)}</span></a>")
    return f"<div class=mosaic>{tiles}</div>"


def _tug(rows: list[dict]) -> str:
    """rows: {title, sub, left, right} in shares — disagreement from a spine.

    Bars are scaled per row (share of that proposal's FOR+AGAINST total): the
    visual is the balance of the disagreement, the labels carry the scale.
    """
    out = ""
    for r in rows:
        total = (r["left"] + r["right"]) or 1
        lp, rp = 100 * r["left"] / total, 100 * r["right"] / total
        out += f"""<div class='tug fitem r'>
<div class=tugmeta><b>{_e(r['title'])}</b> <span class=meta>{_e(r['sub'])}</span></div>
<div class=tugbar>
<div class=tugL><span class=trk><i style='width:{0.95*lp:.1f}%'></i></span>
<b>{r['left']:,.0f} sh ({lp:.0f}%) AGAINST</b></div>
<div class=tugR><span class=trk><i style='width:{0.95*rp:.1f}%'></i></span>
<b>{r['right']:,.0f} sh ({rp:.0f}%) FOR</b></div>
</div></div>"""
    return out


def _timeline_svg(versions: list[dict]) -> str:
    """versions: {date 'YYYY-MM-DD', label, sha, live} on a real year axis."""
    if not versions:
        return ""
    def yr(v):
        return int(v["date"][:4]) + (int(v["date"][5:7]) - 1) / 12
    lo = int(min(yr(v) for v in versions))
    hi = int(max(yr(v) for v in versions)) + 1
    W, H, pad = 980, 130, 50
    def x(v):
        return pad + (yr(v) - lo) / max(hi - lo, 1) * (W - 2 * pad)
    years = "".join(
        f"<text class=tl-year x={pad + (y - lo)/max(hi - lo, 1)*(W - 2*pad):.0f} y={H-12} "
        f"text-anchor=middle>{y}</text>"
        f"<line x1={pad + (y - lo)/max(hi - lo, 1)*(W - 2*pad):.0f} y1={H-38} "
        f"x2={pad + (y - lo)/max(hi - lo, 1)*(W - 2*pad):.0f} y2={H-30} class=tl-axis/>"
        for y in range(lo, hi + 1))
    nodes = ""
    for i, v in enumerate(versions):
        cx = x(v)
        cy = H - 34
        ty = 28 + (i % 2) * 16
        nodes += (f"<line x1={cx:.0f} y1={cy} x2={cx:.0f} y2={ty+6} class=tl-axis "
                  f"stroke-dasharray='2 3'/>"
                  f"<circle class='tl-node{' live' if v.get('live') else ''}' "
                  f"cx={cx:.0f} cy={cy} r=6><title>{_e(v['date'])} sha {_e(v['sha'])}</title></circle>"
                  f"<text class=tl-sha x={cx:.0f} y={ty} text-anchor=middle>"
                  f"{_e(v['date'])}</text>")
    return (f"<div class=tlwrap><svg viewBox='0 0 {W} {H}' width='100%' "
            f"preserveAspectRatio='xMidYMid meet'>"
            f"<line x1={pad} y1={H-34} x2={W-pad} y2={H-34} class=tl-axis/>{years}{nodes}"
            f"</svg></div>")


# ── data synthesis ───────────────────────────────────────────────────────────

def _vote_split(conn, inst_id: str | None = None) -> list[tuple[str, int]]:
    where, args = "", ()
    if inst_id:
        where, args = "AND f.institution_id = ?", (inst_id,)
    rows = conn.execute(
        f"""SELECT v.how_voted, COUNT(*) FROM votes v
            JOIN filings f ON f.accession = v.accession
            WHERE v.how_voted != '' AND v.is_duplicate = 0 {where}
            GROUP BY v.how_voted ORDER BY 2 DESC""", args).fetchall()
    main = [(k, n) for k, n in rows if k in _VOTE_COLORS]
    other = sum(n for k, n in rows if k not in _VOTE_COLORS)
    return main + ([("OTHER", other)] if other else [])


def _theme_stances(conn, inst_id: str) -> list[dict]:
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
        f"WHERE f.institution_id = ? AND v.is_duplicate = 0", (inst_id,)).fetchone()
    out = []
    for t in kw:
        f_, a_ = row[f"{t}_for"], row[f"{t}_against"]
        if f_ or a_:
            out.append({"label": t.replace("-", " "), "for": f_, "against": a_})
    return sorted(out, key=lambda d: -(d["for"] + d["against"]))


def _splits(conn, inst_id: str, limit: int = 12) -> list[dict]:
    groups = conn.execute(
        """SELECT v.issuer_name, v.meeting_date, v.vote_description, v.cusip,
                  SUM(CASE WHEN v.how_voted='AGAINST' THEN v.shares_voted ELSE 0 END) AS sh_against,
                  SUM(CASE WHEN v.how_voted='FOR' THEN v.shares_voted ELSE 0 END) AS sh_for
           FROM votes v JOIN filings f ON f.accession=v.accession
           WHERE f.institution_id=? AND v.how_voted IN ('FOR','AGAINST') AND v.is_duplicate = 0
           GROUP BY v.cusip, v.meeting_date, v.vote_description
           HAVING sh_against > 0 AND sh_for > 0 AND sh_against != sh_for
           ORDER BY MIN(sh_against, sh_for) DESC LIMIT ?""",
        (inst_id, limit)).fetchall()
    # sh_against != sh_for: identical share counts on both sides are, in the
    # data we have seen, the same position reported twice as filed — an
    # artifact, not a disagreement. Excluded pending verification.
    return [{"title": g["issuer_name"], "left": g["sh_against"], "right": g["sh_for"],
             "sub": f"{g['meeting_date']} — {(g['vote_description'] or '')[:130]}"}
            for g in groups]


# ── pages ────────────────────────────────────────────────────────────────────

def _approved_findings(conn) -> list[dict]:
    """Human-approved findings only — the publish boundary for the static
    site. Unreviewed candidates are operator-facing (workbench) and must
    never reach a public page; a candidate is an unverified lead, and a
    public page naming an institution on a lead is the false-accusation
    risk the whole project guards against."""
    import json as _json
    out = []
    for r in conn.execute(
            "SELECT payload, reviewer_note, reviewed_date FROM findings "
            "WHERE status='approved' ORDER BY reviewed_date DESC").fetchall():
        out.append({**_json.loads(r["payload"]),
                    "_note": r["reviewer_note"], "_reviewed": r["reviewed_date"]})
    return out


def _finding_card(p: dict, featured: bool = False) -> str:
    extra = ""
    if featured:
        extra = ("<div style='margin-top:1rem'>"
                 + _donut(100.0, "of cited shares", "var(--against)",
                          f"{int(float(p['shares_voted'])):,} shares voted "
                          f"{_e(p['how_voted'])} on this proposal") + "</div>")
    return f"""<div class='card claim fitem r'>
  <span class='ribbon ok'>verified · human reviewed {_e(p.get('_reviewed', ''))}</span>
  <h3 style='margin-top:0'>{_e(p['institution_id'])} · {_e(p['theme'])} · {_e(p['issuer_name'])}</h3>
  <div class=grid2>
    <div class='saydid say'><div class=tag>What it says</div>
      <blockquote>“{_e(p['commitment_quote'])}”</blockquote>
      <div class=cite>{_e(p['doc_label'])} · version {_e(p['doc_version'])} · sha256
      {_e(p['doc_sha256'][:16])}… · <a href='{_e(p['doc_url'])}'>source document</a></div></div>
    <div class='saydid did'><div class=tag>What it did</div>
      <blockquote>Voted <b style='color:var(--against)'>{_e(p['how_voted'])}</b> —
      {int(float(p['shares_voted'])):,} shares</blockquote>
      <div class=cite>“{_e(p['vote_description'])}” — {_e(p['issuer_name'])}, meeting
      {_e(p['meeting_date'])} · SEC Form N-PX {_e(p['accession'])}</div>{extra}</div>
  </div>
  <p class=meta>Reviewer's note: {_e(p.get('_note', ''))}</p></div>"""


def build(conn: sqlite3.Connection, out_dir: Path = SITE_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear previously generated pages so a page we no longer emit (e.g. the
    # retired candidates.html) can never linger and leak. The site dir holds
    # only generated artifacts.
    for stale in (*out_dir.glob("*.html"), *out_dir.glob("*.xml")):
        stale.unlink()
    findings = _approved_findings(conn)

    stats = {r[0]: r[1] for r in conn.execute(
        "SELECT 'votes', COUNT(*) FROM votes WHERE is_duplicate = 0 UNION ALL "
        "SELECT 'enforcement', COUNT(*) FROM enforcement_actions WHERE is_duplicate = 0 "
        "UNION ALL SELECT 'holdings', COUNT(*) FROM holdings UNION ALL "
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

    _build_index(conn, out_dir, stats, insts, findings)
    from .investigate import build_matrix as _bm
    _matrix = _bm(conn)                       # built once, shared by the pages below
    _build_systemic(out_dir, _matrix)
    _build_record(conn, out_dir, _matrix)
    _build_detectors(conn, out_dir, _matrix)
    _build_institutions_index(conn, out_dir, insts)
    n_inst = sum(_build_institution(conn, out_dir, r, findings) for r in insts)
    _build_findings(conn, out_dir)
    _build_how_to_read(out_dir)
    n_fs = _build_firststone(out_dir)
    _write_feed(conn, out_dir)
    _write_institution_feeds(conn, out_dir, insts, findings)
    return {"pages": 7 + n_inst + n_fs, "findings": len(findings)}


def _build_detectors(conn, out_dir, matrix=None) -> None:
    """The public 'what we check — and how each check is validated' page. The
    catalogue of detectors, in registrar voice, each with its live scorecard.
    Publishing the validation is the novel part: the tool accountable for its
    own method."""
    from . import detectors, timeline
    _timelines = timeline.load_timelines()
    cards = ""
    for d in detectors.registry().values():
        t = detectors.TECHNIQUES[d.technique]
        # Pass the SHARED caches: without them every detector rebuilds the
        # 3.4M-row matrix (and the timelines) from scratch, so the page cost
        # scaled with the size of the library.
        sc = d.scorecard(conn, matrix=matrix, timelines=_timelines)
        note = _e(sc.get("note", "")) or _e(d.validation)
        sel = _e(sc.get("selectivity_note", ""))
        sel_html = f"<p class=meta><b>Selectivity:</b> {sel}</p>" if sel else ""
        leads = sc.get("leads")
        badge = f"<span class=cite>{leads} current leads</span>" if leads is not None else ""
        cards += f"""<div class='card'>
<p class=kicker style='margin:0 0 .2rem'>{_e(t['family'])}</p>
<h3 style='margin:.1rem 0'>{_e(d.name)}</h3>
<p><b>The question:</b> {_e(d.question)}</p>
<p class=meta><b>Reads:</b> {_e(t['reads'])}</p>
<p class=secnote style='margin:.4rem 0 0'><b>How it's validated:</b> {note}</p>
{sel_html}{badge}</div>"""
    body = f"""<h1>What we check</h1>
<p class=lede>Glasshouse is a library of <b>detectors</b> — each a single, sharp
question asked of the primary record. Every detector states cited acts, dates and
votes; none asserts motive. Each is quarantined as a <b>lead</b> until a human
verifies it.</p>
<p class=secnote>Every detector below carries its own validation — including, honestly,
when a check does <i>not</i> discriminate on the current record. The method is held
to the same standard as the institutions it examines.</p>
{cards}"""
    (out_dir / "detectors.html").write_text(_page("What we check", body, "detect"))


def _pretty_stamp(v: str) -> str:
    return f"{v[:4]}-{v[4:6]}-{v[6:8]}" if len(v) >= 8 and v[:8].isdigit() else v


def _build_systemic(out_dir, matrix) -> None:
    """The lead public page: does a stewardship promise predict anything?

    This is the project's headline claim and the safest one — a statistical
    statement about an industry practice, computed PAIRED (each manager against
    itself) so house voting philosophy cannot manufacture the result. It reports
    managers that vote BETTER on their committed themes as plainly as the
    reverse."""
    from . import systemic
    s = systemic.industry_summary(matrix)
    def _pct(x):
        return "—" if x is None else f"{x:.1%}"
    rows = ""
    for p in s["pairs"]:
        cls = {"better": "for", "worse": "against", "no difference": "muted"}[p.direction]
        mark = {"better": "votes for it more than mix predicts",
                "worse": "votes against it more than mix predicts",
                "no difference": "no measurable difference"}[p.direction]
        rows += (f"<tr><th scope=row>{_e(p.institution_name)}</th>"
                 f"<td><b>{p.committed_rate:.0%}</b><span>against · "
                 f"{p.committed_n:,} votes</span></td>"
                 f"<td><b>{p.baseline_rate:.0%}</b><span>against · "
                 f"{p.baseline_n:,} votes</span></td>"
                 f"<td><b>{p.delta:+.1%}</b><span>raw</span></td>"
                 f"<td><b>{p.expected_delta:+.1%}</b><span>theme mix</span></td>"
                 f"<td style='color:var(--{cls})'><b>{p.residual:+.1%}</b>"
                 f"<span>{mark}</span></td></tr>")
    body = f"""<h1>Does a promise predict anything?</h1>
<p class=lede>{_e(s['verdict'])}</p>
<p class=kicker>Method</p><h2>Each manager against itself</h2>
<p class=secnote>{_e(s['method'])}</p>
<div class=statband>{_stat(s['n_managers'], 'managers compared')}
{_stat(s['n_better'], 'vote FOR the theme more than their theme mix predicts')}
{_stat(s['n_worse'], 'vote against it more than their theme mix predicts')}
{_stat(f"{s['paired_median_residual']:+.1%}" if s['paired_median_residual'] is not None else '—',
       'median residual (theme mix removed)')}</div>
<div class='card flat' style='overflow-x:auto'><table class=rc>
<thead><tr><th></th><th>on themes it commits to</th><th>on its own other themes</th>
<th>raw diff.</th><th>predicted by theme mix</th><th>residual</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class=secnote>All rates are <b>against</b>-rates. A negative <b>residual</b> means the
manager votes <b>for</b> the theme more often than its own theme mix predicts — this
record reports that as plainly as the reverse. The raw difference is shown for
transparency, but it is mostly composition: a manager's committed and uncommitted
baskets contain different themes, and themes have very different industry-wide rates,
so only the residual — and only when it exceeds sampling noise — carries a label.</p>
<p class=kicker>Transparency</p><h2>The raw comparison, and why we do not rely on it</h2>
<p class=secnote>Pooled across managers, commitment themes were voted against
{_pct(s['raw_committed_rate'])} of the time versus {_pct(s['raw_uncommitted_rate'])} on
uncommitted themes ({s['raw_votes']:,} votes). {_e(s['raw_caveat'])}</p>
<p class=meta>Built {_e(s['generated'][:10])} from the voting record as ingested
(see the coverage statement in the release datasheet — this is the build date, not
the end of the proxy-vote record). Every figure is recomputable from the public ledger. This page reports rates and differences in the voting record; it
does not state why any institution voted as it did.</p>"""
    (out_dir / "promise.html").write_text(_page("Does a promise predict anything?", body, "promise"))


def _build_record(conn, out_dir, matrix=None) -> None:
    """The record — the public say-vs-do matrix, in registrar voice: rates and
    counts from the ledger, framed as leads for the reader to verify, never as
    conclusions."""
    from .investigate import build_matrix
    m = matrix if matrix is not None else build_matrix(conn)
    used = [t for t in m["themes"] if any(t in i["cells"] for i in m["institutions"])]
    head = "".join(f"<th>{_e(t.replace('-', ' '))}</th>" for t in used)
    rows = ""
    for inst in sorted(m["institutions"], key=lambda i: i["name"].lower()):
        tds = ""
        for th in used:
            c = inst["cells"].get(th)
            if not c:
                tds += "<td></td>"
            elif not c["committed"]:
                tds += ("<td class=dot title='votes on this theme; no binding commitment "
                        "sentence found in its archived policy'>·</td>")
            elif not (c["for"] + c["against"]):
                tds += ("<td class=dot title='commitment on record; no cast FOR/AGAINST "
                        "votes matched this theme'>–</td>")
            else:
                denom = c["for"] + c["against"]
                mark = "*" if c.get("low_confidence") else ""
                heat = int(c["rate"] * 52)
                tds += (f"<td style='background:color-mix(in srgb,var(--against) {heat}%,"
                        f"transparent)'><b>{round(c['rate'] * 100)}%{mark}</b>"
                        f"<span>{c['against']:,}/{denom:,} against</span></td>")
        rows += (f"<tr><th scope=row><a href='institution-{_e(inst['id'])}.html'>"
                 f"{_e(inst['name'])}</a></th>{tds}</tr>")
    body = f"""<h1>The record</h1>
<p class=lede>Each committed cell: how often a manager's funds voted <b>against</b>
shareholder proposals advancing a theme its own archived policy commits to. SAY is a
verbatim, dated policy sentence; DO is the de-duplicated SEC N-PX voting record.</p>
<div class='card flat' style='overflow-x:auto'><table class=rc>
<thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></div>
<p class=secnote>A high rate is a <b>lead, not a finding</b>: theme matching is
lexical, so confirm each proposal's text and intent — and the policy version in force
at the vote — against the linked sources before drawing a conclusion. Proposals that
oppose a theme are excluded from its rate; “·” = votes on the theme with no binding
commitment sentence on record (no say-vs-do tension); “*” = fewer than 5 committed
votes, treat with caution. <a href='how-to-read.html'>How to read Glasshouse</a>.</p>
<p class=meta>Data as of {_e(m['generated'][:10])}. Every underlying vote carries its
SEC accession number; every policy sentence its archived, content-hashed source.</p>"""
    (out_dir / "record.html").write_text(_page("The record", body, "record"))


# ── First Stone: the newsroom's own identity, built on the registrar ─────────
# The two-layer rule (decided 2026-07-06): Glasshouse the registrar accuses no
# one; First Stone the newsroom argues from its record — under its own
# masthead, in its own ink, and only after a human publishes.

_FS_CSS = """
:root{--accent:#8a5a00;--accent-soft:#f6ecd4}
@media (prefers-color-scheme:dark){:root{--accent:#e3b855;--accent-soft:#33290f}}
.fsword{font:600 1.05rem/1 var(--display);letter-spacing:.3em;text-transform:uppercase}
.fsword b{color:var(--accent);border-left:2px solid var(--accent);
  padding-left:.3em;margin-left:.1em}
.deskrow{display:flex;gap:.8rem;padding:.5rem 0;border-bottom:1px solid var(--line);
  align-items:baseline}
.deskrow b{font:700 .78rem var(--mono);letter-spacing:.08em;min-width:14rem}
.deskrow span{color:var(--muted);font-size:.92rem}
.deskrow.human b{color:var(--accent)}
article.story{max-width:46rem}
article.story blockquote{border-left:3px solid var(--accent);padding-left:1rem;margin-left:0}
/* the staff — correspondents by beat */
.staff{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:1rem;margin:1rem 0}
.corr{border:1px solid var(--edge);border-radius:10px;padding:1rem 1.1rem;background:var(--panel)}
.corr .nm{font:600 1.05rem var(--serif);color:var(--ink)}
.corr .bt{font:700 .66rem var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin:.15rem 0 .4rem}
.corr .bi{color:var(--muted);font-size:.9rem;line-height:1.5}
.eic{border:1px solid var(--edge);border-left:4px solid var(--accent);border-radius:10px;
  padding:1rem 1.2rem;background:var(--panel);margin:1rem 0}
.eic .nm{font:600 1.2rem var(--serif)} .eic .rl{font:700 .68rem var(--mono);
  letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.ethic{padding:.6rem 0;border-bottom:1px solid var(--line)}
.ethic b{font:600 1rem var(--sans)} .ethic span{display:block;color:var(--muted);
  font-size:.92rem;margin-top:.15rem}
.disclose{border:1.5px dashed var(--accent);border-radius:8px;padding:.9rem 1.1rem;
  background:var(--accent-soft);color:var(--ink);font-size:.92rem;margin:1.2rem 0}
/* story furniture */
article.story .kicker-line{font:700 .72rem var(--mono);letter-spacing:.2em;
  text-transform:uppercase;color:var(--accent);margin:0}
article.story .byline{font:600 1rem var(--sans);margin:.3rem 0 0}
"""


def _fs_page(title: str, body: str, active: str = "stories") -> str:
    from .firststone import MASTHEAD
    links = [("firststone.html", "Stories", "stories"),
             ("firststone-masthead.html", "Masthead & standards", "masthead")]
    nav = "".join(f"<a href='{h}'{' class=on' if k == active else ''}>{t}</a>"
                  for h, t, k in links)
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)} — First Stone</title>"
            f"<style>{_CSS}{_FS_CSS}</style></head><body>"
            f"<nav><div class=wrap><span class=fsword>FIRST<b>STONE</b></span>{nav}"
            f"<a href='index.html'>Glasshouse — the registry ↗</a></div></nav>"
            f"<div class=wrap>{body}<footer>{_e(MASTHEAD['tagline'])} "
            f"{_e(MASTHEAD['disclosure'])} Built on the Glasshouse registry; every "
            f"number can be recomputed from the public ledger.</footer></div>"
            f"{_JS}</body></html>")


def _md_html(md: str) -> str:
    """Minimal renderer for First Stone's own templated Markdown (headings,
    blockquotes, lists, bold, links, inline code) — not general-purpose."""
    def inline(t: str) -> str:
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<a href='\2'>\1</a>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    out, para, lst = [], [], []

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    def flush_list():
        if lst:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in lst) + "</ul>")
            lst.clear()

    for raw in md.splitlines():
        line = _e(raw.rstrip())
        if line.startswith("## "):
            flush_para()
            flush_list()
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_para()
            flush_list()
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("&gt; "):
            flush_para()
            flush_list()
            out.append(f"<blockquote>{inline(line[5:])}</blockquote>")
        elif line.startswith("- "):
            flush_para()
            lst.append(line[2:])
        elif not line.strip():
            flush_para()
            flush_list()
        else:
            flush_list()
            para.append(line)
    flush_para()
    flush_list()
    return "".join(out)


def _build_firststone(out_dir) -> int:
    from .firststone import MASTHEAD, load_published
    pub = load_published()

    # ── the front page: the edition ──
    if pub:
        cards = "".join(
            f"<div class='card claim r'><span class='ribbon ok'>● published "
            f"{_e(p['published'][:10])}</span>"
            f"<p class=meta>{_e(p.get('beat', ''))}{' · by ' + _e(p['byline']) if p.get('byline') else ''}</p>"
            f"<h3><a href='firststone-story-{_e(p['slug'])}.html'>{_e(p['headline'])}</a></h3>"
            f"<p>{_e(p['standfirst'])}</p>"
            f"<p class=cite>Publisher's note: {_e(p['publisher_note'])}</p></div>"
            for p in pub)
    else:
        cards = ("<div class=card><p>No story has cleared the publisher's chair yet. "
                 "The desks draft and check; a human decides — that order is the "
                 "point.</p></div>")
    body = f"""<h1>{_e(MASTHEAD['name'])}</h1>
<p class=lede>{_e(MASTHEAD['tagline'])}</p>
<div class=disclose><b>How to read First Stone.</b> {_e(MASTHEAD['disclosure'])}</div>
<p class=kicker>The edition</p><h2>Published stories</h2>
{cards}
<p class=secnote style='margin-top:1.4rem'>See the
<a href='firststone-masthead.html'>masthead, correspondents and standards ↗</a>.</p>"""
    (out_dir / "firststone.html").write_text(_fs_page("First Stone", body, "stories"))

    # ── the masthead & standards page: who we are, how we work ──
    eic = MASTHEAD["editor"]
    se = MASTHEAD["standards_editor"]
    corrs = "".join(
        f"<div class=corr><div class=nm>{_e(c['name'])}</div>"
        f"<div class=bt>{_e(c['beat'])}</div>"
        f"<div class=bi>An automated correspondent who {_e(c['bio'])}</div></div>"
        for c in MASTHEAD["correspondents"])
    ethics = "".join(
        f"<div class=ethic><b>{_e(t)}</b><span>{_e(d)}</span></div>"
        for t, d in MASTHEAD["ethics"])
    desks = "".join(
        f"<div class='deskrow{' human' if key == 'publisher' else ''}'>"
        f"<b>{_e(name)}</b><span>{_e(charge)}</span></div>"
        for key, name, charge in MASTHEAD["desks"])
    mast = f"""<h1>Masthead &amp; standards</h1>
<p class=lede>{_e(MASTHEAD['about'])}</p>
<div class=disclose>{_e(MASTHEAD['disclosure'])}</div>
<p class=kicker>Editor</p><h2>Who runs the edition</h2>
<div class=eic><div class=rl>{_e(eic['role'])}</div><div class=nm>{_e(eic['name'])}</div>
<p class=bi>{_e(eic['name'])} {_e(eic['note'])}</p></div>
<div class=eic><div class=rl>{_e(se['role'])}</div><div class=nm>{_e(se['name'])}</div>
<p class=bi>{_e(se['note'])}</p></div>
<p class=kicker>Correspondents</p><h2>The beats</h2>
<div class=staff>{corrs}</div>
<p class=kicker>How a story is made</p><h2>From the record to the page</h2>
<p class=secnote>Every story passes these desks in order. A story spikes the moment
any desk's check fails — and no story is published until the human publisher signs it.</p>
<div class='card flat'>{desks}</div>
<p class=kicker>Ethics</p><h2>The code we hold</h2>
<div class='card flat'>{ethics}</div>
<p class=kicker>Corrections</p><h2>When we get it wrong</h2>
<div class=card><p>{_e(MASTHEAD['corrections'])}</p></div>"""
    (out_dir / "firststone-masthead.html").write_text(
        _fs_page("Masthead & standards", mast, "masthead"))

    for p in pub:
        story = (f"<article class=story>{_md_html(p['body'])}"
                 f"<p class=cite>Publisher's note: {_e(p['publisher_note'])} · "
                 f"published {_e(p['published'][:10])}</p></article>")
        (out_dir / f"firststone-story-{p['slug']}.html").write_text(
            _fs_page(p["headline"], story, "stories"))
    return 2 + len(pub)


def _build_findings(conn, out_dir) -> None:
    import json as _json
    rows = conn.execute("SELECT status, reviewer_note, reviewed_date, payload "
                        "FROM findings ORDER BY reviewed_date DESC").fetchall()
    approved = [r for r in rows if r["status"] == "approved"]
    n_rejected = sum(1 for r in rows if r["status"] == "rejected")
    n_pending = sum(1 for r in rows if r["status"] == "pending")

    cards = "".join(
        _finding_card({**_json.loads(r["payload"]), "_note": r["reviewer_note"],
                       "_reviewed": r["reviewed_date"]})
        for r in approved)

    if not approved:
        cards = ("<div class=card><p>No findings have cleared human review yet. "
                 "The machine produces candidates; a person promotes them — or "
                 "doesn't, on the record. Candidates are reviewed in the private "
                 "operator workbench and only appear here once verified.</p></div>")
    body = f"""<h1>Findings</h1>
<p class=lede>A finding is a candidate that survived human review of both primary
sources. The numbers below are part of the method: what we discard matters as
much as what we publish.</p>
<div class=statband>{_stat(len(approved), 'approved findings')}
{_stat(n_rejected, 'rejected after review')}{_stat(n_pending, 'pending review')}</div>
{cards}"""
    (out_dir / "findings.html").write_text(_page("Findings", body, "find"))


def _write_institution_feeds(conn, out_dir, insts, findings) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for r in insts:
        if not (r["n_votes"] or r["n_docs"]):
            continue
        entries = []
        # Approved findings only — feeds are a publication surface; candidates
        # never go out over RSS.
        for p in [p for p in findings if p["institution_id"] == r["id"]][:15]:
            title = f"Finding: {p['theme']} — voted {p['how_voted']} at {p['issuer_name']} ({p['meeting_date']})"
            entries.append(
                f"<entry><title>{_e(title)}</title>"
                f"<id>urn:glasshouse:finding:{_e(p['accession'])}:{_e(p['cusip'])}:{_e(p['theme'])}</id>"
                f"<updated>{now}</updated><content type='text'>VERIFIED FINDING. "
                f"{_e(p['commitment_quote'][:200])} | N-PX {_e(p['accession'])}</content></entry>")
        for d in conn.execute(
                "SELECT doc_label, sha256, retrieval_date FROM commitments "
                "WHERE institution_id=? GROUP BY CASE WHEN text_sha256='' THEN 'raw:'||sha256 ELSE text_sha256 END "
                "ORDER BY id DESC LIMIT 10", (r["id"],)):
            entries.append(
                f"<entry><title>Policy version: {_e(d['doc_label'])}</title>"
                f"<id>urn:glasshouse:doc:{_e(d['sha256'][:16])}</id>"
                f"<updated>{now}</updated><content type='text'>sha256 "
                f"{_e(d['sha256'])}</content></entry>")
        feed = (f"<?xml version='1.0' encoding='utf-8'?>"
                f"<feed xmlns='http://www.w3.org/2005/Atom'>"
                f"<title>Glasshouse — {_e(r['display_name'])}</title>"
                f"<id>urn:glasshouse:feed:{_e(r['id'])}</id>"
                f"<updated>{now}</updated>{''.join(entries)}</feed>")
        (out_dir / f"feed-{r['id']}.xml").write_text(feed)


def _build_index(conn, out_dir, stats, insts, findings) -> None:
    enf = conn.execute(
        "SELECT agency, COUNT(*) FROM enforcement_actions WHERE is_duplicate = 0 "
        "GROUP BY agency ORDER BY 2 DESC LIMIT 8").fetchall()
    split = _vote_split(conn)
    featured = max(findings, key=lambda p: float(p["shares_voted"])) if findings else None
    top = next((r for r in insts if r["n_votes"]), None)

    body = f"""
<h1>What they promise.<br>How they vote.<br>The gap, on the record.</h1>
<p class=lede>Glasshouse joins the published commitments of major financial
institutions with their actual proxy votes, holdings, and the documented
enforcement records of the companies they fund. Every clause of every claim
traces to a public primary source. <a href='how-to-read.html'>New here? Start
with how to read this →</a></p>
<div class='statband r'>
{_stat(stats.get('votes', 0), 'proxy votes on record (SEC N-PX)')}
{_stat(stats.get('issuers', 0), 'companies voted on')}
{_stat(stats.get('holdings', 0), '13-F holdings')}
{_stat(stats.get('enforcement', 0), 'enforcement actions indexed')}
{_stat(stats.get('commitments', 0), 'archived policy versions')}
</div>"""

    if featured:
        body += ("<p class=kicker>Exhibit A</p><h2>The latest verified finding</h2>"
                 "<p class=secnote>A verbatim sentence from the institution's own archived "
                 "policy, next to a vote its funds actually cast — confirmed by human "
                 "review of both primary sources.</p>"
                 + _finding_card(featured, featured=True)
                 + "<p class=meta><a href='findings.html'>All findings →</a></p>")
    else:
        body += ("<p class=kicker>Method</p><h2>Findings, not allegations</h2>"
                 "<p class=secnote>No findings have cleared human review yet. The machine "
                 "selects candidates; a person verifies both primary sources before "
                 "anything is published here. Candidates are never shown publicly — that "
                 "discipline is the point. <a href='how-to-read.html'>How to read "
                 "Glasshouse →</a></p>")

    body += f"""
<p class=kicker>Scale</p><h2>Two million votes, square by square</h2>
<p class=secnote>Every square is ~{(sum(v for _, v in split) or 200)//200:,} proxy votes
cast by the tracked institutions. Voting is an active choice — the “passive index”
defense does not apply.</p>
<div class='card r'>{_waffle(split)}</div>"""

    if top:
        stances = _theme_stances(conn, top["id"])
        if stances:
            body += (f"<p class=kicker>Stances</p><h2>{_e(top['display_name'])}, when the "
                     f"proposal mentions…</h2><p class=secnote>Keyword match on proposal "
                     f"text; opposition pulls left. Context varies — verify any individual "
                     f"vote before citing it.</p><div class='card r'>{_butterfly(stances)}</div>")

    body += f"""
<p class=kicker>The record</p><h2>The enforcement landscape</h2>
<p class=secnote>Documented actions indexed per agency — each tile sized by count.
Resolution types are preserved and legally distinct.</p>
<div class=r>{_mosaic([(a, n, 'how-to-read.html') for a, n in enf])}</div>

<p class=kicker>Who</p><h2>Institutions under glass</h2>
<p class=secnote>Only institutions with ingested data appear here — showing an
empty page would imply a clean record that no one has checked.
{sum(1 for r in insts if not (r['n_votes'] or r['n_docs'] or r['n_holdings']))} more
are registered and queued for ingestion.</p>
{_inst_cards(conn, [r for r in insts if r['n_votes'] or r['n_docs'] or r['n_holdings']])}
<p class=meta><a href='institutions.html'>Full registry, including not-yet-ingested →</a></p>"""
    (out_dir / "index.html").write_text(_page("Glasshouse", body, "home"))


def _inst_cards(conn, insts) -> str:
    cards = ""
    for r in insts:
        gauge = ""
        if r["n_votes"]:
            split = dict(_vote_split(conn, r["id"]))
            total = sum(split.values()) or 1
            with_mgmt = 100 * split.get("FOR", 0) / total
            gauge = _donut(with_mgmt, "voted for", "var(--accent)",
                           f"{r['n_votes']:,} votes on record")
        else:
            gauge = "<p class=meta>Not yet ingested — an empty row means no data, not innocence.</p>"
        cards += f"""<div class='card fitem r'><h3 style='margin-top:0'>
<a href='institution-{_e(r['id'])}.html'>{_e(r['display_name'])}</a></h3>
<div class=meta>{_e(r['type'] or '')} · {_e(r['country'] or '')} ·
{r['n_docs']} policy versions · {r['n_holdings']:,} holdings</div>
<div style='margin-top:.7rem'>{gauge}</div></div>"""
    return f"<div class=grid3>{cards}</div>"


def _build_institutions_index(conn, out_dir, insts) -> None:
    body = (f"<h1>Institutions</h1><p class=lede>One entry in the registry adds any "
            f"SEC 13-F filer. Counts reflect what has been ingested so far.</p>"
            f"<input class=filter placeholder='Filter institutions…' data-target='#il' "
            f"oninput='ghFilter(this)'><div id=il>{_inst_cards(conn, insts)}</div>")
    (out_dir / "institutions.html").write_text(_page("Institutions", body, "inst"))


def _build_institution(conn, out_dir, r, findings) -> int:
    inst_id = r["id"]
    body = f"""<h1>{_e(r['display_name'])}</h1>
<p class=meta>{_e(r['type'] or '')} · {_e(r['country'] or '')}</p>
<div class='statband r'>
{_stat(r['n_votes'], 'proxy votes on record')}
{_stat(r['n_holdings'], '13-F holdings')}
{_stat(r['n_docs'], 'archived policy versions')}</div>"""

    if r["n_votes"]:
        split = _vote_split(conn, inst_id)
        body += (f"<p class=kicker>Behavior</p><h2>How its funds vote</h2>"
                 f"<div class='card r'>{_waffle(split)}</div>")
        stances = _theme_stances(conn, inst_id)
        if stances:
            body += (f"<p class=kicker>Stances</p><h2>When the proposal mentions…</h2>"
                     f"<p class=secnote>Keyword match on proposal text; opposition pulls "
                     f"left, support pulls right.</p>"
                     f"<div class='card r'>{_butterfly(stances)}</div>")

    docs = conn.execute(
        """SELECT doc_label, sha256, wayback_timestamp,
                  COALESCE(NULLIF(wayback_timestamp,''), NULLIF(public_by,''), retrieval_date) AS version
           FROM commitments WHERE institution_id=? AND superseded=0
           GROUP BY CASE WHEN text_sha256='' THEN 'raw:'||sha256 ELSE text_sha256 END ORDER BY version""",
        (inst_id,)).fetchall()
    if docs:
        versions = []
        for d in docs:
            v = d["version"]
            pretty = f"{v[:4]}-{v[4:6]}-{v[6:8]}" if re.fullmatch(r"\d{14}", v) else v
            versions.append({"date": pretty, "label": d["doc_label"],
                             "sha": d["sha256"][:10], "live": not d["wayback_timestamp"]})
        body += (f"<p class=kicker>Paper trail</p><h2>Every version of its own words</h2>"
                 f"<p class=secnote>Each node is a distinct archived version of the "
                 f"institution's policy (teal = Wayback Machine, red = live fetch). "
                 f"<strong>Dates are capture dates, not publication dates</strong> — "
                 f"they establish that the text was public by that day. A policy is "
                 f"routinely archived months after it takes effect. "
                 f"Sentence-level differences are documented in the change log below.</p>"
                 f"<div class='card r'>{_timeline_svg(versions)}</div>")

    tl = timeline.institution_timeline(conn, inst_id)
    ev_themes = {th: d for th, d in tl["themes"].items() if d["events"]}
    if ev_themes:
        blocks = ""
        for th, d in sorted(ev_themes.items()):
            items = ""
            for ev in d["events"]:
                frm, to = _pretty_stamp(ev["from"]["version"]), _pretty_stamp(ev["to"]["version"])
                cite = (f"<span class=cite><a href='{_e(ev['from']['url'])}'>version {frm}</a>"
                        f" → <a href='{_e(ev['to']['url'])}'>version {to}</a>"
                        f" · {_e(ev['doc_label'])}</span>")
                for s in ev["removed"]:
                    items += (f"<li>present in {frm}, <b>not present in {to}</b>: "
                              f"<q>{_e(s)}</q>{cite}</li>")
                for s in ev["added"]:
                    items += (f"<li><b>added in {to}</b> (not present in {frm}): "
                              f"<q>{_e(s)}</q>{cite}</li>")
                for old, new in ev["revised"]:
                    items += (f"<li>revised between {frm} and {to}: <q>{_e(old)}</q> → "
                              f"<q>{_e(new)}</q>{cite}</li>")
            blocks += f"<h3>{_e(th.replace('-', ' '))}</h3><ul class=chg>{items}</ul>"
        body += (f"<p class=kicker>Change log</p><h2>What changed in its own words</h2>"
                 f"<p class=secnote>Sentence-level differences between consecutive archived "
                 f"versions of the same document, quoted verbatim with both versions linked. "
                 f"The record documents the change; interpretation is the reader's.</p>"
                 f"<div class='card flat'>{blocks}</div>")

    mine = [p for p in findings if p["institution_id"] == inst_id]
    if mine:
        body += ("<p class=kicker>Say × do</p><h2>Verified findings</h2>"
                 + "".join(_finding_card(p) for p in mine[:5]))

    if r["n_votes"]:
        tug_rows = _splits(conn, inst_id)
        if tug_rows:
            body += (f"<p class=kicker>House divided</p><h2>Its own funds, disagreeing</h2>"
                     f"<p class=secnote>The same manager casting shares on both sides of the "
                     f"identical proposal. Finding-grade: the contradiction is internal to one "
                     f"filer's own N-PX report. Ranked by the size of the losing side.</p>"
                     f"<input class=filter placeholder='Filter by company or proposal…' "
                     f"data-target='#split' oninput='ghFilter(this)'>"
                     f"<div id=split class=card>{_tug(tug_rows)}</div>")

    (out_dir / f"institution-{inst_id}.html").write_text(_page(r["display_name"], body, "inst"))
    return 1


def _build_how_to_read(out_dir) -> None:
    body = """<h1>How to read Glasshouse</h1>
<p class=lede>Glasshouse exists to make one gap visible: the distance between what
financial institutions publicly commit to and what they actually do. Here is how to
use it without being misled — by us or by anyone.</p>

<p class=kicker>Anatomy</p><h2>The anatomy of a claim</h2>
<ol class=steps>
<li><b>SAY</b> — a verbatim sentence from the institution's own published policy,
pinned to a dated, content-hashed archived version. We never paraphrase commitments.</li>
<li><b>DO</b> — an act from a regulatory filing: a proxy vote (SEC Form N-PX, with
accession number), a holding (SEC Form 13-F), or a documented silence.</li>
<li><b>The join</b> — what connects them: the same institution, the same theme, the
same company. The strength of every claim lives or dies on this join.</li>
</ol>

<p class=kicker>Trust</p><h2>Leads vs. findings</h2>
<div class=card><p>Anything marked <span class=ribbon>◌ quarantined</span> is a
<b>lead</b>: a machine-generated candidate awaiting human verification. The failure
mode is real — on our first live run, a sanctions entry for “Aldar Properties” (a
Sudan-based entity) matched the name of Aldar Properties PJSC, an unrelated Abu
Dhabi-listed developer. Same normalized name, different company. <b>Name matches are
never findings.</b> A lead is promoted only when corroborated by an identifier
(CUSIP, LEI, CIK) or human review of the primary source.</p></div>

<p class=kicker>Law</p><h2>Resolution types are not interchangeable</h2>
<table>
<tr><th>Resolution</th><th>Criminal conviction?</th><th>Admission of guilt?</th></tr>
<tr><td><b>Guilty plea</b></td><td>Yes</td><td>Yes</td></tr>
<tr><td><b>DPA</b> (deferred prosecution)</td><td>No — dismissed if compliant</td><td>No</td></tr>
<tr><td><b>NPA</b> (non-prosecution)</td><td>No — no charges filed</td><td>No</td></tr>
<tr><td><b>Civil settlement</b></td><td>No (civil only)</td><td>Typically no</td></tr>
<tr><td><b>Debarment / sanction / expulsion</b></td><td>No (administrative)</td><td>N/A</td></tr>
<tr><td><b>Docket / pending matter</b></td><td><b>Allegation only — never a finding</b></td><td>—</td></tr>
</table>

<p class=kicker>Charts</p><h2>What the visuals mean</h2>
<ol class=steps>
<li><b>Waffle grids</b> — every square is the same number of votes; the colors are how
they were cast. Scale you can feel rather than read.</li>
<li><b>Butterfly charts</b> — opposition pulls left (red), support pulls right (green),
from a shared spine. The asymmetry is the picture.</li>
<li><b>Tug-of-war bars</b> — one proposal, the same manager's shares on both sides of it.</li>
<li><b>Timelines</b> — each node is a distinct, content-hashed version of the
institution's own policy document. Drift between nodes is a silent edit.</li>
</ol>

<p class=kicker>Why votes</p><h2>Why votes, not just holdings</h2>
<div class=card><p>Holding a stock through an index fund supports a credible “we just
track the index” defense. <b>Voting does not.</b> Every proxy vote is an active choice
by the institution's stewardship team — which is why N-PX voting records are the spine
of this project, and holdings-only claims are explicitly labeled as the weakest class.</p></div>

<p class=kicker>Verify</p><h2>Verify everything yourself</h2>
<ol class=steps>
<li>Every vote cites its SEC accession number — open the filing directly on EDGAR.</li>
<li>Every policy quote links the source document and its content hash — fetch and hash it.</li>
<li>The full SQLite ledger ships with the project; run any SQL you like via Datasette.</li>
</ol>
<p>If you find an error, we want it: discarding almost-right findings is the discipline
this project is built on.</p>

<p class=kicker>Use it</p><h2>Tell us if you used this</h2>
<div class=card><p>This dataset exists to be used, and the only measure that matters
to us is whether it was. If you cited it, wrote from it, put it in a board pack,
taught with it, or filed with it — <b>tell us</b>, in one line, so the project knows
what to build next. Corrections are the most valuable use of all: if a figure is
wrong, the record should change, and being corrected in public is the point.</p>
<p class=cite>How: open an issue on the project repository titled
<code>used: &lt;who you are&gt;</code>, or cite the dataset DOI and say so. Recorded
uses are kept in <code>ADOPTION.md</code> in the repository.</p></div>"""
    (out_dir / "how-to-read.html").write_text(_page("How to read", body, "how"))


def _write_feed(conn, out_dir) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
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
