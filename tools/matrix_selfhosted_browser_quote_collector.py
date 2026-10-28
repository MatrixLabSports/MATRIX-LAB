from __future__ import annotations
import hashlib, json, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"config"/"MATRIX_SELF_HOSTED_BROWSER_AUTOMATION.json"
AUDIT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json"
ADAPTERS=ROOT/"config"/"MATRIX_BROWSER_BOOKMAKER_ADAPTERS.json"
OUT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_BROWSER_CDP_COLLECTION_LAST.json"
RAW_ROOT=ROOT/"evidence"/"notifications"/"telegram"/"browser_cdp"

DOMAIN_BOOKS={
 "betano.co":"betano","betplay.com.co":"betplay","betsson.co":"betsson","bwin.co":"bwin",
 "codere.com.co":"codere","luckia.co":"luckia","mryoker.co":"mryoker","rivalo.co":"rivalo",
 "rushbet.co":"rushbet","sportium.com.co":"sportium","stake.com.co":"stake","wplay.co":"wplay",
 "yajuego.co":"yajuego","zamba.co":"zamba",
}

def load(path:Path)->dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def norm(s:Any)->str:
    x=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+"," ",x).strip()

def split_match(name:str)->tuple[str,str]|None:
    parts=re.split(r"\s+vs\.?\s+",str(name or ""),maxsplit=1,flags=re.I)
    if len(parts)!=2: return None
    a,b=(norm(x) for x in parts)
    return (a,b) if a and b else None

def book_from_url(url:str)->str|None:
    host=urlparse(url).netloc.casefold().split(":")[0]
    host=host[4:] if host.startswith("www.") else host
    for domain,key in DOMAIN_BOOKS.items():
        if host==domain or host.endswith("."+domain):
            return key
    return None

def candidate_rows(audit:dict[str,Any],now:datetime)->list[dict[str,Any]]:
    out=[]
    for r in audit.get("records") or []:
        if not isinstance(r,dict): continue
        kickoff=r.get("kickoff")
        try:
            kd=datetime.fromisoformat(str(kickoff).replace("Z","+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        sec=(kd-now).total_seconds()
        if sec<=0 or sec>120*60: continue
        if float(r.get("p_matrix") or 0)<0.60: continue
        if split_match(str(r.get("match") or "")) is None: continue
        out.append(r)
    return sorted(out,key=lambda x:x["kickoff"])

def page_matches_candidate(text:str,candidate:dict[str,Any])->bool:
    parts=split_match(str(candidate.get("match") or ""))
    if parts is None: return False
    t=norm(text)
    home,away=parts
    return home in t and away in t

def main()->None:
    cfg=load(CONFIG); audit=load(AUDIT); adapters=load(ADAPTERS)
    endpoint=os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT",cfg["browser"]["default_cdp_endpoint"]).strip()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    candidates=candidate_rows(audit,now)
    RAW_ROOT.mkdir(parents=True,exist_ok=True)
    pages=[]; matched=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=15000)
        contexts=browser.contexts
        if not contexts:
            raise SystemExit("BROWSER_CDP_NO_CONTEXTS")
        for ci,ctx in enumerate(contexts):
            existing_books={book_from_url(page.url or "") for page in ctx.pages}
            for book,adapter in (adapters.get("bookmakers") or {}).items():
                if book in existing_books:
                    continue
                entry=str((adapter or {}).get("entry_url") or "").strip()
                if not entry:
                    continue
                try:
                    page=ctx.new_page()
                    page.goto(entry,wait_until="domcontentloaded",timeout=20000)
                except Exception:
                    try:
                        page.close()
                    except Exception:
                        pass
            for pi,page in enumerate(ctx.pages):
                url=page.url or ""; book=book_from_url(url)
                if not book: continue
                try:
                    title=page.title()
                    text=page.locator("body").inner_text(timeout=10000)
                except Exception as e:
                    pages.append({"bookmaker":book,"url":url,"status":"READ_ERROR","error":type(e).__name__})
                    continue
                sha=hashlib.sha256(text.encode("utf-8","ignore")).hexdigest()
                adapter=(adapters.get("bookmakers") or {}).get(book) or {}
                page_rec={
                  "bookmaker":book,"url":url,"title":title,"status":"CAPTURED",
                  "body_sha256":sha,"raw_evidence_path":None,
                  "adapter_status":adapter.get("status","MISSING")
                }
                matching=[c for c in candidates if page_matches_candidate(text,c)]
                if matching:
                    raw_name=f"{now.strftime('%Y%m%dT%H%M%SZ')}_{book}_{ci}_{pi}_{sha[:12]}.txt"
                    raw_path=RAW_ROOT/raw_name
                    raw_path.write_text(text,encoding="utf-8")
                    page_rec["raw_evidence_path"]=str(raw_path.relative_to(ROOT))
                pages.append(page_rec)
                for c in matching:
                    matched.append({
                      "fixture_id":str(c.get("fixture_id") or ""),"match":c.get("match"),"kickoff":c.get("kickoff"),
                      "p_matrix":c.get("p_matrix"),"bookmaker":book,"url":url,
                      "raw_evidence_path":page_rec["raw_evidence_path"],
                      "adapter_status":adapter.get("status","MISSING"),
                      "execution_quote_emitted":False,
                      "blocker":None if adapter.get("status")=="CERTIFIED_EXACT_OVER25" else "BOOKMAKER_ADAPTER_NOT_CERTIFIED"
                    })
        # IMPORTANT: connected via CDP to an externally managed persistent browser.
        # Do not call browser.close(); that would terminate the shared Chrome/Opera process.
    out={
      "schema":"MATRIX_BROWSER_CDP_COLLECTION_V1",
      "generated_at_utc":now.isoformat(),
      "source_audit_generated_at_utc":audit.get("generated_at_utc"),
      "cdp_endpoint":endpoint,
      "candidate_count_in_final_window":len(candidates),
      "authorized_book_pages_captured":len([x for x in pages if x.get("status")=="CAPTURED"]),
      "candidate_page_matches":len(matched),
      "pages":pages,"matches":matched,
      "policy":{
        "raw_capture_is_not_execution_quote":True,
        "site_specific_certified_adapter_required":True,
        "captcha_or_antibot_bypass_forbidden":True,
        "automatic_wagering":False,"real_money":"BLOCKED"
      },
      "status":"PASS_CAPTURED" if pages else "NO_AUTHORIZED_BOOK_PAGES_VISIBLE"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"candidates":len(candidates),"pages":len(pages),"matches":len(matched)},sort_keys=True))

if __name__=="__main__":
    main()
