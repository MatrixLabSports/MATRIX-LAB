from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MIN_TEAM_HISTORY=5
MAX_TEAM_HISTORY=20

METRICS={
    "CORNERS":"Corner Kicks",
    "TEAM_SHOTS_ON_TARGET":"Shots on Goal",
    "TEAM_TOTAL_SHOTS":"Total Shots",
    "TEAM_FOULS":"Fouls",
    "TEAM_GOALKEEPER_SAVES":"Goalkeeper Saves",
    "TEAM_YELLOW_CARDS":"Yellow Cards",
    "TEAM_RED_CARDS":"Red Cards",
    "TEAM_TOTAL_PASSES":"Total passes",
    "TEAM_ACCURATE_PASSES":"Passes accurate",
}

DATASET_PATHS=(
    Path("evidence/api_football/market_expansion/historical_bootstrap/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_warmup/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3/normalized_dataset.jsonl"),
)

def _utc(v:object)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)

def _read_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def _load_development_rows()->tuple[list[dict[str,Any]],int]:
    by_id={}
    duplicate_count=0
    for path in DATASET_PATHS:
        for row in _read_jsonl(path):
            fid=str(row.get("fixture_id") or "")
            if not fid:
                continue
            if fid in by_id:
                duplicate_count+=1
                continue
            by_id[fid]=row
    rows=list(by_id.values())
    rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
    return rows,duplicate_count

def _load_identity_map(raw_dir:Path)->dict[str,dict[str,str]]:
    out={}
    for path in sorted(raw_dir.glob("league_*_season_*.bin")):
        payload=json.loads(path.read_bytes().decode("utf-8"))
        response=payload.get("response") if isinstance(payload,Mapping) else None
        if not isinstance(response,list):
            continue
        for raw in response:
            if not isinstance(raw,Mapping):
                continue
            fixture=raw.get("fixture"); teams=raw.get("teams")
            if not isinstance(fixture,Mapping) or not isinstance(teams,Mapping):
                continue
            home=teams.get("home"); away=teams.get("away")
            if not isinstance(home,Mapping) or not isinstance(away,Mapping):
                continue
            try:
                fid=str(int(fixture.get("id")))
                hid=str(int(home.get("id")))
                aid=str(int(away.get("id")))
            except (TypeError,ValueError):
                continue
            out[fid]={
                "home_team_id":hid,"away_team_id":aid,
                "home_team_name":str(home.get("name") or ""),
                "away_team_name":str(away.get("name") or ""),
            }
    return out

def _num(v:Any)->float|None:
    if v is None or isinstance(v,bool):
        return None
    if isinstance(v,(int,float)):
        return float(v)
    s=str(v).strip().replace("%","")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def _metric_value(row:Mapping[str,Any],team_id:str,provider_name:str)->float|None:
    teams=row.get("team_statistics")
    if not isinstance(teams,Mapping):
        return None
    team=teams.get(team_id)
    if not isinstance(team,Mapping):
        return None
    stats=team.get("statistics")
    if not isinstance(stats,Mapping):
        return None
    return _num(stats.get(provider_name))

def _mean(xs:list[float])->float:
    return sum(xs)/len(xs)

def _history_values(history:list[dict[str,Any]],metric_key:str)->tuple[list[float],list[float]]:
    recent=history[-MAX_TEAM_HISTORY:]
    own=[float(x["own"][metric_key]) for x in recent if x["own"].get(metric_key) is not None]
    allowed=[float(x["allowed"][metric_key]) for x in recent if x["allowed"].get(metric_key) is not None]
    return own,allowed

