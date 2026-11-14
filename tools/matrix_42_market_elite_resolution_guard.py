from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/"config"/"MATRIX_42_MARKET_ELITE_RESOLUTION_MATRIX.json"

def load():
    return json.loads(MATRIX.read_text(encoding="utf-8"))

def validate(data):
    lanes=data.get("lanes") or []
    if len(lanes)!=42:
        raise RuntimeError(f"LANE_COUNT_INVALID:{len(lanes)}")
    keys=[x.get("market_key") for x in lanes]
    if len(keys)!=len(set(keys)):
        raise RuntimeError("DUPLICATE_MARKET_KEY")
    for row in lanes:
        if not row.get("blocking_owner"):
            raise RuntimeError(f"UNOWNED_BLOCKER:{row.get('market_key')}")
        if not row.get("mandatory_action"):
            raise RuntimeError(f"MISSING_ACTION:{row.get('market_key')}")
        if row.get("real_money")!="BLOCKED":
            raise RuntimeError(f"REAL_MONEY_NOT_BLOCKED:{row.get('market_key')}")
        if row.get("elite_resolution_status")=="LIVE_FEATURE_PATH_NOT_VALID_AS_PREMATCH_MODEL":
            if row.get("prematch_model_capable_now") is not False:
                raise RuntimeError(f"LIVE_AS_PREMATCH_REGRESSION:{row.get('market_key')}")
        if row.get("telegram_authorized_now"):
            if row.get("market_key")!="TOTAL_GOALS_OVER_UNDER":
                raise RuntimeError(f"UNAUTHORIZED_TELEGRAM_MARKET:{row.get('market_key')}")
    if not any(x.get("market_key")=="ACES" for x in lanes):
        raise RuntimeError("ACES_MISSING")
    if not any(x.get("market_key")=="FIRST_HALF_TOTAL_GOALS_OVER_UNDER" for x in lanes):
        raise RuntimeError("FIRST_HALF_GOALS_MISSING")
    if not any(x.get("market_key")=="SECOND_HALF_TOTAL_GOALS_OVER_UNDER" for x in lanes):
        raise RuntimeError("SECOND_HALF_GOALS_MISSING")
    return {
        "status":"PASS",
        "total_lanes":42,
        "owned_blockers":42,
        "telegram_authorized_market_families":[x["market_key"] for x in lanes if x.get("telegram_authorized_now")]
    }

def main():
    print(json.dumps(validate(load()),sort_keys=True))

if __name__=="__main__":
    main()
