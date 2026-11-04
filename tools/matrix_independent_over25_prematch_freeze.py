"""Immutable independent football-data.org Over 2.5 research prediction freeze.

This acts on a live same-cycle independently captured intake+shadow, *only
before kickoff*. Never recreates a past forecast. Original calibrated log-pool
parameters are imported read-only; the alternative provider is not promoted.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from tools.matrix_football_independent_over25_shadow import historic_rows
from tools.api_football_market_shadow_p_matrix import _inputs_for_target, _pool_over25

SCHEMA="MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1"
ROOT=Path("evidence/football_research_freezes")
MAX_BODY=3_000_000

def stamp(value):
    try: dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (ValueError,TypeError) as exc: raise ValueError("INVALID_TIME") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)

def digest(data:bytes):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,
                       separators=(",",":"))+"\n").encode("utf-8")

def seal_source(folder:Path,raw:bytes)->Path:
    """Content-addressed immutable historical input, never overwritten."""
    if len(raw)>24_000_000:
        raise ValueError("AUTHENTIC_RAW_SOURCE_TOO_LARGE")
    target=folder/"sources"/(digest(raw)+".json")
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if target.read_bytes()!=raw:
            raise ValueError("SOURCE_SNAPSHOT_MUTATION_FORBIDDEN")
    else:
        with target.open("xb") as f:
            f.write(raw)
    return target

def freeze(intake:dict,shadow:dict,*,intake_bytes:bytes,shadow_bytes:bytes,
           now:datetime,folder:Path,allow_write=True)->dict:
    now=now.astimezone(timezone.utc)
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or intake.get("real_money")!="BLOCKED" or shadow.get("real_money")!="BLOCKED"
        or intake.get("signal_generation_authorized") is not False
        or shadow.get("market_signal_authorized") is not False
        or shadow.get("parameter_refit") is not False
        or intake.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("source")!="FOOTBALL_DATA_ORG"
        or intake.get("target_date_bogota")!=shadow.get("target_date_bogota")):
        raise ValueError("INDEPENDENT_FREEZE_GOVERNANCE_INVALID")
    intake_at=stamp(intake["generated_at_utc"])
    shadow_at=stamp(shadow["generated_at_utc"])
    if intake_at>shadow_at or shadow_at>now:
        raise ValueError("SHADOW_CAPTURE_ORDER_OR_FUTURE_INVALID")
    allowed={str(r["source_fixture_id"]):r for r in intake.get("fixtures",[])
             if isinstance(r,dict) and r.get("source_fixture_id")}
    groups=shadow.get("authenticated_raw_group_replay_evidence") or {}
    accepted=[];blocked=[]
    seen=set()
    for target in shadow.get("scored") or []:
        fid=str(target.get("source_fixture_id") or "")
        try:
            if not fid or fid in seen:raise ValueError("DUPLICATE_OR_EMPTY_TARGET")
            seen.add(fid)
            fixture=allowed.get(fid)
            if fixture is None:raise ValueError("TARGET_NOT_IN_ORIGINAL_PREMATCH_INTAKE")
            kickoff=stamp(fixture["kickoff_utc"])
            if target.get("kickoff_utc")!=fixture.get("kickoff_utc"):
                raise ValueError("TARGET_KICKOFF_MISMATCH")
            if not (intake_at<kickoff and shadow_at<kickoff and now<kickoff):
                raise ValueError("TARGET_ALREADY_STARTED_OR_FREEZE_TOO_LATE")
            if fixture.get("source_status") not in ("SCHEDULED","TIMED"):
                raise ValueError("TARGET_NOT_VERIFIED_FUTURE")
            cid=str(fixture["source_competition_id"])
            if cid!=str(target.get("competition_id")):
                raise ValueError("COMPETITION_ID_CONFLICT")
            g=groups.get(cid)
            if not isinstance(g,dict):raise ValueError("ORIGINAL_RAW_SOURCE_MISSING")
            raw=base64.b64decode(g["response_base64"],validate=True)
            if len(raw)>MAX_BODY or digest(raw)!=g.get("source_payload_sha256"):
                raise ValueError("SOURCE_BYTES_OR_HASH_INVALID")
            observed=stamp(g["observed_at_utc"])
            if not (intake_at<=observed<=shadow_at<=now<kickoff):
                raise ValueError("RAW_HISTORY_NOT_CAPTURED_BEFORE_KICKOFF")
            original=json.loads(raw)
            # Last provider update for finished fixtures must be available
            # at capture. A response seen after kickoff is categorically excluded.
            available=[]
            for m in original.get("matches",[]):
                if not isinstance(m,dict):continue
                if m.get("status")=="FINISHED" and m.get("lastUpdated"):
                    if stamp(m["lastUpdated"])>observed:
                        continue
                available.append(m)
            history=historic_rows({**original,"matches":available},int(cid))
            prior=[r for r in history if r["kickoff_utc"]<observed and
                   r["kickoff_utc"]<kickoff]
            pair={"kickoff_utc":fixture["kickoff_utc"],
                  "home_team_id":str(fixture["home_source_team_id"]),
                  "away_team_id":str(fixture["away_source_team_id"])}
            features,reason=_inputs_for_target(prior,pair)
            if features is None:raise ValueError("HISTORICAL_FEATURES_NOT_READY:"+str(reason))
            if features["home_history_count"]<5 or features["away_history_count"]<5:
                raise ValueError("INSUFFICIENT_HISTORY_COUNTS")
            expected=_pool_over25(features["poisson"]["over_2_5"],
                                  features["baseline"]["over_2_5"])
            stored=target.get("p_over25_research")
            if (isinstance(stored,bool) or not isinstance(stored,(float,int))
                or not math.isfinite(stored) or abs(expected-stored)>1e-9):
                raise ValueError("LIVE_SHADOW_PROBABILITY_MISMATCH")
            # Capture before the game is required for every reported source;
            # the original shadow itself remains a SHA-bound immutable input.
            # Only after all gates pass, physically preserve the exact
            # original inputs. These are append-only SHA-named source files.
            intake_ref=folder/"sources"/(digest(intake_bytes)+".json")
            shadow_ref=folder/"sources"/(digest(shadow_bytes)+".json")
            row={"schema":SCHEMA,"provider":"FOOTBALL_DATA_ORG",
                "provider_fixture_id":fid,"provider_competition_id":cid,
                "kickoff_utc":kickoff.isoformat(),
                "intake_captured_at_utc":intake_at.isoformat(),
                "history_captured_at_utc":observed.isoformat(),
                "model_calculated_at_utc":shadow_at.isoformat(),
                "sealed_at_utc":now.isoformat(),
                "source_snapshot_sha256":g["source_payload_sha256"],
                "source_intake_file_sha256":digest(intake_bytes),
                "source_shadow_file_sha256":digest(shadow_bytes),
                "source_intake_file_path":str(intake_ref).replace("\\\\","/"),
                "source_shadow_file_path":str(shadow_ref).replace("\\\\","/"),
                "source_history_home_count":features["home_history_count"],
                "source_history_away_count":features["away_history_count"],
                "research_probability_over25":round(expected,10),
                "frozen_calibrated_model_parameters_mutated":False,
                "original_vs_alternative_equivalence_certified":False,
                "source_fixture_crosswalk_verified":False,
                "scientific_holdout_certified":False,
                "production_p_matrix_authorized":False,
                "telegram_signal_authorized":False,
                "automatic_wagering":False,"real_money":"BLOCKED"}
            content=canonical(row)
            name=f"{fid}_{digest(content)[:20]}.json"
            dest=folder/name
            if dest.exists():
                if dest.read_bytes()!=content:
                    raise ValueError("IMMUTABLE_SNAPSHOT_REWRITE_BLOCKED")
                action="ALREADY_IDENTICAL"
            else:
                action="FROZEN" if allow_write else "DRY_RUN"
            if allow_write:
                seal_source(folder,intake_bytes)
                seal_source(folder,shadow_bytes)
                if not dest.exists():
                    folder.mkdir(parents=True,exist_ok=True)
                    # exclusive creation; never overwrite an earlier seal
                    with dest.open("xb") as f:f.write(content)
            accepted.append({"fixture_id":fid,"path":str(dest).replace("\\","/"),
                             "snapshot_sha256":digest(content),"status":action})
        except (ValueError,TypeError,KeyError,OverflowError,UnicodeError,
                json.JSONDecodeError,base64.binascii.Error) as exc:
            blocked.append({"fixture_id":fid,"reason":str(exc)[:130]})
    return {"schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT_V1",
        "target_date_bogota":intake["target_date_bogota"],
        "captured_fixture_count":len(allowed),"research_scored_rows":len(shadow.get("scored") or []),
        "immutable_prematch_freeze_count":len(accepted),
        "sealed":accepted,"blocked":blocked,
        "status":"RESEARCH_SNAPSHOTS_SEALED_NO_PRODUCTION_PROMOTION" if accepted
                 else "NO_AUTHENTIC_PREMATCH_SNAPSHOTS_TO_SEAL",
        "original_calibrated_model_untouched":True,
        "six_league_prospective_parity_certified":False,
        "production_p_matrix_authorized":False,"telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--intake",type=Path,required=True)
    p.add_argument("--shadow",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--freeze-dir",type=Path)
    a=p.parse_args()
    if any(k in a.out.parts for k in ("telegram","daily_prematch_reports","tennis_signals","governance")):
        raise SystemExit("RESEARCH_FREEZE_MUST_NOT_WRITE_PRODUCTION")
    if a.freeze_dir is not None and not str(a.freeze_dir).replace("\\","/").startswith(str(ROOT)):
        raise SystemExit("INVALID_RESEARCH_FREEZE_DIRECTORY")
    now=datetime.now(timezone.utc)
    inp=a.intake.read_bytes();sha=a.shadow.read_bytes()
    intake=json.loads(inp);shadow=json.loads(sha)
    dirpath=a.freeze_dir or ROOT/intake["target_date_bogota"]
    report=freeze(intake,shadow,intake_bytes=inp,shadow_bytes=sha,now=now,folder=dirpath)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_bytes(canonical(report))
    print(json.dumps({k:report[k] for k in
       ("status","captured_fixture_count","research_scored_rows",
        "immutable_prematch_freeze_count","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":main()
