from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path

from tools.api_football_prediction_store import load_chunked_json
from typing import Any, Mapping

from app.research.football.experimental_evaluator import evaluate_transparent_poisson_baseline
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_freeze_experimental_shadow import _rehydrate_input

EPS=1e-12
MIN_GROUP_HISTORY=20
FINAL_STATUSES={"FT","AET","PEN"}


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _logit(p:float)->float:
    p=_clip(p)
    return log(p/(1-p))


def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-x)
        return 1/(1+z)
    z=exp(x)
    return z/(1+z)


def _sha(payload:Any)->str:
    return sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def _historical_group_baseline(raw_path:Path, freeze_at:datetime)->dict[str,float]|None:
    if not raw_path.exists():
        return None
    payload=_load(raw_path)
    response=payload.get("response")
    if not isinstance(response,list):
        return None
    finals=[]
    for row in response:
        if not isinstance(row,Mapping):
            continue
        fixture=row.get("fixture"); goals=row.get("goals")
        if not isinstance(fixture,Mapping) or not isinstance(goals,Mapping):
            continue
        status=fixture.get("status")
        if not isinstance(status,Mapping) or str(status.get("short") or "").upper() not in FINAL_STATUSES:
            continue
        try:
            kickoff=_utc(fixture.get("date"))
        except Exception:
            continue
        if kickoff>=freeze_at:
            continue
        hg=goals.get("home"); ag=goals.get("away")
        if isinstance(hg,bool) or isinstance(ag,bool) or not isinstance(hg,int) or not isinstance(ag,int):
            continue
        finals.append((kickoff,hg,ag))
    finals.sort()
    if len(finals)<MIN_GROUP_HISTORY:
        return None
    n=len(finals)
    return {
        "H":sum(hg>ag for _,hg,ag in finals)/n,
        "D":sum(hg==ag for _,hg,ag in finals)/n,
        "A":sum(hg<ag for _,hg,ag in finals)/n,
        "over_2_5":sum(hg+ag>=3 for _,hg,ag in finals)/n,
        "btts":sum(hg>0 and ag>0 for _,hg,ag in finals)/n,
        "sample_size":n,
    }


def _mc_pool(poisson:Mapping[str,float], baseline:Mapping[str,float], a:float,c:float)->dict[str,float]:
    scores={}
    for k,pkey in (("H","home_win"),("D","draw"),("A","away_win")):
        pp=max(float(poisson[pkey]),EPS); bp=max(float(baseline[k]),EPS)
        scores[k]=exp(a*log(pp)+c*log(bp))
    total=sum(scores.values())
    return {k:v/total for k,v in scores.items()}


def _bin_pool(poisson_p:float, baseline_p:float, a:float,c:float,b:float)->float:
    return _sigmoid(a*_logit(poisson_p)+c*_logit(baseline_p)+b)


def _btts_v2_probability(*,poisson_p:float,baseline_p:float,ehg:float,eag:float,home_count:int,away_count:int,weights:list[float])->float:
    x=[
        1.0,
        _logit(poisson_p),
        _logit(baseline_p),
        float(ehg),
        float(eag),
        abs(float(ehg)-float(eag)),
        min(float(ehg),float(eag)),
        float(home_count)/20.0,
        float(away_count)/20.0,
    ]
    if len(weights)!=len(x):
        raise ValueError("BTTS_V2_WEIGHT_DIMENSION_MISMATCH")
    return _sigmoid(sum(w*v for w,v in zip(weights,x)))


