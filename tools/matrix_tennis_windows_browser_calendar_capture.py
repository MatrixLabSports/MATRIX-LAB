"""User-authorized Windows CDP tennis calendar observation, browser-first.

Reads only visible links from normal SofaScore/Flashscore pages, never private
API endpoints or disguised requests. Domain/date guard, free research only.
Do NOT read odds, calculate probabilities, mutate any models or bet.
"""
from __future__ import annotations
import argparse,json,re
from datetime import date,datetime,timedelta,timezone
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
    """A rendered, full-year date marker is required, never just a URL query.

    Match exact numeric date tokens or Spanish full-year date labels. Reject
    substring collisions, e.g. the fifth must not match the fifteenth.
    """
    d=date.fromisoformat(day)
    months=("enero","febrero","marzo","abril","mayo","junio","julio",
            "agosto","septiembre","octubre","noviembre","diciembre")
    month=months[d.month-1]
    variants=(
        rf"{d.day:02d}/{d.month:02d}/{d.year}",
        rf"{d.day}/{d.month}/{d.year}",
        rf"{d.day:02d}/{d.month:02d}/{str(d.year)[-2:]}",
        rf"{d.day}/{d.month}/{str(d.year)[-2:]}",
        rf"{d.day:02d}\.{d.month:02d}\.{d.year}",
        rf"{d.day}\.{d.month}\.{d.year}",
        rf"{d.year}-{d.month:02d}-{d.day:02d}",
        rf"{d.day}\s+de\s+{month}\s+de\s+{d.year}",
    )
    return bool(re.search(
        r"(?<![0-9])(?:"+"|".join(variants)+r")(?![0-9])",
        str(text),flags=re.IGNORECASE))


def date_evidence(source:str,day:str,*,controls:list[str],visible_text:str)->str|None:
    """Prefer visible calendar controls to avoid dates inside other page news."""
    if source not in PROVIDERS:raise ValueError("UNKNOWN_PROVIDER")
    for marker in controls[:800]:
        if day_visible(source,day,str(marker)):
            return "VISIBLE_CALENDAR_CONTROL_FULL_YEAR"
    # Flashscore's daily view has a dedicated selected-day control. A news
    # headline for tomorrow must NOT be mistaken for the selected calendar day.
    if source == "FLASHSCORE":
        return None
    # SofaScore renders dates in its actual visible event list. This remains
    # link discovery, NOT an individual-match kickoff/surface certificate.
    if day_visible(source,day,visible_text[:200000]):
        return "VISIBLE_BODY_FULL_YEAR_DATE"
    return None

def replace_if_not_regressed(root:Path,day:str,source:str,report:dict):
    """Keep every real nonempty dated snapshot, even when visible coverage shrinks.

    A lower link count is not proof of tampering: schedules change and sites
    paginate. Preserve the previous bytes by digest before advancing the
    current pointer. Empty/older/unauthorized captures still fail closed.
    """
    import hashlib
    if source not in PROVIDERS or report.get("source") != source or report.get("target_date_bogota") != day:
        raise ValueError("BROWSER_CAPTURE_SOURCE_OR_DATE_MISMATCH")
    if (report.get("schema") != "MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1"
        or report.get("canonical_fixture_export_authorized") is not False
        or report.get("probability_generation_authorized") is not False
        or report.get("real_money") != "BLOCKED"):
        raise ValueError("BROWSER_CAPTURE_GOVERNANCE_MISMATCH")
    path=root/ROOT/day/PROVIDERS[source]["name"]
    path.parent.mkdir(parents=True,exist_ok=True)
    matches=report.get("matches")
    if not isinstance(matches,list) or not matches or len(matches)!=report.get("observed_link_count"):
        return {"source":source,"status":"REJECTED_EMPTY_OR_INVALID_BROWSER_RESULT",
                "new":len(matches) if isinstance(matches,list) else 0}
    incoming=datetime.fromisoformat(str(report["collected_at_utc"]).replace("Z","+00:00"))
    if incoming.tzinfo is None or incoming.utcoffset() is None:
        raise ValueError("BROWSER_CAPTURE_CLOCK_WITHOUT_TIMEZONE")
    old_count=0
    if path.is_file():
        old_bytes=path.read_bytes()
        old=json.loads(old_bytes.decode("utf-8-sig"))
        if old.get("target_date_bogota")!=day or old.get("source")!=source:
            raise ValueError("EXISTING_BROWSER_CAPTURE_IDENTITY_MISMATCH")
        old_count=int(old.get("observed_link_count") or 0)
        previous=datetime.fromisoformat(str(old["collected_at_utc"]).replace("Z","+00:00"))
        if previous.tzinfo is None or previous.utcoffset() is None:
            raise ValueError("EXISTING_BROWSER_CAPTURE_CLOCK_WITHOUT_TIMEZONE")
        if incoming<=previous:
            return {"source":source,"status":"REJECTED_STALE_BROWSER_RESULT",
                    "new":len(matches),"old":old_count}
        digest=hashlib.sha256(old_bytes).hexdigest()
        archive=path.parent/"archive"/(source.lower()+"_"+digest+".json")
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists():
            if archive.read_bytes()!=old_bytes:
                raise ValueError("BROWSER_ARCHIVE_HASH_COLLISION")
        else:
            archive.write_bytes(old_bytes)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"source":source,"status":"PERSISTED_VISIBLE_BROWSER_LINKS",
            "new":len(matches),"old":old_count,
            "previous_snapshot_archived":bool(old_count)}

