from __future__ import annotations

import hashlib, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE="https://api.livetennisapi.com/api/public/v1"
MATCH_ID=200549
OUT=Path("evidence/live_tennis_lab/2026-10-06/MATRIX_LIVE_TENNIS_MICRO_LAB_200549.json")

def h(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def get_score(key):
    r=requests.get(f"{BASE}/matches/{MATCH_ID}/score",headers={"X-API-Key":key},timeout=20)
    b=bytes(r.content)
    try: j=r.json()
    except Exception: j={"_non_json":True}
    return {
      "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "http_status":r.status_code,
      "response_sha256":h(b),
      "score":j
    }

def main():
    key=os.environ.get("LIVE_TENNIS_API_KEY","").strip()
    if not key: raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")
    snaps=[]
    for i in range(6):
        s=get_score(key)
        snaps.append(s)
        print(json.dumps({"i":i,"captured_at_utc":s["captured_at_utc"],"http_status":s["http_status"],"sets":s["score"].get("sets"),"games":s["score"].get("games"),"points":s["score"].get("points"),"server":s["score"].get("server"),"stale":s["score"].get("stale")},sort_keys=True))
        if i<5: time.sleep(10)
    payload={
      "schema":"MATRIX_LIVE_TENNIS_MICRO_LAB_V1",
      "match_id":MATCH_ID,
      "match":"Anna Pushkareva vs Duru Soke",
      "tournament":"ITF W35 Las Vegas, NV 2 Women",
      "surface":"hard",
      "snapshots":snaps,
      "snapshot_count":len(snaps),
      "protections":{
        "prematch_freeze_mutated":False,
        "live_data_used_for_prematch_model":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "secrets_persisted":False
      }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
if __name__=="__main__": main()