def build_freeze(
    root:Path,
    freeze_at:datetime,
    *,
    canonical_root:Path|None=None,
    history_root:Path|None=None,
)->dict[str,Any]:
    freeze=freeze_at.astimezone(timezone.utc).replace(microsecond=0)
    canonical_dir=canonical_root or (root/"evidence/api_football/canonical_analysis")
    history_dir=history_root or (root/"evidence/api_football/history")
    canonical,manifest=load_chunked_canonical_bundle(canonical_dir)
    gov=_load(root/"evidence/api_football/market_governance/market_governance.json")
    btts=_load(root/"evidence/api_football/btts_challenger_v2/manifest.json")
    retrospective=load_chunked_json(root/"evidence/api_football/model_validation/retrospective_predictions_manifest.json")
    excluded_original=_load(root/"evidence/api_football/btts_challenger_v2/exclusion_registry.json")

    if set(gov["approved_markets"])!={"1x2","over_2_5"}:
        raise ValueError("MARKET_GOVERNANCE_NOT_EXPECTED")
    if btts["candidate_status"]!="FROZEN_BTTS_V2_AWAITING_NEW_PROSPECTIVE_HOLDOUT":
        raise ValueError("BTTS_V2_NOT_FROZEN")
    if btts["forbidden_final_holdout_outcomes_read"] is not False:
        raise ValueError("ORIGINAL_HOLDOUT_CONTAMINATED")

    historical_seen={str(r["fixture_id"]) for r in retrospective.get("rows",[]) if isinstance(r,Mapping)}
    forbidden={str(x) for x in excluded_original.get("forbidden_fixture_ids",[])}
    if len(forbidden)!=357:
        raise ValueError("FORBIDDEN_REGISTRY_COUNT_CHANGED")

    gov_by_market={r["market"]:r for r in gov["markets"]}
    p1=gov_by_market["1x2"]["frozen_parameters"]
    po=gov_by_market["over_2_5"]["frozen_parameters"]
    weights=list(btts["selected"]["weights"])

    frozen=[]
    exclusions=[]
    for raw in canonical.get("inputs",[]):
        value=_rehydrate_input(raw)
        kickoff=_utc(value.kickoff_utc)
        fid=str(value.fixture_id)
        if freeze>=kickoff:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"NOT_FUTURE_AT_FREEZE"})
            continue
        if fid in historical_seen or fid in forbidden:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"NOT_UNSEEN_EVENT"})
            continue

        raw_path=history_dir/f"raw/league_{value.competition_id}_season_{value.season}.bin"
        baseline=_historical_group_baseline(raw_path,freeze)
        if baseline is None:
            exclusions.append({
                "fixture_id":fid,
                "target_key":value.target_key,
                "reason":"FEATURE_NOT_REPRODUCIBLE",
                "required_source":raw_path.as_posix(),
            })
            continue

        ev=evaluate_transparent_poisson_baseline(value)
        if ev.probabilities is None or ev.expected_home_goals is None or ev.expected_away_goals is None:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"POISSON_INPUT_NOT_EXECUTABLE"})
            continue
        home_count=ev.readiness.home_history_count
        away_count=ev.readiness.away_history_count

        p_1x2=_mc_pool(ev.probabilities,baseline,float(p1["a"]),float(p1["c"]))
        p_over=_bin_pool(float(ev.probabilities["over_2_5"]),float(baseline["over_2_5"]),float(po["a"]),float(po["c"]),float(po["b"]))
        p_btts=_btts_v2_probability(
            poisson_p=float(ev.probabilities["btts"]),
            baseline_p=float(baseline["btts"]),
            ehg=float(ev.expected_home_goals),
            eag=float(ev.expected_away_goals),
            home_count=home_count,
            away_count=away_count,
            weights=weights,
        )
        frozen.append({
            "fixture_id":fid,
            "target_key":value.target_key,
            "competition_id":value.competition_id,
            "competition_name":value.competition_name,
            "home_team_id":value.home_team_id,
            "home_team_name":value.home_team_name,
            "away_team_id":value.away_team_id,
            "away_team_name":value.away_team_name,
            "season":value.season,
            "kickoff_utc":value.kickoff_utc,
            "freeze_at_utc":freeze.isoformat(),
            "input_sha256":value.canonical_sha256(),
            "historical_baseline_source":(
                raw_path.relative_to(root).as_posix()
                if raw_path.is_relative_to(root)
                else raw_path.as_posix()
            ),
            "historical_baseline_sample_size":baseline["sample_size"],
            "poisson_reference":{
                "1x2":{"H":ev.probabilities["home_win"],"D":ev.probabilities["draw"],"A":ev.probabilities["away_win"]},
                "over_2_5":ev.probabilities["over_2_5"],
                "btts":ev.probabilities["btts"],
            },
            "frozen_research_probabilities":{
                "1x2":p_1x2,
                "over_2_5":p_over,
                "btts_v2":p_btts,
            },
            "market_status":{
                "1x2":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW",
                "over_2_5":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW",
                "btts_v2":"NEW_PROSPECTIVE_HOLDOUT",
            },
            "outcome":None,
            "settlement_status":"PENDING_FINAL",
            "odds_used_to_generate_probability":False,
            "p_matrix":None,
        })

    frozen.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    exclusions.sort(key=lambda r:int(r["fixture_id"]))
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_MARKET_FREEZE_V1",
        "created_at_utc":freeze.isoformat(),
        "source_canonical_bundle_sha256":manifest["bundle_sha256"],
        "source_market_governance_holdout_sha256":gov["holdout_seal_sha256"],
        "source_btts_v2_exclusion_registry_sha256":btts["exclusion_registry_sha256"],
        "historical_seen_fixture_count":len(historical_seen),
        "permanently_forbidden_original_holdout_count":len(forbidden),
        "frozen_event_count":len(frozen),
        "excluded_event_count":len(exclusions),
        "rows":frozen,
        "exclusions":exclusions,
        "protections":{
            "future_only":True,
            "unseen_events_only":True,
            "freeze_strictly_before_kickoff":True,
            "original_357_holdout_excluded":True,
            "missing_feature_imputation":False,
            "outcomes_read_at_freeze":False,
            "settlement_final_only":True,
            "odds_used_to_generate_probability":False,
            "p_matrix_generated":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def _row_identity(row:Mapping[str,Any])->tuple[str,str]:
    return str(row.get("fixture_id") or ""), _sha(row)


def _physical_key(row:Mapping[str,Any])->tuple[str,str,str,str,str]:
    return (
        str(row.get("competition_id") or ""),
        str(row.get("season") or ""),
        str(row.get("home_team_id") or ""),
        str(row.get("away_team_id") or ""),
        str(row.get("kickoff_utc") or ""),
    )


def _pair_key(row:Mapping[str,Any])->tuple[str,str,str,str]:
    return (
        str(row.get("competition_id") or ""),
        str(row.get("season") or ""),
        str(row.get("home_team_id") or ""),
        str(row.get("away_team_id") or ""),
    )


def _hours_apart(left:Mapping[str,Any],right:Mapping[str,Any])->float:
    return abs((_utc(left.get("kickoff_utc"))-_utc(right.get("kickoff_utc"))).total_seconds())/3600.0


def merge_incremental_freeze(
    *,
    existing:Mapping[str,Any]|None,
    candidate:Mapping[str,Any],
)->tuple[dict[str,Any],dict[str,Any]]:
    candidate_rows=candidate.get("rows")
    if not isinstance(candidate_rows,list):
        raise ValueError("CANDIDATE_FREEZE_ROWS_INVALID")

    if existing is None:
        physical_seen:set[tuple[str,str,str,str,str]]=set()
        pair_seen:dict[tuple[str,str,str,str],list[Mapping[str,Any]]]={}
        accepted=[]
        physical_collisions=[]
        suspicious_collisions=[]
        for row in candidate_rows:
            if not isinstance(row,Mapping):
                raise ValueError("CANDIDATE_FREEZE_ROW_INVALID")
            pkey=_physical_key(row)
            if pkey in physical_seen:
                physical_collisions.append({
                    "fixture_id":str(row.get("fixture_id") or ""),
                    "reason":"DUPLICATE_PHYSICAL_EVENT_DIFFERENT_FIXTURE_ID",
                })
                continue
            pair=_pair_key(row)
            near=[
                prior for prior in pair_seen.get(pair,[])
                if str(prior.get("fixture_id"))!=str(row.get("fixture_id"))
                and _hours_apart(prior,row)<=36.0
            ]
            if near:
                suspicious_collisions.append({
                    "fixture_id":str(row.get("fixture_id") or ""),
                    "reason":"SUSPECT_SAME_TEAMS_WITHIN_36H",
                    "conflicts_with":[str(x.get("fixture_id") or "") for x in near],
                })
                continue
            accepted.append(dict(row))
            physical_seen.add(pkey)
            pair_seen.setdefault(pair,[]).append(row)

        merged=dict(candidate)
        merged["rows"]=accepted
        merged["frozen_event_count"]=len(accepted)
        merged["incremental_mode"]=True
        merged["freeze_cycle_count"]=1
        merged["last_cycle_new_event_count"]=len(accepted)
        merged["last_cycle_candidate_event_count"]=len(candidate_rows)
        merged["last_cycle_excluded_event_count"]=int(candidate.get("excluded_event_count") or 0)
        return merged,{
            "status":"INITIAL_FREEZE",
            "previous_event_count":0,
            "candidate_event_count":len(candidate_rows),
            "new_event_count":len(accepted),
            "cumulative_event_count":len(accepted),
            "existing_rows_unchanged":True,
            "physical_collision_blocked_count":len(physical_collisions)+len(suspicious_collisions),
            "physical_duplicate_collisions":physical_collisions,
            "suspicious_physical_collisions":suspicious_collisions,
        }

    old_rows=existing.get("rows")
    if not isinstance(old_rows,list):
        raise ValueError("EXISTING_FREEZE_ROWS_INVALID")
    old_protections=existing.get("protections")
    if old_protections!=candidate.get("protections"):
        raise ValueError("FREEZE_PROTECTIONS_CHANGED")

    existing_by_id:dict[str,dict[str,Any]]={}
    old_hashes:dict[str,str]={}
    existing_physical:dict[tuple[str,str,str,str,str],str]={}
    existing_pairs:dict[tuple[str,str,str,str],list[Mapping[str,Any]]]={}
    for row in old_rows:
        if not isinstance(row,Mapping):
            raise ValueError("EXISTING_FREEZE_ROW_INVALID")
        fid,row_hash=_row_identity(row)
        if not fid or fid in existing_by_id:
            raise ValueError("EXISTING_FREEZE_DUPLICATE_OR_MISSING_FIXTURE")
        pkey=_physical_key(row)
        if pkey in existing_physical and existing_physical[pkey]!=fid:
            raise ValueError("EXISTING_FREEZE_PHYSICAL_DUPLICATE:"+fid)
        existing_by_id[fid]=dict(row)
        old_hashes[fid]=row_hash
        existing_physical[pkey]=fid
        existing_pairs.setdefault(_pair_key(row),[]).append(row)

    new_rows=[]
    skipped_existing=[]
    physical_collisions=[]
    suspicious_collisions=[]
    for row in candidate_rows:
        if not isinstance(row,Mapping):
            raise ValueError("CANDIDATE_FREEZE_ROW_INVALID")
        fid=str(row.get("fixture_id") or "")
        if not fid:
            raise ValueError("CANDIDATE_FREEZE_FIXTURE_ID_MISSING")
        if fid in existing_by_id:
            skipped_existing.append(fid)
            continue
        freeze_at=_utc(row.get("freeze_at_utc"))
        kickoff=_utc(row.get("kickoff_utc"))
        if freeze_at>=kickoff:
            raise ValueError("INCREMENTAL_FREEZE_NOT_PREMATCH:"+fid)

        pkey=_physical_key(row)
        prior_fid=existing_physical.get(pkey)
        if prior_fid is not None and prior_fid!=fid:
            physical_collisions.append({
                "fixture_id":fid,
                "reason":"DUPLICATE_PHYSICAL_EVENT_DIFFERENT_FIXTURE_ID",
                "conflicts_with":[prior_fid],
            })
            continue

        pair=_pair_key(row)
        near=[
            prior for prior in existing_pairs.get(pair,[])
            if str(prior.get("fixture_id"))!=fid
            and _hours_apart(prior,row)<=36.0
        ]
        if near:
            suspicious_collisions.append({
                "fixture_id":fid,
                "reason":"SUSPECT_SAME_TEAMS_WITHIN_36H",
                "conflicts_with":[str(x.get("fixture_id") or "") for x in near],
            })
            continue

        new_rows.append(dict(row))
        existing_physical[pkey]=fid
        existing_pairs.setdefault(pair,[]).append(row)

    merged_rows=[dict(row) for row in old_rows]+new_rows
    merged_rows.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))

    # Existing rows are immutable: adding a new cycle cannot change any old row.
    for row in merged_rows:
        fid=str(row["fixture_id"])
        if fid in old_hashes and _sha(row)!=old_hashes[fid]:
            raise ValueError("EXISTING_FREEZE_ROW_MUTATED:"+fid)

    merged=dict(existing)
    merged["rows"]=merged_rows
    merged["frozen_event_count"]=len(merged_rows)
    merged["updated_at_utc"]=candidate["created_at_utc"]
    merged["source_canonical_bundle_sha256"]=candidate["source_canonical_bundle_sha256"]
    merged["incremental_mode"]=True
    merged["freeze_cycle_count"]=int(existing.get("freeze_cycle_count") or 1)+(1 if new_rows else 0)
    merged["last_cycle_new_event_count"]=len(new_rows)
    merged["last_cycle_candidate_event_count"]=len(candidate_rows)
    merged["last_cycle_excluded_event_count"]=int(candidate.get("excluded_event_count") or 0)
    merged["last_cycle_skipped_existing_fixture_ids"]=sorted(skipped_existing,key=int)
    merged["exclusions"]=candidate.get("exclusions",[])
    merged["excluded_event_count"]=int(candidate.get("excluded_event_count") or 0)

    summary={
        "status":"APPENDED" if new_rows else "NO_NEW_ELIGIBLE_EVENTS",
        "previous_event_count":len(old_rows),
        "candidate_event_count":len(candidate_rows),
        "new_event_count":len(new_rows),
        "new_fixture_ids":[str(r["fixture_id"]) for r in new_rows],
        "skipped_existing_count":len(skipped_existing),
        "physical_collision_blocked_count":len(physical_collisions)+len(suspicious_collisions),
        "physical_duplicate_collisions":physical_collisions,
        "suspicious_physical_collisions":suspicious_collisions,
        "cumulative_event_count":len(merged_rows),
        "existing_rows_unchanged":True,
        "previous_freeze_sha256":_sha(existing),
        "merged_freeze_sha256":_sha(merged),
        "real_money":"BLOCKED",
        "automatic_wagering":False,
    }
    return merged,summary


