"""User-authorized Windows CDP tennis calendar observation, browser-first.

Reads only visible links from normal SofaScore/Flashscore pages, never private
API endpoints or disguised requests. Domain/date guard, free research only.
Do NOT read odds, calculate probabilities, mutate any models or bet.
"""
from __future__ import annotations
import argparse,json,re
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")
ROOT=Path("evidence/tennis_calendar_physical")
PROVIDERS={
    "SOFASCORE":{"host":"www.sofascore.com","prefix":"/es/tennis/match/","name":"sofascore_opera_full_link_observations.json"},
    "FLASHSCORE":{"host":"www.flashscore.co","prefix":"/partido/tenis/","name":"flashscore_opera_full_link_observations.json"}
}
LIMIT=1800

def observed(day:str,source:str,records:list,*,page_url:str,page_date_verified:bool,now:datetime)->dict:
    date.fromisoformat(day)
    if source not in PROVIDERS:raise ValueError("UNKNOWN_PROVIDER")
    conf=PROVIDERS[source]
    if not page_date_verified:
        raise ValueError("TARGET_DATE_NOT_VISIBLE_ON_PROVIDER_CALENDAR")
    urls=set();matches=[]
    for row in records[:LIMIT]:
        if not isinstance(row,dict):continue
        url=str(row.get("url") or "")
        p=urlparse(url)
        if p.scheme!="https" or p.hostname!=conf["host"] or not p.path.startswith(conf["prefix"]) or p.username or p.password:
            continue
        if url in urls:continue
        urls.add(url)
        if source=="SOFASCORE":
            ident=re.fullmatch(r"id:(\d+)",p.fragment)
            if not ident:continue
            fields={"source_event_id":ident.group(1),"explicit_target_date_label":False,
                    "visible_local_clock":bool(re.search(r"\b\d{1,2}:\d{2}\b",str(row.get("name") or "")))}
        else:
            mid=parse_qs(p.query).get("mid",[])
            fields={"visible_mid_query":mid[0] if len(mid)==1 and mid[0].isalnum() else None}
        matches.append({"display_name":str(row.get("name") or "")[:280],"url":url,**fields})
    return {"schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
       "source_order":["SOFASCORE","FLASHSCORE","APIS"],
       "target_date_bogota":day,
       "source":source,"source_page_url":page_url,
       "capture_method":"AUTHORIZED_WINDOWS_CDP_VISIBLE_LINKS_WITH_EXACT_DATE_BROWSER_PAGE",
       "collected_at_utc":now.astimezone(timezone.utc).isoformat(),
       "observed_link_count":len(matches),
       "raw_link_occurrences":len(records),
       "coverage_claim":"VISIBLE_LINKS_ONLY_NOT_WORLD_COMPLETE",
       "time_zone_per_event_verified":False,
       "surface_per_event_verified":False,
       "individual_match_date_verified":False,
       "canonical_fixture_export_authorized":False,
       "probability_generation_authorized":False,
       "telegram_signals_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED",
       "matches":matches}

def day_visible(source:str,day:str,text:str):
    d=date.fromisoformat(day)
    candidates=(f"{d.day}/{d.month}/{d.year}",f"{d.day}/{d.month}/{str(d.year)[-2:]}",
       f"{d.day:02d}/{d.month:02d}/{d.year}",f"{d.year}-{d.month:02d}-{d.day:02d}",
       f"{d.day:02d}.{d.month:02d}.{d.year}",f"{d.day}.{d.month}.{d.year}")
    if source=="FLASHSCORE":
        months=("enero","febrero","marzo","abril","mayo","junio","julio",
                "agosto","septiembre","octubre","noviembre","diciembre")
        candidates+=(f"{d.day} de {months[d.month-1]} de {d.year}",)
    return any(x.casefold() in text.casefold() for x in candidates)

def replace_if_not_regressed(root:Path,day:str,source:str,report:dict):
    path=root/ROOT/day/PROVIDERS[source]["name"]
    path.parent.mkdir(parents=True,exist_ok=True)
    old_count=0
    if path.is_file():
        old=json.loads(path.read_text(encoding="utf-8-sig"))
        if old.get("target_date_bogota")==day and old.get("source")==source:
            old_count=int(old.get("observed_link_count") or 0)
    if len(report["matches"])<max(1,old_count):
        return {"source":source,"status":"REJECTED_EMPTY_OR_REGRESSED_BROWSER_RESULT",
                "new":len(report["matches"]),"old":old_count}
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"source":source,"status":"PERSISTED_VISIBLE_BROWSER_LINKS","new":len(report["matches"]),"old":old_count}

def run(root:Path,day:str,endpoint:str):
    from playwright.sync_api import sync_playwright,Error
    date.fromisoformat(day)
    sources=(("SOFASCORE",f"https://www.sofascore.com/es/tennis/{day}"),
             ("FLASHSCORE",f"https://www.flashscore.co/tenis/?d={day}"))
    stats=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=12000)
        if not browser.contexts:raise ValueError("WINDOWS_CDP_NO_CONTEXT")
        for source,url in sources:
            page=browser.contexts[0].new_page()
            try:
                response=page.goto(url,wait_until="domcontentloaded",timeout=18000)
                if response is not None and response.status in (401,403,429):
                    stats.append({"source":source,"status":"PROVIDER_ACCESS_REFUSED","http_status":response.status})
                    continue
                page.wait_for_timeout(1000)
                info=page.evaluate("""() => ({
                  text:String(document.body?.innerText||'').slice(0,12000),
                  links:Array.from(document.querySelectorAll('a[href]'))
                    .filter(a=>a.getClientRects().length>0).slice(0,4500)
                    .map(a=>({url:a.href,name:String(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,300)}))
                })""")
                if not day_visible(source,day,str(info.get("text") or "")):
                    stats.append({"source":source,"status":"BROWSER_VISIBLE_CALENDAR_DATE_NOT_VERIFIED"})
                    continue
                result=observed(day,source,info.get("links") or [],
                   page_url=url,page_date_verified=True,now=datetime.now(timezone.utc))
                stats.append(replace_if_not_regressed(root,day,source,result))
            except (Error,OSError,ValueError,TypeError) as exc:
                stats.append({"source":source,"status":"READ_ONLY_BROWSER_CAPTURE_BLOCKED",
                              "reason_type":type(exc).__name__})
            finally:
                page.close()
    return {"schema":"MATRIX_TENNIS_WINDOWS_BROWSER_CAPTURE_CYCLE_V1",
       "checked_at_utc":datetime.now(timezone.utc).isoformat(),
       "target_date_bogota":day,"provider_results":stats,
       "provider_direct_api_used":False,"model_parameters_modified":False,
       "holdout_admitted":0,"telegram_signal_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--date",default=datetime.now(BOGOTA).date().isoformat())
    p.add_argument("--cdp",default="http://127.0.0.1:9222")
    args=p.parse_args()
    result=run(args.root,args.date,args.cdp)
    path=args.root/"evidence/tennis_calendar_reconciliation/MATRIX_TENNIS_WINDOWS_BROWSER_CAPTURE_CYCLE_LAST.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
