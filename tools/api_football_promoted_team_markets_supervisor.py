from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
import requests

from tools.api_football_market_expansion_live_probe import _future_events, _extract_odds

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20.0
MIN_HISTORY=5
MAX_HISTORY=20
MAX_NEW_FREEZES_PER_RUN=4
GATES=(30,50,100,200)
BOOK_PRIORITY=("pinnacle","betano","bwin","betplay","rushbet")

LANES={
 "TEAM_TOTAL_SHOTS_HOME":{
   "bet_id":221,"metric":"Total Shots","target":"HOME",
   "model_path":"evidence/api_football/market_expansion/team_total_shots_side_models/home_model.json",
   "source_dataset":"evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl",
 },
 "TEAM_TOTAL_SHOTS_AWAY":{
   "bet_id":220,"metric":"Total Shots","target":"AWAY",
   "model_path":"evidence/api_football/market_expansion/team_total_shots_side_models/away_model.json",
   "source_dataset":"evidence/api_football/market_expansion/team_pit/team_total_shots_pit.jsonl",
 },
 "TEAM_FOULS_TOTAL":{
   "bet_id":173,"metric":"Fouls","target":"TOTAL",
   "model_path":"evidence/api_football/market_expansion/failed_team_markets_v3/team_fouls_model_v3.json",
   "source_dataset":"evidence/api_football/market_expansion/team_pit/team_fouls_pit.jsonl",
 },
}

def _utc(v:object)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return d.astimezone(timezone.utc)

def _canonical(v:Any)->str:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def _sha(v:Any)->str:
    return hashlib.sha256(_canonical(v).encode()).hexdigest()

