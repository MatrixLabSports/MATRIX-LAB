from __future__ import annotations
import hashlib, json, os, re, unicodedata
from datetime import datetime, timezone, timedelta
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
    # Prefer the governed discovery inventory. Legacy blocker records are NOT
    # a complete intake: they omit candidates without pre_send_gate entries.
    intake=audit.get("browser_prematch_candidate_rows")
    if isinstance(intake,list):
        try:
            generated=datetime.fromisoformat(str(audit.get("generated_at_utc")).replace("Z","+00:00"))
            age=(now.astimezone(timezone.utc)-generated.astimezone(timezone.utc)).total_seconds()
            if not (-120<=age<=35*60):
                return []
        except (ValueError,TypeError,OverflowError,AttributeError):
            return []
        rows=intake
    else:
        rows=audit.get("records") or []
    out=[]
    for r in rows:
        if not isinstance(r,dict): continue
        kickoff=r.get("kickoff")
        try:
            kd=datetime.fromisoformat(str(kickoff).replace("Z","+00:00"))
            if kd.tzinfo is None:
                continue
            kd=kd.astimezone(timezone.utc)
            probability=float(r.get("p_matrix"))
        except (TypeError, ValueError, OverflowError):
            continue
        sec=(kd-now).total_seconds()
        if not (0<sec<=120*60): continue
        if not (0.60<=probability<1.0): continue
        if split_match(str(r.get("match") or "")) is None: continue
        out.append(r)
    return sorted(out,key=lambda x:x["kickoff"])

def independent_research_quote_targets(now:datetime,root:Path=ROOT)->list[dict[str,Any]]:
    """Separate read-only quote lookup for triple-verified fixtures, NEVER signal candidates.

    No research probability is promoted into p_matrix. All three underlying
    fixtures and browser identity reports must be authentic and date scoped.
    """
    if now.tzinfo is None:
        raise ValueError("RESEARCH_TARGETS_REQUIRE_AWARE_CLOCK")
    day=now.astimezone(timezone(timedelta(hours=-5))).date()
    output=[]
    for offset in (0,1):
        date=(day+timedelta(days=offset)).isoformat()
        folder=root/"evidence"/"football_world_inventory"/date
        files={
            "source":folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
            "sofa":folder/"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
            "flash":folder/"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
        }
        if not all(p.is_file() for p in files.values()):
            continue
        try:
            docs={k:load(p) for k,p in files.items()}
            source,sofa,flash=(docs[k] for k in ("source","sofa","flash"))
            if any(d.get("real_money")!="BLOCKED" or d.get("signal_generation_authorized") is not False
                   for d in docs.values()):
                continue
            if (source.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
                or source.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE"
                or source.get("source")!="FOOTBALL_DATA_ORG"
                or source.get("target_date_bogota")!=date
                or sofa.get("target_date_bogota")!=date
                or flash.get("target_date_bogota")!=date
                or flash.get("flashscore_verified") is not True
                or flash.get("sofascore_verified") is not True):
                continue
            generated=datetime.fromisoformat(str(source["generated_at_utc"]).replace("Z","+00:00"))
            age=(now.astimezone(timezone.utc)-generated.astimezone(timezone.utc)).total_seconds()
            if not (0<=age<=36*3600):
                continue
            sr=source.get("fixtures")
            so=sofa.get("matched")
            fl=flash.get("matched")
            if not all(isinstance(x,list) for x in (sr,so,fl)):
                continue
            if (len(sr)!=source.get("fixture_count")
                or len(so)!=sofa.get("matched_count")
                or len(fl)!=flash.get("matched_count")):
                continue
            def index(rows,key):
                ids=[str(r.get(key) or "") for r in rows if isinstance(r,dict)]
                if len(ids)!=len(rows) or not all(ids) or len(set(ids))!=len(ids):
                    raise ValueError("RESEARCH_DUPLICATE_OR_MISSING_SOURCE_ID")
                return dict(zip(ids,rows))
            src=index(sr,"source_fixture_id")
            sofa_ids=index(so,"fixture_id")
            flash_ids=index(fl,"source_fixture_id")
            used_events=set()
            for fid,fr in sorted(flash_ids.items()):
                a,b=src.get(fid),sofa_ids.get(fid)
                if a is None or b is None:
                    continue
                if (fr.get("three_source_calendar_identity_verified") is not True
                    or b.get("identity_time_and_teams_verified") is not True
                    or a.get("source")!="FOOTBALL_DATA_ORG"
                    or a.get("signal_generation_authorized") is not False
                    or a.get("api_football_fixture_id") is not None):
                    continue
                sofa_event=str(b.get("sofascore_event_id") or "")
                flash_event=str(fr.get("flashscore_mid") or "")
                if (not sofa_event or not flash_event
                    or sofa_event!=str(fr.get("sofascore_event_id") or "")
                    or (sofa_event,flash_event) in used_events):
                    continue
                used_events.add((sofa_event,flash_event))
                kickoff=a.get("kickoff_utc")
                if kickoff!=b.get("kickoff_utc") or kickoff!=fr.get("kickoff_utc"):
                    continue
                kd=datetime.fromisoformat(str(kickoff).replace("Z","+00:00"))
                if kd.tzinfo is None or kd.astimezone(timezone(timedelta(hours=-5))).date().isoformat()!=date:
                    continue
                delta=(kd.astimezone(timezone.utc)-now.astimezone(timezone.utc)).total_seconds()
                if not 0<delta<=120*60:
                    continue
                home=str(a.get("home") or "").strip()
                away=str(a.get("away") or "").strip()
                if not home or not away or norm(home)==norm(away):
                    continue
                output.append({
                    "fixture_id":"FOOTBALL_DATA_ORG:"+fid,
                    "match":home+" vs "+away,
                    "kickoff":kd.isoformat(),
                    "p_matrix":None,
                    "research_only":True,
                    "triple_source_calendar_identity_verified":True,
                    "production_probability_authorized":False,
                    "telegram_signal_authorized":False,
                    "calendar_source_date":date,
                    "sofascore_event_id":sofa_event,
                    "flashscore_mid":flash_event,
                })
        except (ValueError,TypeError,KeyError,OverflowError,OSError,json.JSONDecodeError):
            continue
    return sorted(output,key=lambda x:(x["kickoff"],x["fixture_id"]))


