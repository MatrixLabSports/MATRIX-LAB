from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20.0
TARGETS={
 "1494023":{"home":"Sarasota Paradise","away":"Charlotte Independence"},
 "1629004":{"home":"USA","away":"Mexico"},
 "1494024":{"home":"Spokane Velocity","away":"Portland Hearts of Pine"},
 "1606681":{"home":"Consadole Sapporo","away":"Iwaki"},
 "1493730":{"home":"Orange County SC","away":"Monterey Bay"},
 "1494021":{"home":"Fort Wayne","away":"Forward Madison"},
}
POLICY_NAMES={"betano","betplay","bwin","rushbet","pinnacle"}

def norm(s: object)->str:
    return str(s or "").strip().casefold().replace(" ","").replace("-","")

def is_over25(v: Mapping[str,Any])->bool:
    text=" ".join(str(v.get(k) or "") for k in ("value","label","name","handicap")).casefold()
    return ("over 2.5" in text or "over2.5" in text or ("over" in text and "2.5" in text))

def run(key: str, out_root: Path)->dict[str,Any]:
    key=str(key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    run_id=now.strftime("%Y%m%dT%H%M%SZ")
    run_dir=out_root/"runs"/run_id; raw=run_dir/"raw"; raw.mkdir(parents=True,exist_ok=True)
    s=requests.Session(); fixtures=[]; calls=0
    for fid,meta in TARGETS.items():
        resp=s.get(BASE_URL+"/odds",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        calls+=1; body=bytes(resp.content); (raw/f"fixture_{fid}.bin").write_bytes(body)
        try: payload=resp.json()
        except ValueError: payload={}
        books=[]
        for fr in (payload.get("response") or []) if isinstance(payload,Mapping) else []:
            if not isinstance(fr,Mapping): continue
            for b in fr.get("bookmakers") or []:
                if not isinstance(b,Mapping): continue
                bname=str(b.get("name") or "")
                hits=[]
                for bet in b.get("bets") or []:
                    if not isinstance(bet,Mapping): continue
                    for val in bet.get("values") or []:
                        if isinstance(val,Mapping) and is_over25(val):
                            hits.append({
                              "bet_id":bet.get("id"),"bet_name":bet.get("name"),
                              "value":val.get("value"),"odd":val.get("odd"),
                              "handicap":val.get("handicap"),"main":val.get("main"),
                              "suspended":val.get("suspended")
                            })
                if hits:
                    n=norm(bname)
                    policy=next((p for p in POLICY_NAMES if p in n),None)
                    books.append({"bookmaker_id":b.get("id"),"bookmaker_name":bname,"policy_match":policy,"offers":hits})
        fixtures.append({
          "fixture_id":fid,**meta,
          "http_status":int(resp.status_code),
          "raw_sha256":hashlib.sha256(body).hexdigest(),
          "bookmakers":books
        })
    payload={
      "schema":"MATRIX_FOOTBALL_OVER25_LIVE_ODDS_PROBE_V1",
      "observed_at_utc":now.isoformat(),"run_id":run_id,"network_calls":calls,
      "fixtures":fixtures,
      "policy_bookmakers":["Betano","BetPlay","bwin","RushBet","Pinnacle"],
      "odds_used_to_generate_probability":False,
      "automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"
    }
    manifest=run_dir/"manifest.json"
    manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    pointer={"schema":"MATRIX_FOOTBALL_OVER25_LIVE_ODDS_POINTER_V1","run_id":run_id,
      "observed_at_utc":now.isoformat(),"manifest_path":str(manifest),
      "manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
      "network_calls":calls,
      "fixtures_with_over25":sum(bool(x["bookmakers"]) for x in fixtures),
      "automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"}
    out_root.mkdir(parents=True,exist_ok=True)
    (out_root/"last_run.json").write_text(json.dumps(pointer,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(pointer,sort_keys=True))
    return payload

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/over25_live_odds"))
