from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LANE_ID = "ATP_CHALLENGER_MEN_SINGLES_CLAY"


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def build_bridge(
    *,
    world_inventory: Path,
    dual_audit: Path,
    holdout_contract: Path,
    bootstrap_manifest: Path,
    out_path: Path,
    as_of_utc: str | None = None,
) -> dict[str, Any]:
    world=json.loads(world_inventory.read_text(encoding="utf-8"))
    dual=json.loads(dual_audit.read_text(encoding="utf-8"))
    holdout=json.loads(holdout_contract.read_text(encoding="utf-8"))
    bootstrap=json.loads(bootstrap_manifest.read_text(encoding="utf-8"))

    if holdout["holdout_id"] != "ATP_CHALLENGER_CLAY_PROSPECTIVE_V1":
        raise ValueError("CLAY_HOLDOUT_ID_MISMATCH")
    if holdout["current_observations"] != 0:
        raise ValueError("CLAY_BRIDGE_INITIALIZATION_REQUIRES_ZERO_OBSERVATIONS")
    if holdout["metrics_opened"] is not False or int(holdout["outcomes_read"]) != 0:
        raise ValueError("CLAY_HOLDOUT_SEAL_VIOLATION")

    now=_parse_utc(as_of_utc) if as_of_utc else datetime.now(timezone.utc).replace(microsecond=0)
    source_max=int(bootstrap["source"]["source_max_tourney_date"])

    primary=dual.get("primary_world_inventory") or {}
    secondary=dual.get("secondary_crosscheck") or {}
    day_capture_pass=(
        primary.get("status") in {"PASS","PASS_WORLD_INVENTORY_CAPTURE","PASS_PROVIDER_CAPTURE_WORLD_UNSEALED"}
        and secondary.get("status") in {"PASS","PASS_SECONDARY_PROVIDER_CROSSCHECK","PASS_PROVIDER_CAPTURE_WORLD_UNSEALED"}
    )

    candidates=[]
    seen=set()
    for row in world.get("events",[]) or []:
        if row.get("circuit_detail") != "ATP_CHALLENGER":
            continue
        if row.get("event_format") != "SINGLES":
            continue
        if str(row.get("surface") or "").strip().upper() != "CLAY":
            continue

        pkey=str(row.get("stable_physical_identity_key") or row.get("physical_event_key") or "")
        if not pkey:
            raise ValueError("CLAY_WORLD_EVENT_PHYSICAL_KEY_MISSING")
        if pkey in seen:
            raise ValueError("CLAY_WORLD_EVENT_DUPLICATE_PHYSICAL_KEY")
        seen.add(pkey)

        start=_parse_utc(str(row["event_start_utc"]))
        future=start > now
        event_date=int(start.strftime("%Y%m%d"))
        blockers=[]
        if not future:
            blockers.append("EVENT_NOT_FUTURE")
        if not day_capture_pass:
            blockers.append("DUAL_PAID_PROVIDER_DAY_CAPTURE_NOT_PASS")
        # The daily dual audit proves both providers were queried, but the current
        # exact-day artifact does not contain an API-Tennis event-level binding.
        blockers.append("API_TENNIS_EVENT_LEVEL_IDENTITY_BINDING_REQUIRED")
        if source_max >= event_date:
            pit_history_gap=False
        else:
            pit_history_gap=True
            blockers.append("PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT")

        status=(
            "PREREG_ELIGIBLE_PENDING_IDENTITY_AND_PIT"
            if future and blockers == ["API_TENNIS_EVENT_LEVEL_IDENTITY_BINDING_REQUIRED", "PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT"]
            else "BLOCKED"
        )
        candidates.append({
            "lane_id":LANE_ID,
            "holdout_id":holdout["holdout_id"],
            "physical_event_key":pkey,
            "source_event_id":row.get("source_event_id"),
            "source_event_aliases":row.get("source_event_aliases") or [],
            "provider_channel":row.get("provider_channel"),
            "tournament_id":row.get("tournament_id"),
            "tournament_name":row.get("tournament_name"),
            "round":row.get("round"),
            "surface":"Clay",
            "player1":row.get("player1"),
            "player2":row.get("player2"),
            "event_start_utc":row.get("event_start_utc"),
            "event_start_bogota":row.get("event_start_bogota"),
            "future_at_bridge":future,
            "dual_paid_provider_day_capture":day_capture_pass,
            "api_tennis_event_level_binding":False,
            "pit_history_source_max_tourney_date":source_max,
            "pit_history_caught_up_to_event":not pit_history_gap,
            "status":status,
            "blockers":blockers,
            "freeze_allowed":False,
        })

    future=[x for x in candidates if x["future_at_bridge"]]
    out={
        "schema":"MATRIX_TENNIS_CLAY_WORLD_CALENDAR_BRIDGE_V1",
        "generated_at_utc":now.isoformat(),
        "lane_id":LANE_ID,
        "holdout_id":holdout["holdout_id"],
        "frozen_model_identity":holdout["frozen_model_identity"],
        "world_inventory_path":str(world_inventory),
        "dual_paid_provider_audit_path":str(dual_audit),
        "source_order":["SOFASCORE","FLASHSCORE","RAPIDAPI_TENNIS","API_TENNIS","IDENTITY","PIT_HISTORY","FREEZE"],
        "world_inventory_clay_singles_count":len(candidates),
        "future_clay_singles_count":len(future),
        "prereg_eligible_pending_count":sum(x["status"]=="PREREG_ELIGIBLE_PENDING_IDENTITY_AND_PIT" for x in future),
        "freeze_ready_count":0,
        "prospective_counter_before":0,
        "prospective_counter_after":0,
        "rows":candidates,
        "connection_status":"CONNECTED_DISCOVERY_PREREG_LAYER_FREEZE_GATED",
        "next_required_steps_for_freeze":[
            "BIND_EVENT_LEVEL_API_TENNIS_IDENTITY_TO_RAPIDAPI_PHYSICAL_EVENT",
            "CATCH_UP_CLAY_PIT_HISTORY_STRICTLY_BEFORE_EVENT_START",
            "VERIFY_EVENT_STILL_FUTURE",
            "FREEZE_WINNER_MODEL_PROBABILITY_WITHOUT_ODDS",
        ],
        "protections":{
            "historical_backfill":False,
            "metrics_opened":False,
            "outcomes_read":0,
            "odds_to_probability":False,
            "missing_not_zero":True,
            "silent_imputation":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }
    raw=json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    out["sha256_without_self"]=hashlib.sha256(raw).hexdigest()
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return out


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--world-inventory",required=True)
    parser.add_argument("--dual-audit",required=True)
    parser.add_argument("--holdout-contract",required=True)
    parser.add_argument("--bootstrap-manifest",required=True)
    parser.add_argument("--out",required=True)
    parser.add_argument("--as-of-utc")
    args=parser.parse_args()
    result=build_bridge(
        world_inventory=Path(args.world_inventory),
        dual_audit=Path(args.dual_audit),
        holdout_contract=Path(args.holdout_contract),
        bootstrap_manifest=Path(args.bootstrap_manifest),
        out_path=Path(args.out),
        as_of_utc=args.as_of_utc,
    )
    print(json.dumps({
        "connection_status":result["connection_status"],
        "world_inventory_clay_singles_count":result["world_inventory_clay_singles_count"],
        "future_clay_singles_count":result["future_clay_singles_count"],
        "freeze_ready_count":result["freeze_ready_count"],
        "prospective_counter_after":result["prospective_counter_after"],
    },sort_keys=True))


if __name__=="__main__":
    main()
