from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Mapping

ATTR=Path("evidence/api_football/edge_attribution/2026-10-16/MATRIX_EDGE_ATTRIBUTION_OVER25_V2.json")
TELEGRAM=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
CLV=Path("evidence/clv/football/over_2_5/prospective_clv_ledger.jsonl")
OUT=Path("evidence/api_football/edge_attribution/2026-10-16/MATRIX_EDGE_PERFORMANCE_LEDGER_V1.json")
MIN_DRIVER_SETTLED_N=30
MIN_CLV_N=300

def _sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def _file_sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _dominant(drivers):
    xs=[d for d in (drivers or []) if d.get("driver") in {"POISSON_OVER25","GROUP_BASELINE_OVER25"}]
    if not xs:return None
    return max(xs,key=lambda d:abs(float(d.get("weighted_logit_contribution") or 0)))["driver"]

def build(attr:Mapping[str,Any], telegram:Mapping[str,Any], clv_events:list[Mapping[str,Any]])->dict[str,Any]:
    settlements={str(x.get("fixture_id")):x for x in telegram.get("settlements",[]) if isinstance(x,Mapping)}
    decisions={}
    closings={}
    for e in clv_events:
        if not isinstance(e,Mapping):continue
        p=e.get("payload") or {}
        if e.get("event_type")=="DECISION_FROZEN": decisions[str(p.get("fixture_id"))]=p
        elif e.get("event_type")=="CLOSING_ODDS_RECORDED": closings[str(p.get("fixture_id"))]=p
    rows=[]
    for r in attr.get("rows",[]):
        fid=str(r.get("fixture_id"))
        drivers=(r.get("edge_attribution") or {}).get("feature_level_drivers")
        dom=_dominant(drivers)
        st=settlements.get(fid)
        dec=decisions.get(fid)
        close=closings.get(fid)
        clv=None
        if dec and close:
            clv=float(close["decimal_odds"])/float(dec["decimal_odds"])-1.0
        rows.append({
            "fixture_id":fid,"match":r.get("match"),"p_matrix":r.get("p_matrix"),
            "dominant_model_driver":dom,
            "driver_status":(r.get("edge_attribution") or {}).get("feature_level_driver_status"),
            "entry_odds": float(dec["decimal_odds"]) if dec else None,
            "closing_odds": float(close["decimal_odds"]) if close else None,
            "clv_decimal_ratio_minus_1":clv,
            "settlement_status":st.get("status") if st else "PENDING_OR_NOT_EXECUTED",
            "won":st.get("won") if st else None,
            "paper_profit_cop":st.get("paper_profit_cop") if st else None,
            "shadow_profit_units":st.get("shadow_profit_units") if st else None,
        })
    groups={}
    for name in ("POISSON_OVER25","GROUP_BASELINE_OVER25"):
        rr=[x for x in rows if x["dominant_model_driver"]==name]
        ss=[x for x in rr if x["shadow_profit_units"] is not None]
        cc=[x for x in rr if x["clv_decimal_ratio_minus_1"] is not None]
        groups[name]={
            "row_count":len(rr),"settled_count":len(ss),"clv_count":len(cc),
            "profit_units_sum":sum(float(x["shadow_profit_units"]) for x in ss) if ss else None,
            "roi_units_per_settled":(sum(float(x["shadow_profit_units"]) for x in ss)/len(ss)) if ss else None,
            "mean_clv_decimal_ratio_minus_1":(sum(float(x["clv_decimal_ratio_minus_1"]) for x in cc)/len(cc)) if cc else None,
            "performance_gate_open":len(ss)>=MIN_DRIVER_SETTLED_N,
            "clv_gate_open":len(cc)>=MIN_CLV_N,
        }
    out={
        "schema":"MATRIX_EDGE_PERFORMANCE_LEDGER_V1",
        "source_artifacts":{
            "edge_attribution":{"path":ATTR.as_posix(),"sha256":_file_sha(ATTR) if ATTR.exists() else None},
            "telegram_signal_ledger":{"path":TELEGRAM.as_posix(),"sha256":_file_sha(TELEGRAM) if TELEGRAM.exists() else None},
            "clv_prospective_ledger":{"path":CLV.as_posix(),"sha256":_file_sha(CLV) if CLV.exists() else None},
        },
        "row_count":len(rows),
        "settled_join_count":sum(x["shadow_profit_units"] is not None for x in rows),
        "clv_join_count":sum(x["clv_decimal_ratio_minus_1"] is not None for x in rows),
        "driver_groups":groups,
        "rows":rows,
        "gates":{
            "remaining_settled_to_open_by_driver":{
                name:max(0,MIN_DRIVER_SETTLED_N-int(group["settled_count"]))
                for name,group in groups.items()
            },
            "remaining_clv_to_open_by_driver":{
                name:max(0,MIN_CLV_N-int(group["clv_count"]))
                for name,group in groups.items()
            },
        },
        "governance":{
            "minimum_settled_per_driver_before_comparison":MIN_DRIVER_SETTLED_N,
            "minimum_clv_observations_before_clv_metrics":MIN_CLV_N,
            "driver_superiority_claim_allowed":False,
            "reason":"SEALED_UNTIL_SAMPLE_GATES",
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    }
    out["artifact_sha256"]=_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    attr=json.loads(ATTR.read_text())
    telegram=json.loads(TELEGRAM.read_text())
    clv=[json.loads(x) for x in CLV.read_text().splitlines() if x.strip()]
    out=build(attr,telegram,clv)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print(json.dumps({k:out[k] for k in ("row_count","settled_join_count","clv_join_count","artifact_sha256")},sort_keys=True))

if __name__=="__main__": main()
