from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools import api_football_promoted_team_markets_supervisor as team_sup

GATES=(30,50,100,200)
METRIC="Total Shots"
TARGET_DATE=os.environ.get("MATRIX_TARGET_DATE_BOGOTA","2026-10-10")


def _read_json(path:Path,default:Any)->Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append_jsonl(path:Path,row:Mapping[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as fh:
        fh.write(json.dumps(dict(row),sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n")


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calibration_metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    if not rows:
        raise ValueError("NO_ROWS_FOR_METRICS")
    probs=[min(max(float(r["frozen_probability_over"]),1e-12),1-1e-12) for r in rows]
    ys=[1.0 if r["outcome_over"] else 0.0 for r in rows]
    n=len(rows)
    brier=sum((p-y)**2 for p,y in zip(probs,ys))/n
    log_loss=sum(-(y*math.log(p)+(1-y)*math.log(1-p)) for p,y in zip(probs,ys))/n

    bins=[]
    weighted=0.0
    max_err=0.0
    for i in range(5):
        lo=i/5
        hi=(i+1)/5
        idx=[k for k,p in enumerate(probs) if (p>=lo and (p<hi or (i==4 and p<=hi)))]
        if not idx:
            continue
        mp=sum(probs[k] for k in idx)/len(idx)
        my=sum(ys[k] for k in idx)/len(idx)
        err=abs(mp-my)
        weighted+=len(idx)/n*err
        max_err=max(max_err,err)
        bins.append({"lo":lo,"hi":hi,"n":len(idx),"mean_probability":mp,"observed_rate":my,"abs_error":err})

    eligible=[]
    for r in rows:
        odds=float(r.get("over_odds") or 0.0)
        p=float(r["frozen_probability_over"])
        if odds>1.50 and p*odds-1.0>0.0:
            eligible.append(r)
    profit=0.0
    for r in eligible:
        odds=float(r["over_odds"])
        profit+=(odds-1.0) if r["outcome_over"] else -1.0
    roi=profit/len(eligible) if eligible else None

    return {
        "sample_size":n,
        "brier_score":brier,
        "log_loss":log_loss,
        "ece_5bin":weighted,
        "max_calibration_error_5bin":max_err,
        "calibration_bins":bins,
        "shadow_policy":{
            "rule":"over_odds>1.50 AND frozen_probability_over*over_odds-1>0",
            "bet_count":len(eligible),
            "profit_units":profit,
            "roi_per_staked_unit":roi,
        },
    }


def build_state(freezes:list[dict[str,Any]],settlements:list[dict[str,Any]],previous:dict[str,Any]|None=None)->dict[str,Any]:
    previous=dict(previous or {})
    freeze_ids=[str(x.get("fixture_id") or "") for x in freezes if x.get("fixture_id")]
    by_id={str(x.get("fixture_id") or ""):x for x in settlements if x.get("fixture_id")}
    ordered_settled=[by_id[fid] for fid in freeze_ids if fid in by_id]
    gates={}
    for threshold in GATES:
        if len(ordered_settled)<threshold:
            gates[str(threshold)]={
                "threshold":threshold,
                "status":"SEALED_AWAIT_FINALS",
                "freeze_count":len(freeze_ids),
                "final_settlement_count":len(ordered_settled),
                "remaining_finals":threshold-len(ordered_settled),
                "metrics_opened":False,
            }
        else:
            prefix=ordered_settled[:threshold]
            gates[str(threshold)]={
                "threshold":threshold,
                "status":"OPENED_AT_THRESHOLD_AWAIT_ADJUDICATION",
                "freeze_count":len(freeze_ids),
                "final_settlement_count":len(ordered_settled),
                "observations_used":threshold,
                "remaining_finals":0,
                "metrics_opened":True,
                "metrics":calibration_metrics(prefix),
            }
    previous.update({
        "schema":"MATRIX_MATCH_TOTAL_SHOTS_PROSPECTIVE_STATE_V2",
        "target_date_bogota":TARGET_DATE,
        "preregistered_fixture_count":previous.get("preregistered_fixture_count",0),
        "cumulative_unique_research_freeze_count":len(freeze_ids),
        "final_settlement_count":len(ordered_settled),
        "gates":gates,
        "gate_30":gates["30"],
        "parameter_tuning_allowed":False,
        "model_promotion_performed":False,
        "telegram_signal_authorized":False,
        "paper_bankroll_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "updated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    return previous


def run(api_key:str,root:Path)->dict[str,Any]:
    if not api_key:
        raise RuntimeError("API_FOOTBALL_KEY_MISSING")
    freezes=_read_jsonl(root/"freeze_ledger.jsonl")
    settlement_path=root/"settlement_ledger.jsonl"
    settlements=_read_jsonl(settlement_path)
    done={str(x.get("fixture_id") or "") for x in settlements}
    now=datetime.now(timezone.utc).replace(microsecond=0)
    run_id=now.strftime("%Y%m%dT%H%M%SZ")
    raw_dir=root/"settlement_raw"/run_id
    session=requests.Session()
    counter=[0]
    new=[]

    for fr in freezes:
        fid=str(fr.get("fixture_id") or "")
        if not fid or fid in done:
            continue
        kickoff=_utc(fr["kickoff_utc"])
        if kickoff+timedelta(minutes=90)>now:
            continue
        detail=team_sup._fixture_detail(session,api_key,fid,raw_dir,counter)
        if not detail or detail.get("status")!="FT":
            continue
        payload=team_sup._api(session,api_key,"/fixtures/statistics",{"fixture":fid},raw_dir,f"fixture_{fid}_stats",counter)
        sm=team_sup._stat_map(payload)
        h=str(detail.get("home_team_id") or "")
        a=str(detail.get("away_team_id") or "")
        if h not in sm or a not in sm or METRIC not in sm[h] or METRIC not in sm[a]:
            continue
        home=float(sm[h][METRIC])
        away=float(sm[a][METRIC])
        total=home+away
        line=float(fr["line"])
        row={
            "schema":"MATRIX_MATCH_TOTAL_SHOTS_SETTLEMENT_V1",
            "fixture_id":fid,
            "home_team":fr.get("home_team"),
            "away_team":fr.get("away_team"),
            "kickoff_utc":fr.get("kickoff_utc"),
            "freeze_at_utc":fr.get("freeze_at_utc"),
            "settled_at_utc":now.isoformat(),
            "terminal_status":"FT",
            "line":line,
            "home_total_shots":home,
            "away_total_shots":away,
            "target_total_shots":total,
            "outcome_over":bool(total>line),
            "frozen_probability_over":float(fr["p_research_over"]),
            "frozen_count_mean":float(fr["frozen_count_mean"]),
            "over_odds":float(fr["over_odds"]),
            "under_odds":float(fr["under_odds"]),
            "model_parameters_sha256":fr.get("model_parameters_sha256"),
            "source_freeze_record_sha256":fr.get("record_sha256"),
            "parameter_tuning_used":False,
            "p_matrix":None,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
        row["record_sha256"]=team_sup._sha(row)
        _append_jsonl(settlement_path,row)
        settlements.append(row)
        done.add(fid)
        new.append(fid)

    previous=_read_json(root/"state.json",{})
    state=build_state(freezes,settlements,previous)
    (root/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    last={
        "schema":"MATRIX_MATCH_TOTAL_SHOTS_SETTLEMENT_POINTER_V1",
        "run_id":run_id,
        "target_date_bogota":TARGET_DATE,
        "checked_freeze_count":len(freezes),
        "new_settlement_count":len(new),
        "new_fixture_ids":new,
        "final_settlement_count":state["final_settlement_count"],
        "gate_30_status":state["gate_30"]["status"],
        "gate_30_metrics_opened":state["gate_30"]["metrics_opened"],
        "network_calls":counter[0],
        "parameter_tuning_allowed":False,
        "telegram_signal_authorized":False,
        "paper_bankroll_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "observed_at_utc":now.isoformat(),
    }
    (root/"settlement_last_run.json").write_text(json.dumps(last,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(last,sort_keys=True))
    return last


if __name__=="__main__":
    root=Path("evidence/api_football/match_total_shots_lab")/TARGET_DATE
    run(os.environ.get("API_FOOTBALL_KEY",""),root)
