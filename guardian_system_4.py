#!/usr/bin/env python3
"""
GUARDIAN ONE CLI v0.2.2 — Cross-platform hardened build
Put this file in any folder. Run: python guardian_system.py list
Requires: Python 3.8+ (standard library only)
"""
import sys
if sys.version_info < (3, 8):
    print("ERROR: Python 3.8+ required. You have " + ".".join(str(x) for x in sys.version_info[:3]))
    sys.exit(1)

import json, hashlib, os, platform
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.2.2"

# --- Resolve script directory (handles frozen exes, symlinks, etc) ---
try:
    SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    SCRIPT_DIR = Path(os.getcwd())

LOG_FILE = str(SCRIPT_DIR / "guardian_one_log.json")
INTERACTIONS_FILE = str(SCRIPT_DIR / "interactions_log.json")

VALID_CATEGORIES = [
    "financial","medical_self","medical_dependent","professional",
    "legal","document","system","relational","correction",
    "state_snapshot","claude_interaction"]
VALID_INTENTS = ["decision","observation","correction","query","reflection","archive"]
VALID_CONFIDENCE = ["high","moderate","low"]
VALID_RTYPES = ["code","analysis","design","document","conversation","debug","lesson"]

# --- Windows ANSI color enable ---
def _win_colors():
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(ctypes.c_ulong(-11 & 0xFFFFFFFF))
        m = ctypes.c_ulong()
        k.GetConsoleMode(h, ctypes.byref(m))
        return bool(k.SetConsoleMode(h, m.value | 0x0004))
    except Exception:
        return False

_USE_COLOR = _win_colors() and ("--no-color" not in sys.argv)
if "--no-color" in sys.argv:
    sys.argv.remove("--no-color")

def _c(code):
    return code if _USE_COLOR else ""

G=_c("\033[92m"); R=_c("\033[91m"); Y=_c("\033[93m"); B=_c("\033[94m")
P=_c("\033[95m"); CN=_c("\033[96m"); D=_c("\033[90m"); BD=_c("\033[1m"); RS=_c("\033[0m")

# --- Safe file I/O (str paths, explicit encoding, fallback writes) ---
def _read_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _write_json(filepath, data):
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        os.replace(tmp, filepath)
    except OSError:
        # Fallback for locked files on Windows
        if os.path.exists(filepath):
            bak = filepath + ".bak"
            try: os.remove(bak)
            except OSError: pass
            os.rename(filepath, bak)
        os.rename(tmp, filepath)

