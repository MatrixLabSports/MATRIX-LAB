from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

EPS=1e-15
MIN_TRACKING_N=15
MIN_STRONG_N=30


def _load_json(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT:"+str(path))
    return value


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest(pattern:str)->Path:
    rows=sorted(Path(".").glob(pattern))
    if not rows:
        raise FileNotFoundError(pattern)
    return rows[-1]


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _mean(xs:list[float])->float:
    return sum(xs)/len(xs)


def _paired_ci95(diffs:list[float])->dict[str,Any]:
    n=len(diffs)
    if not n:
        return {"n":0,"mean":None,"se":None,"ci95":None}
    m=_mean(diffs)
    if n==1:
        return {"n":1,"mean":m,"se":None,"ci95":None}
    var=sum((x-m)**2 for x in diffs)/(n-1)
    se=math.sqrt(var/n)
    return {"n":n,"mean":m,"se":se,"ci95":[m-1.96*se,m+1.96*se]}


def _competition_index(freeze:Mapping[str,Any])->dict[str,dict[str,Any]]:
    out={}
    for row in freeze.get("rows") or []:
        if not isinstance(row,Mapping):
            continue
        fid=str(row.get("fixture_id") or "")
        if not fid:
            continue
        out[fid]={
            "competition_id":str(row.get("competition_id") or ""),
            "competition_name":row.get("competition_name"),
            "season":row.get("season"),
        }
    return out


def _binary_metrics(rows:list[dict[str,Any]],market:str)->dict[str,Any]:
    cb=pb=cl=pl=0.0
    db=[]; dl=[]
    for row in rows:
        y=1 if bool(row["outcomes"][market]) else 0
        cp=_clip(row["frozen_challenger_probabilities"][market])
        pp=_clip(row["frozen_poisson_reference"][market])
        cbi=(cp-y)**2; pbi=(pp-y)**2
        cli=-(y*math.log(cp)+(1-y)*math.log(1-cp))
        pli=-(y*math.log(pp)+(1-y)*math.log(1-pp))
        cb+=cbi; pb+=pbi; cl+=cli; pl+=pli
        db.append(cbi-pbi); dl.append(cli-pli)
    n=len(rows)
    return {
        "n":n,
        "challenger_brier":cb/n,
        "reference_brier":pb/n,
        "delta_brier":cb/n-pb/n,
        "challenger_log_loss":cl/n,
        "reference_log_loss":pl/n,
        "delta_log_loss":cl/n-pl/n,
        "paired_brier":_paired_ci95(db),
        "paired_log_loss":_paired_ci95(dl),
    }


def _multiclass_1x2_metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    cb=pb=cl=pl=0.0; ca=pa=0
    db=[]; dl=[]; da=[]
    labels=("H","D","A")
    for row in rows:
        y=str(row["outcomes"]["1x2"])
        cp=row["frozen_challenger_probabilities"]["1x2"]
        pp=row["frozen_poisson_reference"]["1x2"]
        cbi=pbi=0.0
        for k in labels:
            yy=1 if y==k else 0
            cbi+=(float(cp[k])-yy)**2
            pbi+=(float(pp[k])-yy)**2
        cli=-math.log(max(float(cp[y]),EPS))
        pli=-math.log(max(float(pp[y]),EPS))
        c_pred=max(labels,key=lambda k:float(cp[k]))
        p_pred=max(labels,key=lambda k:float(pp[k]))
        cai=1 if c_pred==y else 0
        pai=1 if p_pred==y else 0
        cb+=cbi; pb+=pbi; cl+=cli; pl+=pli; ca+=cai; pa+=pai
        db.append(cbi-pbi); dl.append(cli-pli); da.append(cai-pai)
    n=len(rows)
    return {
        "n":n,
        "challenger_brier":cb/n,
        "reference_brier":pb/n,
        "delta_brier":cb/n-pb/n,
        "challenger_log_loss":cl/n,
        "reference_log_loss":pl/n,
        "delta_log_loss":cl/n-pl/n,
        "challenger_accuracy":ca/n,
        "reference_accuracy":pa/n,
        "delta_accuracy":ca/n-pa/n,
        "paired_brier":_paired_ci95(db),
        "paired_log_loss":_paired_ci95(dl),
        "paired_accuracy":_paired_ci95(da),
    }


def _strength_from_metrics(metrics:Mapping[str,Any])->tuple[str,str]:
    n=int(metrics["n"])
    db=float(metrics["delta_brier"])
    dl=float(metrics["delta_log_loss"])
    bci=metrics.get("paired_brier",{}).get("ci95")
    lci=metrics.get("paired_log_loss",{}).get("ci95")

    if n<MIN_TRACKING_N:
        return "INSUFFICIENT_DATA","N_BELOW_15"

    strong=(
        n>=MIN_STRONG_N and db<0 and dl<0
        and isinstance(bci,list) and bci[1]<0
        and isinstance(lci,list) and lci[1]<0
    )
    if strong:
        return "STRONG","BOTH_PROPER_SCORES_BETTER_AND_95CI_FAVORABLE"

    no_go=(
        n>=MIN_STRONG_N and db>0 and dl>0
        and isinstance(bci,list) and bci[0]>0
        and isinstance(lci,list) and lci[0]>0
    )
    if no_go:
        return "NO_GO","BOTH_PROPER_SCORES_WORSE_AND_95CI_UNFAVORABLE"

    return "DEVELOPING","TRACKING_SAMPLE_WITHOUT_DECISIVE_STRONG_OR_NO_GO_EVIDENCE"


def _radar_index(path:Path)->dict[str,dict[str,Any]]:
    if not path.exists():
        return {}
    d=_load_json(path)
    rows=d.get("selected_leagues") or d.get("leagues") or []
    return {str(r.get("league_id")):dict(r) for r in rows if isinstance(r,Mapping) and r.get("league_id") is not None}


def _football_cells(
    ledger:list[dict[str,Any]],
    freeze:Mapping[str,Any],
    market_master:Mapping[str,Any],
    radar:dict[str,dict[str,Any]],
)->list[dict[str,Any]]:
    comp=_competition_index(freeze)
    joined=[]
    for row in ledger:
        fid=str(row.get("fixture_id") or "")
        meta=comp.get(fid)
        if not meta:
            continue
        joined.append({**row,"_competition":meta})

    cells=[]
    grouped=defaultdict(list)
    for row in joined:
        cid=row["_competition"]["competition_id"]
        grouped[cid].append(row)

    def make_metric_cell(cid:str,name:str,season:Any,market:str,rows:list[dict[str,Any]],metrics:dict[str,Any]):
        strength,reason=_strength_from_metrics(metrics)
        radar_row=radar.get(cid)
        return {
            "sport":"FOOTBALL",
            "competition_id":cid,
            "competition_name":name,
            "season":season,
            "market":market,
            "scope":"COMPETITION",
            "strength_class":strength,
            "classification_reason":reason,
            "prospective_n":metrics["n"],
            "metrics":metrics,
            "league_radar_context":(
                {
                    "radar_bucket":radar_row.get("radar_bucket"),
                    "league_sample_n":radar_row.get("sample_n"),
                    "league_over_2_5_pct":radar_row.get("season_over_2_5_pct"),
                    "p_matrix_adjustment":0.0,
                } if radar_row else None
            ),
            "model_mutation_allowed":False,
            "cell_used_to_generate_probability":False,
        }

    for cid,rows in grouped.items():
        meta=rows[0]["_competition"]
        cells.append(make_metric_cell(cid,meta["competition_name"],meta["season"],"OVER_2_5",rows,_binary_metrics(rows,"over_2_5")))
        cells.append(make_metric_cell(cid,meta["competition_name"],meta["season"],"1X2",rows,_multiclass_1x2_metrics(rows)))

    # Global football proper-score cells.
    if joined:
        for market in ("OVER_2_5","1X2"):
            metrics=_binary_metrics(joined,"over_2_5") if market=="OVER_2_5" else _multiclass_1x2_metrics(joined)
            strength,reason=_strength_from_metrics(metrics)
            cells.append({
                "sport":"FOOTBALL","competition_id":"ALL","competition_name":"ALL_COMPETITIONS",
                "season":"MIXED","market":market,"scope":"GLOBAL_MARKET",
                "strength_class":strength,"classification_reason":reason,
                "prospective_n":metrics["n"],"metrics":metrics,
                "model_mutation_allowed":False,"cell_used_to_generate_probability":False,
            })

    # Global market-governance cells for lanes without competition-level prospective samples.
    status_map=market_master.get("markets") or {}
    for market_key,row in status_map.items():
        if market_key in {"OVER_2_5","ONE_X_TWO"} or not isinstance(row,Mapping):
            continue
        status=str(row.get("status") or "")
        oos=row.get("oos") if isinstance(row.get("oos"),Mapping) else None
        if "NO_GO" in status or "REJECTED" in status:
            strength="NO_GO"
            reason="FORMAL_GOVERNANCE_NO_GO"
        elif bool(row.get("historical_oos_passed")) or bool(oos and oos.get("gate_passed")):
            strength="DEVELOPING"
            reason="HISTORICAL_OOS_PASS_PROSPECTIVE_SAMPLE_NOT_MATURE"
        else:
            strength="INSUFFICIENT_DATA"
            reason="NO_MATURE_PROSPECTIVE_EVIDENCE"
        cells.append({
            "sport":"FOOTBALL","competition_id":"ALL","competition_name":"ALL_COMPETITIONS",
            "season":"MIXED","market":market_key,"scope":"GLOBAL_MARKET",
            "strength_class":strength,"classification_reason":reason,
            "prospective_n":int(row.get("calibration_observation_count") or row.get("freeze_observation_count") or 0),
            "governance_status":status,
            "historical_oos_passed":bool(row.get("historical_oos_passed") or (oos and oos.get("gate_passed"))),
            "metrics":oos,
            "model_mutation_allowed":False,"cell_used_to_generate_probability":False,
        })

    # Add radar-only competitions not yet present in prospective calibration.
    existing={(x["competition_id"],x["market"]) for x in cells if x["scope"]=="COMPETITION"}
    for cid,r in radar.items():
        key=(cid,"OVER_2_5")
        if key in existing:
            continue
        cells.append({
            "sport":"FOOTBALL","competition_id":cid,
            "competition_name":r.get("provider_name") or r.get("label"),
            "season":r.get("season"),"market":"OVER_2_5","scope":"COMPETITION",
            "strength_class":"INSUFFICIENT_DATA",
            "classification_reason":"RADAR_PRIORITY_WITHOUT_15_PROSPECTIVE_SETTLED_OBSERVATIONS",
            "prospective_n":0,
            "league_radar_context":{
                "radar_bucket":r.get("radar_bucket"),
                "league_sample_n":r.get("sample_n"),
                "league_over_2_5_pct":r.get("season_over_2_5_pct"),
                "p_matrix_adjustment":0.0,
            },
            "model_mutation_allowed":False,"cell_used_to_generate_probability":False,
        })
    return cells


def _tennis_cells(
    uniqueness:Mapping[str,Any],
    binding:Mapping[str,Any],
)->list[dict[str,Any]]:
    observations=uniqueness.get("canonical_observations") or []
    counts=Counter(str(r.get("competition") or "UNKNOWN") for r in observations if isinstance(r,Mapping))
    candidates=binding.get("candidates") or {}
    model_ids={
        "elo":(candidates.get("elo") or {}).get("identity"),
        "glicko":(candidates.get("glicko") or {}).get("identity"),
    }
    cells=[]
    for competition,n in sorted(counts.items()):
        cells.append({
            "sport":"TENNIS",
            "competition_id":competition,
            "competition_name":competition,
            "season":2026,
            "market":"MATCH_WINNER",
            "scope":"COMPETITION",
            "strength_class":"INSUFFICIENT_DATA",
            "classification_reason":"METRICS_SEALED_UNTIL_600",
            "prospective_n":n,
            "models":model_ids,
            "domain":"ATP_CHALLENGER_HARD",
            "metrics_opened":False,
            "outcomes_read":0,
            "model_mutation_allowed":False,
            "cell_used_to_generate_probability":False,
        })
    total=int(uniqueness.get("unique_calibration_observations") or 0)
    cells.append({
        "sport":"TENNIS",
        "competition_id":"ATP_CHALLENGER_HARD",
        "competition_name":"ATP Challenger Hard",
        "season":2026,
        "market":"MATCH_WINNER",
        "scope":"DOMAIN",
        "strength_class":"INSUFFICIENT_DATA",
        "classification_reason":"ACTIVE_PROSPECTIVE_CALIBRATION_BUT_METRICS_SEALED_UNTIL_600",
        "prospective_n":total,
        "target_n":600,
        "remaining_to_600":max(0,600-total),
        "models":model_ids,
        "metrics_opened":False,
        "outcomes_read":0,
        "model_mutation_allowed":False,
        "cell_used_to_generate_probability":False,
    })
    return cells


def _latest_football_world_registry()->dict[str,Any] | None:
    candidates=list(Path("evidence/api_football/prospective_daily").rglob("future_fixture_registry.json"))
    if not candidates:
        return None
    parsed=[]
    for p in candidates:
        try:
            d=_load_json(p)
            parsed.append((str(d.get("captured_at_utc") or ""),p,d))
        except Exception:
            continue
    if not parsed:
        return None
    parsed.sort(key=lambda x:x[0])
    _,p,d=parsed[-1]
    return {"path":str(p),"sha256":_sha(p),"payload":d}


def _world_coverage(
    freeze:Mapping[str,Any],
    tennis_world:Mapping[str,Any],
    tennis_horizon:Mapping[str,Any],
)->dict[str,Any]:
    football_registry=_latest_football_world_registry()
    if football_registry:
        events=football_registry["payload"].get("events") or []
        comp_ids={str(x.get("provider_league_id") or "") for x in events if isinstance(x,Mapping)}
        football={
            "mode":"WORLD_DAILY_FUTURE_FIXTURE_REGISTRY",
            "source_path":football_registry["path"],
            "source_sha256":football_registry["sha256"],
            "future_fixture_count":len(events),
            "competition_count":len({x for x in comp_ids if x}),
        }
    else:
        rows=freeze.get("rows") or []
        football={
            "mode":"FALLBACK_FREEZE_UNIVERSE_NO_CURRENT_WORLD_REGISTRY_FOUND",
            "future_fixture_count":None,
            "competition_count":len({str(x.get("competition_id") or "") for x in rows if isinstance(x,Mapping)}),
        }
    football["evaluation_policy"]="ALL_DISCOVERED_COMPETITIONS_REMAIN_VISIBLE; MISSING_STRENGTH_EVIDENCE=INSUFFICIENT_DATA"

    tennis={
        "mode":"WORLD_INVENTORY_THEN_GOVERNED_DOMAIN_FILTER",
        "world_inventory_target_date":tennis_world.get("world_inventory_target_date"),
        "world_inventory_total":int(tennis_world.get("world_inventory_total") or 0),
        "world_domain_candidates_input":int(tennis_world.get("world_domain_candidates_input") or 0),
        "eligible_current_world_candidates":int(tennis_world.get("eligible_input_events") or 0),
        "dual_source_logical_horizon_days":int(tennis_horizon.get("logical_horizon_days") or 0),
        "rapidapi_base_candidates":int((tennis_horizon.get("rapidapi_tennis") or {}).get("base_candidates") or 0),
        "api_tennis_base_candidates":int((tennis_horizon.get("api_tennis") or {}).get("base_candidates") or 0),
        "evaluation_policy":"WORLD_EVENTS_PRESERVED_BEFORE_DOMAIN_FILTER; EACH_DOMAIN_REQUIRES_INDEPENDENT_MODEL_AND_CALIBRATION",
    }
    return {"FOOTBALL":football,"TENNIS":tennis}


def build(root:Path)->dict[str,Any]:
    football_ledger_path=root/"evidence/api_football/prospective_calibration/ledger.jsonl"
    football_freeze_path=root/"evidence/api_football/prospective_market_freeze/freeze.json"
    football_master_path=max((root/"evidence/api_football/governance").glob("MATRIX_FOOTBALL_MARKET_RESOLUTION_MASTER_*.json"))
    radar_path=root/"evidence/api_football/league_over25_radar/league_policy_current.json"
    tennis_unique_path=root/"evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json"
    tennis_binding_path=root/"evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json"
    tennis_world_path=root/"evidence/cor0203/runtime/MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_LAST.json"
    tennis_horizon_path=root/"evidence/cor0203/runtime/MATRIX_COR0203_DUAL_8DAY_HORIZON_LAST.json"

    ledger=_load_jsonl(football_ledger_path)
    freeze=_load_json(football_freeze_path)
    master=_load_json(football_master_path)
    radar=_radar_index(radar_path)
    uniqueness=_load_json(tennis_unique_path)
    binding=_load_json(tennis_binding_path)
    tennis_world=_load_json(tennis_world_path)
    tennis_horizon=_load_json(tennis_horizon_path)

    cells=_football_cells(ledger,freeze,master,radar)+_tennis_cells(uniqueness,binding)
    priority={"STRONG":0,"DEVELOPING":1,"INSUFFICIENT_DATA":2,"NO_GO":3}
    cells.sort(key=lambda r:(r["sport"],priority.get(r["strength_class"],9),str(r["competition_name"]),str(r["market"])))

    counts=Counter(r["strength_class"] for r in cells)
    payload={
        "schema":"MATRIX_GLOBAL_STRENGTH_MAP_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "definition":"Evidence-only map of SPORT x COMPETITION x MARKET. Never a probability generator.",
        "classes":{
            "STRONG":"Prospective sample >=30, challenger better in Brier and Log Loss, and paired 95% CIs fully favorable.",
            "DEVELOPING":"At least 15 prospective observations or historical OOS pass, but decisive STRONG evidence not yet established.",
            "NO_GO":"Formal governance rejection or statistically decisive underperformance versus reference.",
            "INSUFFICIENT_DATA":"Evidence below minimum, unavailable, or metrics sealed by governance.",
        },
        "world_coverage":_world_coverage(freeze,tennis_world,tennis_horizon),
        "cell_count":len(cells),
        "class_counts":dict(counts),
        "cells":cells,
        "sources":{
            "football_ledger":{"path":str(football_ledger_path.relative_to(root)),"sha256":_sha(football_ledger_path),"rows":len(ledger)},
            "football_freeze":{"path":str(football_freeze_path.relative_to(root)),"sha256":_sha(football_freeze_path),"rows":len(freeze.get("rows") or [])},
            "football_market_master":{"path":str(football_master_path.relative_to(root)),"sha256":_sha(football_master_path)},
            "football_league_radar":{"path":str(radar_path.relative_to(root)),"sha256":_sha(radar_path) if radar_path.exists() else None},
            "tennis_uniqueness":{"path":str(tennis_unique_path.relative_to(root)),"sha256":_sha(tennis_unique_path),"unique_observations":uniqueness.get("unique_calibration_observations")},
            "tennis_model_binding":{"path":str(tennis_binding_path.relative_to(root)),"sha256":_sha(tennis_binding_path)},
            "tennis_world_discovery":{"path":str(tennis_world_path.relative_to(root)),"sha256":_sha(tennis_world_path)},
            "tennis_dual_horizon":{"path":str(tennis_horizon_path.relative_to(root)),"sha256":_sha(tennis_horizon_path)},
        },
        "protections":{
            "read_only_evidence_aggregation":True,
            "changes_p_matrix":False,
            "changes_frozen_probabilities":False,
            "changes_model_parameters":False,
            "changes_feature_values":False,
            "changes_discovery_eligibility":False,
            "changes_bet_decision":False,
            "uses_odds_to_generate_probability":False,
            "opens_sealed_tennis_metrics":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "status":"PASS",
    }
    return payload


def write_outputs(root:Path,out:Path)->dict[str,Any]:
    payload=build(root)
    out.mkdir(parents=True,exist_ok=True)
    json_path=out/"strength_map.json"
    json_path.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")

    csv_path=out/"strength_map.csv"
    fields=[
        "sport","competition_id","competition_name","season","market","scope",
        "strength_class","classification_reason","prospective_n",
        "delta_brier","delta_log_loss","model_mutation_allowed","cell_used_to_generate_probability"
    ]
    with csv_path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields)
        w.writeheader()
        for row in payload["cells"]:
            metrics=row.get("metrics") if isinstance(row.get("metrics"),Mapping) else {}
            w.writerow({
                "sport":row.get("sport"),"competition_id":row.get("competition_id"),
                "competition_name":row.get("competition_name"),"season":row.get("season"),
                "market":row.get("market"),"scope":row.get("scope"),
                "strength_class":row.get("strength_class"),"classification_reason":row.get("classification_reason"),
                "prospective_n":row.get("prospective_n"),
                "delta_brier":metrics.get("delta_brier"),"delta_log_loss":metrics.get("delta_log_loss"),
                "model_mutation_allowed":row.get("model_mutation_allowed"),
                "cell_used_to_generate_probability":row.get("cell_used_to_generate_probability"),
            })

    summary={
        "schema":"MATRIX_GLOBAL_STRENGTH_MAP_SUMMARY_V1",
        "generated_at_utc":payload["generated_at_utc"],
        "cell_count":payload["cell_count"],
        "class_counts":payload["class_counts"],
        "football_global_cells":[r for r in payload["cells"] if r["sport"]=="FOOTBALL" and r["scope"]=="GLOBAL_MARKET"],
        "tennis_domain_cells":[r for r in payload["cells"] if r["sport"]=="TENNIS" and r["scope"]=="DOMAIN"],
        "world_coverage":payload["world_coverage"],
        "status":"PASS",
    }
    summary_path=out/"summary.json"
    summary_path.write_text(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")

    manifest={
        "schema":"MATRIX_GLOBAL_STRENGTH_MAP_MANIFEST_V1",
        "generated_at_utc":payload["generated_at_utc"],
        "strength_map_json_sha256":_sha(json_path),
        "strength_map_csv_sha256":_sha(csv_path),
        "summary_sha256":_sha(summary_path),
        "cell_count":payload["cell_count"],
        "class_counts":payload["class_counts"],
        "source_hashes":payload["sources"],
        "protections":payload["protections"],
        "status":"PASS",
    }
    manifest_path=out/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def main()->None:
    root=Path(".")
    out=Path("evidence/global_strength_map")
    result=write_outputs(root,out)
    print(json.dumps({
        "status":result["status"],
        "cell_count":result["cell_count"],
        "class_counts":result["class_counts"],
        "real_money":result["protections"]["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
