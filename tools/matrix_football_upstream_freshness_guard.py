from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_MANIFEST=Path("evidence/api_football/canonical_analysis/manifest.json")
PERIOD_AUDIT=Path("evidence/market_portfolio/MATRIX_42_LANE_PERIOD_GOALS_FREEZE_BRIDGE_LAST.json")
OUT=Path("evidence/market_portfolio/MATRIX_FOOTBALL_UPSTREAM_FRESHNESS_GUARD_LAST.json")
MAX_CANONICAL_AGE_HOURS=30.0


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _utc(v:Any)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def build(now_utc:datetime|None=None)->dict[str,Any]:
    now=(now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    canonical=_load(CANONICAL_MANIFEST)
    period=_load(PERIOD_AUDIT)
    captured=_utc(canonical.get("source_fixture_capture_at_utc") or canonical.get("analysis_as_of_utc"))
    age_hours=(now-captured).total_seconds()/3600.0
    future_candidates=int(period.get("future_source_fixture_candidates") or 0)
    feature_eligible=int(period.get("feature_eligible_future_unique_fixtures") or 0)
    admitted=int(period.get("eligible_future_unique_fixtures") or 0)
    duplicates=int(period.get("duplicate_existing_lane_rows") or 0)
    blocked=int(period.get("blocked_count") or 0)
    stale=age_hours>MAX_CANONICAL_AGE_HOURS
    if stale:
        action="REFRESH_GOVERNED_DAILY_OR_HORIZON_UPSTREAM_BEFORE_DIAGNOSING_NO_NEW_EVENTS"
        state="STALE_UPSTREAM_BLOCKS_NEW_EVENT_CONVERSION"
    elif admitted==0 and future_candidates>0 and feature_eligible>0 and duplicates>0:
        action="WAIT_FOR_GENUINELY_NEW_PREMATCH_FIXTURES_AND_KEEP_15M_DEDUP_SUPERVISION"
        state="FRESH_UPSTREAM_ALL_ELIGIBLE_EVENTS_ALREADY_SEEN"
    else:
        action="CONTINUE_15M_GOVERNED_SUPERVISION"
        state="UPSTREAM_FRESH_OR_NEW_EVENTS_AVAILABLE"
    return {
        "schema":"MATRIX_FOOTBALL_UPSTREAM_FRESHNESS_GUARD_V1",
        "generated_at_utc":now.replace(microsecond=0).isoformat(),
        "status":"PASS",
        "upstream_state":state,
        "canonical_source_fixture_capture_at_utc":captured.isoformat(),
        "canonical_age_hours":round(age_hours,3),
        "maximum_allowed_canonical_age_hours":MAX_CANONICAL_AGE_HOURS,
        "canonical_stale":stale,
        "period_conversion":{
            "future_source_fixture_candidates":future_candidates,
            "feature_eligible_future_unique_fixtures":feature_eligible,
            "new_unique_fixtures_admitted":admitted,
            "duplicate_existing_lane_rows":duplicates,
            "blocked_count":blocked,
        },
        "next_required_action":action,
        "protections":{
            "stale_upstream_never_interpreted_as_zero_demand":True,
            "duplicates_never_recounted":True,
            "post_start_backfill":False,
            "silent_imputation":False,
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
        "upstream_state":out["upstream_state"],
        "canonical_age_hours":out["canonical_age_hours"],
        "canonical_stale":out["canonical_stale"],
        "next_required_action":out["next_required_action"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
