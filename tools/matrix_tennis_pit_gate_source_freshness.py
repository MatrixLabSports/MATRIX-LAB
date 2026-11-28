"""Fail closed when cloud Challenger PIT report is stale vs current browser bytes.

Research-only. Intended to run after git fetch/rebase, immediately before a
cloud evidence push. No data mutation, model promotion or wagering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

DETAIL_ROOT=Path("evidence/tennis_calendar_physical")
GATE_ROOT=Path("evidence/tennis_calendar_reconciliation")
DETAIL="sofascore_verified_match_details.json"
GATE="MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_LAST.json"

def verify(root:Path, day:str)->dict:
    date.fromisoformat(day)
    detail=root/DETAIL_ROOT/day/DETAIL
    gate=root/GATE_ROOT/day/GATE
    if not detail.is_file() and not gate.is_file():
        return {"date":day,"status":"NO_DETAIL_AND_NO_GATE_NOT_ADMITTED",
                "current_source_sha256":None,"gate_source_sha256":None,
                "same_source":False,"publish_safe":True}
    if not detail.is_file() or not gate.is_file():
        return {"date":day,"status":"MISSING_GOVERNED_PIT_GATE_OR_VISIBLE_DETAILS",
                "current_source_sha256":None,"gate_source_sha256":None,
                "same_source":False,"publish_safe":False}
    original=detail.read_bytes()
    source_sha=hashlib.sha256(original).hexdigest()
    d=json.loads(original)
    report=json.loads(gate.read_bytes())
    if (d.get("schema")!="MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or d.get("target_date_bogota")!=day
        or d.get("real_money")!="BLOCKED"
        or d.get("new_model_observations_admitted")!=0
        or report.get("schema")!="MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_V1"
        or report.get("target_date_bogota")!=day
        or report.get("real_money")!="BLOCKED"
        or report.get("new_hard_holdout_observations")!=0
        or report.get("new_clay_holdout_observations")!=0):
        return {"date":day,"status":"SOURCE_OR_REPORT_GOVERNANCE_INVALID",
                "current_source_sha256":source_sha,
                "gate_source_sha256":report.get("match_detail_sha256"),
                "same_source":False,"publish_safe":False}
    reported_sha=report.get("match_detail_sha256")
    same=reported_sha==source_sha
    return {"date":day,"status":"SOURCE_SHA256_BOUND_REPORT_CURRENT" if same
            else "PIT_GATE_SOURCE_DRIFT_AFTER_GIT_REBASE",
            "current_source_sha256":source_sha,"gate_source_sha256":reported_sha,
            "same_source":same,"publish_safe":same}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",action="append",required=True)
    ap.add_argument("--root",type=Path,default=Path("."))
    args=ap.parse_args()
    reports=[verify(args.root,day) for day in args.date]
    print(json.dumps({"status":"PASS" if all(d["publish_safe"] for d in reports)
          else "BLOCKED_NO_STALE_PIT_EVIDENCE_PUSH",
          "days":reports,"real_money":"BLOCKED",
          "new_hard_holdout_observations":0,
          "new_clay_holdout_observations":0},sort_keys=True))
    return 0 if all(d["publish_safe"] for d in reports) else 1

if __name__=="__main__":
    raise SystemExit(main())
