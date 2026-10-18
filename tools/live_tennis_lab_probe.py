from __future__ import annotations

import json, os, hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE="https://api.livetennisapi.com/api/public/v1"
OUT=Path("evidence/live_tennis_lab/2026-10-06/MATRIX_LIVE_TENNIS_LAB_SNAPSHOT.json")

def shab(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def get(path, key, params=None):
    r=requests.get(BASE+path, headers={"X-API-Key":key}, params=params or {}, timeout=20)
    body=bytes(r.content)
    meta={
      "path":path,"params":params or {},"http_status":r.status_code,
      "response_bytes":len(body),"response_sha256":shab(body),
      "content_type":r.headers.get("content-type")
    }
    try: j=r.json()
    except Exception: j={"_non_json":True}
    return j,meta

def player_names(row):
    players=row.get("players") if isinstance(row.get("players"),dict) else {}
    p1=players.get("p1") if isinstance(players.get("p1"),dict) else {}
    p2=players.get("p2") if isinstance(players.get("p2"),dict) else {}
    return str(p1.get("name") or row.get("p1_name") or "").strip(), str(p2.get("name") or row.get("p2_name") or "").strip()

def is_singles(row):
    if row.get("is_doubles") is True:
        return False
    p1,p2=player_names(row)
    if not p1 or not p2:
        return False
    blob=" ".join(str(row.get(k) or "") for k in ("draw","event_type","match_type","tournament","round")).lower()
    return "double" not in blob

def main():
    key=os.environ.get("LIVE_TENNIS_API_KEY","").strip()
    if not key: raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")
    live,meta=get("/matches",key,{"status":"live","limit":50})
    rows=live.get("data") if isinstance(live,dict) and isinstance(live.get("data"),list) else []
    singles=[x for x in rows if isinstance(x,dict) and is_singles(x)]
    enriched=[]
    for row in singles[:10]:
        mid=row.get("id")
        if mid is None: continue
        score,smeta=get(f"/matches/{mid}/score",key)
        p1,p2=player_names(row)
        enriched.append({
          "match":{
            "id":mid,
            "status":row.get("status"),
            "event_status":row.get("event_status"),
            "tour":row.get("tour"),
            "tournament":row.get("tournament"),
            "round":row.get("round"),
            "round_code":row.get("round_code"),
            "surface":row.get("surface"),
            "best_of":row.get("best_of"),
            "is_doubles":row.get("is_doubles"),
            "p1_name":p1,
            "p2_name":p2,
            "p1_ranking":((row.get("players") or {}).get("p1") or {}).get("ranking") if isinstance(row.get("players"),dict) else row.get("p1_ranking"),
            "p2_ranking":((row.get("players") or {}).get("p2") or {}).get("ranking") if isinstance(row.get("players"),dict) else row.get("p2_ranking"),
            "embedded_score":row.get("score")
          },
          "score":score,
          "score_request":smeta
        })
    selected=enriched[0] if enriched else None
    payload={
      "schema":"MATRIX_LIVE_TENNIS_LAB_SNAPSHOT_V1",
      "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "source":"Live Tennis API",
      "live_request":meta,
      "live_rows_returned":len(rows),
      "live_singles_candidates":len(singles),
      "candidates":enriched,
      "selected":selected,
      "protections":{
        "prematch_freeze_mutated":False,
        "live_data_used_for_prematch_model":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "secrets_persisted":False
      },
      "status":"PASS" if selected else "NO_LIVE_SINGLES_AVAILABLE"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":payload["status"],
      "live_rows_returned":len(rows),
      "live_singles_candidates":len(singles),
      "selected_id": (selected or {}).get("match",{}).get("id"),
      "selected_players":[
         (selected or {}).get("match",{}).get("p1_name"),
         (selected or {}).get("match",{}).get("p2_name")
      ] if selected else []
    },sort_keys=True))
if __name__=="__main__": main()
