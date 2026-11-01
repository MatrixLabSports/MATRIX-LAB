"""Bounded public TheSportsDB football fixture probe. Research-only, never a worldwide inventory."""
from __future__ import annotations
import argparse
import json
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError

def classify(data: dict, day: str) -> dict:
    events=data.get("events") if isinstance(data,dict) else None
    if not isinstance(events,list):
        return {"status":"NO_USABLE_EVENT_LIST_FAIL_CLOSED","returned_count":0,"events":[]}
    rows=[]
    for e in events[:3]:
        if not isinstance(e,dict):continue
        rows.append({"provider_event_id":str(e.get("idEvent") or ""),"date":str(e.get("dateEvent") or ""),"home":str(e.get("strHomeTeam") or ""),"away":str(e.get("strAwayTeam") or ""),"league":str(e.get("strLeague") or "")})
    return {"status":"PARTIAL_SAMPLE_ONLY_NOT_WORLD_INVENTORY","returned_count":len(rows),"events":rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--allow-one-public-call",action="store_true")
    p.add_argument("--out",type=Path,default=Path("evidence/governance/MATRIX_FOOTBALL_PUBLIC_FREE_PROBE_LAST.json"))
    a=p.parse_args()
    date.fromisoformat(a.date)
    if not a.allow_one_public_call:raise SystemExit("EXPLICIT_PUBLIC_PROBE_OPT_IN_REQUIRED")
    endpoint="https://www.thesportsdb.com/api/v1/json/123/eventsday.php?"+urlencode({"d":a.date,"s":"Soccer"})
    try:
        with urlopen(Request(endpoint,headers={"User-Agent":"MATRIX-Research-ReadOnly/1.0"}),timeout=15) as response:
            http=response.status
            payload=json.loads(response.read(250000).decode("utf-8"))
    except (HTTPError,URLError,TimeoutError,ValueError) as exc:
        raise SystemExit("PUBLIC_PROBE_FAILED_FAIL_CLOSED:"+type(exc).__name__)
    result={"schema":"MATRIX_FOOTBALL_PUBLIC_FREE_PROBE_V1","provider":"thesportsdb","date":a.date,
      "checked_at_utc":datetime.now(timezone.utc).isoformat(),"http_status":http,
      "network_calls":1,"provider_free_event_cap":3,
      "worldwide_inventory_complete":False,"canonical_candidate_generation_authorized":False,
      "signal_generation_authorized":False,"real_money":"BLOCKED","automatic_wagering":False,
      **classify(payload,a.date)}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
