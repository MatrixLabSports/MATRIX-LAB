"""Browser-only free tennis calendar collection for MATRIX Windows CDP.

Uses only normal public SofaScore/Flashscore tennis pages. Stores a bounded
link inventory, NOT verified schedule, surface, identities or model forecasts.
It never modifies betting tabs, frozen holdouts or creates automated wagers.
"""
from __future__ import annotations
import argparse,json,os,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT=Path("evidence/tennis_calendar_physical")
MAX_MATCHES=1800
SOURCES={
 "SOFASCORE":{
   "url":lambda d:"https://www.sofascore.com/es/tennis/"+d,
   "domain":"sofascore.com","segment":"/tennis/match/",
   "filename":"sofascore_opera_full_link_observations.json"},
 "FLASHSCORE":{
   "url":lambda d:"https://www.flashscore.co/tenis/?d="+d,
   "domain":"flashscore.co","segment":"/partido/tenis/",
   "filename":"flashscore_opera_full_link_observations.json"},
}

def source_match(url:str,source:str)->bool:
    if not isinstance(url,str) or len(url)>1200:return False
    parsed=urlparse(url)
    domain=SOURCES[source]["domain"]
    return bool(parsed.scheme=="https" and parsed.hostname in (domain,"www."+domain)
                and parsed.username is None and parsed.password is None
                and SOURCES[source]["segment"] in parsed.path)

def snapshot(*,source:str,day:str,rows:list[dict],page_url:str,captured:str)->dict:
    if source not in SOURCES:raise ValueError("UNSUPPORTED_TENNIS_PROVIDER")
    if page_url!=SOURCES[source]["url"](day):
        raise ValueError("SOURCE_PAGE_DATE_SCOPE_MISMATCH")
    unique={}
    for row in rows:
        url=row.get("url")
        if not source_match(url,source):continue
        if len(unique)>=MAX_MATCHES:raise ValueError("CALENDAR_SNAPSHOT_TOO_MANY_MATCHES")
        if url not in unique:
            unique[url]={"display_name":str(row.get("display_name") or "")[:300],
                         "url":url}
            if source=="SOFASCORE":
                event_id=re.search(r"#id:(\d+)",url)
                unique[url]["source_event_id"]=event_id.group(1) if event_id else None
            else:
                mid=re.search(r"[?&]mid=([^&#]+)",url)
                unique[url]["visible_mid_query"]=mid.group(1) if mid else None
    return {
      "schema":"MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
      "source":source,"source_page_url":page_url,
      "target_date_bogota":day,
      "collected_at_utc":captured,
      "capture_method":"Windows read-only CDP public page anchors; calendar-level scope only",
      "observed_link_count":len(unique),
      "coverage_claim":"VISIBLE_LINKS_ONLY_NOT_WORLD_COMPLETE",
      "individual_match_date_verified":False,
      "time_zone_per_event_verified":False,
      "surface_per_event_verified":False,
      "provider_event_identity_certified":False,
      "canonical_fixture_export_authorized":False,
      "probability_generation_authorized":False,
      "telegram_signals_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED",
      "matches":list(unique.values()),
    }

