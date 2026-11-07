"""Audit real existing non-canonical Over2.5 production reports without promotion.

This scans only tracked JSON in known football evidence lanes. A historical
probability candidate remains unverified until all pre-kickoff and independent
source references pass the separately governed six-league OOS audit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from tools.matrix_six_league_existing_evidence_recovery import ROOT, relative_paths
from tools.matrix_six_league_prospective_preflight import REGISTRY

OUTPUT=Path("evidence/football_world_inventory/2026-11-04/MATRIX_OVER25_NONCANONICAL_PROBABILITY_RECOVERY_LAST.json")
LANES=("over25_shadow_ev","shadow_quote_freeze","browser_physical_verification")
MAX_BYTES=12*1024*1024
MAX_ROWS=200000

def tracked_report_path(path:str)->bool:
    parts=path.replace("\\","/").split("/")
    return (len(parts)>=6 and parts[:3]==["evidence","api_football","daily_prematch_reports"]
            and parts[4] in LANES and parts[-1].endswith(".json"))

def numeric_probability(value)->bool:
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<value<1

def rows_from_document(doc:dict)->list[dict]:
    a=doc.get("all_rows")
    b=doc.get("rows")
    rows=a if isinstance(a,list) else b if isinstance(b,list) else []
    if len(rows)>MAX_ROWS:
        raise ValueError("OVER25_REPORT_TOO_MANY_ROWS")
    return rows

def inspect(root:Path,paths:list[str])->dict:
    reg=json.loads((root/REGISTRY).read_text(encoding="utf-8"))
    ids=reg.get("original_six_league_ids")
    if (reg.get("schema")!="MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        or reg.get("scope_approved") is not True or not isinstance(ids,list)
        or len(ids)!=6 or len(set(ids))!=6):
        raise ValueError("SIX_LEAGUE_SCOPE_INVALID")
    matches=[p for p in paths if tracked_report_path(p)]
    counters=Counter()
    reasons=Counter()
    by_league={i:{"report_mentions":0,"rows_with_numeric_probability":0,
                 "source_attested_valid_prospective_rows":0} for i in ids}
    examples=[]
    oversized=[]
    unique_six_fixtures={i:set() for i in ids}
    globally_scoped_identified=set()
    globally_unscoped_ids=set()
    for relative in sorted(matches):
        file=root/relative
        try:
            if not file.is_file():
                raise ValueError("REPORT_NOT_PHYSICALLY_PRESENT")
            if file.stat().st_size>MAX_BYTES:
                raise ValueError("REPORT_TOO_LARGE")
            data=json.loads(file.read_text(encoding="utf-8-sig"))
            if not isinstance(data,dict):
                raise ValueError("REPORT_NOT_JSON_OBJECT")
            rows=rows_from_document(data)
            lane=relative.replace("\\","/").split("/")[4]
            counters["readable_reports"]+=1
            counters["readable_"+lane]+=1
            counters["rows_examined"]+=len(rows)
            saw_numeric=False
            for row in rows:
                if not isinstance(row,dict):continue
                p_matrix=row.get("p_matrix")
                p_over25=row.get("p_over_2_5")
                matrix_ok=numeric_probability(p_matrix)
                over25_ok=numeric_probability(p_over25)
                if not (matrix_ok or over25_ok):
                    continue
                saw_numeric=True
                counters["numeric_probability_rows_unverified"]+=1
                if matrix_ok:
                    counters["rows_with_numeric_p_matrix_field"]+=1
                if over25_ok:
                    counters["rows_with_numeric_p_over_2_5_field"]+=1
                if matrix_ok and over25_ok and abs(p_matrix-p_over25)>1e-9:
                    counters["rows_with_conflicting_numeric_probability_fields"]+=1
                league=str(row.get("league_id") or row.get("competition_id") or
                           row.get("league") or data.get("league_id") or "")
                fixture_id=str(row.get("fixture_id") or "").strip()
                if league in by_league:
                    by_league[league]["rows_with_numeric_probability"]+=1
                    if fixture_id:
                        unique_six_fixtures[league].add(fixture_id)
                        globally_scoped_identified.add((league,fixture_id))
                    else:
                        counters["recognized_league_rows_missing_fixture_id"]+=1
                else:
                    counters["numeric_rows_without_recognized_six_league_id"]+=1
                    if fixture_id:
                        globally_unscoped_ids.add(fixture_id)
                if len(examples)<50:
                    examples.append({
                        "source":relative,
                        "fixture_id":str(row.get("fixture_id") or ""),
                        "league_id":league,
                        "p_matrix_present_numeric":matrix_ok,
                        "p_over_2_5_present_numeric":over25_ok,
                        "two_numeric_fields_consistent":(abs(p_matrix-p_over25)<=1e-9
                                                        if matrix_ok and over25_ok else None),
                        "genuine_pre_kickoff_triplet_source_verified":False,
                        "production_equivalence_authorized":False,
                    })
            if saw_numeric:
                counters["reports_with_numeric_probability_unverified"]+=1
            if data.get("probability_status")=="FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY":
                counters["reports_claiming_frozen_governed_probability"]+=1
            if data.get("signal_generation_authorized") is True:
                counters["reports_claiming_signal_generation_authorization"]+=1
            for i in ids:
                if str(data.get("league_id") or "")==i:
                    by_league[i]["report_mentions"]+=1
        except (OSError,TypeError,ValueError,UnicodeError,json.JSONDecodeError) as exc:
            reasons[type(exc).__name__+":"+str(exc)[:65]]+=1
            if len(oversized)<30:
                oversized.append({"path":relative,"failure":str(exc)[:100]})
    for ident in ids:
        by_league[ident]["distinct_identified_fixture_ids_with_numeric_probability"]=len(unique_six_fixtures[ident])
        by_league[ident]["not_prospectively_certified_unique_fixture_count"]=len(unique_six_fixtures[ident])
    return {
       "schema":"MATRIX_OVER25_NONCANONICAL_PROBABILITY_RECOVERY_V1",
       "status":"NONCANONICAL_RESEARCH_AUDIT_ONLY_NO_PROSPECTIVE_CERTIFICATION",
       "tracked_report_file_count":len(matches),
       "counts":dict(sorted(counters.items())),
       "unreadable_report_count":sum(reasons.values()),
       "unreadable_reason_counts":dict(sorted(reasons.items())),
       "unreadable_report_examples":oversized,
       "six_original_leagues":by_league,
       "distinct_identified_six_league_fixture_keys":len(globally_scoped_identified),
       "distinct_unscoped_fixture_ids_with_numeric_probability":len(globally_unscoped_ids),
       "distinct_unscoped_fixture_id_not_equivalent_to_verified_league":True,
       "deduplication_scope":"PER_ORIGINAL_LEAGUE_ID_AND_FIXTURE_ID_ACROSS_REPORT_SNAPSHOTS",
       "numeric_probability_sample_without_values":examples,
       "strict_original_alternative_result_triplet_certified":0,
       "numeric_value_not_evidence_of_model_or_freeze":True,
       "p_over_2_5_is_original_field_not_automatically_governed_p_matrix":True,
       "report_auth_claim_not_evidence_of_prospective_parity":True,
       "complete_football_production_repository_scan":False,
       "limited_to_daily_prematch_reports_three_lanes":True,
       "historical_recovery_not_prospective_certification":True,
       "calibration_untouched":True,
       "production_p_matrix_authorized":False,
       "telegram_signal_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=OUTPUT)
    args=p.parse_args()
    if any(x in args.out.parts for x in ("telegram","governance","daily_prematch_reports","tennis_signals")):
        raise SystemExit("NONCANONICAL_AUDIT_CANNOT_WRITE_PRODUCTION")
    result=inspect(args.root,relative_paths(args.root))
    destination=args.out if args.out.is_absolute() else args.root/args.out
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "tracked_report_file_count":result["tracked_report_file_count"],
        "counts":result["counts"],
        "unreadable_report_count":result["unreadable_report_count"],
        "strict_original_alternative_result_triplet_certified":0,
        "production_p_matrix_authorized":False,
    },sort_keys=True))

if __name__=="__main__":main()
