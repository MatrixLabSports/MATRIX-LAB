"""Independent six-league enriched-feature + prospective holdout audit.

Read-only and fail-closed. A historical match result is never a prospective
prediction, and source data availability is never model certification.
This script cannot write to any production, canonical or Telegram directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="MATRIX_SIX_LEAGUE_ENRICHED_OOS_AUDIT_V1"
SOURCE_SCHEMA="MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE_V1"
MIN_OOS_PER_LEAGUE=30  # conservative prospective screening floor, not original policy
SIX=6

def stamp(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("OOS_NAIVE_TIME")
    return t.astimezone(timezone.utc)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def finite_p(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and 0<x<1

def normalized_input(record,fixmap):
    """Verify actual frozen enriched-input contract, using provider ID crosswalk."""
    from app.research.football.match_analysis_input import (
        FootballMatchAnalysisInput, FootballHistoryObservation,
        assess_match_analysis_readiness,
    )
    if not isinstance(record,dict):
        raise ValueError("ENRICHED_INPUT_MISSING")
    obj=dict(record)
    obj.pop("canonical_sha256",None)
    obj.pop("readiness",None)
    for side in ("home_history","away_history"):
        obj[side]=tuple(FootballHistoryObservation(**row) for row in obj.get(side,[]))
    value=FootballMatchAnalysisInput(**obj)
    ready=assess_match_analysis_readiness(value)
    if not ready.ready:
        raise ValueError("ENRICHED_HISTORY_NOT_READY")
    if any(row.fixture_identity_kind!="provider" or row.time_precision!="datetime"
           for row in value.home_history+value.away_history):
        raise ValueError("ENRICHED_HISTORY_IDENTITY_OR_PRECISION_NOT_CERTIFIED")
    if any(row.source_payload_sha256 is None for row in value.home_history+value.away_history):
        raise ValueError("ENRICHED_HISTORY_RAW_SOURCE_HASH_MISSING")
    if not isinstance(fixmap,dict) or not fixmap:
        raise ValueError("ENRICHED_PROVIDER_CROSSWALK_MISSING")
    def map_id(v):
        if v not in fixmap or not str(fixmap[v]):
            raise ValueError("ENRICHED_PROVIDER_CROSSWALK_INCOMPLETE")
        return str(fixmap[v])
    canonical={
        "kickoff_utc":stamp(value.kickoff_utc).isoformat(),
        "as_of_utc":stamp(value.as_of_utc).isoformat(),
        "season":value.season,"round_name":value.round_name,
        "competition_name":value.competition_name,
        "venue_name":value.venue_name,
        "home_team_name":value.home_team_name.casefold().strip(),
        "away_team_name":value.away_team_name.casefold().strip(),
        "fixture_id":map_id(value.fixture_id),
        "home_team_id":map_id(value.home_team_id),
        "away_team_id":map_id(value.away_team_id),
    }
    for side in ("home_history","away_history"):
        hist=[]
        for r in getattr(value,side):
            hist.append({
                "fixture_id":map_id(r.fixture_id),
                "team_id":map_id(r.team_id),
                "opponent_id":map_id(r.opponent_id),
                "kickoff_utc":stamp(r.kickoff_utc).isoformat(),
                # Capture times are independently validated before the freeze;
                # providers need not have observed the same match at the same second.
                "venue_role":r.venue_role,
                "goals_for":r.goals_for,"goals_against":r.goals_against,
                "competition":r.competition,
            })
        canonical[side]=sorted(hist,key=lambda x:(x["kickoff_utc"],x["fixture_id"]))
    return canonical

def enriched_pair_ok(row):
    if not isinstance(row,dict) or row.get("source_verified") is not True:
        return False
    try:
        orig=row["original_input"]
        alt=row["alternative_input"]
        left=normalized_input(orig,row["original_to_canonical_id"])
        right=normalized_input(alt,row["alternative_to_canonical_id"])
        return left==right
    except (ValueError,TypeError,KeyError,AttributeError):
        return False

def calculate(rows,expected_leagues):
    """No forecasting or refitting. Strict six-league evaluation of pre-frozen rows."""
    if not isinstance(expected_leagues,list) or len(expected_leagues)!=SIX or len(set(expected_leagues))!=SIX:
        raise ValueError("SIX_LEAGUE_SCOPE_MUST_BE_ORIGINAL_AND_UNIQUE")
    if not all(isinstance(x,str) and x.strip() for x in expected_leagues):
        raise ValueError("SIX_LEAGUE_ID_INVALID")
    if not isinstance(rows,list):
        raise ValueError("OOS_ROWS_MUST_BE_ARRAY")
    grouped=defaultdict(list)
    seen=set()
    for rec in rows:
        if not isinstance(rec,dict):
            raise ValueError("OOS_RECORD_INVALID")
        league=rec.get("league")
        if league not in expected_leagues:
            raise ValueError("OOS_UNKNOWN_LEAGUE")
        fixture=str(rec.get("fixture_id") or "")
        if not fixture or (league,fixture) in seen:
            raise ValueError("OOS_DUPLICATE_OR_EMPTY_FIXTURE")
        seen.add((league,fixture))
        grouped[league].append(rec)
    groups=[]
    for league in expected_leagues:
        items=grouped[league];good=[];fail=defaultdict(int)
        original_probs=[];alternative_probs=[];outcomes=[]
        for r in items:
            try:
                freeze=stamp(r["frozen_at_utc"])
                kickoff=stamp(r["kickoff_utc"])
                observed=stamp(r["result_observed_at_utc"])
                target=r["over25_result"]
                if isinstance(target,bool) or not isinstance(target,int) or target not in (0,1):
                    raise ValueError("OOS_OUTCOME_INVALID")
                if not (freeze<kickoff<observed):
                    raise ValueError("OOS_LEAKAGE_PREDICTION_OR_RESULT_TIME")
                if r.get("training_or_original_holdout_overlap") is not False:
                    raise ValueError("OOS_HOLDOUT_OVERLAP_NOT_EXCLUDED")
                if (r.get("original_probability_frozen") is not True
                    or r.get("alternative_probability_frozen") is not True
                    or r.get("result_verified_by_independent_source") is not True):
                    raise ValueError("OOS_NOT_INDEPENDENTLY_VERIFIED")
                a,b=r["original_p_over25"],r["alternative_p_over25"]
                if not finite_p(a) or not finite_p(b):
                    raise ValueError("OOS_PROBABILITY_NOT_FROZEN")
                if not enriched_pair_ok(r):
                    raise ValueError("OOS_ENRICHED_FEATURE_PARITY_MISSING")
                if abs(a-b)>1e-9:
                    raise ValueError("OOS_PROBABILITY_PARITY_DIFFERENCE")
                original_probs.append(a);alternative_probs.append(b);outcomes.append(target)
                good.append(r["fixture_id"])
            except (ValueError,TypeError,KeyError,AttributeError) as exc:
                fail[str(exc)]+=1
        # For an equivalent frozen model the alternative cannot be worse if
        # predictions are exactly equal; no new calibration/threshold is implied.
        brier_original=(sum((p-y)**2 for p,y in zip(original_probs,outcomes))/len(good)
                        if good else None)
        brier_alternative=(sum((p-y)**2 for p,y in zip(alternative_probs,outcomes))/len(good)
                           if good else None)
        passed=(len(good)>=MIN_OOS_PER_LEAGUE and len(items)==len(good)
                and brier_original==brier_alternative)
        groups.append({
            "league":league,"total_rows":len(items),"validated_prospective_rows":len(good),
            "minimum_prospective_rows":MIN_OOS_PER_LEAGUE,
            "rejected_reasons":dict(sorted(fail.items())),
            "brier_original":brier_original,"brier_alternative":brier_alternative,
            "all_enriched_input_pairs_equal":len(items)>0 and not fail,
            "prospective_holdout_certified":passed,
        })
    all_pass=all(x["prospective_holdout_certified"] for x in groups)
    return {
        "schema":SCHEMA,
        "status":"PASS_SIX_LEAGUE_ENRICHED_PROSPECTIVE_OOS" if all_pass else
                 "BLOCKED_MISSING_ENRICHED_OR_PROSPECTIVE_EVIDENCE",
        "minimum_leagues":SIX,
        "leagues":groups,
        "production_p_matrix_authorized":False,
        "six_league_scientific_validation_passed":all_pass,
        "calibration_parameters_mutated":False,
        "original_holdout_reused":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }

def _read_bound_json(root:Path,ref:dict):
    """Require an independently persisted byte-for-byte SHA-256-bound source."""
    if not isinstance(ref,dict):raise ValueError("OOS_PROVENANCE_REFERENCE_MISSING")
    relative=ref.get("path")
    expected=ref.get("sha256")
    if (not isinstance(relative,str) or not relative
        or not isinstance(expected,str) or len(expected)!=64
        or any(c not in "0123456789abcdef" for c in expected)):
        raise ValueError("OOS_PROVENANCE_INVALID")
    base=root.resolve()
    target=(base/relative).resolve()
    try:target.relative_to(base)
    except ValueError as exc:raise ValueError("OOS_SOURCE_PATH_ESCAPE") from exc
    if "evidence" not in target.relative_to(base).parts or not target.is_file():
        raise ValueError("OOS_SOURCE_NOT_PHYSICALLY_PRESENT")
    if sha(target)!=expected:raise ValueError("OOS_SOURCE_SHA_MISMATCH")
    data=json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise ValueError("OOS_SOURCE_NOT_OBJECT")
    return data

def verify_row_source_provenance(rec:dict,root:Path)->bool:
    """Unbound results or post-hoc summaries cannot constitute prospective OOS."""
    try:
        refs=rec["source_snapshot_refs"]
        if not isinstance(refs,dict) or set(refs)!={
            "original_prematch","alternative_prematch","settled_result"
        }:return False
        original=_read_bound_json(root,refs["original_prematch"])
        alternative=_read_bound_json(root,refs["alternative_prematch"])
        outcome=_read_bound_json(root,refs["settled_result"])
        if (original.get("input")!=rec.get("original_input")
            or alternative.get("input")!=rec.get("alternative_input")
            or original.get("p_over25")!=rec.get("original_p_over25")
            or alternative.get("p_over25")!=rec.get("alternative_p_over25")
            or original.get("frozen_at_utc")!=rec.get("frozen_at_utc")
            or alternative.get("frozen_at_utc")!=rec.get("frozen_at_utc")
            or outcome.get("over25_result")!=rec.get("over25_result")
            or outcome.get("result_observed_at_utc")!=rec.get("result_observed_at_utc")
            or any(d.get("fixture_id")!=rec.get("fixture_id")
                   for d in (original,alternative,outcome))):
            return False
        if original.get("source")!="ORIGINAL_FROZEN_MODEL":
            return False
        if alternative.get("source")!="INDEPENDENT_VERIFIED_PROVIDER":
            return False
        if outcome.get("source")!="INDEPENDENT_FINAL_SCORE":
            return False
        return True
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError):
        return False

def audit(path):
    doc=json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema")!=SOURCE_SCHEMA or doc.get("real_money")!="BLOCKED":
        raise ValueError("OOS_UNTRUSTED_SOURCE_ENVELOPE")
    if doc.get("signal_generation_authorized") is not False:
        raise ValueError("OOS_UNTRUSTED_SIGNAL_AUTHORIZATION")
    # Claims inside a JSON envelope cannot self-certify historical freezing.
    # Verify distinct persisted pre-match forecasts and independently settled
    # results, each byte-hash-bound to the original evidence directory.
    checked=[]
    for row in doc.get("rows",[]):
        if not isinstance(row,dict):raise ValueError("OOS_ROW_NOT_OBJECT")
        checked.append({**row,"source_verified":
            verify_row_source_provenance(row,Path.cwd())})
    archive_scope=scan_archived_references(Path.cwd())
    archived_ids={str(row["original_league_id"]) for row in archive_scope["reference_groups"]}
    supplied=doc.get("original_six_league_ids")
    if (len(archived_ids)!=SIX or not isinstance(supplied,list)
        or set(map(str,supplied))!=archived_ids):
        raise ValueError("OOS_ORIGINAL_SIX_LEAGUES_NOT_GROUNDED_IN_ARCHIVE")
    result=calculate(checked,supplied)
    result["evidence_sha256"]=sha(path)
    return result

def scan_archived_references(root:Path):
    """Inventory actual frozen reference groups, no imagined six-league IDs."""
    import re
    pattern=re.compile(r"^league_(\\d+)_season_(\\d+)\\.bin$")
    source=root/"evidence"/"api_football"/"prospective_daily"
    seen={}
    for p in sorted(source.glob("*/**/history/raw/league_*_season_*.bin")):
        match=pattern.fullmatch(p.name)
        if not match or not p.is_file():continue
        league,season=map(int,match.groups())
        key=(league,season)
        seen.setdefault(key,[]).append(str(p.relative_to(root)))
    return {"schema":"MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY_V1",
       "archived_reference_group_count":len(seen),
       "reference_groups":[{"original_league_id":k[0],"season":k[1],
                            "archive_files":v,"source":"ORIGINAL_API_FOOTBALL_ARCHIVE"}
                           for k,v in sorted(seen.items())],
       "six_archived_league_ids_found":len({k[0] for k in seen})==SIX,
       "six_original_leagues_confirmed":False,  # absence of approved league registry
       "enriched_feature_equivalence_certified":False,
       "prospective_oos_certified":False,
       "production_p_matrix_authorized":False,
       "telegram_signal_authorized":False,"automatic_wagering":False,
       "real_money":"BLOCKED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",type=Path)
    parser.add_argument("--scan-original-root",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if (args.evidence is None)==(args.scan_original_root is None):
        raise SystemExit("CHOOSE_EVIDENCE_OR_ORIGINAL_DISCOVERY")
    if any(x in args.out.parts for x in ("telegram","daily_prematch_reports",
                                          "tennis_signals","governance")):
        raise SystemExit("OOS_AUDIT_MUST_NOT_WRITE_TO_PRODUCTION")
    result=(audit(args.evidence) if args.evidence is not None
            else scan_archived_references(args.scan_original_root))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result.get("status","REFERENCE_DISCOVERY_ONLY_NOT_CERTIFICATION"),
        "archived_reference_group_count":result.get("archived_reference_group_count"),
        "six_league_scientific_validation_passed":result.get(
            "six_league_scientific_validation_passed",False),
        "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
