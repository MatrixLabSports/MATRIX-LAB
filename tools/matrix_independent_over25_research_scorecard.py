"""Read-only, cumulative out-of-sample research scoreboard for sealed forecasts.

Groups strictly independent postmatch settlement files by *free-provider*
competition ID. Does not pretend this is parity to API-Football, does not
select the original six leagues, and cannot promote Telegram.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from tools.matrix_independent_over25_prematch_freeze import canonical,stamp,SCHEMA

ROOT=Path("evidence/football_research_freezes")
OUT=Path("evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def evaluate(root:Path):
    collected=defaultdict(list);rejected=[];seen=set()
    for result in sorted((root/ROOT).glob("20??-??-??/[0-9]*_result_*.json")):
        try:
            row=json.loads(result.read_text(encoding="utf-8"))
            if (row.get("schema")!="MATRIX_INDEPENDENT_OVER25_SETTLED_RESEARCH_V1"
                or row.get("telegram_signal_authorized") is not False
                or row.get("real_money")!="BLOCKED"):
                raise ValueError("RESULT_GOVERNANCE_INVALID")
            fid=str(row["fixture_id"])
            key=(row["competition_id"],fid)
            if key in seen:raise ValueError("DUPLICATE_PROVIDER_FIXTURE")
            seen.add(key)
            cutoff=stamp(row["kickoff_utc"])
            if not (stamp(row["forecast_frozen_at_utc"])<cutoff<
                    stamp(row["result_observed_at_utc"])):
                raise ValueError("PROSPECTIVE_TIME_SEQUENCE_INVALID")
            forecasts=list(result.parent.glob(f"{fid}_*.json"))
            forecasts=[x for x in forecasts if "_result_" not in x.name]
            match=[x for x in forecasts if digest(x)==row["forecast_sha256"]]
            if len(match)!=1:raise ValueError("ORIGINAL_FROZEN_FORECAST_SHA_NOT_FOUND")
            original=json.loads(match[0].read_text(encoding="utf-8"))
            if (original.get("schema")!=SCHEMA or
                str(original["provider_competition_id"])!=str(row["competition_id"]) or
                original["research_probability_over25"]!=row["research_probability_over25"]):
                raise ValueError("ORIGINAL_RESEARCH_PROBABILITY_MISMATCH")
            raw=result.parent/"sources"/f"{row['raw_result_sha256']}.json"
            if digest(raw)!=row["raw_result_sha256"]:
                raise ValueError("FINAL_RESULT_SOURCE_HASH_MISMATCH")
            p=row["research_probability_over25"]; y=row["over25_outcome"]
            if type(p) not in (int,float) or not math.isfinite(p) or not 0<p<1 or type(y)!=int or y not in (0,1):
                raise ValueError("INVALID_BRIER_INPUT")
            if (type(row.get("home_goals"))!=int or type(row.get("away_goals"))!=int or
                int(row["home_goals"]+row["away_goals"]>2)!=y):
                raise ValueError("FINAL_SCORE_OUTCOME_MISMATCH")
            if abs((p-y)**2-row["brier_loss"])>1e-8:
                raise ValueError("BARRIER_LOSS_MISMATCH")
            collected[str(row["competition_id"])].append({"p":p,"y":y,"id":fid})
        except (OSError,KeyError,ValueError,TypeError,json.JSONDecodeError) as exc:
            rejected.append({"file":result.relative_to(root).as_posix(),
                             "reason":str(exc)[:110]})
    groups=[]
    for league,rows in sorted(collected.items()):
        n=len(rows)
        brier=sum((x["p"]-x["y"])**2 for x in rows)/n
        logloss=-sum(x["y"]*math.log(x["p"])+(1-x["y"])*math.log1p(-x["p"]) for x in rows)/n
        groups.append({"source_competition_id":league,"independent_out_of_sample_rows":n,
            "mean_brier":round(brier,8),"mean_logloss":round(logloss,8),
            "actual_over25_rate":round(sum(x["y"] for x in rows)/n,8),
            "research_probability_mean":round(sum(x["p"] for x in rows)/n,8),
            "minimum_research_screening_rows":30,"at_least_30_rows":n>=30,
            "scientific_original_six_league_equivalence_certified":False})
    return {"schema":"MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_V1",
        "provider":"FOOTBALL_DATA_ORG",
        "status":"RESEARCH_PERFORMANCE_ONLY_NO_ORIGINAL_MODEL_EQUIVALENCE",
        "total_verified_settled_rows":sum(x["independent_out_of_sample_rows"] for x in groups),
        "rejected_settlements":rejected,"provider_competitions":groups,
        "original_six_league_parity_certified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,"automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--out",type=Path,default=OUT)
    a=p.parse_args()
    if any(x in a.out.parts for x in ("telegram","governance","daily_prematch_reports","tennis_signals")):
        raise SystemExit("RESEARCH_SCORECARD_CANNOT_WRITE_PRODUCTION")
    value=evaluate(a.root)
    target=a.out if a.out.is_absolute() else a.root/a.out
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(canonical(value))
    print(json.dumps({"verified_settled_rows":value["total_verified_settled_rows"],
          "groups":len(value["provider_competitions"]),
          "rejected":len(value["rejected_settlements"]),
          "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":main()
