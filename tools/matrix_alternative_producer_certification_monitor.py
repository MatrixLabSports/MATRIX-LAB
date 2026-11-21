"""Recurring six-league alternative-producer audit report; no production writes."""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_six_league_enriched_oos_audit import scan_archived_references,audit

def report(root:Path):
    reference=scan_archived_references(root)
    provenance=root/"evidence"/"football_world_inventory"/"2026-11-04"/"MATRIX_ALTERNATIVE_PRODUCER_SCOPE_CERTIFICATE.json"
    prospective=root/"evidence"/"certification"/"MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE.json"
    blockers=[]
    historical=None
    if provenance.is_file():
        historical=json.loads(provenance.read_text(encoding="utf-8"))
        if (historical.get("status")!="PASS_SCOPED_HISTORICAL_RAW_GROUP_ONLY_PRODUCTION_BLOCKED"
            or historical.get("production_p_matrix_authorized") is not False):
            blockers.append("HISTORICAL_SOURCE_CERTIFICATE_INVALID")
    else:
        blockers.append("HISTORICAL_SOURCE_CERTIFICATE_MISSING")
    distinct=sorted({row["original_league_id"] for row in reference["reference_groups"]})
    if len(distinct)<6:
        blockers.append("FEWER_THAN_SIX_ORIGINAL_ARCHIVED_LEAGUES")
    blockers.append("SIX_GOVERNED_VALIDATION_COHORTS_NOT_YET_SELECTED")
    blockers.append("ORIGINAL_ENRICHED_VARIABLE_PARITY_NOT_YET_CERTIFIED")
    blockers.append("SIX_LEAGUE_PROSPECTIVE_HOLDOUT_NOT_YET_CERTIFIED")
    prospective_status="NO_SOURCE_EVIDENCE"
    prospective_count=0
    if prospective.is_file():
        try:
            result=audit(prospective)
            prospective_count=sum(x["validated_prospective_rows"] for x in result["leagues"])
            prospective_status=result["status"]
            if result["six_league_scientific_validation_passed"]:
                blockers=[b for b in blockers if b not in (
                    "ORIGINAL_ENRICHED_VARIABLE_PARITY_NOT_YET_CERTIFIED",
                    "SIX_LEAGUE_PROSPECTIVE_HOLDOUT_NOT_YET_CERTIFIED")]
        except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
            prospective_status="REJECTED_UNTRUSTED_OR_INCOMPLETE_SOURCE"
    if not prospective.is_file():
        blockers.append("PROSPECTIVE_FREEZE_SNAPSHOT_SOURCE_MISSING")
    return {
      "schema":"MATRIX_ALTERNATIVE_PRODUCER_SIX_LEAGUE_MONITOR_V1",
      "checked_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":"SCIENTIFIC_REVIEW_REQUIRED_NO_PRODUCTION_AUTHORIZATION",
      "historical_raw_group_scoped_certified":bool(
          historical and historical.get("historical_scope",{}).get("certified") is True),
      "original_archived_league_ids":distinct,
      "archived_league_id_count":len(distinct),
      "scoped_six_leagues_independently_verified":False,
      "prospective_evidence_file_exists":prospective.is_file(),
      "prospective_evidence_status":prospective_status,
      "prospective_validated_prediction_count":prospective_count,
      "unresolved_requirements":blockers,
      "original_model_untouched":True,"calibration_untouched":True,
      "full_alternative_producer_certified":False,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED",
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--out",required=True,type=Path)
    a=parser.parse_args()
    if any(part in a.out.parts for part in ("telegram","daily_prematch_reports",
                                             "tennis_signals","governance")):
        raise SystemExit("CERTIFICATION_MONITOR_CANNOT_WRITE_TO_PRODUCTION")
    result=report(a.root)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
      "archived_league_id_count":result["archived_league_id_count"],
      "prospective_validated_prediction_count":result["prospective_validated_prediction_count"],
      "real_money":result["real_money"]},sort_keys=True))

if __name__=="__main__":
    main()
