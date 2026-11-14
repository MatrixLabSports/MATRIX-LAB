from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from math import log
from pathlib import Path
from typing import Any, Mapping

ACTION_BOARD=Path("evidence/market_portfolio/MATRIX_42_LANE_ACTION_BOARD_LAST.json")
PORTFOLIO_LEDGER=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
CALIBRATION_LEDGER=Path("evidence/api_football/prospective_calibration/ledger.jsonl")
FREEZE=Path("evidence/api_football/prospective_market_freeze/freeze.json")
OUT=Path("evidence/market_portfolio/MATRIX_GATE600_POST_AUDIT_LAST.json")
EPS=1e-15


def _load_json(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    rows=[]
    if not path.exists():
        return rows
    for n,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not raw.strip():
            continue
        value=json.loads(raw)
        if not isinstance(value,dict):
            raise ValueError(f"EXPECTED_OBJECT_JSONL:{path}:{n}")
        rows.append(value)
    return rows


def _sha(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _ece_binary(probs:list[float], ys:list[int])->dict[str,Any]:
    if not probs:
        raise ValueError("ECE_REQUIRES_ROWS")
    bins=[]
    total=len(probs)
    ece=0.0
    for i in range(10):
        lo=i/10
        hi=(i+1)/10
        idx=[k for k,p in enumerate(probs) if (lo<=p<hi) or (i==9 and p==1.0)]
        if not idx:
            continue
        mp=sum(probs[k] for k in idx)/len(idx)
        oy=sum(ys[k] for k in idx)/len(idx)
        gap=abs(mp-oy)
        ece+=(len(idx)/total)*gap
        bins.append({"lower":lo,"upper":hi,"count":len(idx),"mean_probability":mp,"observed_rate":oy,"absolute_gap":gap})
    return {"method":"EQUAL_WIDTH_10_BINS","ece":ece,"nonempty_bins":bins}


def _binary_metrics(probs:list[float], ys:list[int])->dict[str,Any]:
    n=len(probs)
    if n==0 or n!=len(ys):
        raise ValueError("BINARY_METRICS_INVALID_SAMPLE")
    brier=sum((p-y)**2 for p,y in zip(probs,ys))/n
    ll=sum(-(y*log(_clip(p))+(1-y)*log(_clip(1-p))) for p,y in zip(probs,ys))/n
    return {"sample_size":n,"brier_score":brier,"log_loss":ll,"calibration":_ece_binary(probs,ys)}


def _multiclass_metrics(probs:list[dict[str,float]], outcomes:list[str])->dict[str,Any]:
    n=len(probs)
    if n==0 or n!=len(outcomes):
        raise ValueError("MULTICLASS_METRICS_INVALID_SAMPLE")
    brier=0.0; ll=0.0; correct=0
    confidence=[]; correctness=[]
    for p,y in zip(probs,outcomes):
        for k in ("H","D","A"):
            target=1.0 if y==k else 0.0
            brier+=(float(p[k])-target)**2
        ll+=-log(_clip(float(p[y])))
        pred=max(("H","D","A"),key=lambda k:float(p[k]))
        correct+=int(pred==y)
        confidence.append(float(p[pred]))
        correctness.append(int(pred==y))
    return {
        "sample_size":n,
        "brier_score":brier/n,
        "log_loss":ll/n,
        "accuracy":correct/n,
        "confidence_ece":_ece_binary(confidence,correctness),
    }


def _lane_values(lane:str, challenger:Mapping[str,Any], poisson:Mapping[str,Any], outcome:str):
    c1=challenger["1x2"]; p1=poisson["1x2"]
    if lane=="MATCH_RESULT_1X2":
        return dict(c1),dict(p1),outcome
    if lane=="DOUBLE_CHANCE_1X":
        return float(c1["H"])+float(c1["D"]),float(p1["H"])+float(p1["D"]),int(outcome in {"H","D"})
    if lane=="DOUBLE_CHANCE_X2":
        return float(c1["D"])+float(c1["A"]),float(p1["D"])+float(p1["A"]),int(outcome in {"D","A"})
    if lane=="DOUBLE_CHANCE_12":
        return float(c1["H"])+float(c1["A"]),float(p1["H"])+float(p1["A"]),int(outcome in {"H","A"})
    raise ValueError("UNSUPPORTED_GATE600_LANE:"+lane)


def _thirds(rows:list[dict[str,Any]], lane:str)->list[dict[str,Any]]:
    if len(rows)<3:
        return []
    ordered=sorted(rows,key=lambda r:(str(r["kickoff_utc"]),str(r["fixture_id"])))
    out=[]
    for i in range(3):
        start=(len(ordered)*i)//3
        end=(len(ordered)*(i+1))//3
        chunk=ordered[start:end]
        if not chunk:
            continue
        out.append(_metrics_for_rows(chunk,lane)|{"segment":i+1,"start_kickoff_utc":chunk[0]["kickoff_utc"],"end_kickoff_utc":chunk[-1]["kickoff_utc"]})
    return out


def _metrics_for_rows(rows:list[dict[str,Any]], lane:str)->dict[str,Any]:
    if lane=="MATCH_RESULT_1X2":
        cp=[]; pp=[]; ys=[]
        for row in rows:
            c,p,y=_lane_values(lane,row["frozen_challenger_probabilities"],row["frozen_poisson_reference"],row["outcomes"]["1x2"])
            cp.append(c);pp.append(p);ys.append(y)
        cm=_multiclass_metrics(cp,ys); pm=_multiclass_metrics(pp,ys)
    else:
        cp=[]; pp=[]; ys=[]
        for row in rows:
            c,p,y=_lane_values(lane,row["frozen_challenger_probabilities"],row["frozen_poisson_reference"],row["outcomes"]["1x2"])
            cp.append(c);pp.append(p);ys.append(y)
        cm=_binary_metrics(cp,ys); pm=_binary_metrics(pp,ys)
    db=float(cm["brier_score"])-float(pm["brier_score"])
    dl=float(cm["log_loss"])-float(pm["log_loss"])
    return {
        "challenger":cm,
        "poisson":pm,
        "delta_brier_challenger_minus_poisson":db,
        "delta_log_loss_challenger_minus_poisson":dl,
        "beats_poisson_brier":db<0,
        "beats_poisson_log_loss":dl<0,
        "proper_scoring_gate_passed":db<0 and dl<0,
    }


def build(generated_at:datetime|None=None)->dict[str,Any]:
    board=_load_json(ACTION_BOARD)
    portfolio=_load_jsonl(PORTFOLIO_LEDGER)
    calibration=_load_jsonl(CALIBRATION_LEDGER)
    freeze=_load_json(FREEZE)

    if board.get("status")!="PASS":
        raise ValueError("ACTION_BOARD_NOT_PASS")
    if board.get("invariants",{}).get("gate600_never_auto_promotes") is not True:
        raise ValueError("GATE600_AUTO_PROMOTION_GUARD_MISSING")

    post600=[
        x for x in board.get("rows") or []
        if isinstance(x,Mapping)
        and x.get("operational_state")=="LAB"
        and int(x.get("prospective_unique_count") or 0)>=600
    ]

    calibration_by_fixture={str(r.get("fixture_id")):r for r in calibration if isinstance(r,Mapping)}
    freeze_by_fixture={str(r.get("fixture_id")):r for r in freeze.get("rows") or [] if isinstance(r,Mapping)}

    lane_results=[]
    for lane_row in sorted(post600,key=lambda x:int(x.get("portfolio_index") or 9999)):
        lane=str(lane_row["market_lane"])
        portfolio_rows=[
            r for r in portfolio
            if isinstance(r,Mapping)
            and str(r.get("market_lane"))==lane
            and r.get("prospective_admitted") is True
        ]
        event_ids=[]
        for r in portfolio_rows:
            fid=str(r.get("fixture_id") or r.get("event_id") or "").strip()
            if fid and fid not in event_ids:
                event_ids.append(fid)

        settled=[]
        missing=[]
        competitions={}
        for fid in event_ids:
            c=calibration_by_fixture.get(fid)
            if c is None:
                missing.append(fid)
                continue
            if c.get("source_terminal_status")!="FT":
                continue
            settled.append(c)
            fr=freeze_by_fixture.get(fid) or {}
            comp=str(fr.get("competition_name") or fr.get("competition_id") or "UNKNOWN")
            competitions[comp]=competitions.get(comp,0)+1

        metrics=_metrics_for_rows(settled,lane) if settled else None
        temporal=_thirds(settled,lane) if settled else []
        settled_count=len(settled)
        freeze_count=len(event_ids)
        if settled_count<600:
            verdict="HOLD"
            reason="AWAITING_600_EXACT_SETTLED_OBSERVATIONS"
        elif metrics and metrics["proper_scoring_gate_passed"]:
            verdict="PASS"
            reason="GATE600_SETTLED_AND_PROPER_SCORING_BEATS_POISSON"
        else:
            verdict="NO_GO"
            reason="GATE600_SETTLED_BUT_PROPER_SCORING_GATE_FAILED"

        lane_results.append({
            "market_lane":lane,
            "display_name":lane_row.get("display_name"),
            "prospective_freeze_count":freeze_count,
            "action_board_count":int(lane_row.get("prospective_unique_count") or 0),
            "exact_settled_count":settled_count,
            "remaining_settled_to_600":max(0,600-settled_count),
            "missing_or_not_yet_final_fixture_count":len(missing),
            "metrics":metrics,
            "temporal_stability_diagnostic":{"method":"CHRONOLOGICAL_THIRDS","segments":temporal},
            "competition_concentration_diagnostic":{
                "competition_count":len(competitions),
                "top_competitions":sorted(
                    ({"competition":k,"count":v,"share":v/settled_count if settled_count else 0.0} for k,v in competitions.items()),
                    key=lambda x:(-x["count"],x["competition"])
                )[:10],
            },
            "verdict":verdict,
            "verdict_reason":reason,
            "automatic_promotion":False,
        })

    overall="PASS" if lane_results and all(x["verdict"]=="PASS" for x in lane_results) else "NO_GO" if any(x["verdict"]=="NO_GO" for x in lane_results) else "HOLD"
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    result={
        "schema":"MATRIX_GATE600_POST_AUDIT_V1",
        "generated_at_utc":now,
        "status":"PASS",
        "audit_overall_verdict":overall,
        "gate600_lab_lane_count":len(post600),
        "lanes":lane_results,
        "adjudication_policy":{
            "freeze_gate_threshold":600,
            "settled_gate_threshold":600,
            "pass_requires_exact_settled_600":True,
            "pass_requires_brier_better_than_poisson":True,
            "pass_requires_logloss_better_than_poisson":True,
            "ece_is_diagnostic_not_a_new_invented_threshold":True,
            "temporal_stability_is_diagnostic_not_a_new_invented_threshold":True,
            "competition_concentration_is_diagnostic_not_a_new_invented_threshold":True,
            "no_automatic_promotion":True,
        },
        "protections":{
            "exact_fixture_intersection_between_42_lane_ledger_and_final_calibration_ledger":True,
            "final_ft_only":True,
            "parameter_tuning_allowed":False,
            "refit_allowed":False,
            "historical_backfill":False,
            "post_start_backfill":False,
            "missing_not_zero":True,
            "silent_imputation":False,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "source_sha256":{
            "action_board":_sha(board),
            "portfolio_ledger":_sha(portfolio),
            "calibration_ledger":_sha(calibration),
        },
    }
    return result


def main()->None:
    result=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "audit_overall_verdict":result["audit_overall_verdict"],
        "gate600_lab_lane_count":result["gate600_lab_lane_count"],
        "lanes":[{"lane":x["market_lane"],"freeze":x["prospective_freeze_count"],"settled":x["exact_settled_count"],"verdict":x["verdict"]} for x in result["lanes"]],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
