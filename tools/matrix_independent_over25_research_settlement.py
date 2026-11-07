"""Settle immutable free-provider research forecasts only from post-kickoff results.

No historical prediction is created here. Once a forecast is sealed, a distinct
provider response is captured after match completion and persisted under a
content-addressed name. Prediction sources/parameters are never modified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from tools.matrix_independent_over25_prematch_freeze import canonical,digest,stamp,SCHEMA

ROOT=Path("evidence/football_research_freezes")
REPORT=Path("evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_SETTLEMENT_LAST.json")
MAX_RESPONSE=1_000_000
MAX_CALLS=6

def _read_json(path:Path):
    if path.stat().st_size>24_000_000:
        raise ValueError("FORECAST_OR_SOURCE_OVERSIZED")
    return json.loads(path.read_text(encoding="utf-8-sig"))

def settle(root:Path,*,now:datetime,token:str,opener=urlopen,
           max_calls:int=MAX_CALLS)->dict:
    now=now.astimezone(timezone.utc)
    if not 0<=max_calls<=MAX_CALLS:
        raise ValueError("INVALID_MAX_CALLS")
    docs=[p for p in (root/ROOT).glob("20??-??-??/[0-9]*_*.json")
          if "_result_" not in p.name]
    def chronological_first(path):
        # Multiple legitimate intraday shadow updates may exist. The
        # earliest sealed forecast wins before any result is observed.
        try:
            start=stamp(_read_json(path)["sealed_at_utc"])
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            start=datetime.min.replace(tzinfo=timezone.utc)
        return (path.name.split("_",1)[0],start,path.as_posix())
    docs.sort(key=chronological_first)
    cases=[];calls=0;finished=0;seen=set()
    for path in docs:
        fid=path.name.split("_",1)[0]
        if not fid.isdecimal() or fid in seen:
            # A later prediction is preserved as a secondary snapshot, but
            # cannot inflate sample size or supersede the first preregistration.
            cases.append({"fixture_id":fid,"status":
                "SECONDARY_FROZEN_SNAPSHOT_EXCLUDED_FROM_PRIMARY_EVALUATION"})
            continue
        seen.add(fid)
        try:
            saved=path.read_bytes()
            forecast=json.loads(saved)
            if (forecast.get("schema")!=SCHEMA or
                forecast.get("provider")!="FOOTBALL_DATA_ORG" or
                forecast.get("telegram_signal_authorized") is not False or
                forecast.get("real_money")!="BLOCKED"):
                raise ValueError("UNTRUSTED_OR_PROMOTED_FORECAST")
            kickoff=stamp(forecast["kickoff_utc"])
            frozen=stamp(forecast["sealed_at_utc"])
            if frozen>=kickoff:raise ValueError("FORECAST_NOT_PREMATCH")
            prob=forecast["research_probability_over25"]
            if (type(prob) not in (int,float) or not math.isfinite(prob) or
                not 0<prob<1):raise ValueError("FORECAST_PROBABILITY_INVALID")
            # Resolve content-addressed sources from the physical forecast
            # directory, NEVER from archived runner-local absolute paths.
            # Older Windows snapshots included C:\\... host paths; those
            # remain auditable via SHA even on Linux without trusting paths.
            original_sources={}
            for key in ("intake","shadow"):
                expected=forecast[f"source_{key}_file_sha256"]
                if (not isinstance(expected,str) or len(expected)!=64
                    or any(c not in "0123456789abcdef" for c in expected)):
                    raise ValueError("SOURCE_HASH_NOT_SHA256")
                original=path.parent/"sources"/(expected+".json")
                if not original.is_file() or digest(original.read_bytes())!=expected:
                    raise ValueError("SOURCE_HASH_MISMATCH")
                original_sources[key]=original
            # Source-native home/away IDs are verified against the immutable
            # original intake, not inferred from current team names.
            immutable_intake=_read_json(original_sources["intake"])
            targets=[f for f in immutable_intake.get("fixtures",[])
                     if isinstance(f,dict) and str(f.get("source_fixture_id"))==fid]
            if len(targets)!=1:
                raise ValueError("IMMUTABLE_INTAKE_FIXTURE_IDENTITY_MISSING_OR_AMBIGUOUS")
            original_target=targets[0]
            if (stamp(original_target["kickoff_utc"])!=kickoff or
                str(original_target["source_competition_id"])!=
                str(forecast["provider_competition_id"])):
                raise ValueError("IMMUTABLE_INTAKE_IDENTITY_MISMATCH")
            base=(root/ROOT)/path.parent.name
            outcomes=list(base.glob(f"{fid}_result_*.json"))
            if outcomes:
                if len(outcomes)>1:raise ValueError("MULTIPLE_FINAL_RESULT_FILES")
                done=_read_json(outcomes[0])
                if (done.get("fixture_id")!=fid or done.get("forecast_sha256")!=digest(saved) or
                    done.get("raw_result_sha256") is None or
                    done.get("result_observed_at_utc") is None):
                    raise ValueError("EXISTING_SETTLEMENT_INTEGRITY_FAILURE")
                rawpath=base/"sources"/f"{done['raw_result_sha256']}.json"
                if digest(rawpath.read_bytes())!=done["raw_result_sha256"]:
                    raise ValueError("EXISTING_RESULT_SOURCE_HASH_MISMATCH")
                cases.append({"fixture_id":fid,"status":"ALREADY_SETTLED",
                              "forecast_sha256":digest(saved),"result_path":outcomes[0].relative_to(root).as_posix()})
                finished+=1
                continue
            if now<=kickoff:
                cases.append({"fixture_id":fid,"status":"AWAITING_KICKOFF"})
                continue
            # A buffer prevents a premature result read and gives provider
            # time to settle. FINISHED + final full-time goals is mandatory.
            if now<kickoff+timedelta(minutes=95):
                cases.append({"fixture_id":fid,"status":"AWAITING_FINAL_SCORE_WINDOW"})
                continue
            if not token:
                cases.append({"fixture_id":fid,"status":"PROVIDER_TOKEN_NOT_AVAILABLE"})
                continue
            if calls>=max_calls:
                cases.append({"fixture_id":fid,"status":"RATE_BUDGET_EXHAUSTED"})
                continue
            request=Request("https://api.football-data.org/v4/matches/"+fid,
                  headers={"X-Auth-Token":token,"Accept":"application/json"})
            calls+=1
            try:
                with opener(request,timeout=25) as response:
                    http=int(response.status)
                    raw=response.read(MAX_RESPONSE+1)
            except (HTTPError,URLError,TimeoutError,OSError) as exc:
                cases.append({"fixture_id":fid,"status":"PROVIDER_READ_BLOCKED",
                              "error_type":type(exc).__name__})
                continue
            if http!=200 or len(raw)>MAX_RESPONSE:
                cases.append({"fixture_id":fid,"status":"PROVIDER_HTTP_OR_SIZE_BLOCK"})
                continue
            source=json.loads(raw.decode("utf-8"))
            score=(source.get("score") or {}).get("fullTime") or {}
            home,away=score.get("home"),score.get("away")
            identity=(str(source.get("id"))==fid and
                str((source.get("competition") or {}).get("id"))==
                str(forecast.get("provider_competition_id")) and
                str((source.get("homeTeam") or {}).get("id"))==
                str(original_target["home_source_team_id"]) and
                str((source.get("awayTeam") or {}).get("id"))==
                str(original_target["away_source_team_id"]))
            try:identity=identity and stamp(source.get("utcDate"))==kickoff
            except (ValueError,TypeError):identity=False
            if (not identity or source.get("status")!="FINISHED" or
                type(home)!=int or type(away)!=int or home<0 or away<0):
                cases.append({"fixture_id":fid,"status":"RESULT_NOT_FINAL_OR_IDENTITY_MISMATCH"})
                continue
            if source.get("lastUpdated"):
                try:
                    if stamp(source["lastUpdated"])>now:
                        raise ValueError("PROVIDER_RESULT_UPDATED_IN_FUTURE")
                except (ValueError,TypeError):
                    cases.append({"fixture_id":fid,"status":"INVALID_RESULT_PROVIDER_UPDATE"})
                    continue
            y=int(home+away>2)
            doc={"schema":"MATRIX_INDEPENDENT_OVER25_SETTLED_RESEARCH_V1",
                 "fixture_id":fid,"provider":"FOOTBALL_DATA_ORG",
                 "competition_id":str(forecast["provider_competition_id"]),
                 "kickoff_utc":kickoff.isoformat(),"forecast_frozen_at_utc":frozen.isoformat(),
                 "forecast_sha256":digest(saved),"research_probability_over25":prob,
                 "result_observed_at_utc":now.isoformat(),
                 "raw_result_sha256":digest(raw),
                 "home_goals":home,"away_goals":away,"over25_outcome":y,
                 "brier_loss":round((prob-y)**2,12),
                 "model_equivalence_certified":False,
                 "telegram_signal_authorized":False,"automatic_wagering":False,
                 "real_money":"BLOCKED"}
            source_dir=base/"sources"
            source_dir.mkdir(parents=True,exist_ok=True)
            rawpath=source_dir/(digest(raw)+".json")
            if rawpath.exists():
                if rawpath.read_bytes()!=raw:raise ValueError("SOURCE_MUTATION_BLOCKED")
            else:
                with rawpath.open("xb") as f:f.write(raw)
            artifact=base/f"{fid}_result_{digest(raw)[:20]}.json"
            with artifact.open("xb") as f:f.write(canonical(doc))
            cases.append({"fixture_id":fid,"status":"SETTLED_RESEARCH_ONLY",
                          "forecast_sha256":digest(saved),
                          "result_path":artifact.relative_to(root).as_posix()})
            finished+=1
        except (ValueError,TypeError,KeyError,OSError,UnicodeError,
                json.JSONDecodeError) as exc:
            cases.append({"fixture_id":fid,"status":"BLOCKED_INVALID_SOURCE",
                          "reason":str(exc)[:120]})
    # A cycle's newly settled count is NOT the cumulative out-of-sample
    # cohort. Recompute the latter only from SHA-backed archive documents.
    # The cumulative scorecard is independent of the current runner's
    # historical intake/shadow checkout, so source-integrity failures are
    # exposed separately rather than overwriting archived results.
    from tools.matrix_independent_over25_research_scorecard import evaluate
    archive=evaluate(root)
    new_count=sum(x["status"]=="SETTLED_RESEARCH_ONLY" for x in cases)
    prior_count=sum(x["status"]=="ALREADY_SETTLED" for x in cases)
    input_integrity_blocked=sum(x["status"]=="BLOCKED_INVALID_SOURCE" for x in cases)
    return {"schema":"MATRIX_INDEPENDENT_OVER25_SETTLEMENT_CYCLE_V1",
            "checked_at_utc":now.isoformat(),"scanned_forecasts":len(docs),
            "http_calls":calls,"settled_total":finished,
            "newly_settled_count":new_count,
            "already_settled_current_cycle_count":prior_count,
            "archived_sha_verified_research_result_count":archive["total_verified_settled_rows"],
            "archive_rejected_result_count":len(archive["rejected_settlements"]),
            "input_source_integrity_blocked_count":input_integrity_blocked,
            "archived_result_does_not_certify_original_input_parity":True,
            "unique_fixture_count":len(seen),
            "secondary_forecast_count":sum(x["status"]==
                "SECONDARY_FROZEN_SNAPSHOT_EXCLUDED_FROM_PRIMARY_EVALUATION"
                for x in cases),
            "selection_rule":"FIRST_AUTHENTIC_SEALED_FORECAST_WINS",
            "decisions":cases,
            "original_calibrated_parameters_mutated":False,
            "scientific_six_league_oos_certified":False,
            "telegram_signal_authorized":False,"automatic_wagering":False,
            "real_money":"BLOCKED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("--out",type=Path,default=REPORT)
    args=parser.parse_args()
    if any(k in args.out.parts for k in ("telegram","governance","daily_prematch_reports","tennis_signals")):
        raise SystemExit("RESEARCH_SETTLEMENT_CANNOT_WRITE_PRODUCTION")
    output=settle(args.root,now=datetime.now(timezone.utc),
                  token=os.getenv("FOOTBALL_DATA_ORG_TOKEN",""))
    path=args.out if args.out.is_absolute() else args.root/args.out
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(output))
    print(json.dumps({"scanned_forecasts":output["scanned_forecasts"],
        "http_calls":output["http_calls"],"settled_total":output["settled_total"],
        "newly_settled_count":output["newly_settled_count"],
        "archived_sha_verified_research_result_count":output["archived_sha_verified_research_result_count"],
        "input_source_integrity_blocked_count":output["input_source_integrity_blocked_count"],
        "status_counts":{s:sum(x["status"]==s for x in output["decisions"]) for s in
                          sorted({v["status"] for v in output["decisions"]})},
        "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":main()
