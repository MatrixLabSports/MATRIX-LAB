from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIN_PLAYER_HISTORY=5
MAX_PLAYER_HISTORY=20

DATASETS=(
    Path("evidence/api_football/market_expansion/historical_prior_season/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_bootstrap/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_warmup/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich/normalized_dataset.jsonl"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3/normalized_dataset.jsonl"),
)

METRICS={
    "PLAYER_SHOTS":"shots_total",
    "PLAYER_SHOTS_ON_TARGET":"shots_on_target",
    "GOALKEEPER_SAVES":"saves",
    "PLAYER_ASSISTS":"assists",
    "PLAYER_PASSES":"passes_total",
    "PLAYER_TACKLES":"tackles_total",
    "PLAYER_FOULS":"fouls_committed",
}


def _utc(v:object)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _load_unique_matches():
    by_id={}
    duplicates=0
    for path in DATASETS:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row=json.loads(raw)
            fid=str(row.get("fixture_id") or "")
            if not fid:
                continue
            if fid in by_id:
                duplicates+=1
                continue
            by_id[fid]=row
    rows=list(by_id.values())
    rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))
    return rows,duplicates


def _mean(values:list[float])->float:
    return sum(values)/len(values)


def build(out_dir:Path)->dict[str,Any]:
    matches,duplicates=_load_unique_matches()
    history=defaultdict(lambda:defaultdict(list))
    outputs=defaultdict(list)
    missing_metric=defaultdict(int)
    insufficient_history=defaultdict(int)

    for match in matches:
        players=match.get("player_statistics")
        if not isinstance(players,list):
            continue

        # Build features for this fixture before appending any current-fixture outcome.
        pending_updates=[]
        for player in players:
            if not isinstance(player,dict):
                continue
            pid=str(player.get("player_id") or "")
            minutes=player.get("minutes")
            if not pid or minutes is None:
                continue
            try:
                minutes_f=float(minutes)
            except (TypeError,ValueError):
                continue
            if minutes_f<=0:
                continue

            for lane,field in METRICS.items():
                value=player.get(field)
                if value is None:
                    missing_metric[lane]+=1
                    continue
                try:
                    target=float(value)
                except (TypeError,ValueError):
                    missing_metric[lane]+=1
                    continue

                prior=history[pid][lane][-MAX_PLAYER_HISTORY:]
                if len(prior)<MIN_PLAYER_HISTORY:
                    insufficient_history[lane]+=1
                else:
                    counts=[float(x["value"]) for x in prior]
                    mins=[float(x["minutes"]) for x in prior]
                    last5=prior[-5:]
                    outputs[lane].append({
                        "fixture_id":str(match["fixture_id"]),
                        "kickoff_utc":match["kickoff_utc"],
                        "league_id":str(match.get("league_id") or ""),
                        "season":match.get("season"),
                        "team_id":str(player.get("team_id") or ""),
                        "team_name":player.get("team_name"),
                        "player_id":pid,
                        "player_name":player.get("player_name"),
                        "prior_appearance_count":len(prior),
                        "prior_mean_count":_mean(counts),
                        "last5_mean_count":_mean([float(x["value"]) for x in last5]),
                        "prior_mean_minutes":_mean(mins),
                        "last5_mean_minutes":_mean([float(x["minutes"]) for x in last5]),
                        "target_count":target,
                        "current_match_minutes_postsettlement_audit_only":minutes_f,
                        "current_match_minutes_used_as_feature":False,
                        "same_match_target_used_in_features":False,
                        "appearance_conditioned_sample":True,
                    })
                pending_updates.append((pid,lane,target,minutes_f))

        for pid,lane,target,minutes_f in pending_updates:
            history[pid][lane].append({
                "fixture_id":str(match["fixture_id"]),
                "value":target,
                "minutes":minutes_f,
            })

    out_dir.mkdir(parents=True,exist_ok=True)
    lane_meta={}
    for lane,rows in outputs.items():
        rows.sort(key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"]),int(r["player_id"] or 0)))
        n=len(rows)
        val_n=50 if n>=250 else max(0,n//5)
        split=n-val_n
        for i,row in enumerate(rows):
            row["split"]="TRAIN" if i<split else "VALIDATION"
        path=out_dir/f"{lane.casefold()}_pit.jsonl"
        path.write_text("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
        lane_meta[lane]={
            "row_count":n,
            "train_count":split,
            "validation_count":val_n,
            "minimum_player_history":MIN_PLAYER_HISTORY,
            "maximum_player_history":MAX_PLAYER_HISTORY,
            "missing_metric_count":missing_metric[lane],
            "insufficient_history_count":insufficient_history[lane],
            "dataset_path":str(path),
            "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    manifest={
        "schema":"MATRIX_FOOTBALL_EXTENDED_PLAYER_PIT_DATASET_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_unique_match_count":len(matches),
        "duplicate_input_matches_quarantined":duplicates,
        "lanes":lane_meta,
        "feature_policy":"STRICTLY_PRIOR_PLAYER_APPEARANCES_ONLY",
        "same_match_target_used_in_features":False,
        "current_match_minutes_used_as_feature":False,
        "sample_scope":"CONDITIONAL_ON_APPEARANCE_RESEARCH_ONLY",
        "prospective_freeze_allowed":False,
        "prospective_blocker":"PIT_LINEUP_AND_EXPECTED_MINUTES_SOURCE_NOT_YET_CERTIFIED",
        "missing_is_zero":False,
        "silent_imputation":False,
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


def main():
    result=build(Path("evidence/api_football/market_expansion/player_pit"))
    print(json.dumps({
        "status":result["status"],
        "input_unique_match_count":result["input_unique_match_count"],
        "lanes":{k:{"rows":v["row_count"],"train":v["train_count"],"validation":v["validation_count"]} for k,v in result["lanes"].items()},
        "prospective_freeze_allowed":result["prospective_freeze_allowed"],
        "prospective_blocker":result["prospective_blocker"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
