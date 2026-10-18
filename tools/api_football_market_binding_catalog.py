from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_URL="https://v3.football.api-sports.io"

KEYWORDS={
 "TEAM_FOULS":["foul"],
 "CORNERS":["corner"],
 "TEAM_YELLOW_CARDS":["card","booking"],
 "TEAM_SHOTS_ON_TARGET":["shots on target","shot on target"],
 "TEAM_GOALKEEPER_SAVES":["save"],
 "PLAYER_SHOTS":["player shots","shots by player"],
 "TEAM_TOTAL_SHOTS":["shots. home total","shots. away total","shots home total","shots away total"],
}

def run(key:str,out:Path):
    key=str(key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    r=requests.get(BASE_URL+"/odds/bets",headers={"x-apisports-key":key},timeout=20)
    if not 200<=r.status_code<300: raise RuntimeError("ODDS_BETS_HTTP_"+str(r.status_code))
    p=r.json()
    rows=p.get("response") or []
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