# --- Core ---
def ts():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def sha(entry):
    h = dict(entry)
    h.pop("entry_hash", None)
    return hashlib.sha256(json.dumps(h, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

SEED = [
    {"entry_id":1,"timestamp":"2026-02-23T17:20:16Z","category":"financial","intent":"decision",
     "summary":"Purchased ASUS ROG Strix Flow laptop, 64GB RAM.",
     "context":"MacBook Pro memory constraints. Ryzen 9 + 64GB for local LLM inference.",
     "outcome":"Purchased. Dev environment migrated.","confidence":"high",
     "references":[],"documents":[],"tags":["hardware","development","overlord-guardian"],
     "metadata":{"amount_usd":2149.0,"vendor":"ASUS","model":"ROG Strix Flow","ram_gb":64},
     "prev_hash":"GENESIS","entry_hash":""},
    {"entry_id":2,"timestamp":"2026-02-23T17:20:16Z","category":"medical_dependent","intent":"decision",
     "summary":"Maintained Chaos on Cyclosporine 50mg q12h + Prednisone 10mg q12h.",
     "context":"IMPA diagnosis via BluePearl. CBC/Chem stable.",
     "outcome":"Continuing regimen. Recheck 4 weeks.","confidence":"high",
     "references":[],"documents":[],"tags":["chaos","impa","cyclosporine","prednisone"],
     "metadata":{"patient":"Chaos","species":"canine","breed":"French Bulldog",
     "provider":"Happy Tails Superior WI / BluePearl Golden Valley"},
     "prev_hash":"","entry_hash":""},
    {"entry_id":3,"timestamp":"2026-02-23T17:20:16Z","category":"system","intent":"decision",
     "summary":"Defined Guardian One schema v0.1.0.",
     "context":"Append-only hash-chained sovereign identity log.",
     "outcome":"Schema finalized.","confidence":"high",
     "references":[],"documents":[],"tags":["guardian-one","overlord-guardian","architecture"],
     "metadata":{"schema_version":"0.1.0","stack_layer":"foundation"},
     "prev_hash":"","entry_hash":""},
    {"entry_id":4,"timestamp":"2026-02-23T17:20:16Z","category":"correction","intent":"correction",
     "summary":"Correcting entry 1: actual purchase price was $2,149.",
     "context":"Verified against order confirmation.",
     "outcome":"Financial metadata complete.","confidence":"high",
     "references":[1],"documents":[],"tags":["correction","hardware","financial"],
     "metadata":{"corrects_entry_id":1,"corrected_field":"metadata.amount_usd","corrected_value":2149.0},
     "prev_hash":"","entry_hash":""},
    {"entry_id":5,"timestamp":"2026-02-23T17:20:16Z","category":"professional","intent":"decision",
     "summary":"Registered jtmdai.com and deployed JTMedAI dashboard.",
     "context":"Healthcare AI dashboard. Cloudflare Workers. $10.46/year.",
     "outcome":"Site live. First public advisory asset.","confidence":"high",
     "references":[3],"documents":[],"tags":["jtmedai","website","cloudflare","advisory","professional"],
     "metadata":{"domain":"jtmdai.com","registrar":"Cloudflare","cost_usd":10.46,
     "hosting":"Cloudflare Workers (free)","invoice":"IN-58178604"},
     "prev_hash":"","entry_hash":""}
]

def _build_seed():
    out = []
    for i, raw in enumerate(SEED):
        e = dict(raw)
        e["prev_hash"] = "GENESIS" if i == 0 else out[i-1]["entry_hash"]
        e["entry_hash"] = ""
        e["entry_hash"] = sha(e)
        out.append(e)
    return out

def load_log():
    doc = _read_json(LOG_FILE)
    if doc is None:
        print(f"  {Y}First run. Creating log...{RS}")
        entries = _build_seed()
        doc = {"log_version":VERSION,"owner":"Jeremy Tabernero, MD",
               "created":ts(),"entries":entries,"entry_count":len(entries)}
        _write_json(LOG_FILE, doc)
        print(f"  {G}Created with {len(entries)} entries.{RS}\n")
        return entries, doc
    return doc.get("entries", []), doc

def save_log(entries, doc=None):
    if doc is None:
        doc = {"log_version":VERSION,"owner":"Jeremy Tabernero, MD",
               "created":ts(),"entries":entries,"entry_count":len(entries)}
    else:
        doc["entries"] = entries; doc["entry_count"] = len(entries)
    _write_json(LOG_FILE, doc)

def load_ints():
    doc = _read_json(INTERACTIONS_FILE)
    return doc.get("interactions", []) if doc else []

def save_ints(ints):
    _write_json(INTERACTIONS_FILE, {"log_version":VERSION,"owner":"Jeremy Tabernero, MD",
                                     "interaction_count":len(ints),"interactions":ints})

def nid(entries):
    return max((e.get("entry_id",0) for e in entries), default=0) + 1

def phash(entries):
    return entries[-1].get("entry_hash","GENESIS") if entries else "GENESIS"

def mkentry(entries, cat, intent, summary, ctx, out=None, conf="high",
            tags=None, meta=None, refs=None, docs=None):
    e = {"entry_id":nid(entries),"timestamp":ts(),"category":cat,"intent":intent,
         "summary":summary,"context":ctx,"outcome":out,"confidence":conf,
         "references":refs or [],"documents":docs or [],"tags":tags or [],
         "metadata":meta or {},"prev_hash":phash(entries),"entry_hash":""}
    e["entry_hash"] = sha(e)
    return e

# --- Display ---
def hdr(text):
    print(f"\n{G}{'='*70}{RS}\n{BD}{G}  {text}{RS}\n{G}{'='*70}{RS}\n")

CAT_C = {"financial":Y,"medical_self":R,"medical_dependent":R,"professional":B,
         "legal":P,"system":CN,"correction":D,"claude_interaction":G}

def show(e, h=False):
    cat = e.get("category","?")
    cc = CAT_C.get(cat, RS)
    print(f"  {BD}[{e.get('entry_id','?')}]{RS}  {cc}{cat.upper()}{RS}  {D}{e.get('timestamp','')}{RS}")
    print(f"       {BD}{e.get('summary','')}{RS}")
    if e.get("outcome"): print(f"       {D}Outcome:{RS} {e['outcome']}")
    if e.get("tags"): print(f"       {' '.join(CN+'#'+t+RS for t in e['tags'])}")
    for k,v in e.get("metadata",{}).items(): print(f"       {D}{k}:{RS} {v}")
    if h: print(f"       {D}hash: {e.get('entry_hash','')[:16]}...{RS}")
    for d in e.get("documents",[]):
        if "interactions_log" in str(d): print(f"       {G}-> {d}{RS}")
    print()

# --- Commands ---
def cmd_help():
    hdr(f"GUARDIAN ONE CLI v{VERSION}")
    for c,d in [("list","All entries"),("add","New entry"),("query","Filter --category --tag --intent"),
                ("search","Text search"),("check","Hash integrity"),("stats","Statistics"),
                ("log-interaction","Log Claude request"),("diagnose","System check")]:
        print(f"    {G}{c:<22}{RS} {d}")
    print(f"\n  {D}Examples:{RS}")
    for x in ["list","query --tag chaos",'search "laptop"',"stats","check","diagnose"]:
        print(f"    {D}python guardian_system.py {x}{RS}")
    print(f"\n  {D}--no-color  disable colors{RS}\n")

def cmd_diag():
    hdr("DIAGNOSTICS")
    v = sys.version_info
    tests = [("Python",f"{v.major}.{v.minor}.{v.micro}",v>=(3,8)),
             ("Platform",f"{platform.system()} {platform.release()}",True),
             ("Script dir",str(SCRIPT_DIR),True),
             ("Colors","on" if _USE_COLOR else "off",True)]
    if os.path.exists(LOG_FILE):
        try:
            d = _read_json(LOG_FILE); tests.append(("Log",f"{len(d.get('entries',[]))} entries",True))
        except Exception as x: tests.append(("Log",str(x),False))
    else: tests.append(("Log","will auto-create",True))
    try:
        tp = os.path.join(str(SCRIPT_DIR),".wtest")
        open(tp,"w").close(); os.remove(tp); tests.append(("Write","OK",True))
    except Exception: tests.append(("Write","DENIED",False))
    tests.append(("Encoding",f"default={sys.getdefaultencoding()} stdout={sys.stdout.encoding}",True))
    for n,v,ok in tests:
        i = f"{G}PASS{RS}" if ok else f"{R}FAIL{RS}"
        print(f"  [{i}] {BD}{n}:{RS} {v}")
    print()

def cmd_list():
    entries,_ = load_log()
    if not entries: hdr("EMPTY LOG"); return
    hdr(f"ALL ENTRIES ({len(entries)})")
    for e in reversed(entries): show(e, h=True)

def cmd_query(args):
    entries,_ = load_log()
    if not entries: print(f"  {D}Empty.{RS}"); return
    cat=None; tags=[]; intent=None; i=0
    while i < len(args):
        a = args[i]
        if a == "--category" and i+1 < len(args):
            cat = args[i+1].lower()
            if cat not in VALID_CATEGORIES:
                print(f"\n  {R}\"{cat}\" invalid.{RS} Valid: {', '.join(VALID_CATEGORIES)}\n"); return
            i += 2
        elif a == "--tag" and i+1 < len(args): tags.append(args[i+1].lower()); i += 2
        elif a == "--tags" and i+1 < len(args):
            tags.extend(t.strip().lower() for t in args[i+1].split(",") if t.strip()); i += 2
        elif a == "--intent" and i+1 < len(args):
            intent = args[i+1].lower()
            if intent not in VALID_INTENTS:
                print(f"\n  {R}\"{intent}\" invalid.{RS} Valid: {', '.join(VALID_INTENTS)}\n"); return
            i += 2
        else: print(f"\n  {R}\"{a}\" unknown.{RS} Use: --category --tag --tags --intent\n"); return
    if not cat and not tags and not intent:
        print(f"\n  {R}Specify a filter.{RS} Example: query --tag chaos\n"); return
    res = []
    for e in entries:
        m = True
        if cat and e.get("category","").lower() != cat: m = False
        if tags:
            et = [t.lower() for t in e.get("tags",[])]
            for rt in tags:
                if rt not in et: m = False; break
        if intent and e.get("intent","").lower() != intent: m = False
        if m: res.append(e)
    parts = []
    if cat: parts.append(f"category={cat}")
    if tags: parts.append(f"tags={','.join(tags)}")
    if intent: parts.append(f"intent={intent}")
    hdr(f"QUERY: {' + '.join(parts)}")
    if not res: print(f"  {D}No matches.{RS}\n"); return
    print(f"  {D}{len(res)} match(es):{RS}\n")
    for e in res: show(e)

def cmd_search(args):
    if not args: print(f"\n  {R}No term.{RS} Example: search \"laptop\"\n"); return
    term = " ".join(args).lower().strip("\"'")
    entries,_ = load_log()
    if not entries: print(f"  {D}Empty.{RS}"); return
    res = [e for e in entries if term in " ".join([
        str(e.get("summary","")),str(e.get("context","")),
        str(e.get("outcome",""))," ".join(e.get("tags",[]))]).lower()]
    hdr(f'SEARCH: "{term}"')
    if not res: print(f"  {D}No matches.{RS}\n"); return
    print(f"  {D}{len(res)} match(es):{RS}\n")
    for e in res: show(e)

def cmd_check():
    entries,_ = load_log()
    if not entries: print(f"  {D}Empty.{RS}"); return
    hdr("HASH CHAIN VERIFICATION")
    ok = True
    for i,e in enumerate(entries):
        eid = e.get("entry_id","?"); exp = sha(e); act = e.get("entry_hash","")
        if exp != act:
            print(f"  {R}X [{eid}] MISMATCH{RS}"); ok = False
        else:
            print(f"  {G}+ [{eid}] VALID{RS}  {D}{act[:16]}...{RS}")
        if i > 0:
            if entries[i-1].get("entry_hash","") != e.get("prev_hash",""):
                print(f"    {R}X CHAIN BREAK{RS}"); ok = False
            else: print(f"    {D}  chain OK{RS}")
        elif e.get("prev_hash") == "GENESIS": print(f"    {D}  genesis{RS}")
    print()
    if ok: print(f"  {G}{BD}ALL {len(entries)} VALID.{RS}")
    else: print(f"  {R}{BD}FAILURES DETECTED.{RS}")
    print()

def cmd_stats():
    entries,_ = load_log(); ints = load_ints()
    hdr("STATISTICS")
    print(f"  {BD}Entries:{RS}       {len(entries)}")
    print(f"  {BD}Interactions:{RS}  {len(ints)}\n")
    if not entries: return
    cats = {}
    for e in entries: c=e.get("category","?"); cats[c]=cats.get(c,0)+1
    print(f"  {BD}Categories:{RS}")
    for c,n in sorted(cats.items(),key=lambda x:-x[1]): print(f"    {c:<22} {G}{'#'*n}{RS} {n}")
    print()
    at = {}
    for e in entries:
        for t in e.get("tags",[]): at[t]=at.get(t,0)+1
    if at:
        print(f"  {BD}Tags:{RS}")
        for t,n in sorted(at.items(),key=lambda x:-x[1])[:10]: print(f"    {CN}#{t}{RS}  ({n})")
        print()
    total = 0.0
    for e in entries:
        if e.get("category")=="correction": continue
        m=e.get("metadata",{}); a=m.get("amount_usd") or m.get("cost_usd") or 0
        if a: total += float(a)
    if total > 0: print(f"  {BD}Spending:{RS}  {Y}${total:,.2f}{RS}")
    tl = [e.get("timestamp","") for e in entries if e.get("timestamp")]
    if tl: print(f"  {BD}Range:{RS}     {tl[0]} -> {tl[-1]}")
    print()

def cmd_add():
    entries,doc = load_log()
    hdr("ADD ENTRY")
    print(f"  {BD}Category:{RS}")
    for i,c in enumerate(VALID_CATEGORIES,1): print(f"    {G}{i:>2}{RS}. {c}")
    try: r = input(f"\n  {CN}Pick: {RS}").strip()
    except (KeyboardInterrupt,EOFError): print(f"\n  {D}Cancelled.{RS}"); return
    if r.isdigit():
        idx = int(r)-1
        if not 0 <= idx < len(VALID_CATEGORIES): print(f"  {R}Out of range.{RS}"); return
        cat = VALID_CATEGORIES[idx]
    elif r.lower() in VALID_CATEGORIES: cat = r.lower()
    else: print(f"  {R}\"{r}\" invalid.{RS}"); return
    print(f"\n  {BD}Intent:{RS}")
    for i,x in enumerate(VALID_INTENTS,1): print(f"    {G}{i}{RS}. {x}")
    try: r = input(f"\n  {CN}Pick: {RS}").strip()
    except (KeyboardInterrupt,EOFError): print(f"\n  {D}Cancelled.{RS}"); return
    if r.isdigit():
        idx = int(r)-1
        if not 0 <= idx < len(VALID_INTENTS): print(f"  {R}Out of range.{RS}"); return
        intent = VALID_INTENTS[idx]
    elif r.lower() in VALID_INTENTS: intent = r.lower()
    else: print(f"  {R}\"{r}\" invalid.{RS}"); return
    try:
        print()
        summary = input(f"  {CN}Summary: {RS}").strip()
        if not summary: print(f"  {R}Required.{RS}"); return
        context = input(f"  {CN}Context: {RS}").strip() or None
        outcome = input(f"  {CN}Outcome: {RS}").strip() or None
        tr = input(f"  {CN}Tags (comma-sep): {RS}").strip()
        tags = [t.strip() for t in tr.split(",") if t.strip()] if tr else []
        cf = input(f"  {CN}Confidence [high]: {RS}").strip().lower()
        conf = cf if cf in VALID_CONFIDENCE else "high"
    except (KeyboardInterrupt,EOFError): print(f"\n  {D}Cancelled.{RS}"); return
    e = mkentry(entries,cat,intent,summary,ctx=context,out=outcome,conf=conf,tags=tags)
    entries.append(e); save_log(entries,doc)
    print(f"\n  {G}Entry #{e['entry_id']} saved.{RS}\n"); show(e,h=True)

def cmd_log_int(args):
    entries,doc = load_log(); ints = load_ints()
    req=out=rt=None; files=[]; tags=[]; dur=None; i=0
    while i < len(args):
        a = args[i]
        if a=="--request" and i+1<len(args): req=args[i+1]; i+=2
        elif a=="--type" and i+1<len(args):
            rt=args[i+1].lower()
            if rt not in VALID_RTYPES: print(f"\n  {R}\"{rt}\" invalid.{RS} Use: {', '.join(VALID_RTYPES)}\n"); return
            i+=2
        elif a=="--outcome" and i+1<len(args): out=args[i+1]; i+=2
        elif a=="--files" and i+1<len(args): files=[f.strip() for f in args[i+1].split(",") if f.strip()]; i+=2
        elif a=="--tags" and i+1<len(args): tags=[t.strip() for t in args[i+1].split(",") if t.strip()]; i+=2
        elif a=="--duration" and i+1<len(args):
            try: dur=int(args[i+1])
            except ValueError: print(f"\n  {R}--duration needs integer.{RS}\n"); return
            i+=2
        else: print(f"\n  {R}\"{a}\" unknown.{RS}\n"); return
    if not req: print(f"\n  {R}--request required.{RS}\n"); return
    iid = len(ints)+1; t = ts()
    ix = {"interaction_id":iid,"date_requested":t,"date_response_received":t,
          "request_text":req,"response_type":rt or "conversation","outcome":out,
          "duration_seconds":dur,"tags":tags,"file_artifacts":files}
    ints.append(ix); save_ints(ints)
    ge = mkentry(entries,"claude_interaction","observation",f"Claude: {out or req}",
                 ctx=req,out=out,tags=tags+["claude-interaction"],
                 meta={"response_type":rt or "conversation","duration_seconds":dur,"file_count":len(files)},
                 docs=[os.path.basename(INTERACTIONS_FILE)+f"#interaction_{iid}"]+files)
    entries.append(ge); save_log(entries,doc)
    print(f"\n  {G}Interaction #{iid} logged.{RS}")
    print(f"  {G}Entry #{ge['entry_id']} created.{RS}\n"); show(ge,h=True)

def main():
    if len(sys.argv) < 2: cmd_help(); return
    c = sys.argv[1].lower().strip(); a = sys.argv[2:]
    r = {"help":cmd_help,"--help":cmd_help,"-h":cmd_help,
         "list":cmd_list,"ls":cmd_list,"add":cmd_add,"new":cmd_add,
         "query":lambda:cmd_query(a),"q":lambda:cmd_query(a),
         "search":lambda:cmd_search(a),"find":lambda:cmd_search(a),
         "check":cmd_check,"verify":cmd_check,"stats":cmd_stats,
         "log-interaction":lambda:cmd_log_int(a),"log":lambda:cmd_log_int(a),
         "diagnose":cmd_diag,"diag":cmd_diag}
    fn = r.get(c)
    if fn: fn()
    else:
        print(f"\n  {R}\"{c}\" not recognized.{RS}")
        m = [k for k in r if not k.startswith("-") and (len(c)>0 and (c[0]==k[0] or c in k))]
        if m: print(f"  {D}Try: {', '.join(m[:3])}{RS}")
        print(f"  {D}python guardian_system.py help{RS}\n")

if __name__ == "__main__":
    main()
