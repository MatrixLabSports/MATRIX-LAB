from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RANKING_CUT, RapidApiTennisClient


def _load(path: Path) -> dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry(
    *,
    catchup: Mapping[str,Any],
    ranking_by_player: Mapping[str,Mapping[str,Any]],
    revision: str,
    max_targets: int,
) -> dict[str,Any]:
    candidates=[]
    blocked=[]
    for raw in catchup.get("unmapped_identity_backlog",[]) or []:
        if not isinstance(raw,Mapping):
            continue
        if len(candidates)>=max(0,int(max_targets)):
            break
        pid=str(raw.get("numeric_player_id") or "").strip()
        provider_id=str(raw.get("provider_player_id") or "")
        if not pid.isdigit() or provider_id!="rapidapi-tennis:player:"+pid:
            blocked.append({"provider_player_id":provider_id,"reason":"BACKLOG_PROVIDER_ID_INVALID"})
            continue
        if raw.get("identity_observation_status")!="CONSISTENT":
            blocked.append({"provider_player_id":provider_id,"reason":"BACKLOG_IDENTITY_OBSERVATION_CONFLICT"})
            continue
        ranking=ranking_by_player.get(pid)
        if not isinstance(ranking,Mapping):
            blocked.append({"provider_player_id":provider_id,"reason":"EXACT_21SEP_RANKING_MISSING"})
            continue
        ranking_name=str(ranking.get("player") or "").strip()
        ranking_ioc=str(ranking.get("country") or "").strip().upper()
        observed_names=[str(x).strip() for x in raw.get("observed_names",[]) or [] if str(x).strip()]
        observed_iocs=[str(x).strip().upper() for x in raw.get("observed_iocs",[]) or [] if str(x).strip()]
        if len(observed_names)!=1:
            blocked.append({"provider_player_id":provider_id,"reason":"OBSERVED_NAME_NOT_UNIQUE"})
            continue
        # Do not join to canonical history here. This only builds provider
        # evidence for the existing fail-closed authority expander.
        event_id=f"CLAY-CATCHUP-IDENTITY-{pid}-{revision}"
        candidates.append({
            "event_id":event_id,
            "canonical_source_event_id":"identity-recovery:"+pid,
            "competition":"CLAY_PIT_CATCHUP_IDENTITY_RECOVERY",
            "competition_id":"identity-recovery",
            "event_start_utc":"2099-01-01T00:00:00+00:00",
            "features_loaded":False,
            "historical_identity_crosswalk_status":"PENDING",
            "identity_crosswalk_required":True,
            "identity_source":"RAPIDAPI_EXACT_RANKING_2026-09-21_PLUS_CATCHUP_RESULT_ID",
            "metrics_opened":False,
            "outcome":None,
            "physical_event_key":"IDENTITY_ONLY:"+pid,
            "player_identities":[{
                "display_name":ranking_name,
                "provider":"rapidapi_tennis",
                "provider_player_id":provider_id,
                "provider_ranking":dict(ranking),
                "catchup_observed_name":observed_names[0],
                "catchup_observed_iocs":observed_iocs,
            }],
            "players":[ranking_name],
            "round":"IDENTITY_ONLY",
            "schedule_source":"identity_recovery_only",
            "source_provider":"rapidapi_tennis",
            "source_snapshot_sha256":"IDENTITY_ONLY",
            "surface":"Clay",
            "target_period":20260921,
            "tour_level":"C",
            "identity_only":True,
            "model_admission_forbidden":True,
            "catchup_matches":int(raw.get("catchup_matches") or 0),
            "target_component_hits":int(raw.get("target_component_hits") or 0),
        })
    return {
        "schema":"MATRIX_TENNIS_CLAY_CATCHUP_IDENTITY_RECOVERY_REGISTRY_V1",
        "revision":revision,
        "lane_id":"ATP_CHALLENGER_MEN_SINGLES_CLAY",
        "created_before_feature_acquisition":True,
        "identity_only":True,
        "model_admission_forbidden":True,
        "ranking_cut":RANKING_CUT.strftime("%Y%m%d"),
        "events":candidates,
        "blocked":blocked,
        "selected_count":len(candidates),
        "backlog_count":int(catchup.get("unmapped_identity_backlog_count") or 0),
        "metrics_opened":False,
        "outcomes_read":0,
        "historical_backfill":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--catchup",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--revision",required=True)
    p.add_argument("--max-targets",type=int,default=12)
    a=p.parse_args()
    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    catchup=_load(Path(a.catchup))
    backlog=[
        row for row in catchup.get("unmapped_identity_backlog",[]) or []
        if isinstance(row,Mapping)
        and row.get("identity_observation_status")=="CONSISTENT"
    ]
    backlog.sort(
        key=lambda row: (
            -int(row.get("target_component_hits") or 0),
            -int(row.get("catchup_matches") or 0),
            str(row.get("provider_player_id") or ""),
        )
    )
    backlog=backlog[:max(0,int(a.max_targets))]
    wanted={str(row.get("numeric_player_id") or "") for row in backlog}
    client=RapidApiTennisClient(key)
    rankings=client.ranking_snapshot(ranking_date=RANKING_CUT,wanted_player_ids=wanted)
    registry=build_registry(
        catchup=catchup,
        ranking_by_player=rankings,
        revision=str(a.revision),
        max_targets=int(a.max_targets),
    )
    registry["ranking_players_requested"]=len(wanted)
    registry["ranking_players_found"]=len(rankings)
    registry["provider_network_calls"]=client.request_count
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(registry,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "backlog_count":registry["backlog_count"],
        "selected_count":registry["selected_count"],
        "ranking_players_requested":registry["ranking_players_requested"],
        "ranking_players_found":registry["ranking_players_found"],
        "blocked_count":len(registry["blocked"]),
        "provider_network_calls":registry["provider_network_calls"],
        "real_money":"BLOCKED"
    },sort_keys=True))


if __name__=="__main__":
    main()
