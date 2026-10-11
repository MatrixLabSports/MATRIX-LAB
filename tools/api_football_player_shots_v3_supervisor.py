from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
import requests

from tools.api_football_market_expansion_live_probe import _future_events, _extract_odds, _extract_lineups

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=20.0
BET_IDS={240:"Home Player Shots",241:"Away Player Shots",265:"Player Shots Total",270:"Home Player Shots Total",276:"Away Player Shots Total"}
BOOK_PRIORITY=("pinnacle","betano","bwin","betplay","rushbet")
MIN_OVERALL_HISTORY=5
MIN_ROLE_HISTORY=3
MAX_OVERALL_HISTORY=20
MAX_ROLE_HISTORY=10
GATES=(30,50,100,200)
MAX_NEW_FREEZES_PER_RUN=8

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

def _append(path:Path,row:Mapping[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as f: f.write(_canonical(dict(row))+"\n")

def _norm(s:object)->str:
    x=unicodedata.normalize("NFKD",str(s or ""))
    x="".join(ch for ch in x if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]","",x.casefold())

def _line(*vals:object)->float|None:
    for raw in vals:
        for m in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)",str(raw or "")):
            x=float(m.group(1))
            if 0.5<=x<=20.5 and abs((x*2)-round(x*2))<1e-9:
                return x
    return None

def _direction(s:object)->str|None:
    t=str(s or "").casefold()
    if "over" in t or "más de" in t or "mas de" in t: return "OVER"
    if "under" in t or "menos de" in t: return "UNDER"
    return None

def _book_rank(name:str)->int:
    n=_norm(name)
    for i,b in enumerate(BOOK_PRIORITY):
        if b in n: return i
    return 999

def _candidate_player(label:str,lineup_players:list[dict[str,Any]])->dict[str,Any]|None:
    n=_norm(label)
    hits=[]
    for p in lineup_players:
        pn=_norm(p.get("player_name"))
        if len(pn)>=4 and (pn in n or (len(n)>=6 and n in pn)):
            hits.append(p)
    by_id={str(x["player_id"]):x for x in hits}
    return next(iter(by_id.values())) if len(by_id)==1 else None

def _parse_offers(hits:list[dict[str,Any]],lineup_players:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    pairs=defaultdict(dict); blockers=[]
    for hit in hits:
        bid=int(hit.get("bet_id") or -1)
        if bid not in BET_IDS or not hit.get("policy_reference_bookmaker"): continue
        book=str(hit.get("bookmaker_name") or "")
        for v in hit.get("values") or []:
            direction=_direction(v.get("value"))
            line=_line(v.get("handicap"),v.get("value"))
            label=" ".join([str(hit.get("bet_name") or ""),str(v.get("value") or ""),str(v.get("handicap") or "")])
            player=_candidate_player(label,lineup_players)
            if direction is None or line is None or player is None:
                blockers.append({"bet_id":bid,"bookmaker":book,"value":v.get("value"),"handicap":v.get("handicap"),"reason":"UNPARSEABLE_PLAYER_DIRECTION_OR_LINE"})
                continue
            try: odd=float(v.get("odd"))
            except (TypeError,ValueError):
                blockers.append({"bet_id":bid,"bookmaker":book,"value":v.get("value"),"reason":"INVALID_DECIMAL_ODD"}); continue
            if odd<=1: continue
            key=(str(player["player_id"]),line,book,bid)
            pairs[key][direction]={"odd":odd,"main":v.get("main"),"player":player}
    offers=[]
    for (pid,line,book,bid),pair in pairs.items():
        if "OVER" not in pair or "UNDER" not in pair: continue
        overround=1/pair["OVER"]["odd"]+1/pair["UNDER"]["odd"]-1
        offers.append({
          "player_id":pid,"player_name":pair["OVER"]["player"]["player_name"],"role":pair["OVER"]["player"]["role"],
          "line":line,"bookmaker_name":book,"bet_id":bid,"bet_name":BET_IDS[bid],
          "over_odds":pair["OVER"]["odd"],"under_odds":pair["UNDER"]["odd"],"overround":overround,
          "book_rank":_book_rank(book)
        })
    offers.sort(key=lambda x:(x["player_id"],x["line"],x["book_rank"],abs(x["overround"]),x["bet_id"]))
    best=[]; seen=set()
    for o in offers:
        k=(o["player_id"],o["line"])
        if k in seen: continue
        seen.add(k); o.pop("book_rank",None); best.append(o)
    return best,blockers

def _features(history:list[dict[str,Any]],player_id:str,role:str,kickoff:datetime)->dict[str,float]|None:
    prior=[r for r in history if str(r["player_id"])==player_id and _utc(r["kickoff_utc"])<kickoff]
    prior.sort(key=lambda r:_utc(r["kickoff_utc"]))
    prior=prior[-MAX_OVERALL_HISTORY:]
    role_prior=[r for r in prior if r["role"]==role][-MAX_ROLE_HISTORY:]
    if len(prior)<MIN_OVERALL_HISTORY or len(role_prior)<MIN_ROLE_HISTORY: return None
    recent=role_prior[-3:]
    def rate(rows):
        mins=sum(float(r["minutes"]) for r in rows)
        return 90*sum(float(r["shots"]) for r in rows)/mins if mins>0 else 0.0
    return {
      "prior_appearance_count":len(prior),"prior_role_appearance_count":len(role_prior),
      "prior_mean_minutes":sum(float(r["minutes"]) for r in prior)/len(prior),
      "role_expected_minutes":sum(float(r["minutes"]) for r in role_prior)/len(role_prior),
      "overall_prior_shots_per90":rate(prior),"role_prior_shots_per90":rate(role_prior),"role_recent3_shots_per90":rate(recent)
    }

def _poisson_over(mu:float,line:float)->float:
    mu=max(0.01,float(mu)); cut=int(math.floor(line)); term=math.exp(-mu); cdf=term
    for k in range(1,cut+1): term*=mu/k; cdf+=term
    return min(max(1-cdf,1e-15),1-1e-15)

def _prob(features:dict[str,float],alpha:float,line:float)->tuple[float,float,float]:
    rate=(1-alpha)*features["role_prior_shots_per90"]+alpha*features["role_recent3_shots_per90"]
    mins=min(90,max(1,features["role_expected_minutes"]))
    mu=max(.01,rate*mins/90)
    ref_mu=max(.01,features["overall_prior_shots_per90"]*min(90,max(1,features["prior_mean_minutes"]))/90)
    return _poisson_over(mu,line),_poisson_over(ref_mu,line),mu

def _api(session,key,path,params,raw_dir,label,counter):
    r=session.get(BASE_URL+path,headers={"x-apisports-key":key},params=params,timeout=TIMEOUT)
    counter[0]+=1; body=bytes(r.content); raw_dir.mkdir(parents=True,exist_ok=True); (raw_dir/f"{label}.bin").write_bytes(body)
    if not 200<=r.status_code<300: raise RuntimeError(f"HTTP_{r.status_code}:{path}")
    try: p=r.json()
    except ValueError as exc: raise RuntimeError("INVALID_JSON:"+path) from exc
    return p if isinstance(p,dict) else {}

def _actual_shots(payload:Mapping[str,Any],player_id:str)->float|None:
    for tr in payload.get("response") or []:
        for pr in tr.get("players") or []:
            p=pr.get("player") if isinstance(pr,Mapping) and isinstance(pr.get("player"),Mapping) else {}
            if str(p.get("id") or "")!=player_id: continue
            for st in pr.get("statistics") or []:
                shots=st.get("shots") if isinstance(st,Mapping) and isinstance(st.get("shots"),Mapping) else {}
                if shots.get("total") is not None:
                    try: return float(shots["total"])
                    except (TypeError,ValueError): return None
    return None

def _fixture_status(payload:Mapping[str,Any])->str|None:
    rows=payload.get("response") or []
    if not rows: return None
    return ((rows[0].get("fixture") or {}).get("status") or {}).get("short")

def _gate(rows):
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
    raw=root/"runs"/run_id/"raw"; session=requests.Session(); calls=[0]
    model=_load_json(Path("evidence/api_football/market_expansion/player_shots_lineup_role_v3/model.json"))
    history=_load_jsonl(Path("evidence/api_football/market_expansion/player_shots_lineup_role_v3/all_role_appearances_history.jsonl"))
    alpha=float(model["selected_parameters"]["alpha_recent_rate"])
    freeze_path=root/"freeze_ledger.jsonl"; cal_path=root/"calibration_ledger.jsonl"
    freezes=_load_jsonl(freeze_path); frozen_keys={(str(r["fixture_id"]),str(r["player_id"]),float(r["market_line"])) for r in freezes}
    events=_future_events(now,4*60,20)
    new_freezes=[]; blockers=[]
    for e in events:
        if len(new_freezes)>=MAX_NEW_FREEZES_PER_RUN: break
        fid=str(e["provider_fixture_id"]); kickoff=_utc(e["event_start_utc"])
        lineup_payload=_api(session,key,"/fixtures/lineups",{"fixture":fid},raw,f"fixture_{fid}_lineups",calls)
        parsed=_extract_lineups(lineup_payload)
        lineup_players=[p for t in parsed["teams"] for p in t["players"]]
        if not lineup_players:
            blockers.append({"fixture_id":fid,"reason":"PREMATCH_LINEUP_NOT_AVAILABLE"}); continue
        odds_payload=_api(session,key,"/odds",{"fixture":fid},raw,f"fixture_{fid}_odds",calls)
        hits=_extract_odds(odds_payload)
        offers,parse_blockers=_parse_offers(hits,lineup_players)
        for b in parse_blockers[:20]: blockers.append({"fixture_id":fid,**b})
        for o in offers:
            k=(fid,o["player_id"],float(o["line"]))
            if k in frozen_keys: continue
            feat=_features(history,o["player_id"],o["role"],kickoff)
            if feat is None:
                blockers.append({"fixture_id":fid,"player_id":o["player_id"],"player_name":o["player_name"],"reason":"INSUFFICIENT_PLAYER_PIT_HISTORY"}); continue
            p,refp,mu=_prob(feat,alpha,float(o["line"]))
            row={
              "schema":"MATRIX_PLAYER_SHOTS_V3_FREEZE_V1","fixture_id":fid,"kickoff_utc":e["event_start_utc"],"freeze_at_utc":now.isoformat(),
              "player_id":o["player_id"],"player_name":o["player_name"],"lineup_role":o["role"],"market_line":float(o["line"]),
              "bet_id":o["bet_id"],"bet_name":o["bet_name"],"bookmaker_name":o["bookmaker_name"],
              "over_odds_observed":o["over_odds"],"under_odds_observed":o["under_odds"],"overround_observed":o["overround"],
              "features":feat,"frozen_probability_over":p,"frozen_reference_probability_over":refp,"frozen_expected_shots":mu,
              "model_selected_parameters_sha256":model["selected_parameters_sha256"],"odds_used_to_generate_probability":False,
              "outcome":None,"automatic_wagering":False,"real_money":"BLOCKED"
            }
            row["record_sha256"]=_sha(row); _append(freeze_path,row); frozen_keys.add(k); new_freezes.append({"fixture_id":fid,"player_id":o["player_id"],"line":o["line"]})
            if len(new_freezes)>=MAX_NEW_FREEZES_PER_RUN: break
    # FINAL-only settlement.
    cal=_load_jsonl(cal_path); done={(str(r["fixture_id"]),str(r["player_id"]),float(r["market_line"])) for r in cal}
    new_settlements=[]
    for fr in _load_jsonl(freeze_path):
        k=(str(fr["fixture_id"]),str(fr["player_id"]),float(fr["market_line"]))
        if k in done or _utc(fr["kickoff_utc"])+timedelta(minutes=90)>now: continue
        detail=_api(session,key,"/fixtures",{"id":fr["fixture_id"]},raw,f"settle_{fr['fixture_id']}_detail",calls)
        if _fixture_status(detail)!="FT": continue
        pp=_api(session,key,"/fixtures/players",{"fixture":fr["fixture_id"]},raw,f"settle_{fr['fixture_id']}_players",calls)
        target=_actual_shots(pp,str(fr["player_id"]))
        if target is None: continue
        row={
          "schema":"MATRIX_PLAYER_SHOTS_V3_CALIBRATION_V1","fixture_id":fr["fixture_id"],"kickoff_utc":fr["kickoff_utc"],"freeze_at_utc":fr["freeze_at_utc"],
          "settled_at_utc":now.isoformat(),"player_id":fr["player_id"],"player_name":fr["player_name"],"market_line":fr["market_line"],
          "target_shots":target,"outcome_over":bool(target>float(fr["market_line"])),"frozen_probability_over":fr["frozen_probability_over"],
          "frozen_reference_probability_over":fr["frozen_reference_probability_over"],"model_selected_parameters_sha256":fr["model_selected_parameters_sha256"],
          "parameter_tuning_used":False,"automatic_wagering":False,"real_money":"BLOCKED"
        }
        row["record_sha256"]=_sha(row); _append(cal_path,row); done.add(k); new_settlements.append({"fixture_id":fr["fixture_id"],"player_id":fr["player_id"]})
    cal=_load_jsonl(cal_path); gates={}
    for g in GATES:
        if len(cal)<g: gates[str(g)]={"threshold":g,"status":"SEALED","observations_available":len(cal),"remaining":g-len(cal),"metrics_opened":False}
        else: gates[str(g)]={"threshold":g,"status":"OPENED_AT_THRESHOLD","observations_available":len(cal),"observations_used":g,"remaining":0,"metrics_opened":True,"metrics":_gate(cal[:g])}
    state={
      "schema":"MATRIX_PLAYER_SHOTS_V3_PROSPECTIVE_STATE_V1","status":"ACTIVE","prospective_lane_ready":True,
      "model_status":model["status"],"model_selected_parameters_sha256":model["selected_parameters_sha256"],
      "historical_role_source":"/fixtures/lineups","prospective_role_source":"/fixtures/lineups",
      "market_bindings":BET_IDS,"freeze_observation_count":len(_load_jsonl(freeze_path)),"calibration_observation_count":len(cal),
      "gates":gates,"parameter_tuning_allowed":False,"automatic_wagering":False,"real_money":"BLOCKED"
    }
    (root/"state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    result={
      "schema":"MATRIX_PLAYER_SHOTS_V3_SUPERVISOR_RUN_V1","run_id":run_id,"observed_at_utc":now.isoformat(),
      "future_events_checked":len(events),"network_calls":calls[0],"new_freezes":new_freezes,"new_settlements":new_settlements,
      "blockers":blockers,"market_bindings":BET_IDS,"odds_used_to_generate_probability":False,
      "automatic_wagering":False,"real_money":"BLOCKED","status":"PASS"
    }
    run_dir=root/"runs"/run_id; run_dir.mkdir(parents=True,exist_ok=True)
    (run_dir/"manifest.json").write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    (root/"last_run.json").write_text(json.dumps({**result,"manifest_path":str(run_dir/"manifest.json")},indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","network_calls":calls[0],"future_events_checked":len(events),"new_freezes":len(new_freezes),"new_settlements":len(new_settlements),"blockers":len(blockers),"real_money":"BLOCKED"},sort_keys=True))
    return result

if __name__=="__main__":
    run(os.environ.get("API_FOOTBALL_KEY",""),Path("evidence/api_football/player_shots_v3_prospective"))