def _load_json(path:Path)->dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _load_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def _append_jsonl(path:Path,row:Mapping[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as f:
        f.write(_canonical(dict(row))+"\n")

def _line(value:object,handicap:object)->float|None:
    for raw in (value,handicap):
        m=re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)",str(raw or ""))
        if m:
            x=float(m.group(1))
            if x>0: return x
    return None

def _book_rank(name:str)->int:
    n=re.sub(r"[^a-z0-9]","",name.casefold())
    for i,key in enumerate(BOOK_PRIORITY):
        if key in n: return i
    return 999

def _canonical_offer(hits:list[dict[str,Any]],bet_id:int)->dict[str,Any]|None:
    candidates=[]
    for hit in hits:
        if int(hit.get("bet_id") or -1)!=bet_id or not hit.get("policy_reference_bookmaker"): continue
        pairs={}
        for v in hit.get("values") or []:
            if v.get("suspended") is True: continue
            label=str(v.get("value") or "").casefold()
            direction="OVER" if "over" in label else "UNDER" if "under" in label else None
            if not direction: continue
            line=_line(v.get("value"),v.get("handicap"))
            if line is None: continue
            try: odd=float(v.get("odd"))
            except (TypeError,ValueError): continue
            if odd<=1: continue
            pairs.setdefault(line,{})[direction]={"odd":odd,"main":v.get("main")}
        for line,pair in pairs.items():
            if "OVER" not in pair or "UNDER" not in pair: continue
            overround=1/pair["OVER"]["odd"]+1/pair["UNDER"]["odd"]-1
            main_penalty=0 if pair["OVER"].get("main") in (True,1,"1","true","True") or pair["UNDER"].get("main") in (True,1,"1","true","True") else 1
            candidates.append({
              "bookmaker_name":hit["bookmaker_name"],"bet_id":bet_id,"line":line,
              "over_odds":pair["OVER"]["odd"],"under_odds":pair["UNDER"]["odd"],
              "overround":overround,"main_penalty":main_penalty,
              "rank":_book_rank(hit["bookmaker_name"])
            })
    if not candidates: return None
    candidates.sort(key=lambda x:(x["rank"],x["main_penalty"],abs(x["overround"]),x["line"]))
    c=candidates[0]; c.pop("rank",None); c.pop("main_penalty",None)
    return c

def _api(session:requests.Session,key:str,path:str,params:dict[str,Any],raw_dir:Path,label:str,counter:list[int])->dict[str,Any]:
    r=session.get(BASE_URL+path,headers={"x-apisports-key":key},params=params,timeout=TIMEOUT)
    counter[0]+=1
    body=bytes(r.content); raw_dir.mkdir(parents=True,exist_ok=True)
    (raw_dir/f"{label}.bin").write_bytes(body)
    if not 200<=r.status_code<300: raise RuntimeError(f"HTTP_{r.status_code}:{path}")
    try: p=r.json()
    except ValueError as exc: raise RuntimeError("INVALID_JSON:"+path) from exc
    return p if isinstance(p,dict) else {}

def _fixture_detail(session,key,fid,raw,counter)->dict[str,Any]|None:
    p=_api(session,key,"/fixtures",{"id":fid},raw,f"fixture_{fid}_detail",counter)
    rows=p.get("response") or []
    if not rows: return None
    r=rows[0]
    f=r.get("fixture") or {}; league=r.get("league") or {}; teams=r.get("teams") or {}
    return {
      "fixture_id":str(f.get("id") or fid),"kickoff_utc":f.get("date"),
      "status":(f.get("status") or {}).get("short"),
      "league_id":str(league.get("id") or ""),"season":league.get("season"),
      "home_team_id":str((teams.get("home") or {}).get("id") or ""),
      "away_team_id":str((teams.get("away") or {}).get("id") or ""),
      "home_team_name":(teams.get("home") or {}).get("name"),
      "away_team_name":(teams.get("away") or {}).get("name"),
    }

def _stat_map(payload:Mapping[str,Any])->dict[str,dict[str,float]]:
    out={}
    for row in payload.get("response") or []:
        team=row.get("team") if isinstance(row,Mapping) else {}
        tid=str(team.get("id") or "")
        vals={}
        for s in row.get("statistics") or []:
            if not isinstance(s,Mapping): continue
            typ=str(s.get("type") or ""); v=s.get("value")
            try:
                if isinstance(v,str) and v.endswith("%"): val=float(v[:-1])
                else: val=float(v)
            except (TypeError,ValueError): continue
            vals[typ]=val
        if tid: out[tid]=vals
    return out

def _team_history(session,key,team_id,league_id,season,before,metric,raw,counter,stats_cache):
    p=_api(session,key,"/fixtures",{"team":team_id,"league":league_id,"season":season,"last":MAX_HISTORY},raw,f"team_{team_id}_{metric.replace(' ','_')}_fixtures",counter)
    rows=[]
    for rr in p.get("response") or []:
        f=rr.get("fixture") or {}; status=(f.get("status") or {}).get("short")
        if status!="FT" or not f.get("date") or _utc(f["date"])>=before: continue
        fid=str(f.get("id") or ""); teams=rr.get("teams") or {}
        hid=str((teams.get("home") or {}).get("id") or ""); aid=str((teams.get("away") or {}).get("id") or "")
        if team_id not in {hid,aid}: continue
        if fid not in stats_cache:
            sp=_api(session,key,"/fixtures/statistics",{"fixture":fid},raw,f"fixture_{fid}_stats",counter)
            stats_cache[fid]=_stat_map(sp)
        sm=stats_cache[fid]
        opp=aid if team_id==hid else hid
        if team_id in sm and opp in sm and metric in sm[team_id] and metric in sm[opp]:
            rows.append({"kickoff_utc":f["date"],"own":sm[team_id][metric],"allowed":sm[opp][metric],"fixture_id":fid})
    rows.sort(key=lambda x:_utc(x["kickoff_utc"]))
    return rows[-MAX_HISTORY:]

def _features(session,key,detail,metric,raw,counter,stats_cache):
    kickoff=_utc(detail["kickoff_utc"])
    h=_team_history(session,key,detail["home_team_id"],detail["league_id"],detail["season"],kickoff,metric,raw,counter,stats_cache)
    a=_team_history(session,key,detail["away_team_id"],detail["league_id"],detail["season"],kickoff,metric,raw,counter,stats_cache)
    if len(h)<MIN_HISTORY or len(a)<MIN_HISTORY: return None
    hm=sum(x["own"] for x in h)/len(h); ha=sum(x["allowed"] for x in h)/len(h)
    am=sum(x["own"] for x in a)/len(a); aa=sum(x["allowed"] for x in a)/len(a)
    eh=(hm+aa)/2; ea=(am+ha)/2
    return {"home_history_count":len(h),"away_history_count":len(a),"home_for_mean":hm,"home_against_mean":ha,"away_for_mean":am,"away_against_mean":aa,"expected_home":eh,"expected_away":ea,"expected_total":eh+ea}

def _poisson_over(mu,line):
    mu=max(.05,float(mu)); cut=int(math.floor(line)); term=math.exp(-mu); cdf=term
    for k in range(1,cut+1): term*=mu/k; cdf+=term
    return min(max(1-cdf,1e-15),1-1e-15)

def _nb_over(mu,r,line):
    mu=max(.05,float(mu)); r=max(.05,float(r)); cut=int(math.floor(line)); q=mu/(r+mu)
    term=(r/(r+mu))**r; cdf=term
    for k in range(1,cut+1): term*=((k-1+r)/k)*q; cdf+=term
    return min(max(1-cdf,1e-15),1-1e-15)

def _probability(lane,model,feat,line):
    if lane.startswith("TEAM_TOTAL_SHOTS"):
        p=model["model_parameters"]; side="expected_home" if lane.endswith("HOME") else "expected_away"
        raw=[feat[side]]
        z=float(p["weights"][0])
        for j,val in enumerate(raw):
            z+=float(p["weights"][j+1])*((float(val)-float(p["means"][j]))/float(p["stds"][j]))
        mu=min(max(math.exp(min(max(z,-6),6)),.05),100)
        return _poisson_over(mu,line),_poisson_over(float(feat[side]),line),mu
    p=model["model_parameters"]
    mu=max(.05,float(p["alpha"])*(float(p["scale"])*float(feat["expected_total"]))+(1-float(p["alpha"]))*float(p["target_mean"]))
    return _nb_over(mu,float(p["dispersion_r"]),line),_poisson_over(float(feat["expected_total"]),line),mu

def _trained_leagues(path:Path)->set[str]:
    return {str(r.get("league_id") or "") for r in _load_jsonl(path) if r.get("split")=="TRAIN"}

def _gate_metrics(rows):
    if not rows: return None
    def m(key):
        b=ll=0.0
        for r in rows:
            p=min(max(float(r[key]),1e-15),1-1e-15); y=1.0 if r["outcome_over"] else 0.0
            b+=(p-y)**2; ll+=-(y*math.log(p)+(1-y)*math.log(1-p))
        return {"sample_size":len(rows),"brier_score":b/len(rows),"log_loss":ll/len(rows)}
    c=m("frozen_probability_over"); ref=m("frozen_reference_probability_over")
    return {"challenger":c,"reference":ref,"gate_passed":c["brier_score"]<ref["brier_score"] and c["log_loss"]<ref["log_loss"]}

def run(key:str,root:Path)->dict[str,Any]:
    key=str(key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    now=datetime.now(timezone.utc).replace(microsecond=0); run_id=now.strftime("%Y%m%dT%H%M%SZ")
    raw=root/"runs"/run_id/"raw"; session=requests.Session(); counter=[0]; stats_cache={}
    events=_future_events(now,24*60,24)
    lane_models={lane:_load_json(Path(cfg["model_path"])) for lane,cfg in LANES.items()}
    lane_leagues={lane:_trained_leagues(Path(cfg["source_dataset"])) for lane,cfg in LANES.items()}
    frozen_new=[]; blockers=[]
    offer_counts={lane:0 for lane in LANES}
    events_with_any_canonical_offer=0
    events_without_target_offer=0
    detail_not_prematch_count=0
    already_frozen_count=0
    for e in events:
        if len(frozen_new)>=MAX_NEW_FREEZES_PER_RUN: break
        fid=str(e["provider_fixture_id"])
        op=_api(session,key,"/odds",{"fixture":fid},raw,f"fixture_{fid}_odds",counter)
        hits=_extract_odds(op)
        offers={lane:_canonical_offer(hits,cfg["bet_id"]) for lane,cfg in LANES.items()}
        offered_lanes=[lane for lane,offer in offers.items() if offer is not None]
        if not offered_lanes:
            events_without_target_offer+=1
            continue
        events_with_any_canonical_offer+=1
        for lane in offered_lanes:
            offer_counts[lane]+=1
        detail=_fixture_detail(session,key,fid,raw,counter)
        if not detail or detail["status"] not in {"NS","TBD"} or _utc(detail["kickoff_utc"])<=now:
            detail_not_prematch_count+=1
            continue
        for lane,cfg in LANES.items():
            offer=offers[lane]
            if offer is None: continue
            ledger=root/lane.casefold()/"freeze_ledger.jsonl"
            existing=_load_jsonl(ledger)
            if any(str(x["fixture_id"])==fid for x in existing):
                already_frozen_count+=1
                continue
            if detail["league_id"] not in lane_leagues[lane]:
                blockers.append({"lane":lane,"fixture_id":fid,"reason":"OUTSIDE_TRAINED_LEAGUE_DOMAIN","league_id":detail["league_id"]}); continue
            feat=_features(session,key,detail,cfg["metric"],raw,counter,stats_cache)
            if feat is None:
                blockers.append({"lane":lane,"fixture_id":fid,"reason":"INSUFFICIENT_CURRENT_PIT_HISTORY"}); continue
            prob,refp,mu=_probability(lane,lane_models[lane],feat,float(offer["line"]))
            row={"schema":"MATRIX_PROMOTED_TEAM_MARKET_FREEZE_V1","lane":lane,"fixture_id":fid,"kickoff_utc":detail["kickoff_utc"],"freeze_at_utc":now.isoformat(),"market_line":float(offer["line"]),"frozen_probability_over":prob,"frozen_reference_probability_over":refp,"frozen_count_mean":mu,"bookmaker_name":offer["bookmaker_name"],"over_odds_observed":offer["over_odds"],"under_odds_observed":offer["under_odds"],"overround_observed":offer["overround"],"features":feat,"model_parameters_sha256":lane_models[lane].get("model_parameters_sha256"),"odds_used_to_generate_probability":False,"outcome":None,"automatic_wagering":False,"real_money":"BLOCKED"}
            row["record_sha256"]=_sha(row); _append_jsonl(ledger,row); frozen_new.append({"lane":lane,"fixture_id":fid})
    # Settlement/calibration of previously frozen records.
    settled_new=[]
    for lane,cfg in LANES.items():
        lane_dir=root/lane.casefold(); freezes=_load_jsonl(lane_dir/"freeze_ledger.jsonl"); cal=_load_jsonl(lane_dir/"calibration_ledger.jsonl")
        done={str(x["fixture_id"]) for x in cal}
        for fr in freezes:
            fid=str(fr["fixture_id"])
            if fid in done or _utc(fr["kickoff_utc"])+timedelta(minutes=90)>now: continue
            detail=_fixture_detail(session,key,fid,raw,counter)
            if not detail or detail["status"]!="FT": continue
            sp=_api(session,key,"/fixtures/statistics",{"fixture":fid},raw,f"settlement_{fid}_stats",counter)
            sm=_stat_map(sp); h=detail["home_team_id"]; a=detail["away_team_id"]
            if h not in sm or a not in sm or cfg["metric"] not in sm[h] or cfg["metric"] not in sm[a]: continue
            if cfg["target"]=="HOME": target=sm[h][cfg["metric"]]
            elif cfg["target"]=="AWAY": target=sm[a][cfg["metric"]]
            else: target=sm[h][cfg["metric"]]+sm[a][cfg["metric"]]
            row={"schema":"MATRIX_PROMOTED_TEAM_MARKET_CALIBRATION_V1","lane":lane,"fixture_id":fid,"kickoff_utc":fr["kickoff_utc"],"freeze_at_utc":fr["freeze_at_utc"],"settled_at_utc":now.isoformat(),"market_line":fr["market_line"],"target_value":target,"outcome_over":bool(target>float(fr["market_line"])),"frozen_probability_over":fr["frozen_probability_over"],"frozen_reference_probability_over":fr["frozen_reference_probability_over"],"model_parameters_sha256":fr["model_parameters_sha256"],"parameter_tuning_used":False,"automatic_wagering":False,"real_money":"BLOCKED"}
            row["record_sha256"]=_sha(row); _append_jsonl(lane_dir/"calibration_ledger.jsonl",row); settled_new.append({"lane":lane,"fixture_id":fid})
        cal=_load_jsonl(lane_dir/"calibration_ledger.jsonl")
        state=_load_json(lane_dir/"state.json") if (lane_dir/"state.json").exists() else {}
        gates={}
        for g in GATES:
            if len(cal)<g: gates[str(g)]={"threshold":g,"status":"SEALED","observations_available":len(cal),"remaining":g-len(cal),"metrics_opened":False}
            else: gates[str(g)]={"threshold":g,"status":"OPENED_AT_THRESHOLD","observations_available":len(cal),"observations_used":g,"remaining":0,"metrics_opened":True,"metrics":_gate_metrics(cal[:g])}
        state.update({"freeze_observation_count":len(_load_jsonl(lane_dir/"freeze_ledger.jsonl")),"calibration_observation_count":len(cal),"gates":gates,"last_supervisor_run_utc":now.isoformat(),"prospective_lane_ready":True,"status":"ACTIVE","automatic_wagering":False,"real_money":"BLOCKED"})
        (lane_dir/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if frozen_new:
        zero_freeze_reason=None
    elif events_with_any_canonical_offer==0:
        zero_freeze_reason="NO_CANONICAL_TARGET_MARKET_OFFERS_IN_CHECKED_EVENTS"
    elif blockers:
        zero_freeze_reason="CANONICAL_OFFERS_FOUND_BUT_BLOCKED_BY_DOMAIN_OR_PIT_GATES"
    elif already_frozen_count:
        zero_freeze_reason="CANONICAL_OFFERS_ALREADY_FROZEN"
    elif detail_not_prematch_count:
        zero_freeze_reason="CANONICAL_OFFERS_NOT_VALID_PREMATCH"
    else:
        zero_freeze_reason="NO_ELIGIBLE_FREEZE_AFTER_GOVERNED_GATES"
    summary={
      "schema":"MATRIX_PROMOTED_TEAM_MARKETS_SUPERVISOR_RUN_V2",
      "run_id":run_id,"observed_at_utc":now.isoformat(),"network_calls":counter[0],
      "future_events_checked":len(events),"new_freezes":frozen_new,"new_settlements":settled_new,
      "blockers":blockers,
      "offer_audit":{
        "events_with_any_canonical_offer":events_with_any_canonical_offer,
        "events_without_target_offer":events_without_target_offer,
        "canonical_offer_fixture_count_by_lane":offer_counts,
        "detail_not_prematch_count":detail_not_prematch_count,
        "already_frozen_count":already_frozen_count,
        "zero_freeze_reason":zero_freeze_reason,
      },
      "odds_used_to_generate_probability":False,"automatic_wagering":False,
      "real_money":"BLOCKED","status":"PASS"
    }
    run_dir=root/"runs"/run_id; run_dir.mkdir(parents=True,exist_ok=True)
    (run_dir/"manifest.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (root/"last_run.json").write_text(json.dumps({**summary,"manifest_path":str(run_dir/"manifest.json")},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","network_calls":counter[0],"new_freezes":len(frozen_new),"new_settlements":len(settled_new),"blockers":len(blockers),"real_money":"BLOCKED"},sort_keys=True))
    return summary

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/promoted_team_markets"))