def quote_eligibility(exact:dict[str,Any]|None, candidate:dict[str,Any], adapter_status:str, now:datetime)->tuple[bool,str|None]:
    """Pure collector-level guard; does not certify quote freshness or Telegram delivery."""
    if adapter_status!="CERTIFIED_EXACT_OVER25":
        return False,"BOOKMAKER_ADAPTER_NOT_CERTIFIED"
    try:
        price=float((exact or {}).get("price"))
    except (TypeError,ValueError,OverflowError):
        return False,"EXACT_OVER25_NOT_FOUND"
    if not (0<price<float("inf")):
        return False,"EXACT_OVER25_NOT_FOUND"
    if price<=1.50:
        return False,"ODDS_BELOW_MIN_1_50"
    try:
        p=float(candidate.get("p_matrix"))
    except (TypeError,ValueError,OverflowError):
        return False,"NO_SIGNAL_ECONOMIC_GATE"
    if not (0<p<1 and p*price-1.0>=0.05):
        return False,"NO_SIGNAL_ECONOMIC_GATE"
    try:
        kickoff=datetime.fromisoformat(str(candidate.get("kickoff")).replace("Z","+00:00"))
        if kickoff.tzinfo is None:
            return False,"NO_SIGNAL_KICKOFF"
        kickoff=kickoff.astimezone(timezone.utc)
    except (TypeError,ValueError,OverflowError):
        return False,"NO_SIGNAL_KICKOFF"
    if now.tzinfo is None or now.astimezone(timezone.utc)>=kickoff:
        return False,"NO_SIGNAL_KICKOFF"
    return True,None


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

