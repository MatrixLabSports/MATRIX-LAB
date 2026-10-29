from __future__ import annotations
import hashlib, json, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Error as PlaywrightError

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

def betano_exact_over25_from_payload(payload:dict[str,Any],home:str,away:str)->dict[str,Any]|None:
    home_n,away_n=norm(home),norm(away)
    def iter_nodes(node:Any):
        if isinstance(node,dict):
            yield node
            for v in node.values():
                yield from iter_nodes(v)
        elif isinstance(node,list):
            for v in node:
                yield from iter_nodes(v)
    id_index={}
    for node in iter_nodes(payload):
        if isinstance(node,dict) and node.get("id") is not None:
            id_index[str(node.get("id"))]=node
    for ev in iter_nodes(payload):
        if not isinstance(ev,dict):
            continue
        participants=ev.get("participants") or ev.get("competitors") or []
        names=[norm((p or {}).get("name") or (p or {}).get("shortName")) for p in participants if isinstance(p,dict)]
        if not names or not any(home_n in n or n in home_n for n in names) or not any(away_n in n or n in away_n for n in names):
            continue
        mids=ev.get("marketIdList") or []
        for mid in mids:
            market=id_index.get(str(mid))
            if not isinstance(market,dict):
                continue
            mname=norm(market.get("name"))
            mtype=str(market.get("type") or "")
            try: mh=float(market.get("handicap"))
            except Exception: mh=None
            if mh!=2.5 or not ("goles totales" in mname or mtype in {"HCTG","OVUN"}):
                continue
            for sid in market.get("selectionIdList") or []:
                sel=id_index.get(str(sid))
                if not isinstance(sel,dict):
                    continue
                try: sh=float(sel.get("handicap"))
                except Exception: sh=None
                if sh==2.5 and "mas de 2 5" in norm(sel.get("name") or sel.get("fullName")) and sel.get("price") is not None:
                    return {
                      "event_id":ev.get("id"),"event_url":ev.get("url"),"event_start_time":ev.get("startTime"),
                      "market_id":market.get("id"),"market_name":market.get("name"),"market_type":mtype,
                      "selection_id":sel.get("id"),"selection_name":sel.get("name"),"price":float(sel.get("price")),
                      "participants":participants,
                    }
    return None

def betano_event_from_payload(payload:dict[str,Any],home:str,away:str)->dict[str,Any]|None:
    home_n,away_n=norm(home),norm(away)
    def walk(node:Any):
        if isinstance(node,dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node,list):
            for v in node:
                yield from walk(v)
    for node in walk(payload):
        if not isinstance(node,dict):
            continue
        participants=node.get("participants") or node.get("competitors") or []
        names=[norm((p or {}).get("name") or (p or {}).get("shortName")) for p in participants if isinstance(p,dict)]
        if not names:
            continue
        if any(home_n in n or n in home_n for n in names) and any(away_n in n or n in away_n for n in names):
            if node.get("id") is not None and node.get("url"):
                return node
    return None

