from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_URL="https://v3.football.api-sports.io"

KEYWORDS={
 "MATCH_RESULT_1X2":["match winner","1x2"],
 "DOUBLE_CHANCE_1X":["double chance"],
 "DOUBLE_CHANCE_X2":["double chance"],
 "DOUBLE_CHANCE_12":["double chance"],
 "TOTAL_GOALS_OVER_UNDER":["goals over/under","goals"],
 "TEAM_TOTAL_GOALS_HOME":["home team total","home goals"],
 "TEAM_TOTAL_GOALS_AWAY":["away team total","away goals"],
 "FIRST_HALF_TOTAL_GOALS_OVER_UNDER":["first half goals","1st half goals"],
 "SECOND_HALF_TOTAL_GOALS_OVER_UNDER":["second half goals","2nd half goals"],
 "FIRST_HALF_TEAM_TOTAL_GOALS_HOME":["first half home team total"],
 "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY":["first half away team total"],
 "SECOND_HALF_TEAM_TOTAL_GOALS_HOME":["second half home team total"],
 "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY":["second half away team total"],
 "BTTS":["both teams score","both teams to score"],
 "ASIAN_OR_EUROPEAN_HANDICAP":["handicap"],
 "CORNERS_OVER_UNDER":["corner"],
 "CARDS_OVER_UNDER":["card","booking"],
 "TEAM_TOTAL_SHOTS_HOME":["shots home total","home total shots"],
 "TEAM_TOTAL_SHOTS_AWAY":["shots away total","away total shots"],
 "TEAM_SHOTS_ON_TARGET_HOME":["home shots on target"],
 "TEAM_SHOTS_ON_TARGET_AWAY":["away shots on target"],
 "TEAM_FOULS_HOME":["home fouls"],
 "TEAM_FOULS_AWAY":["away fouls"],
 "GOALKEEPER_SAVES":["save"],
 "PLAYER_SHOTS":["player shots"],
 "PLAYER_SHOTS_ON_TARGET":["player shots on target"],
 "PLAYER_ASSISTS":["player assists"],
 "PLAYER_PASSES":["player passes"],
 "PLAYER_TACKLES":["player tackles"],
 "PLAYER_FOULS":["player fouls"],
}

def run(key:str,out:Path):
    key=str(key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    previous=None
    if out.exists():
        try:
            previous=json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            previous=None
    r=requests.get(BASE_URL+"/odds/bets",headers={"x-apisports-key":key},timeout=20)
    if not 200<=r.status_code<300: raise RuntimeError("ODDS_BETS_HTTP_"+str(r.status_code))
    p=r.json()
    errors=p.get("errors") if isinstance(p,dict) else None
    rows=p.get("response") or []
    error_text=json.dumps(errors,sort_keys=True,ensure_ascii=False).casefold() if errors not in ({},[],None) else ""
    provider_error_classification=("DAILY_REQUEST_LIMIT_REACHED" if ("request limit" in error_text or "reached the request limit" in error_text) else "PLAN_OR_ENTITLEMENT_BLOCK" if ("upgrade your plan" in error_text or "subscription" in error_text) else "PROVIDER_ERROR_OTHER" if error_text else None)
    if not rows:
        if isinstance(previous,dict) and int(previous.get("catalog_count") or 0)>0:
            degraded={
              **previous,
              "refresh_attempted_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "refresh_status":"PROVIDER_EMPTY_LAST_NONEMPTY_PRESERVED",
              "provider_empty_response_count":0,
              "automatic_wagering":False,
              "real_money":"BLOCKED",
              "status":"STALE_LAST_NONEMPTY_FAIL_CLOSED",
            }
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text(json.dumps(degraded,indent=2,sort_keys=True)+"\n",encoding="utf-8")
            print(json.dumps({"status":degraded["status"],"catalog_count":degraded["catalog_count"]},sort_keys=True))
            return degraded
        empty={
          "schema":"MATRIX_API_FOOTBALL_MARKET_BINDING_CATALOG_V1",
          "observed_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "provider":"api_football","catalog_count":0,
          "matches":{lane:[] for lane in KEYWORDS},
          "automatic_wagering":False,"real_money":"BLOCKED",
          "status":"PROVIDER_EMPTY_FAIL_CLOSED",
        }
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(empty,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"status":empty["status"],"catalog_count":0},sort_keys=True))
        return empty
    matches={}
    for lane,terms in KEYWORDS.items():
        found=[]
        for row in rows:
            name=str(row.get("name") or "")
            low=name.casefold()
            if any(term in low for term in terms):
                found.append({"id":row.get("id"),"name":name})
        matches[lane]=found
    payload={
      "schema":"MATRIX_API_FOOTBALL_MARKET_BINDING_CATALOG_V1",
      "observed_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "provider":"api_football","catalog_count":len(rows),"matches":matches,
      "automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","catalog_count":len(rows),"match_counts":{k:len(v) for k,v in matches.items()}},sort_keys=True))
    return payload

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/market_expansion/market_binding_catalog.json"))