def betano_dom_exact_over25(detail_page,event_url:str,home:str,away:str)->dict[str,Any]|None:
    try:
        title=norm(detail_page.title())
        if norm(home) not in title or norm(away) not in title:
            return None
        role_hits=detail_page.get_by_role(
            "button",
            name=re.compile(r"Bet on M[aá]s de\s*2[\.,]5 with odds\s*[0-9]+(?:[\.,][0-9]+)?",re.I),
        )
        for i in range(min(role_hits.count(),20)):
            btn=role_hits.nth(i)
            try:
                aria=btn.get_attribute("aria-label") or ""
                txt=(btn.inner_text(timeout=1000) or "").strip()
                market_text=btn.evaluate(r"""el=>{
                  let cur=el;
                  for(let depth=0;depth<16&&cur;depth++,cur=cur.parentElement){
                    const t=(cur.innerText||'').trim();
                    if(/Goles totales\s+M[aá]s\/Menos/i.test(t)) return t.slice(0,3000);
                  }
                  return null;
                }""")
            except Exception:
                continue
            if not market_text:
                continue
            combined=(aria+" "+txt).strip()
            m=re.search(r"odds\s*([0-9]+(?:[\.,][0-9]+)?)",combined,re.I)
            if not m:
                continue
            price=float(m.group(1).replace(",","."))
            em=re.search(r"/(\d{6,})/?$",str(event_url).rstrip("/"))
            return {
              "event_id":em.group(1) if em else None,
              "event_url":str(event_url),
              "participants":[home,away],
              "market_id":None,
              "market_name":"Goles totales Más/Menos",
              "market_type":"DOM_EVENT_MARKET",
              "handicap":2.5,
              "selection_id":None,
              "selection_name":"Más de 2.5",
              "price":price,
              "endpoint":"EVENT_DETAIL_ACCESSIBLE_ROLE_BUTTON",
              "binding_evidence":"EVENT_URL+PAGE_TITLE+BOTH_TEAMS+MARKET_CONTAINER+ACCESSIBLE_BUTTON_NAME",
              "read_only":True,
              "dom_aria":aria,
              "dom_text":txt,
              "market_text":market_text[:1200]
            }
    except Exception:
        return None
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
        detail_page.wait_for_timeout(1500)

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
        try:
            detail_page.wait_for_function(
                """() => [...document.querySelectorAll('button')].some(el => {
                  const a=(el.getAttribute('aria-label')||'')+' '+(el.innerText||'');
                  if(!/M[aá]s de\\s*2[\\.,]5/i.test(a)) return false;
                  let cur=el;
                  for(let d=0;d<14&&cur;d++,cur=cur.parentElement){
                    if(/Goles totales\\s+M[aá]s\\/Menos/i.test((cur.innerText||''))) return true;
                  }
                  return false;
                })""",
                timeout=8000
            )
        except Exception:
            diagnostics.append("DOM_OVER25_WAIT_TIMEOUT")
        dom_exact=betano_dom_exact_over25(detail_page,event_url,home,away)
        if dom_exact:
            diagnostics.append("DOM_EVENT_MARKET_OVER25")
            return dom_exact,diagnostics
        try:
            dom_probe=detail_page.evaluate("""() => ({
              title:document.title,
              button_count:document.querySelectorAll('button').length,
              over25_buttons:[...document.querySelectorAll('button')]
                .map(el=>({aria:el.getAttribute('aria-label')||'',text:(el.innerText||'').trim()}))
                .filter(x=>/2[\\.,]5/.test(x.aria+' '+x.text)).slice(0,12)
            })""")
            diagnostics.append("DOM_PROBE:"+json.dumps(dom_probe,ensure_ascii=False,separators=(',',':')))
        except Exception:
            diagnostics.append("DOM_PROBE_ERROR")
        return None,diagnostics
    finally:
        if detail_page is not None:
            try:
                if not detail_page.is_closed():
                    detail_page.close()
            except Exception:
                pass

