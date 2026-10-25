from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIT_MANIFEST=Path("evidence/api_football/market_expansion/team_pit/manifest.json")
TEAM_SHOTS_AUDIT=Path("evidence/market_portfolio/MATRIX_42_LANE_TEAM_SHOTS_OFFLINE_BRIDGE_LAST.json")
OUT=Path("evidence/market_portfolio/MATRIX_TEAM_SHOTS_PIT_FRESHNESS_GUARD_LAST.json")
MAX_AGE_HOURS=48.0


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def build(now_utc:datetime|None=None)->dict[str,Any]:
    now=(now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    pit=_load(PIT_MANIFEST)
    audit=_load(TEAM_SHOTS_AUDIT)
    generated=_utc(pit["generated_at_utc"])
    age=(now-generated).total_seconds()/3600.0
    lane=(pit.get("lanes") or {}).get("TEAM_TOTAL_SHOTS") or {}
    blocked_reasons=audit.get("blocked_reason_counts") or {}
    insufficient=int(blocked_reasons.get("INSUFFICIENT_PERSISTED_TEAM_SHOTS_PIT_HISTORY") or 0)
    future=int(audit.get("future_source_fixture_candidates") or 0)
    eligible=int(audit.get("eligible_future_unique_fixtures") or 0)
    stale=age>MAX_AGE_HOURS
    zero_history_pattern=(future>0 and eligible==0 and insufficient>0)
    needs_refresh=stale and zero_history_pattern
    return {
        "schema":"MATRIX_TEAM_SHOTS_PIT_FRESHNESS_GUARD_V1",
        "generated_at_utc":now.replace(microsecond=0).isoformat(),
        "status":"PASS",
        "pit_generated_at_utc":generated.isoformat(),
        "pit_age_hours":round(age,3),
        "maximum_allowed_age_hours":MAX_AGE_HOURS,
        "pit_stale":stale,
        "future_source_fixture_candidates":future,
        "eligible_future_unique_fixtures":eligible,
        "insufficient_pit_history_blocked_count":insufficient,
        "pit_row_count":int(lane.get("row_count") or 0),
        "pit_train_count":int(lane.get("train_count") or 0),
        "pit_validation_count":int(lane.get("validation_count") or 0),
        "requires_causal_pit_refresh":needs_refresh,
        "next_required_action":(
            "REFRESH_TEAM_TOTAL_SHOTS_PIT_FROM_STRICTLY_PRIOR_GOVERNED_HISTORY"
            if needs_refresh else
            "CONTINUE_TEAM_SHOTS_PROSPECTIVE_BRIDGE"
        ),
        "protections":{
            "stale_pit_never_interpreted_as_true_zero_history":True,
            "minimum_history_not_lowered":True,
            "post_start_backfill":False,
            "same_match_target_used_in_features":False,
            "silent_imputation":False,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def main()->None:
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "pit_age_hours":out["pit_age_hours"],
        "pit_stale":out["pit_stale"],
        "requires_causal_pit_refresh":out["requires_causal_pit_refresh"],
        "next_required_action":out["next_required_action"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
