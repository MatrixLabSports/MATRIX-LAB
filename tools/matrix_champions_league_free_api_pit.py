"""UEFA Champions League (football-data.org CL/2001) isolated authentic PIT audit.

One bounded provider history call only if authenticated fixture intake contains CL.
Never turns CL-only histories into cross-league feature equivalence or p_matrix.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

COMPETITION_ID=2001
URL="https://api.football-data.org/v4/competitions/CL/matches"
MAX_BYTES=3_000_000

def aware(s):
    v=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return v.astimezone(timezone.utc)

def inspect(intake, token, *, opener=urlopen, now=None):
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1" or
        intake.get("source")!="FOOTBALL_DATA_ORG" or
        intake.get("signal_generation_authorized") is not False or
        intake.get("real_money")!="BLOCKED"):
        raise ValueError("CHAMPIONS_UNTRUSTED_INTAKE")
    clock=now or datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("NAIVE_NOW")
    clock=clock.astimezone(timezone.utc)
    fixtures=[f for f in intake.get("fixtures",[]) if isinstance(f,dict)
              and f.get("source_competition_id")==COMPETITION_ID
              and f.get("source_competition_code")=="CL"]
    result={
      "schema":"MATRIX_CHAMPIONS_LEAGUE_FREE_API_PIT_AUDIT_V1",
      "target_date_bogota":intake["target_date_bogota"],
      "checked_at_utc":clock.isoformat(),
      "competition":"UEFA_CHAMPIONS_LEAGUE",
      "provider":"FOOTBALL_DATA_ORG",
      "provider_competition_id":COMPETITION_ID,
      "provider_competition_code":"CL",
      "source_order":["SOFASCORE","FLASHSCORE","APIS"],
      "status":"NO_CHAMPIONS_FIXTURE_IN_AUTHENTICATED_CALENDAR",
      "fixture_count":len(fixtures),
      "history_network_calls":0,
      "history_sha256":None,
      "provider_history_finished_pit_rows":0,
      "fixture_checks":[],
      "same_competition_history_is_not_cross_league_feature_parity":True,
      "original_six_leagues_scope_unchanged":True,
      "calibrated_parameters_mutated":False,
      "research_probability_authorized":False,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED",
    }
    if not fixtures: return result,None
    for f in fixtures:
        if (not str(f.get("source_fixture_id","")).isdigit()
            or str(f.get("home_source_team_id",""))==""
            or str(f.get("away_source_team_id",""))==""
            or aware(f["kickoff_utc"])<=clock):
            raise ValueError("CHAMPIONS_FIXTURE_NOT_PROSPECTIVE")
    if not token.strip():
        result["status"]="MISSING_FOOTBALL_DATA_ORG_TOKEN"
        return result,None
    req=Request(URL,headers={"X-Auth-Token":token,"Accept":"application/json"})
    result["history_network_calls"]=1
    try:
        with opener(req,timeout=25) as response:
            status=response.status
            raw=response.read(MAX_BYTES+1)
        if status!=200 or len(raw)>MAX_BYTES:
            result["status"]="BLOCKED_HTTP_OR_OVERSIZED_SOURCE"
            return result,None
        payload=json.loads(raw)
        if (not isinstance(payload,dict) or
            not isinstance(payload.get("matches"),list)):
            result["status"]="BLOCKED_INVALID_HISTORY_RESPONSE"
            return result,None
        rows=[];seen=set()
        for m in payload["matches"]:
            if not isinstance(m,dict) or m.get("status")!="FINISHED":continue
            comp=m.get("competition") or payload.get("competition") or {}
            if str(comp.get("id"))!=str(COMPETITION_ID):
                result["status"]="BLOCKED_HISTORY_COMPETITION_IDENTITY_MISMATCH"
                return result,None
            try:
                mid=str(int(m["id"]))
                start=aware(m["utcDate"]);updated=aware(m["lastUpdated"])
                h=str(int(m["homeTeam"]["id"]));a=str(int(m["awayTeam"]["id"]))
                hg=m["score"]["fullTime"]["home"];ag=m["score"]["fullTime"]["away"]
                if type(hg)!=int or type(ag)!=int or hg<0 or ag<0:continue
            except (ValueError,TypeError,KeyError,OverflowError):
                continue
            if mid in seen:
                result["status"]="BLOCKED_DUPLICATE_HISTORY_ID"
                return result,None
            seen.add(mid)
            if not (start<updated<=clock):continue
            rows.append({"fixture_id":mid,"start":start,"updated":updated,"home":h,"away":a})
        result["history_sha256"]=hashlib.sha256(raw).hexdigest()
        result["provider_history_finished_pit_rows"]=len(rows)
        for f in fixtures:
            kickoff=aware(f["kickoff_utc"])
            as_of=[m for m in rows if m["start"]<kickoff and m["updated"]<=clock]
            home_id=str(f["home_source_team_id"]);away_id=str(f["away_source_team_id"])
            home=sum(home_id in (m["home"],m["away"]) for m in as_of)
            away=sum(away_id in (m["home"],m["away"]) for m in as_of)
            result["fixture_checks"].append({
              "provider_fixture_id":str(f["source_fixture_id"]),
              "kickoff_utc":kickoff.isoformat(),
              "prior_champions_only_home_rows":home,
              "prior_champions_only_away_rows":away,
              "original_model_enriched_input_complete":False,
              "reason":"CROSS_LEAGUE_HISTORY_FEATURE_PARITY_NOT_CERTIFIED",
              "telegram_signal_authorized":False})
        result["status"]="AUTHENTICATED_CHAMPIONS_HISTORY_RESEARCH_ONLY"
        return result,raw
    except HTTPError as err:
        result["http_status"]=err.code
        result["status"]="PROVIDER_HTTP_ERROR"
    except (URLError,TimeoutError,OSError,ValueError,TypeError):
        result["status"]="HISTORY_CAPTURE_FAILED"
    return result,None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--intake",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--raw-out",required=True,type=Path)
    args=p.parse_args()
    row,raw=inspect(json.loads(args.intake.read_bytes()),os.getenv("FOOTBALL_DATA_ORG_TOKEN",""))
    if raw is not None:
        if args.raw_out.parent!=args.out.parent/"sources":
            raise SystemExit("CHAMPIONS_RAW_PATH_MUST_BE_IN_DATE_SOURCES")
        args.raw_out.parent.mkdir(parents=True,exist_ok=True)
        args.raw_out.write_bytes(raw)
        if hashlib.sha256(args.raw_out.read_bytes()).hexdigest()!=row["history_sha256"]:
            raise SystemExit("CHAMPIONS_SOURCE_SHA_MISMATCH")
        row["history_raw_source_path"]=args.raw_out.as_posix()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(row,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":row["status"],"fixtures":row["fixture_count"],
       "history_pit_rows":row["provider_history_finished_pit_rows"],
       "network_calls":row["history_network_calls"],"signal":False}))
if __name__=="__main__":main()
