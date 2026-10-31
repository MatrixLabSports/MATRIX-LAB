from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE_FREEZE=Path("evidence/api_football/prospective_market_freeze/freeze.json")
PIT=Path("evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl")
HOME_MODEL=Path("evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json")
AWAY_MODEL=Path("evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json")
DEFAULT_INBOX=Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
DEFAULT_LEDGER=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
DEFAULT_AUDIT=Path("evidence/market_portfolio/MATRIX_42_LANE_TEAM_SHOTS_OFFLINE_BRIDGE_LAST.json")
MIN_HISTORY=5
MAX_HISTORY=20


def _load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v


def _jsonl(path:Path)->list[dict[str,Any]]:
    out=[]
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            v=json.loads(line)
            if isinstance(v,dict):
                out.append(v)
    return out


def _utc(v:object)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return d.astimezone(timezone.utc)


def _sha(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _poisson_over(mu:float,line:float)->float:
    mu=max(.05,float(mu)); cut=int(math.floor(line)); term=math.exp(-mu); cdf=term
    for k in range(1,cut+1):
        term*=mu/k; cdf+=term
    return min(max(1-cdf,1e-15),1-1e-15)


def _model_probability(model:Mapping[str,Any], expected:float, line:float)->tuple[float,float]:
    p=model["model_parameters"]
    z=float(p["weights"][0])
    z+=float(p["weights"][1])*((float(expected)-float(p["means"][0]))/float(p["stds"][0]))
    mu=min(max(math.exp(min(max(z,-6),6)),.05),100)
    return _poisson_over(mu,line),mu


def _history_index(rows:list[dict[str,Any]])->dict[tuple[str,int,str],list[dict[str,Any]]]:
    by=defaultdict(list)
    for r in rows:
        try:
            kickoff=_utc(r.get("kickoff_utc"))
            league=str(r.get("league_id") or "")
            season=int(r.get("season"))
            hid=str(r.get("home_team_id") or ""); aid=str(r.get("away_team_id") or "")
            th=float(r.get("target_home")); ta=float(r.get("target_away"))
        except (TypeError,ValueError):
            continue
        if not league or not hid or not aid:
            continue
        base={"kickoff":kickoff,"fixture_id":str(r.get("fixture_id") or "")}
        by[(league,season,hid)].append({**base,"own":th,"allowed":ta})
        by[(league,season,aid)].append({**base,"own":ta,"allowed":th})
    for key in by:
        by[key].sort(key=lambda x:(x["kickoff"],x["fixture_id"]))
    return by


def build_rows(
    *,
    source:Mapping[str,Any],
    pit_rows:list[dict[str,Any]],
    home_model:Mapping[str,Any],
    away_model:Mapping[str,Any],
    now_utc:datetime,
    existing_keys:set[str],
)->tuple[list[dict[str,Any]],dict[str,Any]]:
    for model,side,line in ((home_model,"HOME",15.5),(away_model,"AWAY",11.5)):
        if model.get("prospective_eligible") is not True:
            raise ValueError(f"{side}_MODEL_NOT_PROSPECTIVE_ELIGIBLE")
        if model.get("status")!="FROZEN_FOR_NEW_PROSPECTIVE_VALIDATION":
            raise ValueError(f"{side}_MODEL_NOT_FROZEN")
        if float(model.get("historical_evaluation_line"))!=line:
            raise ValueError(f"{side}_MODEL_LINE_CHANGED")
        if model.get("odds_used_to_generate_probability") is not False or model.get("real_money")!="BLOCKED":
            raise ValueError(f"{side}_MODEL_PROTECTION_INVALID")

    idx=_history_index(pit_rows)
    admitted=[]; blocked=[]
    candidates=0
    for src in source.get("rows") or []:
        if not isinstance(src,Mapping):
            continue
        try:
            start=_utc(src.get("kickoff_utc")); freeze=_utc(src.get("freeze_at_utc"))
            league=str(src.get("competition_id") or "")
            season=int(src.get("season"))
            hid=str(src.get("home_team_id") or ""); aid=str(src.get("away_team_id") or "")
            fid=str(src.get("fixture_id") or "")
        except (TypeError,ValueError) as exc:
            blocked.append({"fixture_id":src.get("fixture_id"),"reason":"SOURCE_IDENTITY_INVALID:"+type(exc).__name__})
            continue
        if start<=now_utc:
            continue
        candidates+=1
        if freeze>=start or src.get("outcome") is not None:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_NOT_VALID_PREMATCH"})
            continue
        hh=[x for x in idx.get((league,season,hid),[]) if x["kickoff"]<freeze][-MAX_HISTORY:]
        ah=[x for x in idx.get((league,season,aid),[]) if x["kickoff"]<freeze][-MAX_HISTORY:]
        if len(hh)<MIN_HISTORY or len(ah)<MIN_HISTORY:
            blocked.append({"fixture_id":fid,"reason":"INSUFFICIENT_PERSISTED_TEAM_SHOTS_PIT_HISTORY","home_count":len(hh),"away_count":len(ah)})
            continue
        hm=sum(x["own"] for x in hh)/len(hh); ha=sum(x["allowed"] for x in hh)/len(hh)
        am=sum(x["own"] for x in ah)/len(ah); aa=sum(x["allowed"] for x in ah)/len(ah)
        expected_home=(hm+aa)/2.0; expected_away=(am+ha)/2.0
        feature={
            "fixture_id":fid,"league_id":league,"season":season,
            "freeze_timestamp_utc":freeze.isoformat(),
            "home_history_count":len(hh),"away_history_count":len(ah),
            "home_for_mean":hm,"home_against_mean":ha,
            "away_for_mean":am,"away_against_mean":aa,
            "expected_home":expected_home,"expected_away":expected_away,
            "feature_policy":"STRICTLY_PRIOR_PERSISTED_PIT_MATCHES_ONLY",
            "pit_source_sha256":_sha(pit_rows),
        }
        feature_sha=_sha(feature)
        for lane,model,expected,line in (
            ("TEAM_TOTAL_SHOTS_HOME",home_model,expected_home,15.5),
            ("TEAM_TOTAL_SHOTS_AWAY",away_model,expected_away,11.5),
        ):
            key=f"football|{lane}|fixture:{fid}|freeze:{freeze.isoformat()}"
            if key in existing_keys:
                continue
            p,mu=_model_probability(model,expected,line)
            prediction={"line":line,"over":p,"under":1-p,"frozen_count_mean":mu}
            admitted.append({
                "observation_key":key,
                "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
                "sport":"football",
                "market_lane":lane,
                "fixture_id":fid,"event_id":fid,
                "event_start_utc":start.isoformat(),
                "freeze_timestamp_utc":freeze.isoformat(),
                "source_schema":source.get("schema"),
                "source_snapshot_sha256":_sha(dict(src)),
                "feature_snapshot_sha256":feature_sha,
                "prediction_snapshot_sha256":_sha({"lane":lane,"prediction":prediction,"feature_snapshot_sha256":feature_sha}),
                "prediction":prediction,
                "model_parameters_sha256":model.get("model_parameters_sha256"),
                "model_basis":"FROZEN_TEAM_TOTAL_SHOTS_SIDE_MODEL_OFFLINE_PIT",
                "price_mode":"MODEL_ONLY_RESEARCH_NO_ODDS",
                "price_observed":False,
                "target_outcome":None,"settlement":None,
                "prospective_admitted":True,
                "counts_toward_100_300_600":True,
                "odds_used_to_generate_probability":False,
                "missing_not_zero":True,"silent_imputation":False,
                "automatic_wagering":False,"real_money":"BLOCKED",
            })

    admitted.sort(key=lambda x:(x["event_start_utc"],x["fixture_id"],x["market_lane"]))
    reasons={}
    for b in blocked:
        reasons[b["reason"]]=reasons.get(b["reason"],0)+1
    audit={
        "schema":"MATRIX_42_LANE_TEAM_SHOTS_OFFLINE_BRIDGE_V1",
        "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
        "future_source_fixture_candidates":candidates,
        "eligible_future_unique_fixtures":len({x["fixture_id"] for x in admitted}),
        "eligible_future_lane_rows":len(admitted),
        "lanes_emitted":["TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY"],
        "blocked_count":len(blocked),"blocked_reason_counts":reasons,"blocked":blocked[:100],
        "protections":{
            "network_calls":0,
            "strictly_prior_persisted_pit_history_only":True,
            "same_match_target_used_in_features":False,
            "historical_model_lines_only":True,
            "price_observed":False,
            "odds_used_to_generate_probability":False,
            "parameter_refit":False,"parameter_search":False,
            "post_start_backfill_forbidden":True,
            "outcomes_read":0,"automatic_wagering":False,"real_money":"BLOCKED",
        },
        "status":"PASS",
    }
    return admitted,audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(SOURCE_FREEZE)); p.add_argument("--pit",default=str(PIT))
    p.add_argument("--home-model",default=str(HOME_MODEL)); p.add_argument("--away-model",default=str(AWAY_MODEL))
    p.add_argument("--inbox",default=str(DEFAULT_INBOX)); p.add_argument("--ledger",default=str(DEFAULT_LEDGER))
    p.add_argument("--audit-out",default=str(DEFAULT_AUDIT)); a=p.parse_args()
    inbox=Path(a.inbox)
    current=_jsonl(inbox); ledger=_jsonl(Path(a.ledger))
    existing={str(x.get("observation_key") or "") for x in current+ledger}
    rows,audit=build_rows(
        source=_load(Path(a.source)),pit_rows=_jsonl(Path(a.pit)),
        home_model=_load(Path(a.home_model)),away_model=_load(Path(a.away_model)),
        now_utc=datetime.now(timezone.utc).replace(microsecond=0),existing_keys=existing,
    )
    if rows:
        inbox.parent.mkdir(parents=True,exist_ok=True)
        with inbox.open("a",encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    out=Path(a.audit_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":audit["status"],"eligible_future_unique_fixtures":audit["eligible_future_unique_fixtures"],"eligible_future_lane_rows":audit["eligible_future_lane_rows"],"blocked_count":audit["blocked_count"],"network_calls":0,"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