def persist_incremental_freeze(
    root:Path,
    freeze_at:datetime,
    *,
    canonical_root:Path|None=None,
    history_root:Path|None=None,
)->dict[str,Any]:
    out=root/"evidence/api_football/prospective_market_freeze"
    out.mkdir(parents=True,exist_ok=True)
    freeze_path=out/"freeze.json"
    existing=_load(freeze_path) if freeze_path.exists() else None
    candidate=build_freeze(
        root,
        freeze_at,
        canonical_root=canonical_root,
        history_root=history_root,
    )
    merged,summary=merge_incremental_freeze(existing=existing,candidate=candidate)

    sync_path=out/"incremental_sync_last.json"
    sync_path.write_text(
        json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    if summary["new_event_count"]==0 and existing is not None:
        return summary
    if merged["frozen_event_count"]<=0:
        raise ValueError("NO_ELIGIBLE_FUTURE_EVENTS_FOR_PROSPECTIVE_FREEZE")

    freeze_path.write_text(
        json.dumps(merged,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    manifest={k:v for k,v in merged.items() if k not in {"rows","exclusions"}}
    manifest["freeze_sha256"]=_sha(merged)
    manifest["incremental_summary"]=summary
    (out/"manifest.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    return summary


def main()->None:
    result=persist_incremental_freeze(Path("."),datetime.now(timezone.utc))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
