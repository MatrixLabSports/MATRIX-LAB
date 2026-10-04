from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=25.0
STANDARD_FINAL={"FT"}

TARGETS=[
  {"label":"Regionalliga Nord","country":"Germany","queries":["Regionalliga Nord","Regionalliga - Nord"]},
  {"label":"Regionalliga West","country":"Germany","queries":["Regionalliga West","Regionalliga - West"]},
  {"label":"Regionalliga Südwest","country":"Germany","queries":["Regionalliga SudWest","Regionalliga Südwest","Regionalliga - SudWest"]},
  {"label":"Regionalliga Bayern","country":"Germany","queries":["Regionalliga Bayern","Regionalliga - Bayern"]},
  {"label":"Oberliga Schleswig-Holstein","country":"Germany","queries":["Oberliga Schleswig-Holstein","Schleswig-Holstein"]},
  {"label":"Oberliga Hamburg","country":"Germany","queries":["Oberliga - Hamburg","Oberliga Hamburg","Hamburg Oberliga"]},
  {"label":"Oberliga Niedersachsen","country":"Germany","queries":["Oberliga Niedersachsen","Niedersachsen"]},
  {"label":"Oberliga Westfalen","country":"Germany","queries":["Oberliga Westfalen","Westfalen"]},
  {"label":"Oberliga Hessen","country":"Germany","queries":["Oberliga Hessen","Hessenliga","Hessen"]},
  {"label":"Oberliga Rheinland-Pfalz/Saar","country":"Germany","queries":["Oberliga Rheinland-Pfalz / Saar","Rheinland-Pfalz","Rheinland Pfalz Saar"]},
  {"label":"Oberliga Bayern Nord","country":"Germany","queries":["Oberliga Bayern Nord","Bayern Nord"]},
  {"label":"Oberliga Bayern Süd","country":"Germany","queries":["Oberliga Bayern Süd","Bayern Sud","Bayern Süd"]},
  {"label":"Oberliga Baden-Württemberg","country":"Germany","queries":["Oberliga Baden-Württemberg","Baden-Württemberg","Baden Wurttemberg"]},
  {"label":"DFB Youth League","country":"Germany","queries":["DFB Youth League","DFB Junioren Bundesliga","U19 Bundesliga"]},
  {"label":"Bundesliga Femenina","country":"Germany","queries":["Frauen Bundesliga","Bundesliga Women","Women Bundesliga"]},
  {"label":"Premier League Femenina","country":"Saudi-Arabia","queries":["Women's Premier League","Women Premier League","Premier League Women"]},
  {"label":"Ligue 2","country":"Algeria","queries":["Ligue 2"]},
  {"label":"Liga Profesional","country":"Argentina","queries":["Liga Profesional Argentina","Liga Profesional"]},
  {"label":"Primera Nacional","country":"Argentina","queries":["Primera Nacional"]},
  {"label":"Primera B","country":"Argentina","queries":["Primera B Metropolitana","Primera B"]},
  {"label":"Primera C","country":"Argentina","queries":["Primera C"]},
  {"label":"Torneo Promocional Amateur","country":"Argentina","queries":["Torneo Promocional Amateur","Promocional Amateur"]},
  {"label":"Primera A Femenina","country":"Argentina","queries":["Primera A Women","Primera A Femenina","Women Primera A"]},
  {"label":"Segunda División","country":"Spain","queries":["Segunda División","Segunda Division"]},
  {"label":"LFPB","country":"Bolivia","queries":["Primera División","Primera Division","LFPB"]},
  {"label":"Premier Liga","country":"Bosnia","queries":["Premijer Liga","Premier Liga"]},
  {"label":"Serie A","country":"Brazil","queries":["Serie A"]},
  {"label":"Serie B","country":"Brazil","queries":["Serie B"]},
  {"label":"Serie C","country":"Brazil","queries":["Serie C"]},
  {"label":"Serie D","country":"Brazil","queries":["Serie D"]},
  {"label":"Copa Paulista","country":"Brazil","queries":["Copa Paulista"]},
  {"label":"Brasileirão Femenino","country":"Brazil","queries":["Brasileiro Women","Brasileirão Women","Serie A Women"]},
  {"label":"First PFL","country":"Bulgaria","queries":["First League","First PFL"]},
  {"label":"Premier League","country":"Burkina-Faso","queries":["Ligue 1","Premier League"]},
  {"label":"Elite One","country":"Cameroon","queries":["Elite One"]},
]

def norm(s:object)->str:
    text=str(s or "").casefold()
    text=text.replace("ü","u").replace("ö","o").replace("ä","a").replace("ß","ss")
    text=text.replace("ã","a").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    return re.sub(r"[^a-z0-9]+"," ",text).strip()

def api_get(session,key,path,params):
    resp=session.get(BASE_URL+path,headers={"x-apisports-key":key},params=params,timeout=TIMEOUT)
    body=bytes(resp.content)
    if not 200<=int(resp.status_code)<300:
        raise RuntimeError(f"HTTP_{resp.status_code}:{path}:{params}")
    payload=resp.json()
    if payload.get("errors"):
        raise RuntimeError(f"PROVIDER_ERROR:{path}:{params}:{payload.get('errors')}")
    return payload,body

def choose_league(rows,target):
    country_n=norm(target["country"])
    candidates=[]
    for item in rows:
        if not isinstance(item,Mapping): continue
        league=item.get("league") if isinstance(item.get("league"),Mapping) else {}
        country=item.get("country") if isinstance(item.get("country"),Mapping) else {}
        name=norm(league.get("name"))
        cn=norm(country.get("name"))
        if cn!=country_n:
            continue
        target_tokens=set(norm(target["label"]).split())
        name_tokens=set(name.split())
        overlap=len(target_tokens & name_tokens)
        exact=int(norm(target["label"])==name)
        candidates.append((exact,overlap,-abs(len(name_tokens)-len(target_tokens)),item))
    if not candidates:
        return None
    candidates.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    return candidates[0][3]

