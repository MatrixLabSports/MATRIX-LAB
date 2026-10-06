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

def is_singles(row):
    blob=" ".join(str(row.get(k) or "") for k in ("draw","event_type","match_type","tournament","round")).lower()
    p1=str(row.get("player1_name") or "").strip()
    p2=str(row.get("player2_name") or "").strip()
    if not p1 or not p2: return False
    return "double" not in blob and "/" not in p1 and "/" not in p2

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
        enriched.append({
          "match":row,
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
         (selected or {}).get("match",{}).get("player1_name"),
         (selected or {}).get("match",{}).get("player2_name")
      ] if selected else []
    },sort_keys=True))
if __name__=="__main__": main()
