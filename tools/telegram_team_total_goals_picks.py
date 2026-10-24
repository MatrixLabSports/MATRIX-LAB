from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import requests

from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS
from tools.api_football_period_goals_lab import _load_group, _team_period_view
from tools.matrix_42_lane_period_goals_freeze_bridge import _predictions

BOGOTA=ZoneInfo("America/Bogota")
SOURCE_FREEZE=Path("evidence/api_football/prospective_market_freeze/freeze.json")
PROSPECTIVE_DAILY_ROOT=Path("evidence/api_football/prospective_daily")
LEDGER=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_LEDGER.json")
AUDIT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_LAST.json")
ODDS_BASE="https://api.odds-api.net/v1"
MIN_P=0.60
MIN_EV=0.05
MIN_ODDS=1.50
QUOTE_WINDOW_MINUTES=120
QUOTE_MAX_AGE_SECONDS=1800
MAX_HISTORY=20
MIN_HISTORY=5
LINES=(0.5,1.5,2.5)
BOOKS=set(EXECUTION_BOOKMAKERS)


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _utc(value:object)->datetime:
    token=str(value or "").strip()
    if not token:
        raise ValueError("TIMESTAMP_MISSING")
    dt=datetime.fromisoformat(token.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def _sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _norm(value:Any)->str:
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+"," ",text).strip()


def _sim(a:Any,b:Any)->float:
    x,y=_norm(a),_norm(b)
    if not x or not y:
        return 0.0
    if x==y:
        return 1.0
    tx,ty=set(x.split()),set(y.split())
    jac=len(tx&ty)/max(1,len(tx|ty))
    return max(jac,SequenceMatcher(None,x,y).ratio())


def _latest_fixture_registry(root:Path,now_utc:datetime)->Path:
    candidates=[]
    for path in root.glob("*/*/fixtures/future_fixture_registry.json"):
        try:
            data=_load(path)
            captured=_utc(data.get("captured_at_utc"))
            future=sum(1 for row in data.get("events") or [] if isinstance(row,Mapping) and _utc(row.get("event_start_utc"))>now_utc)
            if future>0:
                candidates.append((captured,path,future))
        except Exception:
            continue
    if not candidates:
        raise FileNotFoundError("NO_FUTURE_FIXTURE_REGISTRY_AVAILABLE")
    candidates.sort(key=lambda x:(x[0],x[1].as_posix()),reverse=True)
    return candidates[0][1]


def _fixture_map(registry:Mapping[str,Any])->dict[str,dict[str,Any]]:
    out={}
    for row in registry.get("events") or []:
        if not isinstance(row,Mapping):
            continue
        fid=str(row.get("provider_fixture_id") or "")
        if fid:
            out[fid]=dict(row)
    return out


def _fulltime_team_view(row:Mapping[str,Any],team_id:str)->tuple[int,int]:
    f_for,f_against=_team_period_view(row,team_id,"first_half")
    s_for,s_against=_team_period_view(row,team_id,"second_half")
    return f_for+s_for,f_against+s_against


def _record(values:list[int],side:str,line:float)->tuple[int,int]:
    if side=="under":
        wins=sum(1 for v in values if v < line)
    else:
        wins=sum(1 for v in values if v > line)
    return wins,len(values)


def _confidence(p:float)->str:
    return "ALTA" if p>=0.70 else "MEDIA"


def build_candidates(
    source:Mapping[str,Any],
    registry:Mapping[str,Any],
    *,
    repo_root:Path,
    now_utc:datetime,
)->tuple[list[dict[str,Any]],dict[str,Any]]:
    fixtures=_fixture_map(registry)
    cache:dict[str,tuple[list[dict[str,Any]],str]]={}
    candidates=[]; blockers=[]
    for src in source.get("rows") or []:
        if not isinstance(src,Mapping):
            continue
        fid=str(src.get("fixture_id") or "")
        ident=fixtures.get(fid)
        if not ident:
            continue
        try:
            start=_utc(src.get("kickoff_utc")); freeze=_utc(src.get("freeze_at_utc"))
        except ValueError:
            continue
        if start<=now_utc or freeze>=start or src.get("outcome") is not None:
            continue
        rel=str(src.get("historical_baseline_source") or "")
        path=repo_root/rel
        if not rel or not path.exists():
            blockers.append({"fixture_id":fid,"reason":"HISTORY_SOURCE_MISSING"})
            continue
        key=path.as_posix()
        if key not in cache:
            try: cache[key]=_load_group(path)
            except Exception:
                blockers.append({"fixture_id":fid,"reason":"HISTORY_LOAD_FAILED"}); continue
        group,digest=cache[key]
        prior=[r for r in group if r["kickoff_utc"]<freeze]
        hid=str(src.get("home_team_id") or ""); aid=str(src.get("away_team_id") or "")
        by_team=defaultdict(list)
        for r in prior:
            by_team[r["home_team_id"]].append(r); by_team[r["away_team_id"]].append(r)
        hh=by_team.get(hid,[])[-MAX_HISTORY:]; ah=by_team.get(aid,[])[-MAX_HISTORY:]
        if len(hh)<MIN_HISTORY or len(ah)<MIN_HISTORY:
            blockers.append({"fixture_id":fid,"reason":"INSUFFICIENT_STRICTLY_PRIOR_HISTORY"})
            continue
        hvals=[_fulltime_team_view(r,hid)[0] for r in hh]
        havg=[_fulltime_team_view(r,hid)[1] for r in hh]
        avals=[_fulltime_team_view(r,aid)[0] for r in ah]
        aavg=[_fulltime_team_view(r,aid)[1] for r in ah]
        home_lambda=max(0.01,min(6.0,(sum(hvals)/len(hvals)+sum(aavg)/len(aavg))/2.0))
        away_lambda=max(0.01,min(6.0,(sum(avals)/len(avals)+sum(havg)/len(havg))/2.0))
        preds=_predictions(home_lambda/2,away_lambda/2,home_lambda/2,away_lambda/2)
        for lane,team_name,team_vals,opp_allowed,team_lambda in (
            ("TEAM_TOTAL_GOALS_HOME",ident.get("home_team"),hvals,aavg,home_lambda),
            ("TEAM_TOTAL_GOALS_AWAY",ident.get("away_team"),avals,havg,away_lambda),
        ):
            pred=preds[lane]
            choices=[]
            for line in LINES:
                for side in ("under","over"):
                    p=float(pred[f"{side}_{str(line).replace('.','_')}"])
                    if p>=MIN_P:
                        w,n=_record(team_vals,side,line)
                        choices.append((p,w/n if n else 0.0,line,side,w,n))
            if not choices:
                continue
            choices.sort(reverse=True)
            p,rate,line,side,w,n=choices[0]
            candidates.append({
                "candidate_key":_sha({"fixture_id":fid,"lane":lane,"line":line,"side":side,"freeze":freeze.isoformat()}),
                "fixture_id":fid,
                "event_start_utc":start.isoformat(),
                "freeze_timestamp_utc":freeze.isoformat(),
                "competition":ident.get("competition"),
                "country":ident.get("country"),
                "home_team":ident.get("home_team"),
                "away_team":ident.get("away_team"),
                "team_name":team_name,
                "market_lane":lane,
                "selection_side":side,
                "line":line,
                "p_matrix":round(p,10),
                "confidence":_confidence(p),
                "team_recent_goals_average":round(sum(team_vals)/len(team_vals),3),
                "opponent_recent_allowed_average":round(sum(opp_allowed)/len(opp_allowed),3),
                "market_record":{"wins":w,"sample":n,"rate":round(rate,6)},
                "history_source":rel,
                "history_source_sha256":digest,
                "model_basis":"PERIOD_TEAM_POISSON_PIT_V1_TEAM_TOTAL_GOALS",
                "team_goal_lambda":round(team_lambda,8),
                "odds_used_to_generate_probability":False,
                "target_outcome":None,
                "automatic_wagering":False,
                "real_money":"BLOCKED",
            })
    candidates.sort(key=lambda x:(x["event_start_utc"],-x["p_matrix"],x["fixture_id"],x["market_lane"]))
    audit={
        "schema":"MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_CANDIDATES_V1",
        "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
        "candidate_count":len(candidates),
        "unique_fixtures":len({x["fixture_id"] for x in candidates}),
        "blocker_count":len(blockers),
        "blockers":blockers[:100],
        "rules":{
            "confidence_high_min_p":0.70,
            "confidence_medium_min_p":0.60,
            "minimum_history":MIN_HISTORY,
            "maximum_history":MAX_HISTORY,
            "lines":list(LINES),
            "record_is_informational_not_probability":True,
        },
        "protections":{
            "strictly_prior_history_only":True,
            "outcomes_read_for_future_event":0,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }
    return candidates,audit


def _parse_line(item:Mapping[str,Any])->float|None:
    try:return float(item.get("line"))
    except Exception:
        text=" ".join(str(item.get(k) or "") for k in ("line","selection_name","selection_key"))
        m=re.search(r"([0-9]+(?:\.[0-9]+)?)",text)
        return float(m.group(1)) if m else None


def find_quote(session:requests.Session,key:str,c:Mapping[str,Any],diagnostic:dict[str,Any])->dict[str,Any]|None:
    diagnostic.clear(); diagnostic["status"]="STARTED"; diagnostic["fixture_id"]=c["fixture_id"]
    start=_utc(c["event_start_utc"])
    now=datetime.now(timezone.utc)
    mins=(start-now).total_seconds()/60.0
    diagnostic["minutes_to_kickoff"]=round(mins,2)
    if mins<=0:
        diagnostic["status"]="BLOCKED_STARTED"; return None
    if mins>QUOTE_WINDOW_MINUTES:
        diagnostic["status"]="WAIT_OUTSIDE_120M_QUOTE_WINDOW"; return None
    if not key:
        diagnostic["status"]="BLOCKED_ODDS_API_KEY_MISSING"; return None
    er=session.get(ODDS_BASE+"/events",headers={"X-API-Key":key,"Accept":"application/json"},params={
        "sport":"soccer","start_from":int(start.timestamp())-7200,"start_to":int(start.timestamp())+7200,
        "limit":100,"include_bookmaker_ids":"true"},timeout=20)
    try: ep=er.json()
    except Exception: ep={}
    events=ep.get("items",[]) if isinstance(ep,Mapping) else []
    scored=[]
    for e in events:
        if not isinstance(e,Mapping): continue
        direct=(_sim(c["home_team"],e.get("home_team"))+_sim(c["away_team"],e.get("away_team")))/2
        swap=(_sim(c["home_team"],e.get("away_team"))+_sim(c["away_team"],e.get("home_team")))/2
        scored.append((max(direct,swap),e))
    scored.sort(key=lambda x:x[0],reverse=True)
    if not scored or scored[0][0]<0.85:
        diagnostic["status"]="BLOCKED_EVENT_IDENTITY"; return None
    event_id=str(scored[0][1].get("event_id") or "")
    if not event_id:
        diagnostic["status"]="BLOCKED_EVENT_ID_MISSING"; return None
    sr=session.get(ODDS_BASE+f"/events/{event_id}/odds/snapshot",headers={"X-API-Key":key,"Accept":"application/json"},params={
        "bookmakers":",".join(sorted(BOOKS)),"types":"total","periods":"full time","include_source":"true","include_unavailable":"true"},timeout=20)
    try: sp=sr.json()
    except Exception: sp={}
    book_ts=sp.get("bookmaker_as_of_ts_ms") or {} if isinstance(sp,Mapping) else {}
    offers=[]
    for item in sp.get("items",[]) if isinstance(sp,Mapping) else []:
        if not isinstance(item,Mapping): continue
        house=str(item.get("bookmaker") or "").casefold()
        if house not in BOOKS or item.get("is_available") is False: continue
        line=_parse_line(item)
        try: dec=float(item.get("odds"))
        except Exception: continue
        if line!=float(c["line"]) or dec<=MIN_ODDS: continue
        text=" ".join(_norm(item.get(k)) for k in ("market_key","bet_type","selection_name","selection_key","side","metric"))
        if "total" not in text: continue
        if _norm(c["team_name"]).split()[0] not in text and "team total" not in text and "home total" not in text and "away total" not in text:
            continue
        side=str(c["selection_side"])
        if side not in text: continue
        ts=book_ts.get(house)
        age=None
        if isinstance(ts,(int,float)) and not isinstance(ts,bool):
            age=max(0,int((now-datetime.fromtimestamp(float(ts)/1000,tz=timezone.utc)).total_seconds()))
            if age>QUOTE_MAX_AGE_SECONDS: continue
        ev=float(c["p_matrix"])*dec-1.0
        if ev<MIN_EV: continue
        offers.append({"house_key":house,"house":house.title(),"odds":dec,"ev":ev,"quote_age_seconds":age,"provider":"odds-api.net","event_id":event_id})
    diagnostic["eligible_offer_count"]=len(offers)
    diagnostic["status"]="PASS_EXACT_TEAM_TOTAL_QUOTE" if offers else "BLOCKED_NO_EXACT_TEAM_TOTAL_QUOTE"
    return max(offers,key=lambda x:x["ev"]) if offers else None


def _message(c:Mapping[str,Any],q:Mapping[str,Any])->str:
    side="Menos de" if c["selection_side"]=="under" else "Más de"
    when=_utc(c["event_start_utc"]).astimezone(BOGOTA).strftime("%d/%m %I:%M %p")
    rec=c["market_record"]
    return (
        f"📊 PICKS NUEVOS MATRIX — SIMULADO\n\n"
        f"⭐ CONFIANZA {c['confidence']} ({float(c['p_matrix'])*100:.1f}%)\n"
        f"⚽ {c['home_team']} vs {c['away_team']}\n"
        f"{c['country']}: {c['competition']} | {when} (COL)\n"
        f"✅ {c['team_name']}: {side} {float(c['line']):.1f} goles\n"
        f"📊 Cuota física: {float(q['odds']):.2f}\n"
        f"💰 Casa: {q['house']}\n"
        f"🔎 {c['team_name']} marca {float(c['team_recent_goals_average']):.1f} por partido; "
        f"su rival recibe {float(c['opponent_recent_allowed_average']):.1f}\n"
        f"🧪 Historial reciente revisado | récord del mercado {rec['wins']}/{rec['sample']}\n"
        f"📈 EV revalidado: {float(q['ev'])*100:+.2f}%\n"
        f"💵 Stake de papel: 1u = COP 25.000\n"
        f"🔒 DINERO REAL MATRIX: BLOQUEADO"
    )


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(SOURCE_FREEZE))
    p.add_argument("--fixtures")
    p.add_argument("--ledger",default=str(LEDGER))
    p.add_argument("--audit",default=str(AUDIT))
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    fixture_path=Path(a.fixtures) if a.fixtures else _latest_fixture_registry(PROSPECTIVE_DAILY_ROOT,now)
    candidates,base=build_candidates(_load(Path(a.source)),_load(fixture_path),repo_root=Path("."),now_utc=now)
    base["fixture_registry_path"]=fixture_path.as_posix()
    ledger_path=Path(a.ledger)
    ledger=_load(ledger_path) if ledger_path.exists() else {"schema":"MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_LEDGER_V1","sent":[]}
    sent_keys={str(x.get("candidate_key") or "") for x in ledger.get("sent",[]) if isinstance(x,Mapping)}
    session=requests.Session(); odds_key=os.getenv("ODDS_API_NET_KEY","").strip()
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    diagnostics=[]; sent=[]; eligible=0
    for c in candidates:
        if c["candidate_key"] in sent_keys: continue
        diag={}; q=find_quote(session,odds_key,c,diag); diagnostics.append({**diag,"candidate_key":c["candidate_key"]})
        if q is None: continue
        eligible+=1
        msg=_message(c,q)
        message_id=None
        if not a.dry_run:
            if not token or not chat: raise SystemExit("TELEGRAM_CREDENTIALS_MISSING")
            resp=session.post(f"https://api.telegram.org/bot{token}/sendMessage",data={"chat_id":chat,"text":msg},timeout=(10,90))
            payload=resp.json()
            if resp.status_code>=300 or payload.get("ok") is not True:
                raise RuntimeError(f"TELEGRAM_SEND_FAILED:{resp.status_code}")
            message_id=int((payload.get("result") or {})["message_id"])
            row={**c,"quote":q,"telegram_message_id":message_id,"sent_at_utc":datetime.now(timezone.utc).isoformat(),"paper_stake_units":1.0,"paper_stake_cop":25000,"real_money":"BLOCKED"}
            ledger.setdefault("sent",[]).append(row); sent.append(row)
    ledger["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    ledger["automatic_wagering"]=False; ledger["real_money"]="BLOCKED"
    ledger_path.parent.mkdir(parents=True,exist_ok=True)
    ledger_path.write_text(json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    audit={
      **base,
      "schema":"MATRIX_TELEGRAM_TEAM_TOTAL_GOALS_PICKS_RUN_V1",
      "quote_window_minutes":QUOTE_WINDOW_MINUTES,
      "minimum_odds_strictly_greater_than":MIN_ODDS,
      "minimum_ev":MIN_EV,
      "eligible_quote_count":eligible,
      "sent_count":len(sent),
      "dry_run":bool(a.dry_run),
      "diagnostics":diagnostics[-200:],
      "protections":{**base["protections"],"physical_exact_quote_required":True,"ev_revalidation_required":True,"minimum_ev":MIN_EV,"minimum_odds":MIN_ODDS,"paper_stake_units":1.0},
      "status":"PASS",
    }
    Path(a.audit).parent.mkdir(parents=True,exist_ok=True)
    Path(a.audit).write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","candidate_count":len(candidates),"eligible_quote_count":eligible,"sent_count":len(sent),"dry_run":bool(a.dry_run),"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
