"""The operator workbench — the human side of the tool, as a tool.

A local-only (127.0.0.1) interactive desk over the ledger for the work the
charter reserves for a person: reviewing candidates, adjudicating entity
leads, managing the outreach queue, and recording distribution signals.

This is NOT a public interface and does not soften the spec's "no custom
API server" rule: the public surfaces stay static site + Datasette + MCP.
The workbench is the operator's desk — it binds to localhost, writes
through the same gated functions the CLI uses, and adds one new loop:
every human lead adjudication is saved as a labeled pair in
data/labels/lead_labels.jsonl, which grows the eval gold set that gates
the LLM triage tier. Your review work trains your own quality bar.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .http import DATA_DIR
from .ledger import DB_PATH

LABELS_PATH = DATA_DIR / "labels" / "lead_labels.jsonl"


# ── state assembly (read side) ───────────────────────────────────────────────

_synced_dbs: set[str] = set()


def _conn(write: bool = False) -> sqlite3.Connection:
    """Reads must not take the write lock: the registry sync (20 upserts +
    commit) runs once per ledger, not per request — found in review when
    GET /api/state contended with a running ingest. Keyed by DB path so a
    second distinct ledger in the same process still gets synced."""
    from . import ledger, registry
    conn = ledger.connect(DB_PATH)
    if write and str(DB_PATH) not in _synced_dbs:
        registry.sync_to_ledger(conn)
        _synced_dbs.add(str(DB_PATH))
    return conn


def _labeled_keys() -> set[str]:
    if not LABELS_PATH.exists():
        return set()
    keys = set()
    for line in LABELS_PATH.read_text().splitlines():
        try:
            keys.add(json.loads(line)["lead_key"])
        except (json.JSONDecodeError, KeyError):
            continue
    return keys


def state(conn: sqlite3.Connection) -> dict:
    from . import review
    from .findings import own_record

    pending = review.queue(conn, "pending")
    done = _labeled_keys()

    leads = []
    for r in own_record(conn):
        key = f"own:{r.institution_id}:{r.primary_ref}:{r.action_date}"
        if key in done:
            continue
        leads.append({
            "lead_key": key,
            "kind": "own-record",
            "a": {"name": r.institution, "context": "tracked institution (registry)"},
            "b": {"name": r.company_name,
                  "context": f"{r.agency} {r.resolution_type} {r.primary_ref or ''} "
                             f"{r.action_date}".strip()},
            "detail": (r.description or "")[:240],
        })

    outreach_rows = [dict(r) for r in conn.execute(
        "SELECT id, kind, institution_id, subject, status, sent_date, response_date, "
        "body_path FROM outreach ORDER BY id DESC LIMIT 50")]

    doctor_report = {}
    rp = DATA_DIR / "doctor" / "report.json"
    if rp.exists():
        doctor_report = json.loads(rp.read_text())

    signals = [dict(r) for r in conn.execute(
        "SELECT ts, kind, detail FROM signals ORDER BY id DESC LIMIT 10")]

    from . import agent, council, firststone, investigate, newsroom
    from .site import _md_html
    recs = council.recommendations(conn)
    for f in pending:
        f["council"] = recs.get(f["fingerprint"])
    fs_run = firststone.load_run()
    if fs_run:  # pre-render each story to HTML so the reading pane is real, not a text dump
        for s in fs_run["stories"]:
            s["body_html"] = _md_html(s.get("body", ""))
    return {
        "review": pending,
        "review_stats": review.stats(conn),
        "leads": leads[:40],
        "outreach": outreach_rows,
        "doctor": doctor_report,
        "signals": signals,
        "gold_labels": len(done),
        "newsroom": newsroom.story_queue(conn),
        "pipeline": newsroom.pipeline_status(conn),
        "investigate": investigate.load_matrix(),   # cached hypocrisy matrix (or None)
        "agent_drafts": agent.load_latest_briefs(),  # latest agent-drafted story leads (or None)
        "firststone": {"run": fs_run,
                       "published": [{k: v for k, v in p.items() if k != "body"}
                                     for p in firststone.load_published()],
                       "masthead": firststone.MASTHEAD},
    }


# ── actions (write side — all through existing gated functions) ─────────────

def act(conn: sqlite3.Connection, action: str, payload: dict) -> dict:
    from . import outreach, review

    if action == "review":
        review.decide(conn, int(payload["id"]), payload["decision"], payload["note"])
        return {"ok": True}

    if action == "lead":
        label = payload["label"]
        if label not in ("match", "no_match", "unsure"):
            raise ValueError("label must be match/no_match/unsure")
        if not payload.get("note", "").strip():
            raise ValueError("a note is required — labels without reasons aren't evidence")
        LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LABELS_PATH, "a") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "lead_key": payload["lead_key"], "label": label,
                "why": payload["note"], "a": payload["a"], "b": payload["b"],
            }) + "\n")
        conn.execute(
            "INSERT OR REPLACE INTO triage (kind, input_key, verdict, confidence, "
            "rationale, model, ts) VALUES ('entity_match', ?, ?, 'high', ?, 'human', ?)",
            (f"human:{payload['lead_key']}", label, payload["note"][:400],
             datetime.now(UTC).isoformat(timespec="seconds")))
        conn.commit()
        return {"ok": True}

    if action == "council":
        from . import council
        from .llm import NotConfigured
        try:
            if payload.get("id"):
                f = next(x for x in review.queue(conn, "pending")
                         if x["id"] == int(payload["id"]))
                rec = council.evaluate(conn, f["payload"], key=f["fingerprint"])
                return {"ok": True, "rec": rec}
            tally = council.evaluate_pending(conn, limit=int(payload.get("limit", 50)))
            return {"ok": True, "tally": tally}
        except NotConfigured as exc:
            return {"ok": False, "error": str(exc)}

    if action == "draft_story":
        from . import newsroom
        oid = newsroom.draft_story(conn, payload["payload"], payload.get("kind", "social_post"))
        row = conn.execute("SELECT body_path FROM outreach WHERE id=?", (oid,)).fetchone()
        return {"ok": True, "id": oid, "body": open(row["body_path"]).read()}

    if action == "outreach_sent":
        outreach.mark_sent(conn, int(payload["id"]),
                           human_confirmed=bool(payload.get("i_sent_this")))
        return {"ok": True}

    if action == "outreach_response":
        outreach.record_response(conn, int(payload["id"]), payload["summary"])
        return {"ok": True}

    if action == "signal":
        conn.execute("INSERT INTO signals (ts, kind, detail, source_url) VALUES (?,?,?,?)",
                     (datetime.now(UTC).isoformat(timespec="seconds"),
                      payload["kind"], payload["detail"], payload.get("url", "")))
        conn.commit()
        return {"ok": True}

    if action == "dossier":
        path = review.dossier(conn, int(payload["id"]))
        return {"ok": True, "path": path, "body": open(path).read()}

    if action == "fs_run":
        from . import firststone
        stories = firststone.run(conn, llm=bool(payload.get("llm")))
        return {"ok": True, "stories": len(stories)}

    if action == "fs_publish":
        # The publisher's chair: this POST is the human's explicit click in the
        # operator desk; the written note is mandatory (enforced downstream too),
        # and the body hash binds the approval to the text the human read.
        from . import firststone
        rec = firststone.publish(payload["slug"], note=payload.get("note", ""),
                                 human_confirmed=bool(payload.get("i_publish_this")),
                                 body_sha256=payload.get("body_sha256"))
        return {"ok": True, "published": rec["slug"]}

    if action == "fs_spike":
        from . import firststone
        firststone.spike(payload["slug"], note=payload.get("note", ""))
        return {"ok": True}

    raise ValueError(f"unknown action {action}")


# ── HTTP plumbing (localhost only) ───────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, _page().encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            conn = _conn()
            try:
                self._send(200, json.dumps(state(conn), default=str).encode(),
                           "application/json")
            finally:
                conn.close()
        elif self.path.startswith("/api/company"):
            from urllib.parse import parse_qs, urlparse
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip()
            conn = _conn()                       # read-only: company-scan never writes
            try:
                from . import investigate
                out = investigate.company_record(conn, q) if q else {"company": "", "holders": []}
                self._send(200, json.dumps(out, default=str).encode(), "application/json")
            finally:
                conn.close()
        else:
            self._send(404, b"not found", "text/plain")

    def _origin_ok(self) -> bool:
        """CSRF guard: browsers attach an Origin header to cross-site POSTs.
        Only the workbench's own origin (or non-browser clients sending no
        Origin) may write — without this, any webpage open in the operator's
        browser could forge ledger decisions via fetch() to localhost."""
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"http://127.0.0.1:{self.server.server_address[1]}",
                          f"http://localhost:{self.server.server_address[1]}")

    def do_POST(self):
        if not self.path.startswith("/api/act/"):
            self._send(404, b"not found", "text/plain")
            return
        if not self._origin_ok():
            self._send(403, json.dumps({"ok": False, "error":
                       "cross-origin request rejected (CSRF origin check)"}).encode(),
                       "application/json")
            return
        action = self.path.rsplit("/", 1)[-1]
        conn = _conn(write=True)
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            out = act(conn, action, payload)
            self._send(200, json.dumps(out, default=str).encode(), "application/json")
        except Exception as exc:
            self._send(400, json.dumps({"ok": False, "error": str(exc)}).encode(),
                       "application/json")
        finally:
            conn.close()


def serve(port: int = 8010) -> ThreadingHTTPServer:
    _conn(write=True).close()  # one registry sync at startup; reads never write
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ── the page ─────────────────────────────────────────────────────────────────

def _page() -> str:
    from .site import _CSS
    return """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Workbench — Glasshouse</title><style>""" + _CSS + """