def current_season(item):
    seasons=item.get("seasons") or []
    currents=[s for s in seasons if isinstance(s,Mapping) and s.get("current") is True]
    if currents:
        return max(int(s["year"]) for s in currents if s.get("year") is not None)
    years=[int(s["year"]) for s in seasons if isinstance(s,Mapping) and s.get("year") is not None]
    return max(years) if years else None

def final_rows(payload):
    out=[]
    for r in payload.get("response") or []:
        if not isinstance(r,Mapping): continue
        fixture=r.get("fixture") if isinstance(r.get("fixture"),Mapping) else {}
        status=fixture.get("status") if isinstance(fixture.get("status"),Mapping) else {}
        short=str(status.get("short") or "").upper()
        if short not in STANDARD_FINAL:
            continue
        goals=r.get("goals") if isinstance(r.get("goals"),Mapping) else {}
        h,a=goals.get("home"),goals.get("away")
        if not isinstance(h,int) or not isinstance(a,int):
            continue
        out.append({
            "fixture_id":str(fixture.get("id") or ""),
            "kickoff":fixture.get("date"),
            "home_goals":h,"away_goals":a,"total_goals":h+a,
            "over_2_5":h+a>=3,
        })
    out.sort(key=lambda x:str(x["kickoff"]))
    return out

def summarize(rows):
    n=len(rows)
    if not n: return None
    def block(rs):
        return {
          "n":len(rs),
          "over_2_5_count":sum(1 for x in rs if x["over_2_5"]),
          "over_2_5_pct":100*sum(1 for x in rs if x["over_2_5"])/len(rs),
          "avg_goals":sum(x["total_goals"] for x in rs)/len(rs),
        }
    out={"season":block(rows)}
    if n>=10: out["last10"]=block(rows[-10:])
    if n>=20: out["last20"]=block(rows[-20:])
    return out

def grade(summary):
    if not summary: return "NO_DATA"
    s=summary["season"]; n=s["n"]; pct=s["over_2_5_pct"]
    if n<8: return "INSUFFICIENT_SAMPLE"
    if pct>=65 and n>=15: return "VERY_HIGH"
    if pct>=58 and n>=15: return "HIGH"
    if pct>=52 and n>=12: return "ABOVE_AVERAGE"
    return "NOT_HIGH"

def run():
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key: raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    session=requests.Session()
    observed=datetime.now(timezone.utc).replace(microsecond=0)
    results=[]; calls=0
    raw_records=[]
    for target in TARGETS:
        selected=None; search_used=None; last_error=None
        for q in target["queries"]:
            try:
                payload,body=api_get(session,key,"/leagues",{"search":q})
                calls+=1; raw_records.append({"kind":"league_search","target":target["label"],"query":q,"sha256":hashlib.sha256(body).hexdigest()})
                selected=choose_league(payload.get("response") or [],target)
                if selected is not None:
                    search_used=q; break
            except Exception as exc:
                last_error=str(exc)
        if selected is None:
            results.append({"label":target["label"],"country":target["country"],"status":"LEAGUE_NOT_FOUND","error":last_error})
            continue
        league=selected["league"]; season=current_season(selected)
        if season is None:
            results.append({"label":target["label"],"country":target["country"],"status":"SEASON_NOT_FOUND","league_id":league.get("id"),"provider_name":league.get("name")})
            continue
        try:
            fp,body=api_get(session,key,"/fixtures",{"league":league["id"],"season":season})
            calls+=1; raw_records.append({"kind":"fixtures","target":target["label"],"league_id":league["id"],"season":season,"sha256":hashlib.sha256(body).hexdigest()})
            rows=final_rows(fp); summary=summarize(rows)
            results.append({
              "label":target["label"],"country":target["country"],"status":"PASS",
              "league_id":str(league.get("id")),"provider_name":league.get("name"),"season":season,
              "search_used":search_used,"final_match_count":len(rows),"summary":summary,"grade":grade(summary),
            })
        except Exception as exc:
            results.append({"label":target["label"],"country":target["country"],"status":"FIXTURE_FETCH_ERROR","league_id":str(league.get("id")),"provider_name":league.get("name"),"season":season,"error":str(exc)})
    good=[r for r in results if r.get("status")=="PASS" and r.get("summary")]
    ranking=sorted(good,key=lambda r:(r["summary"]["season"]["over_2_5_pct"],r["summary"]["season"]["n"]),reverse=True)
    payload={
      "schema":"MATRIX_FOOTBALL_OVER25_LEAGUE_AUDIT_SCREENSHOTS_V1",
      "observed_at_utc":observed.isoformat(),
      "source":"API_FOOTBALL",
      "network_calls":calls,
      "rules":{"standard_final_only":True,"minimum_sample_for_high":15,"very_high_pct":65,"high_pct":58,"above_average_pct":52},
      "results":results,
      "ranking":[{"label":r["label"],"country":r["country"],"league_id":r["league_id"],"provider_name":r["provider_name"],"season":r["season"],"grade":r["grade"],**r["summary"]["season"],"last10":r["summary"].get("last10"),"last20":r["summary"].get("last20")} for r in ranking],
      "automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"
    }
    out=Path("evidence/api_football/league_over25_audit")
    out.mkdir(parents=True,exist_ok=True)
    (out/"audit_last.json").write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    (out/"raw_manifest.json").write_text(json.dumps({"records":raw_records},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"network_calls":calls,"ranked":len(ranking),"top10":payload["ranking"][:10],"status":"PASS"},sort_keys=True))

if __name__=="__main__":
    run()
