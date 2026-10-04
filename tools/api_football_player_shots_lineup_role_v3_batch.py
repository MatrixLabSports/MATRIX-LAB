from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

from tools.api_football_player_shots_expected_minutes_v2 import _load_fixture_sources
from tools.api_football_player_shots_lineup_role_v3 import build_dataset, build_model

BASE_URL="https://v3.football.api-sports.io"
MAX_NEW_PER_RUN=80
TIMEOUT=20.0

def run(key:str,out:Path)->dict:
    key=str(key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    fixtures,_=_load_fixture_sources()
    cache=out/"raw_lineups"; cache.mkdir(parents=True,exist_ok=True)
    missing=[f for f in fixtures if not (cache/f"fixture_{f['fixture_id']}_lineups.json").exists()]
    session=requests.Session(); calls=0; stopped_reason=None; headers_last={}
    for f in missing[:MAX_NEW_PER_RUN]:
        fid=str(f["fixture_id"])
        r=session.get(BASE_URL+"/fixtures/lineups",headers={"x-apisports-key":key},params={"fixture":fid},timeout=TIMEOUT)
        calls+=1
        headers_last={k.lower():v for k,v in r.headers.items() if "ratelimit" in k.lower()}
        if r.status_code==429:
            stopped_reason="PROVIDER_RATE_LIMIT_429"
            break
        if not 200<=r.status_code<300:
            stopped_reason=f"HTTP_{r.status_code}"
            break
        try: payload=r.json()
        except ValueError:
            stopped_reason="INVALID_JSON"
            break
        (cache/f"fixture_{fid}_lineups.json").write_text(json.dumps(payload,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
        remain=headers_last.get("x-ratelimit-requests-remaining")
        try:
            if remain is not None and int(remain)<=5:
                stopped_reason="PROVIDER_REMAINING_REQUESTS_SAFETY_STOP"
                break
        except ValueError:
            pass
    cached=sum((cache/f"fixture_{f['fixture_id']}_lineups.json").exists() for f in fixtures)
    remaining=len(fixtures)-cached
    model_status=None; prospective_eligible=False
    if remaining==0:
        dataset=build_dataset(key,out)
        model=build_model(out)
        (out/"model.json").write_text(json.dumps(model,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        summary={"schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_V3_SUMMARY","dataset":{"rows":dataset["row_count"],"train":dataset["train_count"],"validation":dataset["validation_count"],"network_calls":dataset["source_audit"]["provider_network_calls"],"fixtures_without_lineup":dataset["source_audit"]["fixtures_without_lineup"]},"model_status":model["status"],"prospective_eligible":model.get("prospective_freeze_allowed",False),"validation":model.get("validation"),"automatic_wagering":False,"real_money":"BLOCKED"}
        (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        model_status=model["status"]; prospective_eligible=bool(model.get("prospective_freeze_allowed"))
    progress={
      "schema":"MATRIX_PLAYER_SHOTS_LINEUP_ROLE_V3_ACQUISITION_PROGRESS_V1",
      "observed_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "fixture_target_count":len(fixtures),"cached_lineup_count":cached,"remaining_lineup_count":remaining,
      "network_calls_this_run":calls,"max_new_per_run":MAX_NEW_PER_RUN,
      "provider_rate_headers_last":headers_last,"stopped_reason":stopped_reason,
      "status":"COMPLETE_MODEL_EVALUATED" if remaining==0 else "ACQUIRING",
      "model_status":model_status,"prospective_eligible":prospective_eligible,
      "automatic_wagering":False,"real_money":"BLOCKED"
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/"acquisition_progress.json").write_text(json.dumps(progress,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(progress,sort_keys=True))
    return progress

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/market_expansion/player_shots_lineup_role_v3"))
