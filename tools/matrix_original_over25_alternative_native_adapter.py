"""Execute the frozen ORIGINAL Over2.5 engine on genuine alternative input.

This proves numerical engine execution and pre-match lineage only; a provider
crosswalk/enriched-input identity and scientific OOS are separate approval gates.
Never modifies market promotion, parameters, Telegram or real-money permissions.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,math
from pathlib import Path
from collections import defaultdict
from tools.api_football_market_shadow_p_matrix import (
    MODEL,PARAMS_OVER25,_inputs_for_target,_pool_over25,
    MIN_TEAM_HISTORY,MIN_GROUP_BASELINE_HISTORY,MAX_TEAM_HISTORY)
from tools.matrix_football_independent_over25_shadow import historic_rows
from tools.matrix_independent_over25_prematch_freeze import canonical,stamp,digest,SCHEMA

ROOT=Path("evidence/football_research_freezes")
OUT=Path("evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_LAST.json")
PROMOTION=Path("evidence/api_football/governance/over_2_5_p_matrix_promotion.json")
MAX_BYTES=24_000_000

def read_sha(path:Path,expect:str)->bytes:
    if not path.is_file() or path.stat().st_size>MAX_BYTES:
        raise ValueError("SOURCE_FILE_MISSING_OR_OVERSIZED")
    raw=path.read_bytes()
    if digest(raw)!=expect:
        raise ValueError("SOURCE_SHA256_INVALID")
    return raw

def source_path(root:Path,forecast:dict,label:str)->Path:
    # Both historical Windows absolute paths and newer portable references
    # must resolve to content-addressed immutable source files INSIDE repo.
    ident=forecast[f"source_{label}_file_sha256"]
    if not isinstance(ident,str) or len(ident)!=64 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("SOURCE_HASH_NOT_SHA256")
    return root/ROOT/forecast["sealed_at_utc"][:10]/"sources"/(ident+".json")

def verify(root:Path,p:Path,promotion:dict)->dict:
    frozen_bytes=p.read_bytes()
    snapshot=json.loads(frozen_bytes)
    if (snapshot.get("schema")!=SCHEMA or snapshot.get("provider")!="FOOTBALL_DATA_ORG"
        or snapshot.get("production_p_matrix_authorized") is not False
        or snapshot.get("telegram_signal_authorized") is not False
        or snapshot.get("real_money")!="BLOCKED"):
        raise ValueError("ORIGINAL_INPUT_GOVERNANCE_UNTRUSTED")
    kickoff=stamp(snapshot["kickoff_utc"])
    saved=stamp(snapshot["sealed_at_utc"])
    calculated=stamp(snapshot["model_calculated_at_utc"])
    if not calculated<=saved<kickoff:raise ValueError("PREDICTION_NOT_CAPTURED_PRE_KICKOFF")
    inp=json.loads(read_sha(source_path(root,snapshot,"intake"),
                  snapshot["source_intake_file_sha256"]))
    shadow=json.loads(read_sha(source_path(root,snapshot,"shadow"),
                  snapshot["source_shadow_file_sha256"]))
    if (inp.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or inp.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("parameter_refit") is not False
        or shadow.get("market_signal_authorized") is not False
        or inp.get("signal_generation_authorized") is not False):
        raise ValueError("INPUT_SHADOW_OR_PROVIDER_NOT_VERIFIED")
    fid=str(snapshot["provider_fixture_id"])
    fixtures=[f for f in inp.get("fixtures",[]) if str(f.get("source_fixture_id"))==fid]
    if len(fixtures)!=1:raise ValueError("NATIVE_FIXTURE_ID_AMBIGUOUS")
    target=fixtures[0]
    cid=str(snapshot["provider_competition_id"])
    if (str(target.get("source_competition_id"))!=cid or
        stamp(target["kickoff_utc"])!=kickoff or
        target.get("source_status") not in ("TIMED","SCHEDULED")):
        raise ValueError("NATIVE_COMPETITION_OR_KICKOFF_MISMATCH")
    groups=shadow.get("authenticated_raw_group_replay_evidence") or {}
    group=groups.get(cid)
    if not isinstance(group,dict):raise ValueError("AUTHENTIC_HISTORY_GROUP_MISSING")
    raw=base64.b64decode(group["response_base64"],validate=True)
    if digest(raw)!=group.get("source_payload_sha256") or digest(raw)!=snapshot["source_snapshot_sha256"]:
        raise ValueError("AUTHENTIC_HISTORY_SHA_MISMATCH")
    observed=stamp(group["observed_at_utc"])
    if not (stamp(inp["generated_at_utc"])<=observed<=
            stamp(shadow.get("completed_at_utc") or shadow["generated_at_utc"])<=calculated<=saved<kickoff):
        raise ValueError("HISTORY_AVAILABILITY_TIMELINE_INVALID")
    payload=json.loads(raw)
    matches=payload.get("matches")
    if not isinstance(matches,list):raise ValueError("AUTHENTIC_HISTORY_MATCHES_MISSING")
    usable=[]
    for m in matches:
        if not isinstance(m,dict):continue
        if m.get("status")!="FINISHED":continue
        if not m.get("lastUpdated"):
            continue  # never guess an undocumented result publication time
        if stamp(m["lastUpdated"])>observed:
            continue
        if stamp(m["utcDate"])>=observed:
            continue
        usable.append(m)
    history=historic_rows({**payload,"matches":usable},int(cid))
    target_for_engine={
        "kickoff_utc":snapshot["kickoff_utc"],
        "home_team_id":str(target["home_source_team_id"]),
        "away_team_id":str(target["away_source_team_id"])}
    features,reason=_inputs_for_target(history,target_for_engine)
    if features is None:raise ValueError("ORIGINAL_INPUT_HISTORY_NOT_READY:"+str(reason))
    if (features["home_history_source"]!="RAW_GROUP_PIT" or
        features["away_history_source"]!="RAW_GROUP_PIT"):
        raise ValueError("UNEXPECTED_ENRICHED_INPUT_FALLBACK")
    probability=_pool_over25(features["poisson"]["over_2_5"],
                              features["baseline"]["over_2_5"])
    stored=snapshot["research_probability_over25"]
    if (isinstance(stored,bool) or not isinstance(stored,(int,float)) or
        not math.isfinite(stored) or abs(stored-probability)>1e-9):
        raise ValueError("ORIGINAL_FROZEN_ENGINE_PROBABILITY_MISMATCH")
    if snapshot.get("source_history_home_count")!=features["home_history_count"] or snapshot.get("source_history_away_count")!=features["away_history_count"]:
        raise ValueError("FROZEN_HISTORY_COUNTS_CHANGED")
    return {
      "fixture_id":fid,"provider_competition_id":cid,
      "status":"FROZEN_ORIGINAL_ENGINE_EXECUTION_MATCHES_ALTERNATIVE_NATIVE_INPUT",
      "forecast_sha256":digest(frozen_bytes),
      "authentic_intake_sha256":snapshot["source_intake_file_sha256"],
      "authentic_shadow_sha256":snapshot["source_shadow_file_sha256"],
      "authentic_history_sha256":snapshot["source_snapshot_sha256"],
      "history_rows_used_by_original_engine":features["prior_group_fixture_count"],
      "home_team_history_count":features["home_history_count"],
      "away_team_history_count":features["away_history_count"],
      "original_frozen_engine":MODEL,
      "original_frozen_over25_parameters":dict(PARAMS_OVER25),
      "recomputed_original_engine_probability":round(probability,10),
      "frozen_probability":stored,
      "model_parameters_modified":False,
      "cross_provider_fixture_id_equivalence_verified":False,
      "original_enriched_input_feature_equivalence_verified":False,
      "prospective_scientific_oos_certified":False,
      "production_p_matrix_authorized":False,"telegram_signal_authorized":False
    }

def evaluate(root:Path)->dict:
    promo=json.loads((root/PROMOTION).read_text(encoding="utf-8"))
    if (promo.get("market")!="OVER_2_5"
        or promo.get("promotion_status")!="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
        or promo.get("engine_executable_for_p_matrix") is not True
        or promo.get("frozen_parameters")!=dict(PARAMS_OVER25)
        or promo.get("parameter_refit_performed") is not False
        or promo.get("promotion_scope")!="MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY"):
        raise ValueError("ORIGINAL_OVER25_PROMOTION_OR_PARAMETERS_CHANGED")
    grouped=defaultdict(list)
    for p in (root/ROOT).glob("20??-??-??/[0-9]*_*.json"):
        if "_result_" not in p.name:
            grouped(p.name.split("_",1)[0]).append(p)
    verified=[];blocked=[];secondary=0
    for fid,files in sorted(grouped.items()):
        # Earliest authentic freeze is the preregistered row for a fixture;
        # secondary predictions never increase the cohort count.
        try:
            seq=sorted(files,key=lambda p:(stamp(json.loads(p.read_text(encoding="utf-8"))["sealed_at_utc"]),p.name))
            first=seq[0]
            secondary+=len(seq)-1
            verified.append(verify(root,first,promo))
        except (KeyError,ValueError,TypeError,OSError,UnicodeError,
                json.JSONDecodeError,base64.binascii.Error) as exc:
            blocked.append({"fixture_id":fid,"reason":str(exc)[:140]})
    return {
       "schema":"MATRIX_OVER25_ORIGINAL_FROZEN_ENGINE_ALTERNATIVE_INPUT_ATTESTATION_V1",
       "status":"ORIGINAL_ENGINE_REEXECUTED_RESEARCH_INPUTS_ONLY",
       "source_market_promotion_sha256":digest((root/PROMOTION).read_bytes()),
       "frozen_original_parameters":dict(PARAMS_OVER25),
       "distinct_fixtures":len(grouped),"original_engine_verified_rows":len(verified),
       "secondary_snapshots_excluded":secondary,
       "blocked":blocked,"verified":verified,
       "native_input_math_equivalence_not_enriched_cross_provider_parity":True,
       "official_original_p_matrix_reinstated":False,
       "telegram_signal_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--out",type=Path,default=OUT)
    args=p.parse_args()
    if any(k in args.out.parts for k in ("telegram","governance","daily_prematch_reports","tennis_signals")):
        raise SystemExit("RESEARCH_ENGINE_ADAPTER_MUST_NOT_WRITE_PRODUCTION")
    result=evaluate(args.root)
    target=args.out if args.out.is_absolute() else args.root/args.out
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(canonical(result))
    print(json.dumps({"original_engine_verified_rows":result["original_engine_verified_rows"],
        "distinct_fixtures":result["distinct_fixtures"],
        "secondary_snapshots_excluded":result["secondary_snapshots_excluded"],
        "blocked":result["blocked"],
        "official_original_p_matrix_reinstated":False},sort_keys=True))

if __name__=="__main__":main()
