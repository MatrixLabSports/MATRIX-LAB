from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping

SNAPSHOT=Path("evidence/api_football/model_validation/benter_second_stage/2026-10-16/MATRIX_BENTER_ALL_CANDIDATE_MARKET_SNAPSHOT_V1.json")
OUT=Path("evidence/api_football/model_validation/benter_second_stage/2026-10-16/MATRIX_BENTER_ALL_CANDIDATE_SETTLED_V1.json")
FINAL_STATUSES={"FT","AET","PEN"}

def _sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def settle(snapshot:Mapping[str,Any], provider_payload:Mapping[str,Any], *, raw_sha256:str|None=None)->dict[str,Any]:
    finals={}
    for item in provider_payload.get("response") or []:
        if not isinstance(item,Mapping): continue
        fx=item.get("fixture") or {}; goals=item.get("goals") or {}
        status=((fx.get("status") or {}).get("short"))
        fid=str(fx.get("id") or "")
        if not fid or str(status or "").upper() not in FINAL_STATUSES: continue
        hg,ag=goals.get("home"),goals.get("away")
        if not isinstance(hg,int) or isinstance(hg,bool) or not isinstance(ag,int) or isinstance(ag,bool): continue
        finals[fid]={"home_goals":hg,"away_goals":ag,"final_status":str(status).upper()}
    rows=[]
    for src in snapshot.get("rows") or []:
        if not isinstance(src,Mapping): continue
        fid=str(src.get("fixture_id") or "")
        fin=finals.get(fid)
        row=dict(src)
        if fin:
            row.update(fin)
            row["outcome_over25"]=(fin["home_goals"]+fin["away_goals"]>=3)
            row["outcome_status"]="FINAL_API_FOOTBALL_PENDING_PRIMARY_SOURCE_RECONCILIATION"
        else:
            row["outcome_over25"]=None
            row["outcome_status"]="PENDING_FINAL_OUTCOME"
        rows.append(row)
    paired=[r for r in rows if r.get("market_probability_devigged_consensus") is not None and r.get("outcome_over25") is not None]
    out={
        "schema":"MATRIX_BENTER_ALL_CANDIDATE_SETTLED_V1",
        "target_date_bogota":snapshot.get("target_date_bogota"),
        "row_count":len(rows),
        "final_outcome_count":sum(r.get("outcome_over25") is not None for r in rows),
        "devigged_market_plus_final_count":len(paired),
        "remaining_to_300_triplets":max(0,300-len(paired)),
        "rows":rows,
        "source_snapshot_sha256":snapshot.get("artifact_sha256"),
        "provider_raw_sha256":raw_sha256,
        "source_policy":{
            "operational_priority":["SOFASCORE","FLASHSCORE","API_FOOTBALL"],
            "automated_settlement_source":"API_FOOTBALL",
            "primary_source_reconciliation_required":True,
        },
        "governance":{
            "research_only":True,
            "production_p_matrix_modified":False,
            "market_probability_fused_into_production":False,
            "fusion_fit_allowed":False,
            "outcome_source_is_tertiary_pending_reconciliation":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    }
    out["artifact_sha256"]=_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    import os,requests
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key: raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    snapshot=json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    date=str(snapshot.get("target_date_bogota") or "")
    r=requests.get("https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key":key},
        params={"date":date,"timezone":"America/Bogota"},timeout=(10,30))
    body=bytes(r.content); raw_sha=hashlib.sha256(body).hexdigest()
    if r.status_code>=300: raise SystemExit(f"API_FOOTBALL_HTTP_{r.status_code}")
    payload=r.json()
    if payload.get("errors") not in ({},[],None): raise SystemExit("API_FOOTBALL_ERRORS")
    out=settle(snapshot,payload,raw_sha256=raw_sha)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":"PASS","row_count":out["row_count"],
        "final_outcome_count":out["final_outcome_count"],
        "devigged_market_plus_final_count":out["devigged_market_plus_final_count"],
        "remaining_to_300_triplets":out["remaining_to_300_triplets"],
        "artifact_sha256":out["artifact_sha256"],
        "real_money":out["governance"]["real_money"],
    },sort_keys=True))

if __name__=="__main__": main()
