#!/usr/bin/env python3
"""Guardian One — Document Search Proof of Concept Server.

Standalone Flask server with embedded Whoosh search engine.
No Docker required — works immediately out of the box.

Usage:
    python search/server.py              # Start on port 5200
    python search/server.py --port 8080  # Custom port

Endpoints:
    GET /                   Landing page with system status
    GET /search/api         JSON search API (?q=...&category=...&doc_type=...)
    GET /search/ui          Full search UI
    GET /health             Health check
    GET /stats              Index statistics
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, Response

# ── Add search dir to path for seed_documents import ──────────
SEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SEARCH_DIR))
from seed_documents import DOCUMENTS

# ── Whoosh setup ──────────────────────────────────────────────
from whoosh import index as whoosh_index
from whoosh.fields import Schema, TEXT, ID, KEYWORD, NUMERIC
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.highlight import UppercaseFormatter
from whoosh import scoring

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("guardian-search")

# ── Schema & Index ────────────────────────────────────────────
SCHEMA = Schema(
    id=ID(stored=True, unique=True),
    title=TEXT(stored=True, field_boost=3.0),
    author=TEXT(stored=True, field_boost=1.5),
    category=TEXT(stored=True),
    doc_type=KEYWORD(stored=True),
    tags=KEYWORD(stored=True, commas=True, scorable=True),
    compliance_status=KEYWORD(stored=True),
    access_level=KEYWORD(stored=True),
    content=TEXT(stored=True),
    date_created=ID(stored=True),
    date_modified=ID(stored=True),
    version=NUMERIC(stored=True, numtype=int),
)

INDEX_DIR = None
IX = None


def build_index():
    """Create Whoosh index in temp dir and populate with seed documents."""
    global INDEX_DIR, IX
    INDEX_DIR = tempfile.mkdtemp(prefix="guardian_search_")
    IX = whoosh_index.create_in(INDEX_DIR, SCHEMA)
    writer = IX.writer()
    for doc in DOCUMENTS:
        writer.add_document(
            id=doc["id"],
            title=doc["title"],
            author=doc["author"],
            category=doc["category"],
            doc_type=doc["doc_type"],
            tags=",".join(doc["tags"]),
            compliance_status=doc["compliance_status"],
            access_level=doc["access_level"],
            content=doc["content"],
            date_created=doc["date_created"],
            date_modified=doc["date_modified"],
            version=doc["version"],
        )
    writer.commit()
    log.info(f"Whoosh index built with {len(DOCUMENTS)} documents at {INDEX_DIR}")


def search_index(q="", category="", doc_type="", compliance_status="",
                 access_level="", page=1, per_page=10, sort="relevance"):
    """Search the Whoosh index. Returns dict with results."""
    if IX is None:
        return {"found": 0, "page": page, "hits": [], "engine": "whoosh"}

    with IX.searcher(weighting=scoring.BM25F()) as searcher:
        parser = MultifieldParser(
            ["title", "content", "author", "tags"],
            schema=IX.schema,
            group=OrGroup,
        )

        if not q or q.strip() == "" or q.strip() == "*":
            from whoosh.query import Every
            query = Every()
        else:
            try:
                query = parser.parse(q)
            except Exception:
                from whoosh.query import Every
                query = Every()

        # Apply filters via filtering
        from whoosh import query as Q
        filters = []
        if category:
            filters.append(Q.Term("category", category.lower()))
        if doc_type:
            filters.append(Q.Term("doc_type", doc_type))
        if compliance_status:
            filters.append(Q.Term("compliance_status", compliance_status))
        if access_level:
            filters.append(Q.Term("access_level", access_level))

        filter_query = Q.And(filters) if filters else None

        results = searcher.search(
            query,
            limit=page * per_page,
            filter=filter_query,
        )
        results.fragmenter.maxchars = 200
        results.fragmenter.surround = 40

        total = len(results)
        start = (page - 1) * per_page
        end = min(start + per_page, total)
        page_hits = []

        for i in range(start, end):
            if i < len(results):
                hit = results[i]
                snippet = hit.highlights("content", top=3) or hit.get("content", "")[:200]
                page_hits.append({
                    "id": hit["id"],
                    "title": hit["title"],
                    "author": hit["author"],
                    "category": hit["category"],
                    "doc_type": hit["doc_type"],
                    "tags": hit.get("tags", "").split(",") if hit.get("tags") else [],
                    "compliance_status": hit["compliance_status"],
                    "access_level": hit["access_level"],
                    "content_snippet": snippet,
                    "date_created": hit["date_created"],
                    "date_modified": hit["date_modified"],
                    "version": hit["version"],
                    "score": round(results.score(i), 4),
                })

        return {
            "engine": "whoosh",
            "found": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
            "hits": page_hits,
            "query": q,
        }


# ── Flask app ─────────────────────────────────────────────────
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
START_TIME = datetime.now(timezone.utc)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.before_request
def log_request():
    log.info(f"{request.method} {request.path} {dict(request.args)}")


@app.route("/health")
def health():
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    return jsonify({
        "status": "healthy",
        "engine": "whoosh",
        "indexed_docs": len(DOCUMENTS),
        "uptime_seconds": round(uptime, 1),
        "index_dir": INDEX_DIR,
    })


@app.route("/stats")
def stats():
    categories = {}
    doc_types = {}
    compliance = {}
    access_levels = {}
    authors = {}
    for doc in DOCUMENTS:
        categories[doc["category"]] = categories.get(doc["category"], 0) + 1
        doc_types[doc["doc_type"]] = doc_types.get(doc["doc_type"], 0) + 1
        compliance[doc["compliance_status"]] = compliance.get(doc["compliance_status"], 0) + 1
        access_levels[doc["access_level"]] = access_levels.get(doc["access_level"], 0) + 1
        authors[doc["author"]] = authors.get(doc["author"], 0) + 1
    return jsonify({
        "total_documents": len(DOCUMENTS),
        "categories": categories,
        "doc_types": doc_types,
        "compliance_statuses": compliance,
        "access_levels": access_levels,
        "authors": authors,
    })


@app.route("/search/api")
def search_api():
    q = request.args.get("q", "")
    category = request.args.get("category", "")
    doc_type = request.args.get("doc_type", "")
    compliance_status = request.args.get("compliance_status", "")
    access_level = request.args.get("access_level", "")
    sort = request.args.get("sort", "relevance")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(100, int(request.args.get("per_page", 10))))
    except (ValueError, TypeError):
        per_page = 10

    results = search_index(
        q=q, category=category, doc_type=doc_type,
        compliance_status=compliance_status, access_level=access_level,
        page=page, per_page=per_page, sort=sort,
    )
    return jsonify(results)


SEARCH_UI_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Guardian One — Document Search</title>
<style>
:root{--p:#1a56db;--pl:#e8f0fe;--t:#1f2937;--tl:#6b7280;--b:#e5e7eb;--bg:#f9fafb;--w:#fff;--r:#dc2626;--y:#f59e0b;--g:#16a34a}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--t);line-height:1.6}
.hdr{background:var(--w);border-bottom:1px solid var(--b);padding:12px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.hdr h1{font-size:18px;color:var(--p);white-space:nowrap}
.hdr input{flex:1;max-width:600px;padding:10px 16px;border:1px solid var(--b);border-radius:8px;font-size:15px;outline:none}
.hdr input:focus{border-color:var(--p);box-shadow:0 0 0 3px rgba(26,86,219,.1)}
.kbd{font-size:11px;color:var(--tl);padding:2px 6px;border:1px solid var(--b);border-radius:4px;font-family:monospace}
.badge-poc{background:#dbeafe;color:var(--p);font-size:11px;font-weight:600;padding:3px 8px;border-radius:10px}
.lay{display:flex;max-width:1400px;margin:0 auto;padding:20px;gap:20px}
.side{width:260px;flex-shrink:0}
.main{flex:1;min-width:0}
.filt{background:var(--w);border:1px solid var(--b);border-radius:8px;padding:14px;margin-bottom:14px}
.filt h3{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--tl);margin-bottom:10px}
.filt label{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--t);cursor:pointer;padding:3px 0}
.filt input[type=checkbox]{accent-color:var(--p)}
.filt .cnt{color:var(--tl);font-size:11px;margin-left:auto}
.stats{font-size:14px;color:var(--tl);margin-bottom:14px;display:flex;justify-content:space-between;align-items:center}
.stats select{padding:5px 10px;border:1px solid var(--b);border-radius:6px;font-size:13px}
.card{background:var(--w);border:1px solid var(--b);border-radius:8px;padding:18px;margin-bottom:10px;transition:border-color .15s}
.card:hover{border-color:var(--p)}
.card-h{display:flex;align-items:flex-start;gap:10px;margin-bottom:6px}
.icon{width:34px;height:34px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0}
.i-PDF{background:#fef2f2;color:var(--r)}.i-DOCX{background:#eff6ff;color:var(--p)}.i-PPTX{background:#fef3c7;color:#b45309}.i-XLSX{background:#ecfdf5;color:var(--g)}.i-web{background:#f3e8ff;color:#7c3aed}
.card-t{font-size:15px;font-weight:600;color:var(--p);line-height:1.3}
.card-s{font-size:13px;color:var(--tl);margin:6px 0;line-height:1.5}
.card-s b,.card-s strong{background:#fef08a;color:inherit;padding:1px 2px;border-radius:2px;font-weight:600}
.card-m{display:flex;align-items:center;gap:14px;font-size:12px;color:var(--tl);flex-wrap:wrap}
.bdg{font-size:10px;font-weight:600;padding:2px 7px;border-radius:8px;text-transform:uppercase}
.b-active{background:#ecfdf5;color:var(--g)}.b-expired{background:#fef2f2;color:var(--r)}.b-under_review{background:#fffbeb;color:var(--y)}.b-NA{background:#f3f4f6;color:var(--tl)}
.empty{text-align:center;padding:48px;color:var(--tl)}
.empty p:first-child{font-size:17px;margin-bottom:6px}
.pag{display:flex;justify-content:center;gap:6px;margin-top:18px}
.pag button{padding:6px 12px;border:1px solid var(--b);border-radius:6px;background:var(--w);cursor:pointer;font-size:13px}
.pag button.act{background:var(--p);color:var(--w);border-color:var(--p)}
.pag button:disabled{opacity:.4;cursor:default}
.skel .card{min-height:100px;background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:shimmer 1.5s infinite}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
@media(max-width:768px){.lay{flex-direction:column}.side{width:100%}}
</style>
</head>
<body>
<div class="hdr">
  <h1>Guardian One</h1>
  <input id="q" type="text" placeholder="Search documents, protocols, and policies..." autofocus>
  <span class="kbd" title="Ctrl+K to focus">Ctrl+K</span>
  <span class="badge-poc">PoC · Whoosh</span>
</div>
<div class="lay">
  <aside class="side" id="filters"></aside>
  <main class="main">
    <div class="stats" id="stats-bar"></div>
    <div id="results"></div>
    <div class="pag" id="pagination"></div>
  </main>
</div>
<script>
const API="/search/api";
let state={q:"",filters:{category:[],doc_type:[],compliance_status:[],access_level:[]},page:1,per_page:10,sort:"relevance"};
let debounceTimer;
const CATEGORIES=["Clinical Protocols & Guidelines","Compliance & Legal","Research & Publications","Operations & Internal","Financial & Billing","Training & Onboarding"];
const DOC_TYPES=["PDF","DOCX","PPTX","XLSX"];
const COMPLIANCE=["active","expired","under_review","N/A"];
const ACCESS=["all_team","clinical_only","leadership_only","compliance_only"];

function renderFilters(){
  let h="";
  [{t:"Category",k:"category",v:CATEGORIES},{t:"Document Type",k:"doc_type",v:DOC_TYPES},{t:"Compliance",k:"compliance_status",v:COMPLIANCE},{t:"Access Level",k:"access_level",v:ACCESS}].forEach(f=>{
    h+=`<div class="filt"><h3>${f.t}</h3>`;
    f.v.forEach(v=>{
      const c=state.filters[f.k].includes(v)?"checked":"";
      h+=`<label><input type="checkbox" data-filter="${f.k}" data-value="${v}" ${c}> ${v.replace(/_/g," ")}</label>`;
    });
    h+="</div>";
  });
  document.getElementById("filters").innerHTML=h;
  document.querySelectorAll('[data-filter]').forEach(cb=>{
    cb.addEventListener("change",e=>{
      const k=e.target.dataset.filter,v=e.target.dataset.value;
      if(e.target.checked){state.filters[k].push(v)}else{state.filters[k]=state.filters[k].filter(x=>x!==v)}
      state.page=1;doSearch();
    });
  });
}

function doSearch(){
  const params=new URLSearchParams();
  if(state.q)params.set("q",state.q);
  params.set("page",state.page);params.set("per_page",state.per_page);
  Object.entries(state.filters).forEach(([k,vals])=>{if(vals.length===1)params.set(k,vals[0])});
  document.getElementById("results").innerHTML='<div class="skel"><div class="card"></div><div class="card"></div><div class="card"></div></div>';
  fetch(API+"?"+params.toString()).then(r=>r.json()).then(renderResults).catch(err=>{
    document.getElementById("results").innerHTML=`<div class="empty"><p>Search error</p><p>${err.message}</p></div>`;
  });
}

function renderResults(data){
  const sb=document.getElementById("stats-bar");
  sb.innerHTML=`<span>${data.found} result${data.found!==1?"s":""} ${state.q?'for "'+esc(state.q)+'"':""}</span><select id="sort-sel"><option value="relevance">Relevance</option><option value="date_desc">Date (newest)</option><option value="date_asc">Date (oldest)</option></select>`;
  document.getElementById("sort-sel").value=state.sort;
  document.getElementById("sort-sel").onchange=e=>{state.sort=e.target.value;state.page=1;doSearch()};

  const res=document.getElementById("results");
  if(!data.hits||data.hits.length===0){
    res.innerHTML=`<div class="empty"><p>No documents found${state.q?' for "'+esc(state.q)+'"':""}</p><p>Try broadening your search or removing filters.</p></div>`;
    document.getElementById("pagination").innerHTML="";return;
  }
  let h="";
  data.hits.forEach(hit=>{
    const ic="i-"+(hit.doc_type||"web");
    const bc="b-"+(hit.compliance_status||"NA").replace("/","");
    h+=`<div class="card"><div class="card-h"><div class="icon ${ic}">${hit.doc_type||"?"}</div><div><div class="card-t">${esc(hit.title)}</div></div></div>`;
    h+=`<div class="card-s">${hit.content_snippet||esc((hit.content||"").slice(0,200))}</div>`;
    h+=`<div class="card-m"><span>${esc(hit.author)}</span><span>${hit.date_modified}</span><span>${esc(hit.category)}</span>`;
    h+=`<span class="bdg ${bc}">${(hit.compliance_status||"N/A").replace(/_/g," ")}</span></div></div>`;
  });
  res.innerHTML=h;

  // Pagination
  const pg=document.getElementById("pagination");
  const tp=data.total_pages||1;
  let ph=`<button ${data.page<=1?"disabled":""} onclick="goPg(${data.page-1})">Prev</button>`;
  for(let i=1;i<=tp;i++){ph+=`<button class="${i===data.page?"act":""}" onclick="goPg(${i})">${i}</button>`}
  ph+=`<button ${data.page>=tp?"disabled":""} onclick="goPg(${data.page+1})">Next</button>`;
  pg.innerHTML=ph;
}

function goPg(p){state.page=p;doSearch()}
function esc(s){if(!s)return"";const d=document.createElement("div");d.textContent=s;return d.innerHTML}

document.getElementById("q").addEventListener("input",e=>{
  clearTimeout(debounceTimer);
  debounceTimer=setTimeout(()=>{state.q=e.target.value;state.page=1;doSearch()},250);
});

document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==="k"){e.preventDefault();document.getElementById("q").focus()}
});

renderFilters();doSearch();
</script>
</body>
</html>'''


@app.route("/search/ui")
def search_ui():
    return Response(SEARCH_UI_HTML, mimetype="text/html")


LANDING_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Guardian One — Document Search PoC</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;color:#1f2937;line-height:1.6}
.hero{background:#1a56db;color:white;padding:48px 32px;text-align:center}
.hero h1{font-size:32px;margin-bottom:8px}
.hero p{font-size:16px;opacity:.85;max-width:600px;margin:0 auto}
.content{max-width:800px;margin:32px auto;padding:0 24px}
.card{background:white;border:1px solid #e5e7eb;border-radius:8px;padding:24px;margin-bottom:16px}
.card h2{font-size:18px;margin-bottom:12px;color:#1a56db}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.status-item{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;text-align:center}
.status-item .num{font-size:28px;font-weight:700;color:#16a34a}
.status-item .lbl{font-size:13px;color:#6b7280}
a.link{display:inline-block;background:#1a56db;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;margin:4px}
a.link:hover{background:#1e40af}
code{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:14px}
pre{background:#1f2937;color:#e5e7eb;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;margin:12px 0}
</style>
</head>
<body>
<div class="hero">
  <h1>Guardian One</h1>
  <p>Document Search — Proof of Concept</p>
</div>
<div class="content">
  <div class="status">
    <div class="status-item"><div class="num">DOCS_COUNT</div><div class="lbl">Documents Indexed</div></div>
    <div class="status-item"><div class="num">Whoosh</div><div class="lbl">Search Engine</div></div>
    <div class="status-item"><div class="num">HEALTHY</div><div class="lbl">Status</div></div>
  </div>
  <div class="card">
    <h2>Search UI</h2>
    <p>Full-featured search interface with faceted filters, highlighted snippets, and keyboard shortcuts.</p>
    <br><a class="link" href="/search/ui">Open Search UI</a>
  </div>
  <div class="card">
    <h2>API Endpoints</h2>
    <p><code>GET /search/api?q=readmission</code> — Full-text search</p>
    <p><code>GET /search/api?q=*&category=Compliance+%26+Legal</code> — Filtered search</p>
    <p><code>GET /health</code> — Health check</p>
    <p><code>GET /stats</code> — Index statistics</p>
    <br><a class="link" href="/search/api?q=readmission">Try API</a>
    <a class="link" href="/health">Health</a>
    <a class="link" href="/stats">Stats</a>
  </div>
  <div class="card">
    <h2>Quick Start</h2>
    <pre>pip install whoosh flask
python search/server.py          # Start PoC server
python search/server.py --port 8080  # Custom port

# Test the API
curl "http://localhost:5200/search/api?q=readmission"
curl "http://localhost:5200/health"</pre>
  </div>
  <div class="card">
    <h2>Production Upgrade Path</h2>
    <p>This PoC uses Whoosh for zero-dependency search. For production:</p>
    <pre>cd search/
docker compose up -d             # Start Typesense + Meilisearch
pip install -r requirements.txt
python seed_documents.py --both  # Seed production engines</pre>
    <p>Then switch to the Typesense or Meilisearch frontend for full fuzzy matching, typo tolerance, and production-grade performance.</p>
  </div>
</div>
</body>
</html>'''


@app.route("/")
def landing():
    html = LANDING_HTML.replace("DOCS_COUNT", str(len(DOCUMENTS)))
    return Response(html, mimetype="text/html")


def cleanup():
    """Remove temp index dir on shutdown."""
    if INDEX_DIR and os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
        log.info(f"Cleaned up index dir: {INDEX_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardian One Search PoC Server")
    parser.add_argument("--port", type=int, default=5200, help="Port (default: 5200)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    args = parser.parse_args()

    build_index()
    import atexit
    atexit.register(cleanup)
    log.info(f"Starting Guardian One Search PoC on http://localhost:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