.tabs{display:flex;gap:.4rem;margin:1.4rem 0 .6rem;flex-wrap:wrap}
.tabs button{font:700 .78rem var(--mono);letter-spacing:.08em;text-transform:uppercase;
  padding:.45rem .9rem;border:1px solid var(--edge);border-radius:999px;cursor:pointer;
  background:var(--panel);color:var(--muted)}
.tabs button.on{background:var(--accent);border-color:var(--accent);color:#fff}
.tabs button .n{font-weight:400;opacity:.8}
textarea,input[type=text]{width:100%;padding:.55rem .8rem;border:1px solid var(--edge);
  border-radius:8px;background:var(--panel);color:var(--ink);font:400 .92rem var(--sans)}
.actions{display:flex;gap:.5rem;margin-top:.6rem;flex-wrap:wrap;align-items:center}
.actions button{font:700 .78rem var(--mono);letter-spacing:.06em;padding:.5rem .9rem;
  border-radius:8px;border:1px solid var(--edge);cursor:pointer;background:var(--panel);
  color:var(--ink)}
button.approve{background:var(--accent);border-color:var(--accent);color:#fff}
button.reject{background:var(--against);border-color:var(--against);color:#fff}
button.ghost{background:none}
.ok-note{font:400 .8rem var(--mono);color:var(--for)}
.err{font:400 .8rem var(--mono);color:var(--against)}
pre.dossier{font:400 .74rem/1.55 var(--mono);white-space:pre-wrap;background:var(--bg);
  border:1px solid var(--edge);border-radius:8px;padding:1rem;max-height:24rem;overflow:auto}
.empty{color:var(--muted);font-family:var(--sans);padding:2rem 0}
label.chk{display:flex;gap:.5rem;align-items:center;font:400 .85rem var(--sans);color:var(--muted)}
table.heat{border-collapse:collapse;margin:.6rem 0 1rem}
table.heat th{font:700 .66rem var(--mono);letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);padding:.3rem .45rem;text-align:center;vertical-align:bottom}
table.heat td{border:1px solid var(--edge);text-align:center;padding:.55rem .65rem;min-width:4.6rem}
table.heat td.rowname{text-align:left;font:600 .84rem var(--sans);color:var(--ink);
  white-space:nowrap;border:none;padding-right:.9rem}
table.heat td.cell{cursor:pointer;font:700 .82rem var(--mono)}
table.heat td.cell:hover{outline:2px solid var(--accent);outline-offset:-2px}
table.heat td.nocommit{color:var(--muted);font-family:var(--mono)}
table.heat td.blank{background:repeating-linear-gradient(45deg,transparent,transparent 5px,var(--bg) 5px,var(--bg) 6px)}
h4.evh{font:700 .78rem var(--mono);letter-spacing:.04em;text-transform:uppercase;margin:.9rem 0 .3rem;color:var(--muted)}

/* ── First Stone: the newsroom has its own world (amber ink) ─────────────── */
.fsroom{--fs:#a5670b;--fsbg:#fbf4e6;--fsedge:#e6d3ab}
@media (prefers-color-scheme:dark){.fsroom{--fs:#e0a021;--fsbg:#2a2008;--fsedge:#4a3a12}}
.fs-mast{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;border:1px solid var(--fsedge);
  border-left:5px solid var(--fs);border-radius:12px;background:var(--fsbg);padding:1rem 1.3rem;margin:.4rem 0 1rem}
.fs-mast .brand{font:700 1.1rem var(--display);letter-spacing:.28em;text-transform:uppercase;color:var(--ink)}
.fs-mast .brand b{color:var(--fs)}
.fs-mast .ed{font:400 .86rem var(--sans);color:var(--muted)}
.fs-mast .ed b{color:var(--fs);font-weight:700}
.fs-mast .grow{flex:1}
.fs-run{font:700 .74rem var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:.55rem 1rem;
  border-radius:8px;border:1px solid var(--fs);background:var(--fs);color:#fff;cursor:pointer}
.fs-run:hover{filter:brightness(1.08)} .fs-run:disabled{opacity:.6;cursor:progress}
.fs-tag{font:700 .68rem var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:1.3rem 0 .5rem}
/* correspondents — the floor */
.fs-floor{display:grid;grid-template-columns:repeat(auto-fill,minmax(13rem,1fr));gap:.7rem}
.fs-corr{display:flex;gap:.7rem;align-items:center;border:1px solid var(--edge);border-radius:10px;
  padding:.6rem .8rem;background:var(--panel)}
.fs-corr .av{width:2.2rem;height:2.2rem;border-radius:50%;background:var(--fsbg);color:var(--fs);
  border:1.5px solid var(--fs);display:grid;place-items:center;font:700 .82rem var(--mono);flex-shrink:0}
.fs-corr .nm{font:600 .92rem var(--sans);color:var(--ink);line-height:1.2}
.fs-corr .be{font:700 .62rem var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--fs)}
.fs-corr .ct{margin-left:auto;font:700 .9rem var(--mono);color:var(--muted)}
/* the production line */
.fs-pipe{display:flex;align-items:center;gap:.2rem;flex-wrap:wrap;border:1px dashed var(--fsedge);
  border-radius:10px;padding:.7rem .9rem;background:var(--fsbg)}
.fs-pipe .step{font:700 .64rem var(--mono);letter-spacing:.04em;text-transform:uppercase;
  padding:.3rem .55rem;border-radius:6px;color:var(--muted);background:var(--panel);border:1px solid var(--edge)}
.fs-pipe .step.hum{color:var(--fs);border-color:var(--fs);font-weight:800}
.fs-pipe .arw{color:var(--fsedge);font-size:.9rem}
/* story cards */
.fs-story{border:1px solid var(--edge);border-radius:12px;background:var(--panel);
  padding:1.1rem 1.3rem;margin:.8rem 0;box-shadow:var(--shadow)}
.fs-story .kick{font:700 .68rem var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--fs);margin:0}
.fs-story h3{font:600 1.28rem/1.15 var(--serif);margin:.25rem 0 .3rem;color:var(--ink)}
.fs-story .byl{font:400 .84rem var(--sans);color:var(--muted);margin:0 0 .5rem}
.fs-story .byl b{color:var(--ink)}
.fs-story .sf{font:400 .95rem/1.5 var(--serif);color:var(--ink);margin:.2rem 0 .7rem}
/* the desk-stamp trail — the agentic workflow made visible */
.fs-trail{display:flex;gap:.3rem;flex-wrap:wrap;align-items:center;margin:.5rem 0}
.fs-stamp{font:700 .62rem var(--mono);letter-spacing:.03em;text-transform:uppercase;padding:.2rem .45rem;
  border-radius:4px;border:1.5px solid var(--fsedge);color:var(--muted);transform:rotate(-1.5deg)}
.fs-stamp.ok{border-color:var(--for);color:var(--for)}
.fs-stamp.spike{border-color:var(--against);color:var(--against)}
.fs-stamp.pub{border-color:var(--fs);color:var(--fs);background:var(--fsbg)}
.fs-pill{display:inline-block;font:700 .64rem var(--mono);letter-spacing:.1em;text-transform:uppercase;
  padding:.25rem .6rem;border-radius:999px}
.fs-pill.await{background:var(--fsbg);color:var(--fs);border:1px solid var(--fs)}
.fs-pill.pubd{background:color-mix(in srgb,var(--for) 15%,transparent);color:var(--for);border:1px solid var(--for)}
.fs-pill.spkd{background:color-mix(in srgb,var(--against) 15%,transparent);color:var(--against);border:1px solid var(--against)}
.fs-open{font:700 .72rem var(--mono);letter-spacing:.04em;padding:.5rem .9rem;border-radius:8px;
  border:1px solid var(--fs);background:none;color:var(--fs);cursor:pointer;margin-top:.3rem}
.fs-open:hover{background:var(--fsbg)}
/* reading view */
.fs-read{border:1px solid var(--fsedge);border-radius:12px;background:var(--panel);padding:0 0 1.5rem;overflow:hidden}
.fs-read .top{display:flex;align-items:center;gap:1rem;padding:.8rem 1.3rem;background:var(--fsbg);
  border-bottom:1px solid var(--fsedge);position:sticky;top:0}
.fs-back{font:700 .72rem var(--mono);border:1px solid var(--fsedge);background:var(--panel);color:var(--ink);
  border-radius:8px;padding:.4rem .8rem;cursor:pointer}
.fs-art{max-width:44rem;margin:1.4rem auto 0;padding:0 1.6rem;font:400 1.02rem/1.65 var(--serif);color:var(--ink)}
.fs-art h1{font:600 2rem/1.15 var(--serif);text-transform:none;letter-spacing:0;margin:.4rem 0 .8rem}
.fs-art h2{font:700 .8rem var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--fs);
  margin:1.6rem 0 .5rem;border:none}
.fs-art blockquote{border-left:3px solid var(--fs);margin:.8rem 0;padding:.2rem 0 .2rem 1.1rem;
  font-style:italic;color:var(--ink)}
.fs-art ul{padding-left:1.1rem} .fs-art li{margin:.35rem 0}
.fs-art a{color:var(--accent)} .fs-art code{font:400 .82rem var(--mono);color:var(--muted)}
.fs-decide{max-width:44rem;margin:1.4rem auto 0;padding:1.1rem 1.6rem;border-top:2px solid var(--fs)}
</style></head><body>
<nav><div class=wrap><span class=wordmark>GLASS<em>HOUSE</em></span>
<a href='#' class=on>Workbench</a><a href='http://localhost:8000' target=_blank>Public site</a></div></nav>
<div class=wrap>
<h1>The desk</h1>
<p class=lede>Everything the charter reserves for a human, in one place.
Decisions write to the ledger through the same gates as the CLI; lead labels
also grow the eval gold set.</p>
<div class=tabs id=tabs></div>
<div id=main></div>
</div>
<script>
let S=null, tab='investigate';
const $=s=>document.querySelector(s);
const e=t=>{const d=document.createElement('div');d.textContent=t??'';return d.innerHTML};

async function load(){S=await (await fetch('/api/state')).json();render()}
async function post(action,payload,el){
  const r=await (await fetch('/api/act/'+action,{method:'POST',body:JSON.stringify(payload)})).json();
  if(!r.ok){el&&(el.innerHTML="<span class=err>"+e(r.error)+"</span>");return null}
  return r}

function tabs(){
  const invN=S.investigate?S.investigate.institutions.filter(i=>
    Object.values(i.cells).some(c=>c.committed&&c.n)).length:0;
  const t=[['investigate','Investigate',invN],
    ['company','Company',''],
    ['firststone','First Stone',(((S.firststone||{}).run||{}).stories||[]).filter(s=>s.state==='awaiting_publisher').length],
    ['drafts','Drafts',((S.agent_drafts||{}).briefs||[]).length],
    ['newsroom','Newsroom',(S.newsroom||[]).length],
    ['review','Review',S.review.length],['leads','Leads',S.leads.length],
    ['outreach','Outreach',S.outreach.filter(o=>o.status!=='declined').length],
    ['signals','Signals',S.signals.length],['doctor','Doctor',
      (S.doctor.checks||[]).filter(c=>!c.ok).length],
    ['pipeline','Pipeline',(S.pipeline||[]).filter(p=>!p.ok).length]];
  $('#tabs').innerHTML=t.map(([k,l,n])=>
    `<button class='${k===tab?'on':''}' onclick='tab="${k}";render()'>${l} <span class=n>${n}</span></button>`).join('')}

function render(){tabs();({investigate,company,firststone,drafts,newsroom,review,leads,outreach,signals,doctor,pipeline})[tab]()}

function company(){
  $('#main').innerHTML=`<p class=secnote>Start from a <b>company</b>: who holds it (13-F value) and how
   they voted there. Type a name and search — AGAINST votes are theme-tagged; everything is a lead to verify.</p>
   <div class=actions>
    <input type=text id=cq placeholder='e.g. Exxon Mobil, Microsoft, Boeing' style='max-width:24rem'
     onkeydown='if(event.key==="Enter")runCompany()'>
    <button class=approve onclick='runCompany()'>Search</button><span class=st></span></div>
   <div id=cres></div>`;
  const last=$('#cq'); if(last) last.focus();
}
async function runCompany(){
  const q=$('#cq').value.trim(), st=$('.actions .st'), res=$('#cres');
  if(!q){st.innerHTML="<span class=err>type a company</span>";return}
  st.innerHTML="<span class=meta>searching…</span>"; res.innerHTML="";
  const r=await (await fetch('/api/company?q='+encodeURIComponent(q))).json();
  st.innerHTML="";
  const rows=(r.holders||[]).filter(h=>h.held_usd||h.votes_against||h.votes_for);
  if(!rows.length){res.innerHTML="<p class=empty>No holdings or votes found for “"+e(q)+"”.</p>";return}
  window._co=rows;
  res.innerHTML=`<h3 style='margin-top:1rem'>${e(r.company)} — who holds it & how they voted there</h3>
   <table class=heat><thead><tr><th></th><th>held (13-F)</th><th>for</th><th>against</th>
    <th style='text-align:left'>notable AGAINST vote</th></tr></thead><tbody>`+
   rows.map((h,i)=>`<tr>
     <td class=rowname>${e(h.institution_name)}</td>
     <td style='font-family:var(--mono)'>${h.held_usd?'$'+(h.held_usd/1e9).toFixed(1)+'B':'—'}</td>
     <td>${h.votes_for}</td>
     <td>${h.votes_against?`<a href='#' onclick='coDrill(${i});return false' style='color:var(--against);font-weight:700'>${h.votes_against}</a>`:'0'}</td>
     <td class=meta style='text-align:left'>${h.examples.length?e(h.examples[0].vote_description.slice(0,52)):''}</td></tr>`).join('')+
   `</tbody></table><p class=meta>Click an AGAINST count for the cited votes.</p><div id=codrill></div>`;
}
function coDrill(i){
  const h=window._co[i], d=$('#codrill');
  d.innerHTML=`<div class='card claim'><span class=ribbon>lead — verify before publishing</span>
   <h3>${e(h.institution_name)} — AGAINST votes here</h3>`+
   (h.examples.map(x=>`<div class=stat><span>${e(x.meeting_date)} ·
     ${Math.round(Number(x.shares_voted)).toLocaleString('en-US')} sh ·
     <span class=meta>${(x.themes||[]).map(e).join(', ')}</span><br>
     <span class=meta>“${e(x.vote_description)}” — N-PX
     <a href='${e(x.source_url||"#")}' target=_blank>${e(x.accession)}</a></span></span></div>`).join('')
     ||"<p class=meta>no cited examples</p>")+`</div>`;
  d.scrollIntoView({behavior:'smooth',block:'nearest'});
}

// The newsroom has two views: the FLOOR (list) and the READING room (one story).
let fsReading=null;   // slug being read, or null for the floor
const _FS_DESKS=[['assignment','Assignment'],['records','Records'],['ledger','Ledger'],
  ['copy','Copy'],['standards','Standards'],['editor','Editor'],['publisher','You']];
const _FS_PILL={awaiting_publisher:['await','awaiting you'],published:['pubd','published'],
  spiked:['spkd','spiked'],assigned:['await','in production']};

function firststone(){
  const F=S.firststone||{}, R=F.run;
  if(fsReading && R){ const s=R.stories.find(x=>x.slug===fsReading); if(s){fsRead(s);return} fsReading=null; }
  fsFloor();
}

function fsFloor(){
  const F=S.firststone||{}, R=F.run, M=F.masthead||{};
  const eic=M.editor||{}, corrs=M.correspondents||[];
  const cnt=st=>R?R.stories.filter(s=>s.state===st).length:0;
  const load=corrs.map(c=>[c, R?R.stories.filter(s=>s.correspondent_id===c.id).length:0]);
  const initials=n=>n.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  let h=`<div class=fsroom>
   <div class=fs-mast>
     <span class=brand>FIRST<b>·</b>STONE</span>
     <span class=ed>Editor-in-Chief <b>${e(eic.name||'')}</b> · automated newsroom on the registry</span>
     <span class=grow></span>
     <button class=fs-run onclick='fsRun(this)'>▷ Run edition cycle</button>
   </div>
   <p class=meta style='margin:-.4rem 0 .2rem'>${F.published.length} published · ${cnt('awaiting_publisher')} awaiting your desk · ${cnt('spiked')} spiked${R?' · edition '+e((R.generated||'').slice(0,10)):''} <span class=st></span></p>
   <p class=fs-tag>The floor — correspondents on the beats</p>
   <div class=fs-floor>`
   +load.map(([c,n])=>`<div class=fs-corr title='${e(c.bio||"")}'>
       <span class=av>${e(initials(c.name))}</span>
       <span><span class=nm>${e(c.name)}</span><br><span class=be>${e(c.beat)}</span></span>
       <span class=ct>${n}</span></div>`).join('')
   +`</div>
   <p class=fs-tag>The production line — every story passes these desks; you are the last chair</p>
   <div class=fs-pipe>`
   +_FS_DESKS.map(([k,l],i)=>`<span class='step${k==='publisher'?' hum':''}'>${e(l)}</span>`
       +(i<_FS_DESKS.length-1?`<span class=arw>→</span>`:``)).join('')
   +`</div>`;
  if(!R||!R.stories.length){$('#main').innerHTML=h+"<p class=empty style='padding:1.5rem 0'>No edition on file. Press <b>Run edition cycle</b> — the correspondents pitch, the desks check, and stories come to your chair.</p></div>";return}
  h+=`<p class=fs-tag>The edition — ${R.stories.length} stories filed</p>`;
  h+=R.stories.map(s=>{
    const [pk,pl]=_FS_PILL[s.state]||['await',s.state];
    const trail=_FS_DESKS.slice(0,6).map(([k,l])=>{
      const st=(s.trail||[]).find(t=>t.desk===k);
      const cls=!st?'':st.verdict==='spike'?'spike':'ok';
      return `<span class='fs-stamp ${cls}' title='${st?e(st.note):"pending"}'>${e(l)}${st?(st.verdict==='spike'?' ✗':' ✓'):''}</span>`;
    }).join('');
    return `<div class=fs-story>
       <span class='fs-pill ${pk}'>${e(pl)}</span>
       <p class=kick style='margin-top:.5rem'>${e(s.beat||s.theme)}</p>
       <h3>${e(s.headline||s.slug)}</h3>
       <p class=byl>By <b>${e(s.byline||'the News Desk')}</b>, automated correspondent · ${Math.round(s.against_rate*100)}% against on ${s.n_votes} votes · newsworthiness ${e(s.score)}</p>
       <p class=sf>${e(s.standfirst||'')}</p>
       <div class=fs-trail>${trail}</div>
       <button class=fs-open onclick='fsReading="${e(s.slug)}";render()'>${s.state==='awaiting_publisher'?'Read &amp; decide →':'Read the file →'}</button>
     </div>`;}).join('');
  $('#main').innerHTML=h+`</div>`;
}

function fsRead(s){
  const decide = s.state==='awaiting_publisher' ? `
     <div class=fs-decide>
       <h4 class=evh>Your desk — the publisher's chair</h4>
       <p class=meta>Publishing is your act, not the desks'. Verify the policy quote and the cited votes against the primary sources, then sign a note.</p>
       <textarea id=fsnote rows=2 placeholder="Publisher's note — what you verified (required)"></textarea>
       <label class=chk style='margin:.5rem 0'><input type=checkbox id=fsok> I verified the policy quote and the cited votes myself — publish under the First Stone masthead</label>
       <div class=actions>
         <button class=fs-run onclick='fsPublish(this)'>Publish</button>
         <button class=reject onclick='fsSpike(this)'>Spike</button><span class=st></span>
       </div>
     </div>` :
     `<div class=fs-decide><p class=meta>This story is <b>${e(s.state.replace('_',' '))}</b>. ${(s.trail||[]).filter(t=>t.desk==='publisher').map(t=>e(t.note)).join(' ')}</p></div>`;
  $('#main').innerHTML=`<div class=fsroom><div class=fs-read>
     <div class=top><button class=fs-back onclick='fsReading=null;render()'>← The floor</button>
       <span class='fs-pill ${(_FS_PILL[s.state]||["await"])[0]}'>${e((_FS_PILL[s.state]||["","in production"])[1])}</span>
       <span class=meta>${e(s.beat||"")} · by ${e(s.byline||"")}</span></div>
     <div class=fs-art>${s.body_html||('<pre>'+e(s.body||'')+'</pre>')}</div>
     ${decide}
   </div></div>`;
  window.scrollTo(0,0);
}

async function fsRun(btn){
  btn.disabled=true;btn.textContent='Desks working…';
  const st=document.querySelector('.st');
  const r=await post('fs_run',{},st);
  if(r){fsReading=null;await load();} else {btn.disabled=false;btn.textContent='▷ Run edition cycle';} }
async function fsPublish(btn){
  const s=S.firststone.run.stories.find(x=>x.slug===fsReading);
  const note=$('#fsnote').value.trim(), ok=$('#fsok').checked, st=btn.parentElement.querySelector('.st');
  if(!note){st.innerHTML="<span class=err>the publisher's note is required</span>";return}
  if(!ok){st.innerHTML="<span class=err>tick the confirmation — publishing is your act</span>";return}
  const r=await post('fs_publish',{slug:s.slug,note,i_publish_this:ok,body_sha256:s.body_sha256},st);
  if(r){fsReading=null;await load();} }
async function fsSpike(btn){
  const s=S.firststone.run.stories.find(x=>x.slug===fsReading);
  const note=$('#fsnote').value.trim(), st=btn.parentElement.querySelector('.st');
  if(!note){st.innerHTML="<span class=err>a kill needs a written reason too</span>";return}
  const r=await post('fs_spike',{slug:s.slug,note},st);
  if(r){fsReading=null;await load();} }

function drafts(){
  const D=S.agent_drafts;
  if(!D||!(D.briefs||[]).length){$('#main').innerHTML="<p class=empty>No agent drafts yet. Run "+
    "<code>glasshouse agent run</code> — it investigates the dataset and writes cited story leads here.</p>";return}
  let h=`<p class=secnote>The findings agent investigated the dataset and drafted these cited story
   <b>leads</b>, ranked by a transparent score (gap × vote-count × manager AUM). Generated ${e(D.generated)}.
   Every draft is an <b>unverified lead</b> — verify each primary source and promote via Review before
   anything is published. Nothing here is sent or published.</p>`;
  h+=D.briefs.map((b,i)=>`<div class='card claim'>
     <span class=ribbon>agent draft — unverified lead</span>
     <div style='display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap'>
      <span class=meta>#${i+1} · score ${e(b.score)} · ${Math.round(b.against_rate*100)}% against · ${e(b.theme)}</span></div>
     <h3 style='margin:.2rem 0'>${e(b.headline)}</h3>
     <p class=meta>${e(b.standfirst)}</p>
     <details><summary class=meta>full cited draft + evidence</summary>
      <pre class=dossier>${e(b.body)}</pre></details></div>`).join('');
  $('#main').innerHTML=h;
}

const _maxRate=i=>Math.max(0,...Object.values(i.cells).filter(c=>c.committed&&c.n).map(c=>c.rate));
function investigate(){
  const M=S.investigate;
  if(!M){$('#main').innerHTML="<p class=empty>The hypocrisy matrix isn't built yet. Run "+
    "<code>glasshouse investigate matrix --cache</code>, then reload this page.</p>";return}
  const themes=M.themes;
  const insts=M.institutions.filter(i=>Object.values(i.cells).some(c=>c.committed&&c.n))
    .sort((a,b)=>_maxRate(b)-_maxRate(a));
  window._inv=insts;
  if(!insts.length){$('#main').innerHTML="<p class=empty>No committed-vs-voted cells yet.</p>";return}
  let h=`<p class=secnote>Each cell = a manager's <b>against-rate</b> on shareholder proposals
   advancing a theme it <b>publicly commits to</b> — what it SAYS × what it DOES. Redder = says one
   thing, votes the other. Anti-theme proposals and unvalidated legacy votes are excluded.
   Built ${e(M.generated)}. <b>Click any cell</b> for the commitment quote and the specific cited votes.</p>`;
  h+="<table class=heat><thead><tr><th></th>"+themes.map(t=>`<th>${e(t)}</th>`).join('')+"</tr></thead><tbody>";
  insts.forEach((i,ri)=>{
    h+=`<tr><td class=rowname>${e(i.name)}</td>`+themes.map(t=>{
      const c=i.cells[t];
      if(!c) return "<td class=blank></td>";
      if(!c.committed) return `<td class=nocommit title='${c.against}/${c.n} against — but no commitment on this theme'>·</td>`;
      const al=(0.12+0.88*c.rate).toFixed(2);
      const col=c.rate>0.5?'#fff':'var(--ink)';
      const star=c.low_confidence?' *':'';
      return `<td class=cell style='background:rgba(176,48,42,${al});color:${col}' `+
        `onclick='drill(${ri},"${t}")'>${Math.round(c.rate*100)}%${star}</td>`}).join('')+"</tr>";
  });
  h+="</tbody></table><div id=drill></div>"+
   "<p class=meta>· = votes on the theme but no commitment (no say-vs-do tension). "+
   "blank = nothing. * = small sample (&lt;5 votes) — treat with caution.</p>";
  $('#main').innerHTML=h;
}

function drill(ri,t){
  const i=window._inv[ri], c=i.cells[t], d=$('#drill');
  const ex=(c.examples||[]).map(x=>`<div class=stat><span>${e(x.meeting_date)} ·
     <b>${e(x.issuer_name)}</b> · ${Math.round(Number(x.shares_voted)).toLocaleString('en-US')} sh<br>
     <span class=meta>“${e(x.vote_description)}” — N-PX ${e(x.accession)}</span></span></div>`).join('')
     ||"<p class=meta>no cited examples</p>";
  const yrs=Object.keys(c.trend||{}).sort();
  const trend=yrs.length>1?`<div class=cite style='margin-top:.4rem'><b>trend</b> (against-rate by year): `+
     yrs.map(y=>`${y} <b style='color:var(--against)'>${Math.round(c.trend[y].rate*100)}%</b>`).join(' · ')+`</div>`:'';
  const hw=c.hw?`<div class=cite style='margin-top:.3rem'><b>skin-in-the-game</b>: votes against
     <b style='color:var(--against)'>${Math.round(c.hw.large_rate*100)}%</b> at its LARGEST positions
     vs ${Math.round(c.hw.small_rate*100)}% at its smallest
     (${c.hw.delta>0?'+':''}${Math.round(c.hw.delta*100)} pts${c.hw.delta>0?' worse where it holds more':''})</div>`:'';
  d.innerHTML=`<div class='card claim'><span class=ribbon>lead — verify before publishing</span>
   <h3>${e(i.name)} · ${e(t)}</h3>
   <div class=grid2>
    <div class='saydid say'><div class=tag>What it says</div>
     <blockquote>“${e(c.quote||'—')}”</blockquote>
     <div class=cite>${e(c.doc_label||'')} @ ${e(c.doc_version||'')} ·
      <a href='${e(c.doc_url||'#')}' target=_blank>source</a></div></div>
    <div class='saydid did'><div class=tag>What it did</div>
     <blockquote>Voted <b style='color:var(--against)'>AGAINST ${c.against}</b> of ${c.for+c.against}
      (${Math.round(c.rate*100)}%) proposals advancing ${e(t)}</blockquote>
     <div class=cite>FOR ${c.for} · AGAINST ${c.against} · ABSTAIN ${c.abstain}${c.low_confidence?' · small sample':''}</div>
     ${trend}${hw}</div>
   </div>
   <h4 class=evh>Top AGAINST votes — the evidence</h4>${ex}
   <p class=meta style='margin-top:.5rem'>Leads with citations: confirm the proposal text and
    polarity against the primary source before publishing (precision over recall).</p></div>`;
  d.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function newsroom(){
  const q=S.newsroom||[];
  if(!q.length){$('#main').innerHTML="<p class=empty>No stories yet — approve a candidate in Review, or run scan-events.</p>";return}
  $('#main').innerHTML=`<p class=secnote>What's publishable now, ranked by newsworthiness with the
   analysis behind each. The newsroom drafts; <b>only you send</b>. Findings float to the top;
   candidates need review first; fresh enforcement triggers are pegged to the news cycle.</p>`+
   q.map((s,i)=>{
    const tag={finding:'var(--for)',candidate:'var(--hold)',event:'var(--accent)'}[s.kind]||'var(--muted)';
    const draftBtns=s.draftable?`
      <button class=approve onclick='draftStory(${i},"social_post",this)'>Draft social post</button>
      <button onclick='draftStory(${i},"pitch",this)'>Draft pitch</button>
      <button onclick='draftStory(${i},"inquiry",this)'>Draft inquiry</button>`
      :`<span class=meta>${s.next_step==='review'?'→ review in the Review tab before drafting':s.next_step==='verify'?'→ verify against primary source (alert pack on disk)':''}</span>`;
    return `<div class=card>
     <div style='display:flex;gap:.6rem;align-items:center;margin-bottom:.3rem'>
      <span class=ribbon style='color:${tag};border-color:${tag};transform:none'>${e(s.kind)}</span>
      <span class=meta>score ${s.score} · ${e(s.status)}</span></div>
     <h3 style='margin:.2rem 0'>${e(s.headline)}</h3>
     <div class=meta>${s.why.map(w=>'· '+e(w)).join('<br>')}</div>
     ${s.drafted.length?`<div class=meta style='margin-top:.4rem'>drafted: ${s.drafted.map(e).join(', ')}</div>`:''}
     <div class=actions>${draftBtns}<span class=st></span></div>
     <div class=dz></div></div>`}).join('')}

async function draftStory(i,kind,btn){
  const s=S.newsroom[i],card=btn.closest('.card'),st=card.querySelector('.st'),dz=card.querySelector('.dz');
  const r=await post('draft_story',{payload:s.payload,kind},st);
  if(r){st.innerHTML="<span class=ok-note>drafted "+kind+" → Outreach tab (NOT sent)</span>";
    dz.innerHTML="<pre class=dossier>"+e(r.body)+"</pre>"}}

function pipeline(){
  const q=S.pipeline||[];
  $('#main').innerHTML=`<p class=secnote>Every stage of the pipeline, what it has produced, and
   whether it looks alive. This is the verifiable-it's-running view.</p>`+
   q.map(p=>`<div class=stat><span>${p.ok?'·':'⚠'} <b style='font-family:var(--mono)'>${e(p.stage)}</b>
     — ${e(p.detail)}${p.note?` <span style='color:var(--hold)'>(${e(p.note)})</span>`:''}</span></div>`).join('')}

const CV={finding:'var(--for)',reject:'var(--against)',needs_human:'var(--hold)'};
function councilBox(c){
  if(!c) return "<div class=meta>AI council: not yet run.</div>";
  const col=CV[c.verdict]||'var(--muted)';
  const notes=c.notes?Object.entries(c.notes).map(([k,v])=>`<b>${e(k)}:</b> ${e(v)}`).join('<br>'):'';
  return `<div class=card style='border-color:${col};margin:.4rem 0'>
   <div style='display:flex;gap:.6rem;align-items:center'>
    <span class=ribbon style='color:${col};border-color:${col};transform:none'>AI council: ${e(c.verdict)}</span>
    <span class=meta>confidence ${e(c.confidence)} · advisory — your decision stands</span></div>
   <p class=meta style='margin:.4rem 0'>${e(c.rationale||'')}</p>
   <details><summary class=meta>reviewer passes</summary><div class=meta style='margin-top:.4rem'>${notes}</div></details>
  </div>`}

function review(){
  const q=S.review;
  if(!q.length){$('#main').innerHTML=`<p class=empty>Review queue is empty. ${S.review_stats.approved||0} approved, ${S.review_stats.rejected||0} rejected so far — run <code>glasshouse review sync</code> after new ingests.</p>`;return}
  const nrec=q.filter(f=>f.council).length;
  $('#main').innerHTML=`<div class=card style='box-shadow:none'>
    <div class=actions><button class=approve onclick='runCouncil(this)'>Run AI council on the queue</button>
    <span class=meta>${nrec}/${q.length} evaluated · the council does the legwork; you ratify. Nothing publishes without your click.</span><span class=st></span></div></div>`+
    q.map(f=>{const p=f.payload;return `
  <div class='card claim'><span class=ribbon>quarantined — your call</span>
   <h3>#${f.id} · ${e(p.institution_id)} · ${e(p.theme)} · ${e(p.issuer_name)}</h3>
   ${councilBox(f.council)}
   <div class=grid2>
    <div class='saydid say'><div class=tag>What it says</div>
     <blockquote>“${e(p.commitment_quote)}”</blockquote>
     <div class=cite>${e(p.doc_label)} @ ${e(p.doc_version)} · sha ${e(p.doc_sha256.slice(0,12))}…</div></div>
    <div class='saydid did'><div class=tag>What it did</div>
     <blockquote>Voted <b style='color:var(--against)'>${e(p.how_voted)}</b> — ${Math.round(Number(p.shares_voted)).toLocaleString('en-US')} sh</blockquote>
     <div class=cite>“${e(p.vote_description)}” — ${e(p.meeting_date)} · N-PX ${e(p.accession)}</div></div>
   </div>
   <div class=actions>
    <button class=ghost onclick='dossier(${f.id},this)'>Open dossier</button>
    <button class=ghost onclick='councilOne(${f.id},this)'>Run council on this</button>
   </div><div class=dz></div>
   <textarea rows=2 placeholder='Reviewer note — required. Why does this hold up, or why not?'></textarea>
   <div class=actions>
    <button class=approve onclick='decide(this,${f.id},"approved")'>Approve as finding</button>
    <button class=reject onclick='decide(this,${f.id},"rejected")'>Reject</button>
    <span class=st></span></div></div>`}).join('')}

async function runCouncil(btn){
  const st=btn.parentElement.querySelector('.st');
  st.innerHTML="<span class=meta>running… (one batch)</span>";
  const r=await post('council',{limit:50},st);
  if(r){st.innerHTML="<span class=ok-note>tiers: "+JSON.stringify(r.tally)+"</span>";setTimeout(load,800)}}

async function councilOne(id,btn){
  const st=btn.closest('.card').querySelector('.st');
  st.innerHTML="<span class=meta>running…</span>";
  if(await post('council',{id},st)) setTimeout(load,500)}

async function decide(btn,id,decision){
  const card=btn.closest('.card'), note=card.querySelector('textarea').value.trim(),
        st=card.querySelector('.st');
  if(!note){st.innerHTML="<span class=err>note required — every decision is documented</span>";return}
  if(await post('review',{id,decision,note},st)){card.style.opacity=.35;
    st.innerHTML="<span class=ok-note>recorded: "+decision+"</span>";setTimeout(load,600)}}

async function dossier(id,btn){
  const card=btn.closest('.card'), dz=card.querySelector('.dz');
  const r=await post('dossier',{id},dz);
  if(r) dz.innerHTML="<pre class=dossier>"+e(r.body)+"</pre>"}

function leads(){
  const q=S.leads;
  if(!q.length){$('#main').innerHTML=`<p class=empty>No unlabeled leads. ${S.gold_labels} human labels recorded — they feed the eval gold set.</p>`;return}
  $('#main').innerHTML=`<p class=secnote>Same legal entity, or not? Your label is saved as
   evidence (data/labels/) and grows the gold set that gates the LLM triage tier.
   ${S.gold_labels} labels so far.</p>`+q.map((l,i)=>`
  <div class=card><h3>${e(l.kind)} lead</h3>
   <div class=grid2>
    <div class='saydid say'><div class=tag>Record A</div><blockquote>${e(l.a.name)}</blockquote>
     <div class=cite>${e(l.a.context)}</div></div>
    <div class='saydid did'><div class=tag>Record B</div><blockquote>${e(l.b.name)}</blockquote>
     <div class=cite>${e(l.b.context)}</div></div></div>
   <p class=meta>${e(l.detail)}</p>
   <textarea rows=1 placeholder='Why? (required — e.g. "same CIK", "subsidiary not parent", "different country")'></textarea>
   <div class=actions>
    <button class=approve onclick='lead(this,${i},"match")'>Same entity</button>
    <button class=reject onclick='lead(this,${i},"no_match")'>Different</button>
    <button onclick='lead(this,${i},"unsure")'>Unsure</button><span class=st></span></div></div>`).join('')}

async function lead(btn,i,label){
  const l=S.leads[i],card=btn.closest('.card'),note=card.querySelector('textarea').value.trim(),
        st=card.querySelector('.st');
  if(!note){st.innerHTML="<span class=err>note required</span>";return}
  if(await post('lead',{lead_key:l.lead_key,label,note,a:l.a,b:l.b},st)){
    card.style.opacity=.35;st.innerHTML="<span class=ok-note>labeled "+label+"</span>";setTimeout(load,600)}}

function outreach(){
  const q=S.outreach;
  if(!q.length){$('#main').innerHTML="<p class=empty>No outreach drafts yet — <code>glasshouse outreach draft</code>.</p>";return}
  $('#main').innerHTML=q.map(o=>`
  <div class=card><h3>#${o.id} [${e(o.status)}] ${e(o.kind)} — ${e(o.institution_id)}</h3>
   <p class=meta>${e(o.subject)} · sent: ${e(o.sent_date||'—')} · response: ${e(o.response_date||'—')}</p>
   <p class=cite>${e(o.body_path)}</p>
   ${o.status==='draft'?`<label class=chk><input type=checkbox> I sent this myself, outside the tool</label>
   <div class=actions><button class=approve onclick='sent(this,${o.id})'>Mark sent</button><span class=st></span></div>`:''}
   ${o.status==='sent'&&!o.response_date?`<textarea rows=1 placeholder='Response summary'></textarea>
   <div class=actions><button onclick='resp(this,${o.id})'>Record response</button><span class=st></span></div>`:''}
  </div>`).join('')}

async function sent(btn,id){
  const card=btn.closest('.card'),st=card.querySelector('.st');
  if(!card.querySelector('input[type=checkbox]').checked){
    st.innerHTML="<span class=err>confirm you sent it yourself — the tool never sends</span>";return}
  if(await post('outreach_sent',{id,i_sent_this:true},st)){setTimeout(load,400)}}

async function resp(btn,id){
  const card=btn.closest('.card'),st=card.querySelector('.st'),
        summary=card.querySelector('textarea').value.trim();
  if(!summary){st.innerHTML="<span class=err>summary required</span>";return}
  if(await post('outreach_response',{id,summary},st)){setTimeout(load,400)}}

function signals(){
  $('#main').innerHTML=`<div class=card><h3>Record a distribution signal</h3>
   <p class=secnote>Pitch replies, citations, subscriber counts — §0 makes these
   first-class inputs that re-rank the roadmap.</p>
   <div class=actions>
    <select id=sk style='font:inherit;padding:.5rem'>
     <option>citation</option><option>pitch_reply</option><option>inquiry_response</option>
     <option>subscriber</option><option>other</option></select></div>
   <textarea id=sd rows=1 placeholder='What happened?'></textarea>
   <input type=text id=su placeholder='URL (optional)' style='margin-top:.5rem'>
   <div class=actions><button class=approve onclick='sig(this)'>Record</button><span class=st></span></div></div>
   <h2 style='margin-top:2rem'>Recent</h2>`+
   (S.signals.map(s=>`<div class=stat><span>${e(s.ts)} [${e(s.kind)}] ${e(s.detail)}</span></div>`).join('')||"<p class=empty>none yet</p>")}

async function sig(btn){
  const st=btn.parentElement.querySelector('.st');
  const d=$('#sd').value.trim(); if(!d){st.innerHTML="<span class=err>detail required</span>";return}
  if(await post('signal',{kind:$('#sk').value,detail:d,url:$('#su').value},st)){setTimeout(load,400)}}

function doctor(){
  const cs=S.doctor.checks||[];
  if(!cs.length){$('#main').innerHTML="<p class=empty>No report — run <code>glasshouse doctor</code>.</p>";return}
  $('#main').innerHTML=`<p class=secnote>As of ${e(S.doctor.ts)} — ${S.doctor.n_errors} errors,
   ${S.doctor.n_warnings} warnings. Repairs: <code>claude --agent source-medic -p "$(cat data/doctor/task.md)"</code></p>`+
   cs.map(c=>`<div class=stat><span>${c.ok?'·':'⚠'} ${e(c.name)} — ${e(c.detail)}</span></div>`).join('')}

load();
</script></body></html>"""