def persist_betano_physical_quote(rec:dict[str,Any],captured_at:datetime)->str|None:
    exact=rec.get("exact_quote") if isinstance(rec,dict) else None
    if not isinstance(exact,dict):
        return None
    try:
        price=float(exact.get("price") or 0)
    except Exception:
        return None
    if price<=1.0:
        return None
    fixture_id=str(rec.get("fixture_id") or "").strip()
    kickoff=str(rec.get("kickoff") or "").strip()
    if not fixture_id or not kickoff:
        return None
    try:
        kickoff_dt=datetime.fromisoformat(kickoff.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:
        return None
    if captured_at>=kickoff_dt:
        return None
    day=kickoff_dt.strftime("%Y%m%d")
    root=ROOT/"evidence"/"football_world_inventory"/day
    root.mkdir(parents=True,exist_ok=True)
    path=root/f"MATRIX_BETANO_QUOTE_{fixture_id}.json"
    payload={
      "schema":"MATRIX_PHYSICAL_BOOK_QUOTE_V1",
      "fixture_id":fixture_id,
      "match":rec.get("match"),
      "market":"Más de 2.5 goles",
      "house":"Betano",
      "decimal_odds":price,
      "captured_at_utc":captured_at.isoformat(),
      "kickoff_utc":kickoff_dt.isoformat(),
      "p_matrix":rec.get("p_matrix"),
      "source":"MATRIX_SELF_HOSTED_BROWSER_QUOTE_COLLECTOR",
      "source_bookmaker":"betano",
      "event_id":exact.get("event_id"),
      "event_url":exact.get("event_url"),
      "market_name":exact.get("market_name"),
      "selection_name":exact.get("selection_name"),
      "binding_evidence":exact.get("binding_evidence"),
      "read_only":exact.get("read_only") is True,
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }
    path.write_text(json.dumps(payload,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    return str(path.relative_to(ROOT))

def candidate_pipeline_diagnostic(audit:dict[str,Any],now:datetime,root:Path=ROOT)->dict[str,Any]:
    """Read-only provenance; zero blocker rows are NOT proof of zero canonical fixtures."""
    if now.tzinfo is None:
        raise ValueError("MATRIX_DIAGNOSTIC_REQUIRES_TZ_AWARE_CLOCK")
    records=audit.get("records")
    audit_rows=len(records) if isinstance(records,list) else None
    intake=audit.get("browser_prematch_candidate_rows")
    intake_rows=len(intake) if isinstance(intake,list) else None
    audit_timestamp=audit.get("generated_at_utc")
    age_seconds=None
    try:
        at=datetime.fromisoformat(str(audit_timestamp).replace("Z","+00:00"))
        if at.tzinfo is not None:
            age_seconds=int((now.astimezone(timezone.utc)-at.astimezone(timezone.utc)).total_seconds())
    except (ValueError,TypeError,OverflowError):
        pass
    local_day=now.astimezone(timezone(timedelta(hours=-5))).date()
    inventory=[]
    for offset in (0,1):
        day=(local_day+timedelta(days=offset)).isoformat()
        football=root/"evidence"/"api_football"/"daily_prematch_reports"/day
        inventory.append({
            "date_bogota":day,
            "football_directory_exists":football.is_dir(),
            "browser_physical_files":len(list(football.glob("browser_physical_verification/*.json"))),
            "shadow_quote_freeze_files":len(list(football.glob("shadow_quote_freeze/*.json"))),
            "over25_shadow_ev_files":len(list(football.glob("over25_shadow_ev/*.json"))),
        })
    if audit_rows is None:
        state="INVALID_AUDIT_RECORDS_FIELD"
    elif age_seconds is None or age_seconds < -120 or age_seconds > 35*60:
        state="AUDIT_TIMESTAMP_UNVERIFIED_OR_STALE"
    elif intake_rows is not None and intake_rows>0:
        state="CANONICAL_BROWSER_INTAKE_PRESENT"
    elif audit_rows==0:
        state="NO_BLOCKER_ROWS_NOT_PROOF_OF_ZERO_CANONICAL_FIXTURES"
    elif not candidate_rows(audit,now):
        state="BLOCKER_ROWS_FILTERED_BY_PREMATCH_PROBABILITY_OR_IDENTITY"
    else:
        state="BLOCKER_ROWS_AVAILABLE_FOR_BROWSER_MATCHING"
    return {
        "schema":"MATRIX_BROWSER_CANDIDATE_PIPELINE_DIAGNOSTIC_V1",
        "status":state,
        "audit_generated_at_utc":audit_timestamp,
        "audit_age_seconds":age_seconds,
        "audit_blocker_record_count":audit_rows,
        "canonical_browser_intake_record_count":intake_rows,
        "browser_intake_present":isinstance(intake,list),
        "canonical_source_inventory":inventory,
        "missing_is_not_zero":True,
        "audit_is_not_all_candidate_inventory":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main()->None:
    cfg=load(CONFIG); audit=load(AUDIT); adapters=load(ADAPTERS)
    endpoint=os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT",cfg["browser"]["default_cdp_endpoint"]).strip()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    candidates=candidate_rows(audit,now)
    research_targets=independent_research_quote_targets(now)
    browser_targets=candidates+research_targets
    pipeline_diagnostic=candidate_pipeline_diagnostic(audit,now)
    RAW_ROOT.mkdir(parents=True,exist_ok=True)
    pages=[]; matched=[]; betano_exact_quotes=[]; betano_research_quotes=[]
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
                text_matching=[c for c in browser_targets if page_matches_candidate(text,c)]
                structured_probe=(book=="betano" and adapter.get("status")=="CERTIFIED_EXACT_OVER25")
                matching=list(browser_targets) if structured_probe else text_matching
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
                    emitted,blocker=quote_eligibility(exact,c,adapter.get("status","MISSING"),now)
                    if c.get("research_only") is True:
                        emitted=False
                        blocker="RESEARCH_ONLY_NO_GOVERNED_P_MATRIX"
                    rec={
                      "fixture_id":str(c.get("fixture_id") or ""),"match":c.get("match"),"kickoff":c.get("kickoff"),
                      "p_matrix":c.get("p_matrix"),"bookmaker":book,"url":url,
                      "raw_evidence_path":page_rec["raw_evidence_path"],
                      "adapter_status":adapter.get("status","MISSING"),
                      "execution_quote_emitted":emitted,
                      "research_only":c.get("research_only") is True,
                      "telegram_signal_authorized":False,
                      "blocker":blocker
                    }
                    if detail_diagnostics:
                        rec["betano_detail_resources_checked"]=detail_diagnostics[:30]
                        rec["betano_detail_diagnostics_tail"]=detail_diagnostics[-8:]
                    if exact:
                        rec["exact_quote"]=exact
                        if c.get("research_only") is True:
                            betano_research_quotes.append({**rec})
                        else:
                            betano_exact_quotes.append({**rec})
                    matched.append(rec)
        # IMPORTANT: connected via CDP to an externally managed persistent browser.
        # Do not call browser.close(); that would terminate the shared Chrome/Opera process.
    canonical_betano_quote_paths=[]
    for rec in betano_exact_quotes:
        pth=persist_betano_physical_quote(rec,now)
        if pth:
            canonical_betano_quote_paths.append(pth)
    out={
      "schema":"MATRIX_BROWSER_CDP_COLLECTION_V1",
      "generated_at_utc":now.isoformat(),
      "source_audit_generated_at_utc":audit.get("generated_at_utc"),
      "cdp_endpoint":endpoint,
      "candidate_count_in_final_window":len(candidates),
      "research_only_quote_target_count":len(research_targets),
      "authorized_book_pages_captured":len([x for x in pages if x.get("status")=="CAPTURED"]),
      "candidate_page_matches":len([r for r in matched if not r.get("research_only")]),
      "research_only_page_matches":len([r for r in matched if r.get("research_only")]),
      "betano_exact_quote_count":len(betano_exact_quotes),
      "research_only_betano_quote_count":len(betano_research_quotes),
      "canonical_betano_quote_paths":canonical_betano_quote_paths,
      "pages":pages,"matches":matched,"betano_exact_quotes":betano_exact_quotes,
      "research_only_betano_quotes":betano_research_quotes,
      "candidate_pipeline_diagnostic":pipeline_diagnostic,
      "policy":{
        "raw_capture_is_not_execution_quote":True,
        "independent_research_never_persists_canonical_quotes":True,
        "independent_research_never_authorizes_signals":True,
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
      "research_only_quote_target_count":len(research_targets),
      "research_only_betano_quote_count":len(betano_research_quotes),
      "betano_exact_quote_first":(betano_exact_quotes[0] if betano_exact_quotes else None),
      "canonical_betano_quote_paths":canonical_betano_quote_paths,
      "betano_zero_diagnostics":zero_diag,
      "candidate_pipeline_diagnostic":pipeline_diagnostic
    },sort_keys=True,ensure_ascii=False))

if __name__=="__main__":
    main()
