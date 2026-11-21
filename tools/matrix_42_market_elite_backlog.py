from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
SUPERVISOR=ROOT/"evidence"/"market_portfolio"/"MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"
REGISTRY=ROOT/"evidence"/"market_portfolio"/"MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
RESOLUTION=ROOT/"config"/"MATRIX_42_MARKET_ELITE_RESOLUTION_MATRIX.json"
OUT=ROOT/"evidence"/"governance"/"MATRIX_42_MARKET_ELITE_BACKLOG_LAST.json"

PRIORITY={
 "OPERATIVE_GOVERNED_SELECTION_SCOPE":0,
 "ACTIVE_MODEL_PRICE_BINDING_BLOCKED":1,
 "MEASURED_PROMOTION_GATE_REQUIRED":2,
 "MEASURED_PRICE_AND_PROMOTION_REQUIRED":2,
 "DEDICATED_PREMATCH_MODEL_AND_CALIBRATION_REQUIRED":3,
 "RESEARCH_MODEL_PROSPECTIVE_COLLECTION_LOW":4,
 "RESEARCH_MODEL_NEEDS_PROSPECTIVE_FREEZES":4,
 "DATA_COVERAGE_PRESENT_PREMATCH_MODEL_REQUIRED":5,
 "LIVE_FEATURE_PATH_NOT_VALID_AS_PREMATCH_MODEL":5,
 "STAT_LAB_PRESENT_PREMATCH_MODEL_REQUIRED":5,
 "DIAGNOSTIC_NOT_PROMOTABLE_CURRENT_CHALLENGER":7,
}

def _load(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def build():
    s=_load(SUPERVISOR); r=_load(REGISTRY); m=_load(RESOLUTION)
    sup={x["market_key"]:x for x in s["rows"]}
    lanes=[]
    for row in m["lanes"]:
        key=row["market_key"]; sr=sup.get(key,{})
        rr=(r.get("lanes") or {}).get(key,{})
        status=row["elite_resolution_status"]
        lanes.append({
          "market_key":key,
          "display_name":row["display_name"],
          "sport":row["sport"],
          "priority":PRIORITY.get(status,9),
          "elite_resolution_status":status,
          "capability_mode":sr.get("capability_mode"),
          "prematch_model_capable":sr.get("prematch_model_capable"),
          "price_state":sr.get("price_state"),
          "prospective_unique_count":int(rr.get("prospective_unique_count") or 0),
          "gate_600_reached":int(rr.get("prospective_unique_count") or 0)>=600,
          "owner":row["blocking_owner"],
          "mandatory_action":row["mandatory_action"],
          "telegram_authorized_now":bool(row["telegram_authorized_now"]),
        })
    lanes.sort(key=lambda x:(x["priority"],x["sport"],x["market_key"]))
    by_owner={}
    for x in lanes:
        if x["telegram_authorized_now"]:
            continue
        by_owner.setdefault(x["owner"],[]).append(x["market_key"])
    return {
      "schema":"MATRIX_42_MARKET_ELITE_BACKLOG_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":"PASS",
      "total_lanes":len(lanes),
      "unresolved_nontelegram_lanes":sum(1 for x in lanes if not x["telegram_authorized_now"]),
      "owners":by_owner,
      "lanes":lanes,
      "governance":{
        "all_unresolved_have_owner":all(x["owner"] for x in lanes if not x["telegram_authorized_now"]),
        "all_unresolved_have_action":all(x["mandatory_action"] for x in lanes if not x["telegram_authorized_now"]),
        "no_live_as_prematch":all(not x["prematch_model_capable"] for x in lanes if x["elite_resolution_status"]=="LIVE_FEATURE_PATH_NOT_VALID_AS_PREMATCH_MODEL"),
        "real_money":"BLOCKED",
      }
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"total_lanes":out["total_lanes"],"unresolved":out["unresolved_nontelegram_lanes"],"owners":len(out["owners"])},sort_keys=True))

if __name__=="__main__":
    main()
