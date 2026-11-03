"""Read-only automatic SofaScore evidence, never probabilities or bets."""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")

def utc(value):
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.utcoffset() is None: raise ValueError("NAIVE_SOURCE_TIME")
    return d.astimezone(timezone.utc)

def exact_label(label,day,clock,home,away):
    from tools.matrix_football_sofa_fixture_crosscheck import norm
    d=datetime.strptime(day,"%Y-%m-%d")
    date=rf"(?<!\d)0?{d.day}[./]0?{d.month}[./](?:{d.year}|{d.year%100:02d})(?!\d)"
    if not re.search(date+rf"\s+{re.escape(clock)}(?!\d)",label): return False
    n=norm(label)
    a,b=norm(home),norm(away)
    return bool(a and b and a!=b and len(a)>=4 and len(b)>=4
        and re.search(r"(?<!\w)"+re.escape(a)+r"(?!\w)",n)
        and re.search(r"(?<!\w)"+re.escape(b)+r"(?!\w)",n))

def extract_sofa(intake,links,observed_at):
    from tools.matrix_football_sofa_fixture_crosscheck import norm,ALIASES
    if intake.get("source")!="FOOTBALL_DATA_ORG" or intake.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE" or intake.get("real_money")!="BLOCKED":
        raise ValueError("UNTRUSTED_INDEPENDENT_INTAKE")
    day=intake["target_date_bogota"]
    matched=[]; seen=set()
    for fixture in intake.get("fixtures",[]):
        if not isinstance(fixture,dict):continue
        kickoff=utc(fixture["kickoff_utc"])
        if observed_at>=kickoff or kickoff.astimezone(BOGOTA).date().isoformat()!=day:continue
        home,away=(ALIASES.get(norm(fixture[k]),norm(fixture[k])) for k in ("home","away"))
        clock=kickoff.astimezone(BOGOTA).strftime("%H:%M")
        candidates=set()
        for link in links:
            url,label=str(link.get("url") or ""),str(link.get("name") or "")
            parsed=urlparse(url)
            event=re.fullmatch(r"id:(\d+)",parsed.fragment)
            if (parsed.scheme=="https" and parsed.netloc=="www.sofascore.com"
                and parsed.path.startswith("/es/football/match/") and event
                and exact_label(label,day,clock,home,away)):
                candidates.add((event.group(1),url))
        if len(candidates)!=1:continue
        sid,url=next(iter(candidates))
        fid=str(fixture["source_fixture_id"])
        if sid in seen:raise ValueError("DUPLICATE_SOFA_ID")
        seen.add(sid)
        matched.append({"provider_fixture_id":fid,"sofascore_event_id":sid,
          "home":home,"away":away,"local_time_bogota":clock,"url":url})
    return {"schema":"MATRIX_SOFA_BROWSER_OBSERVATIONS_V1",
      "source":"SOFASCORE","target_date_bogota":day,
      "observed_at_utc":observed_at.isoformat(),
      "source_order":["SOFASCORE","FLASHSCORE","APIS"],
      "browser_tab_url":f"https://www.sofascore.com/es/football/{day}",
      "capture_method":"CDP_VISIBLE_EXACT_DATE_TIME_TEAMS_EVENT_ID",
      "source_scope":"ONLY_EXACT_PROSPECTIVE_MATCHES",
      "matches":matched,"quotes_verified":False,"flashscore_corroborated":False,
      "signal_generation_authorized":False,"automatic_wagering":False,
      "real_money":"BLOCKED"}

def run(intake_path,endpoint):
    from playwright.sync_api import sync_playwright
    intake=json.loads(intake_path.read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc)
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=15000)
        if not browser.contexts:raise ValueError("NO_CDP_CONTEXT")
        page=browser.contexts[0].new_page()
        try:
            page.goto(f"https://www.sofascore.com/es/football/{intake['target_date_bogota']}",wait_until="domcontentloaded",timeout=16000)
            page.wait_for_timeout(2000)
            links=page.evaluate(""""""() => Array.from(document.querySelectorAll('a[href]'))
                .filter(a=>a.getClientRects().length>0).slice(0,3000)
                .map(a=>({url:a.href,name:String(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,400)}))""")
        finally: page.close()
    return extract_sofa(intake,links,now)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--intake",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--cdp",default="http://127.0.0.1:9222")
    a=ap.parse_args()
    result=run(a.intake,a.cdp)
    # Never replace a larger observation set with an empty/partial browser load.
    if result["matches"]:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        prior=json.loads(a.out.read_text(encoding="utf-8")) if a.out.is_file() else {}
        if (prior.get("target_date_bogota")!=result["target_date_bogota"]
            or len(prior.get("matches") or [])<=len(result["matches"])):
            a.out.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"SOFA_OBSERVED" if result["matches"] else "NO_EXACT_SOFA_OBSERVATIONS",
                      "matches":len(result["matches"]),"signals":False,"real_money":"BLOCKED"}))

if __name__=="__main__":main()