def build(out_dir:Path,raw_dir:Path=Path("evidence/api_football/history/raw"))->dict[str,Any]:
    rows,duplicate_input_count=_load_development_rows()
    identities=_load_identity_map(raw_dir)
    history=defaultdict(list)
    output=defaultdict(list)
    blocked=defaultdict(int)
    identity_missing=0
    identity_stats_mismatch=0

    for row in rows:
        fid=str(row["fixture_id"])
        ident=identities.get(fid)
        if ident is None:
            identity_missing+=1
            continue
        home=ident["home_team_id"]; away=ident["away_team_id"]
        team_stats=row.get("team_statistics") or {}
        if home not in team_stats or away not in team_stats:
            identity_stats_mismatch+=1
            continue

        current_own={home:{},away:{}}
        for metric_key,provider_name in METRICS.items():
            current_own[home][metric_key]=_metric_value(row,home,provider_name)
            current_own[away][metric_key]=_metric_value(row,away,provider_name)

            h_own,h_allowed=_history_values(history[home],metric_key)
            a_own,a_allowed=_history_values(history[away],metric_key)
            if min(len(h_own),len(h_allowed),len(a_own),len(a_allowed)) < MIN_TEAM_HISTORY:
                blocked[metric_key]+=1
                continue
            th=current_own[home][metric_key]; ta=current_own[away][metric_key]
            if th is None or ta is None:
                blocked[metric_key]+=1
                continue

            expected_home=(_mean(h_own)+_mean(a_allowed))/2.0
            expected_away=(_mean(a_own)+_mean(h_allowed))/2.0
            output[metric_key].append({
                "fixture_id":fid,
                "kickoff_utc":row["kickoff_utc"],
                "league_id":str(row.get("league_id") or ""),
                "season":row.get("season"),
                "home_team_id":home,
                "away_team_id":away,
                "home_team_name":ident["home_team_name"],
                "away_team_name":ident["away_team_name"],
                "home_history_count":min(len(h_own),len(h_allowed)),
                "away_history_count":min(len(a_own),len(a_allowed)),
                "home_for_mean":_mean(h_own),
                "home_against_mean":_mean(h_allowed),
                "away_for_mean":_mean(a_own),
                "away_against_mean":_mean(a_allowed),
                "expected_home":expected_home,
                "expected_away":expected_away,
                "expected_total":expected_home+expected_away,
                "target_home":float(th),
                "target_away":float(ta),
                "target_total":float(th)+float(ta),
                "feature_policy":"STRICTLY_PRIOR_MATCHES_ONLY",
                "same_match_target_used_in_features":False,
            })

        # Update state only after every feature calculation for the target fixture.
        home_allowed={k:current_own[away][k] for k in METRICS}
        away_allowed={k:current_own[home][k] for k in METRICS}
        history[home].append({"fixture_id":fid,"own":dict(current_own[home]),"allowed":home_allowed})
        history[away].append({"fixture_id":fid,"own":dict(current_own[away]),"allowed":away_allowed})

    out_dir.mkdir(parents=True,exist_ok=True)
    lane_manifests={}
    for lane,lane_rows in output.items():
        lane_rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
        n=len(lane_rows)
        val_n=min(50,max(0,n//5))
        if n>=250:
            val_n=50
        split_at=n-val_n
        for i,r in enumerate(lane_rows):
            r["split"]="TRAIN" if i<split_at else "VALIDATION"
        path=out_dir/f"{lane.casefold()}_pit.jsonl"
        path.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in lane_rows),encoding="utf-8")
        lane_manifests[lane]={
            "row_count":n,
            "train_count":split_at,
            "validation_count":val_n,
            "dataset_path":str(path),
            "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "minimum_history":MIN_TEAM_HISTORY,
            "maximum_history":MAX_TEAM_HISTORY,
            "blocked_before_pit_eligibility":blocked[lane],
        }

    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_TEAM_PIT_DATASET_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_unique_fixture_count":len(rows),
        "duplicate_input_rows_quarantined":duplicate_input_count,
        "identity_map_count":len(identities),
        "identity_missing_count":identity_missing,
        "identity_stats_mismatch_count":identity_stats_mismatch,
        "lanes":lane_manifests,
        "feature_policy":"STRICTLY_PRIOR_MATCHES_ONLY_AND_STATE_UPDATED_AFTER_TARGET_FEATURES",
        "same_match_target_used_in_features":False,
        "validation_used_for_parameter_tuning":False,
        "protected_final_holdout_used":False,
        "prospective_calibration_used":False,
        "odds_used_to_generate_probability":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest

def main()->None:
    result=build(Path("evidence/api_football/market_expansion/team_pit"))
    print(json.dumps({
        "status":result["status"],
        "input_unique_fixture_count":result["input_unique_fixture_count"],
        "identity_missing_count":result["identity_missing_count"],
        "identity_stats_mismatch_count":result["identity_stats_mismatch_count"],
        "lane_rows":{k:v["row_count"] for k,v in result["lanes"].items()},
        "real_money":result["real_money"],
    },sort_keys=True))

if __name__=="__main__":
    main()