def betano_detail_exact_over25(page,event_url:str,home:str,away:str)->tuple[dict[str,Any]|None,list[str]]:
    ctx=page.context
    diagnostics=[]
    detail_page=None
    captured_json=[]
    try:
        detail_page=ctx.new_page()
        target=event_url if str(event_url).startswith("http") else "https://www.betano.co"+str(event_url)

        def on_response(response):
            try:
                url=str(response.url or "")
                if "betano.co" not in url.casefold():
                    return
                ct=str(response.headers.get("content-type") or "").casefold()
                rtype=str(response.request.resource_type or "")
                if "json" not in ct and rtype not in {"xhr","fetch"}:
                    return
                body=response.json()
                if isinstance(body,(dict,list)):
                    captured_json.append({"url":url,"status":response.status,"resource_type":rtype,"body":body})
            except Exception:
                return

        detail_page.on("response",on_response)
        detail_page.goto(target,wait_until="domcontentloaded",timeout=15000)
        detail_page.wait_for_timeout(2500)

        for rec in captured_json[:100]:
            diagnostics.append(str(rec.get("url") or ""))
            body=rec.get("body")
            if isinstance(body,(dict,list)):
                exact=betano_exact_over25_from_payload(body,home,away)
                if exact:
                    exact["detail_resource_url"]=str(rec.get("url") or "")
                    exact["detail_resource_type"]=rec.get("resource_type")
                    exact["event_detail_page"]=target
                    return exact,diagnostics

        # Secondary bounded fallback for resources that were loaded before listener processing
        resources=detail_page.evaluate("""() => performance.getEntriesByType('resource')
          .filter(r => ['fetch','xmlhttprequest'].includes(String(r.initiatorType||'').toLowerCase()))
          .map(r=>({url:r.name,initiatorType:r.initiatorType}))""")
        seen=set(diagnostics)
        for item in resources[:40]:
            u=str((item or {}).get("url") or "")
            if not u or u in seen or "betano.co" not in u.casefold():
                continue
            seen.add(u)
            try:
                res=detail_page.evaluate("""async (url)=>{
                  const controller=new AbortController();
                  const timer=setTimeout(()=>controller.abort(),2500);
                  try{
                    const r=await fetch(url,{credentials:'include',cache:'no-store',signal:controller.signal});
                    const ct=r.headers.get('content-type')||'';
                    if(!ct.includes('json')) return {url,status:r.status,contentType:ct,body:null};
                    return {url,status:r.status,contentType:ct,body:await r.json()};
                  }catch(e){return {url,error:String(e),body:null};}
                  finally{clearTimeout(timer);}
                }""",u)
            except Exception:
                continue
            diagnostics.append(str((res or {}).get("url") or u))
            body=(res or {}).get("body") if isinstance(res,dict) else None
            if isinstance(body,(dict,list)):
                exact=betano_exact_over25_from_payload(body,home,away)
                if exact:
                    exact["detail_resource_url"]=str((res or {}).get("url") or u)
                    exact["detail_resource_type"]=str((item or {}).get("initiatorType") or "")
                    exact["event_detail_page"]=target
                    return exact,diagnostics
        return None,diagnostics
    finally:
        if detail_page is not None:
            try:
                if not detail_page.is_closed():
                    detail_page.close()
            except Exception:
                pass