def collect(*,day:str,endpoint:str)->dict:
    from playwright.sync_api import sync_playwright
    evidence={"schema":"MATRIX_TENNIS_CDP_CALENDAR_CAPTURE_RECEIPT_V1",
      "target_date_bogota":day,
      "checked_at_utc":datetime.now(timezone.utc).isoformat(),
      "source_observations":[],"paid_api_calls":0,
      "models_modified":False,"telegram_signal_authorized":False,
      "real_money":"BLOCKED"}
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=12000)
        contexts=browser.contexts
        if not contexts:
            evidence["status"]="BLOCKED_NO_BROWSER_CONTEXT"
            return evidence
        ctx=contexts[0]
        for source,config in SOURCES.items():
            out=ROOT/day/config["filename"]
            if out.is_file():
                try:
                    old=json.loads(out.read_text(encoding="utf-8"))
                    if (old.get("schema")=="MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1" and
                        old.get("source")==source and
                        old.get("target_date_bogota")==day and
                        old.get("observed_link_count",0)>0):
                        evidence["source_observations"].append({
                            "source":source,"status":"REUSED_ARCHIVED_AUTHENTIC_CAPTURE",
                            "observed_link_count":old["observed_link_count"]})
                        continue
                except (OSError,ValueError,TypeError):
                    pass
            url=config["url"](day)
            page=ctx.new_page()
            try:
                page.goto(url,wait_until="domcontentloaded",timeout=25000)
                page.wait_for_timeout(2500)
                if not page.url.startswith(url.split("?")[0]):
                    raise ValueError("UNEXPECTED_BROWSER_REDIRECT")
                anchors=page.locator('a[href*="'+config["segment"]+'"]')
                rows=[]
                count=min(anchors.count(),MAX_MATCHES+1)
                if count>MAX_MATCHES:raise ValueError("CALENDAR_TOO_LARGE")
                for i in range(count):
                    anchor=anchors.nth(i)
                    href=anchor.get_attribute("href")
                    if not href:continue
                    if href.startswith("/"):
                        href="https://www."+config["domain"]+href
                    if source_match(href,source):
                        rows.append({"url":href,"display_name":anchor.inner_text(timeout=1500)})
                record=snapshot(source=source,day=day,rows=rows,
                    page_url=url,captured=datetime.now(timezone.utc).isoformat())
                if not record["observed_link_count"]:
                    evidence["source_observations"].append({
                        "source":source,"status":"BLOCKED_ZERO_VISIBLE_AUTHENTIC_LINKS"})
                    continue
                out.parent.mkdir(parents=True,exist_ok=True)
                # Do not overwrite a previous authentic research snapshot.
                with out.open("x",encoding="utf-8") as f:
                    json.dump(record,f,sort_keys=True,ensure_ascii=False,indent=2)
                    f.write("\n")
                evidence["source_observations"].append({
                   "source":source,"status":"CAPTURED_BROWSER_ONLY_NOT_CERTIFIED",
                   "observed_link_count":record["observed_link_count"]})
            except Exception as exc:
                evidence["source_observations"].append({
                    "source":source,"status":"BLOCKED_BROWSER_CAPTURE",
                    "error_type":type(exc).__name__})
            finally:
                page.close()
    statuses=[x["status"] for x in evidence["source_observations"]]
    evidence["status"]=("BROWSER_LINK_CAPTURE_AVAILABLE_NOT_MODEL_ELIGIBLE" if
      len(statuses)==2 and all(x in
      ("REUSED_ARCHIVED_AUTHENTIC_CAPTURE","CAPTURED_BROWSER_ONLY_NOT_CERTIFIED")
       for x in statuses) else "BROWSER_INPUT_PARTIAL_OR_BLOCKED")
    return evidence

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--endpoint",default=os.getenv("MATRIX_BROWSER_CDP_ENDPOINT","http://127.0.0.1:9222"))
    args=p.parse_args()
    from datetime import date
    day=args.date or datetime.now(ZoneInfo("America/Bogota")).date().isoformat()
    date.fromisoformat(day)
    out=Path(f"evidence/tennis_calendar_reconciliation/{day}/MATRIX_TENNIS_CDP_CAPTURE_RECEIPT_LAST.json")
    try:
        record=collect(day=day,endpoint=args.endpoint)
    except Exception as exc:
        record={"schema":"MATRIX_TENNIS_CDP_CALENDAR_CAPTURE_RECEIPT_V1",
          "target_date_bogota":day,
          "checked_at_utc":datetime.now(timezone.utc).isoformat(),
          "status":"BLOCKED_BROWSER_TRANSPORT",
          "error_type":type(exc).__name__,
          "paid_api_calls":0,"models_modified":False,
          "telegram_signal_authorized":False,"real_money":"BLOCKED"}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(record,sort_keys=True,ensure_ascii=False))
if __name__=="__main__":main()