def run(root:Path,day:str,endpoint:str):
    from playwright.sync_api import sync_playwright,Error
    date.fromisoformat(day)
    tomorrow=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
    # Today's and tomorrow's calendars are independently verified against
    # their rendered dates. Never reuse one page's date evidence for another.
    calendar_days=(day,tomorrow)
    stats=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=12000)
        if not browser.contexts:raise ValueError("WINDOWS_CDP_NO_CONTEXT")
        for target_day in calendar_days:
            sources=(("SOFASCORE",f"https://www.sofascore.com/es/tennis/{target_day}"),
                     ("FLASHSCORE",(
                        "https://www.flashscore.co/tenis/manana/"
                        if date.fromisoformat(target_day)==datetime.now(BOGOTA).date()+timedelta(days=1)
                        else f"https://www.flashscore.co/tenis/?d={target_day}"
                     )))
            for source,url in sources:
                page=browser.contexts[0].new_page()
                try:
                    response=page.goto(url,wait_until="domcontentloaded",timeout=18000)
                    if response is not None and response.status in (401,403,429):
                        stats.append({"date":target_day,"source":source,
                                      "status":"PROVIDER_ACCESS_REFUSED","http_status":response.status})
                        continue
                    result=None
                    observed_marker=None
                    text_size=0
                    visible_links=0
                    for attempt in range(3):
                        page.wait_for_timeout(1200 if attempt==0 else 2000)
                        info=page.evaluate("""() => ({
                          text:String(document.body?.innerText||'').slice(0,200000),
                          dateControls:Array.from(document.querySelectorAll(
                            '[aria-haspopup="listbox"],[role="combobox"],' +
                            '[class*="calendar__datepicker"],[class*="calendar__navigation"],' +
                            'button,[role="button"],time,input,[aria-label],[title]'
                          )).filter(a=>a.getClientRects().length>0).slice(0,5000).map(
                            a=>String(a.getAttribute('aria-label')||
                              a.getAttribute('title')||a.getAttribute('datetime')||
                              a.getAttribute('data-date')||a.innerText||'').trim().slice(0,180)
                          ),
                          links:Array.from(document.querySelectorAll('a[href]'))
                            .filter(a=>a.getClientRects().length>0).slice(0,4500)
                            .map(a=>({url:a.href,name:String(a.innerText||
                              a.getAttribute('aria-label')||'').trim().slice(0,300)}))
                        })""")
                        text_size=len(str(info.get("text") or ""))
                        visible_links=len(info.get("links") or [])
                        observed_marker=date_evidence(
                            source,target_day,controls=info.get("dateControls") or [],
                            visible_text=str(info.get("text") or ""))
                        if observed_marker:
                            result=observed(target_day,source,info.get("links") or [],
                              page_url=url,page_date_verified=True,now=datetime.now(timezone.utc))
                            # The date verifies only the rendered calendar context,
                            # never each match's kickoff, surface or identity.
                            result["rendered_calendar_date_evidence"]=observed_marker
                            result["selected_day_control_required"]=(source=="FLASHSCORE")
                            break
                    if result is None:
                        stats.append({"date":target_day,"source":source,
                          "status":"BROWSER_VISIBLE_CALENDAR_DATE_NOT_VERIFIED",
                          "bounded_retries":3,"visible_text_characters":text_size,
                          "visible_anchors":visible_links,
                          "source_url_date_is_not_admission_proof":True})
                        continue
                    receipt=replace_if_not_regressed(root,target_day,source,result)
                    stats.append({"date":target_day,**receipt,
                                  "rendered_calendar_date_evidence":observed_marker})
                except (Error,OSError,ValueError,TypeError) as exc:
                    stats.append({"date":target_day,"source":source,
                                  "status":"READ_ONLY_BROWSER_CAPTURE_BLOCKED",
                                  "reason_type":type(exc).__name__})
                finally:
                    page.close()
    return {"schema":"MATRIX_TENNIS_WINDOWS_BROWSER_CAPTURE_CYCLE_V1",
       "checked_at_utc":datetime.now(timezone.utc).isoformat(),
       "target_date_bogota":day,"capture_dates_bogota":list(calendar_days),
       "provider_results":stats,
       "source_first_then_free_api_only":True,"paid_api_used":False,
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