def main()->None:
    cfg=load(CONFIG); audit=load(AUDIT); adapters=load(ADAPTERS)
    endpoint=os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT",cfg["browser"]["default_cdp_endpoint"]).strip()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    candidates=candidate_rows(audit,now)
    RAW_ROOT.mkdir(parents=True,exist_ok=True)
    pages=[]; matched=[]; betano_exact_quotes=[]
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
                    page.goto(entry,wait_until="domcontentloaded",timeout=12000)
                except PlaywrightError as e:
                    pages.append({
                      "bookmaker":book,
                      "url":entry,
                      "status":"OPEN_ERROR",
                      "error":type(e).__name__
                    })
                    try:
                        if not page.is_closed():
                            page.close()
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    pages.append({
                      "bookmaker":book,
                      "url":entry,
                      "status":"OPEN_ERROR",
                      "error":type(e).__name__
                    })
                    try:
                        if not page.is_closed():
                            page.close()
                    except Exception:
                        pass
                    continue
            for pi,page in enumerate(list(ctx.pages)):
                try:
                    if page.is_closed():
                        continue
                    url=page.url or ""
                except Exception:
                    continue
                book=book_from_url(url)
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
                text_matching=[c for c in candidates if page_matches_candidate(text,c)]
                structured_probe=(book=="betano" and adapter.get("status")=="CERTIFIED_EXACT_OVER25")
                matching=list(candidates) if structured_probe else text_matching
                page_rec["candidate_match_basis"]="STRUCTURED_API_PROBE" if structured_probe else "VISIBLE_PAGE_TEXT"
                page_rec["visible_text_candidate_matches"]=len(text_matching)
                if text_matching:
                    raw_name=f"{now.strftime('%Y%m%dT%H%M%SZ')}_{book}_{ci}_{pi}_{sha[:12]}.txt"
                    raw_path=RAW_ROOT/raw_name
                    raw_path.write_text(text,encoding="utf-8")
                    page_rec["raw_evidence_path"]=str(raw_path.relative_to(ROOT))
                pages.append(page_rec)
                betano_payloads=[]
                if structured_probe and matching:
                    try:
                        betano_payloads=page.evaluate("""async()=>{
                          const eps=['/api/home/top-events-v2/','/danae-webapi/api/live/overview/latest?includeVirtuals=true&queryLanguageId=8&queryOperatorId=17'];
                          const out=[];
                          for(const endpoint of eps){
                            const controller=new AbortController();
                            const timer=setTimeout(()=>controller.abort(),3000);
                            try{ const r=await fetch(endpoint,{credentials:'include',cache:'no-store',signal:controller.signal}); out.push({endpoint,status:r.status,body:await r.json()}); }
                            catch(e){ out.push({endpoint,error:String(e)}); }
                            finally{clearTimeout(timer);}
                          }
                          return out;
                        }""")
                    except Exception:
                        betano_payloads=[]
                for c in matching:
                    exact=None
                    detail_diagnostics=[]
                    if book=="betano" and betano_payloads:
                        parts=split_match(str(c.get("match") or ""))
                        if parts:
                            home_raw,away_raw=[x.strip() for x in re.split(r"\s+vs\.?\s+",str(c.get("match") or ""),maxsplit=1,flags=re.I)]
                            event_obj=None
                            for payload_rec in betano_payloads:
                                body=payload_rec.get("body") if isinstance(payload_rec,dict) else None
                                if isinstance(body,dict):
                                    exact=betano_exact_over25_from_payload(body,home_raw,away_raw)
                                    if exact:
                                        exact["endpoint"]=payload_rec.get("endpoint")
                                        break
                                    if event_obj is None:
                                        event_obj=betano_event_from_payload(body,home_raw,away_raw)
                            if exact is None and isinstance(event_obj,dict) and event_obj.get("url"):
                                exact,detail_diagnostics=betano_detail_exact_over25(page,str(event_obj.get("url")),home_raw,away_raw)
                                if exact:
                                    exact["endpoint"]="EVENT_DETAIL_PAGE_NETWORK"
                    emitted=bool(exact and float(exact.get("price") or 0)>0)
                    rec={
                      "fixture_id":str(c.get("fixture_id") or ""),"match":c.get("match"),"kickoff":c.get("kickoff"),
                      "p_matrix":c.get("p_matrix"),"bookmaker":book,"url":url,
                      "raw_evidence_path":page_rec["raw_evidence_path"],
                      "adapter_status":adapter.get("status","MISSING"),
                      "execution_quote_emitted":emitted,
                      "blocker":None if emitted else ("EXACT_OVER25_NOT_FOUND" if adapter.get("status")=="CERTIFIED_EXACT_OVER25" else "BOOKMAKER_ADAPTER_NOT_CERTIFIED")
                    }
                    if detail_diagnostics:
                        rec["betano_detail_resources_checked"]=detail_diagnostics[:30]
                    if exact:
                        rec["exact_quote"]=exact
                        betano_exact_quotes.append({**rec})
                    matched.append(rec)
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
      "betano_exact_quote_count":len(betano_exact_quotes),
      "pages":pages,"matches":matched,"betano_exact_quotes":betano_exact_quotes,
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
    zero_diag=[]
    if not betano_exact_quotes:
        for rec in matched:
            if rec.get("bookmaker")=="betano":
                zero_diag.append({
                  "fixture_id":rec.get("fixture_id"),
                  "match":rec.get("match"),
                  "kickoff":rec.get("kickoff"),
                  "blocker":rec.get("blocker"),
                  "url":rec.get("url"),
                  "betano_detail_resources_checked":rec.get("betano_detail_resources_checked") or []
                })
    print(json.dumps({
      "status":out["status"],"candidates":len(candidates),"pages":len(pages),"matches":len(matched),
      "betano_exact_quote_count":len(betano_exact_quotes),
      "betano_exact_quote_first":(betano_exact_quotes[0] if betano_exact_quotes else None),
      "betano_zero_diagnostics":zero_diag
    },sort_keys=True,ensure_ascii=False))

if __name__=="__main__":
    main()
