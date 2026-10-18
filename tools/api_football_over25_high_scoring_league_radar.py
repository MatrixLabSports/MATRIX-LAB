from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_league(row:Mapping[str,Any])->str:
    n=int(row.get("n") or 0)
    pct=float(row.get("over_2_5_pct") or 0.0)
    last20=row.get("last20")
    last20_pct=float(last20.get("over_2_5_pct")) if isinstance(last20,Mapping) and last20.get("over_2_5_pct") is not None else None

    if 15 <= n < 30 and pct >= 65.0:
        return "EXPERIMENTAL_HIGH"
    if n >= 30 and pct >= 65.0 and last20_pct is not None and last20_pct >= 55.0:
        return "PRIORITY_A_PLUS"
    if n >= 30 and pct >= 58.0 and last20_pct is not None and last20_pct >= 50.0:
        return "PRIORITY_A"
    if n >= 30 and pct >= 52.0:
        return "WATCH_ONLY"
    return "NOT_PRIORITY"


def build_league_policy(audit:Mapping[str,Any])->dict[str,Any]:
    ranking=audit.get("ranking")
    if not isinstance(ranking,list):
        raise ValueError("AUDIT_RANKING_MISSING")

    rows=[]
    for raw in ranking:
        if not isinstance(raw,Mapping):
            continue
        league_id=str(raw.get("league_id") or "").strip()
        if not league_id:
            continue
        bucket=classify_league(raw)
        rows.append({
            "league_id":league_id,
            "label":raw.get("label"),
            "provider_name":raw.get("provider_name"),
            "country":raw.get("country"),
            "season":raw.get("season"),
            "sample_n":int(raw.get("n") or 0),
            "season_over_2_5_pct":float(raw.get("over_2_5_pct") or 0.0),
            "season_avg_goals":float(raw.get("avg_goals") or 0.0),
            "last10_over_2_5_pct":(
                float(raw["last10"]["over_2_5_pct"])
                if isinstance(raw.get("last10"),Mapping) and raw["last10"].get("over_2_5_pct") is not None
                else None
            ),
            "last20_over_2_5_pct":(
                float(raw["last20"]["over_2_5_pct"])
                if isinstance(raw.get("last20"),Mapping) and raw["last20"].get("over_2_5_pct") is not None
                else None
            ),
            "radar_bucket":bucket,
            "eligible_for_priority_radar":bucket in {"PRIORITY_A_PLUS","PRIORITY_A","EXPERIMENTAL_HIGH"},
            "eligible_to_modify_p_matrix":False,
        })
    rows.sort(key=lambda r:(r["eligible_for_priority_radar"],r["season_over_2_5_pct"],r["sample_n"]),reverse=True)
    selected=[r for r in rows if r["eligible_for_priority_radar"]]
    return {
        "schema":"MATRIX_OVER25_HIGH_SCORING_LEAGUE_POLICY_V1",
        "source_audit_observed_at_utc":audit.get("observed_at_utc"),
        "thresholds":{
            "PRIORITY_A_PLUS":{"min_n":30,"min_season_over25_pct":65.0,"min_last20_over25_pct":55.0},
            "PRIORITY_A":{"min_n":30,"min_season_over25_pct":58.0,"min_last20_over25_pct":50.0},
            "EXPERIMENTAL_HIGH":{"min_n":15,"max_n_exclusive":30,"min_season_over25_pct":65.0},
        },
        "selected_league_count":len(selected),
        "selected_league_ids":[r["league_id"] for r in selected],
        "leagues":rows,
        "protections":{
            "discovery_sidecar_only":True,
            "filters_world_inventory":False,
            "reorders_history_queue":False,
            "changes_features":False,
            "changes_model_parameters":False,
            "changes_frozen_probabilities":False,
            "changes_p_matrix":False,
            "league_rate_used_as_probability":False,
            "odds_used":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def build_radar(*,audit:Mapping[str,Any],registry:Mapping[str,Any])->dict[str,Any]:
    if registry.get("future_only") is not True:
        raise ValueError("FUTURE_ONLY_REQUIRED")
    events=registry.get("events")
    if not isinstance(events,list):
        raise ValueError("EVENTS_MUST_BE_LIST")

    original=copy.deepcopy(events)
    policy=build_league_policy(audit)
    by_id={r["league_id"]:r for r in policy["leagues"]}
    candidates=[]
    for row in events:
        if not isinstance(row,Mapping):
            raise ValueError("EVENT_NOT_OBJECT")
        league_id=str(row.get("provider_league_id") or "").strip()
        league=by_id.get(league_id)
        if not league or not league["eligible_for_priority_radar"]:
            continue
        candidates.append({
            "provider_fixture_id":str(row.get("provider_fixture_id") or ""),
            "provider_league_id":league_id,
            "event_start_utc":row.get("event_start_utc"),
            "competition":row.get("competition"),
            "country":row.get("country"),
            "home_team":row.get("home_team"),
            "away_team":row.get("away_team"),
            "radar_bucket":league["radar_bucket"],
            "league_sample_n":league["sample_n"],
            "league_season_over_2_5_pct":league["season_over_2_5_pct"],
            "league_last20_over_2_5_pct":league["last20_over_2_5_pct"],
            "league_rate_role":"DISCOVERY_PRIORITY_CONTEXT_ONLY",
            "p_matrix_adjustment":0.0,
            "bet_decision":"NOT_EVALUATED_BY_RADAR",
        })
    candidates.sort(key=lambda r:(r["event_start_utc"],r["provider_fixture_id"]))

    if events != original:
        raise AssertionError("RADAR_MUTATED_WORLD_REGISTRY")

    return {
        "schema":"MATRIX_OVER25_HIGH_SCORING_LEAGUE_RADAR_V1",
        "target_date":registry.get("target_date"),
        "captured_at_utc":registry.get("captured_at_utc"),
        "source_audit_observed_at_utc":audit.get("observed_at_utc"),
        "world_future_fixture_count":len(events),
        "priority_radar_fixture_count":len(candidates),
        "selected_league_count":policy["selected_league_count"],
        "selected_league_ids":policy["selected_league_ids"],
        "candidates":candidates,
        "protections":policy["protections"],
        "p_matrix_status":"NOT_GENERATED_BY_RADAR",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }


def write_outputs(*,audit_path:Path,registry_path:Path,out_dir:Path)->dict[str,Any]:
    audit=_load(audit_path)
    registry=_load(registry_path)
    policy=build_league_policy(audit)
    radar=build_radar(audit=audit,registry=registry)
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/"league_policy.json").write_text(json.dumps(policy,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    (out_dir/"radar.json").write_text(json.dumps(radar,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    manifest={
        "schema":"MATRIX_OVER25_HIGH_SCORING_LEAGUE_RADAR_MANIFEST_V1",
        "audit_path":str(audit_path),
        "audit_sha256":_sha(audit_path),
        "registry_path":str(registry_path),
        "registry_sha256":_sha(registry_path),
        "league_policy_sha256":_sha(out_dir/"league_policy.json"),
        "radar_sha256":_sha(out_dir/"radar.json"),
        "selected_league_count":policy["selected_league_count"],
        "priority_radar_fixture_count":radar["priority_radar_fixture_count"],
        "matrix_mutation_performed":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--audit",default="evidence/api_football/league_over25_audit/audit_last.json")
    p.add_argument("--registry",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=write_outputs(audit_path=Path(a.audit),registry_path=Path(a.registry),out_dir=Path(a.out))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
