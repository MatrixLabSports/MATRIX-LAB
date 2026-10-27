from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("evidence/api_football/prospective_calibration/ledger.jsonl")
CHECKPOINT = Path("evidence/api_football/calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
OUT = Path("evidence/api_football/calibration_v2/OOS_4001_5000_STATE.json")
BASELINE = 4000
TARGET = 5000


def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows=[]
    for line_no,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():
            continue
        value=json.loads(line)
        if not isinstance(value,dict):
            raise ValueError(f"EXPECTED_OBJECT_LINE:{line_no}")
        rows.append(value)
    return rows


def sha_ids(ids:list[str]) -> str:
    return hashlib.sha256(("\n".join(ids)+"\n").encode("utf-8")).hexdigest()


def build(rows:list[dict[str,Any]], checkpoint:dict[str,Any]) -> dict[str,Any]:
    if len(rows) < BASELINE:
        raise ValueError("LEDGER_BELOW_FIXED_4000_CHECKPOINT")
    ids=[str(x.get("fixture_id") or "") for x in rows]
    if any(not x for x in ids):
        raise ValueError("EMPTY_FIXTURE_ID")
    prefix=rows[:BASELINE]
    prefix_ids=ids[:BASELINE]
    source=checkpoint.get("source") or {}
    if len(set(prefix_ids)) != BASELINE:
        raise ValueError("FIXED_PREFIX_4000_NOT_UNIQUE")
    if str(prefix_ids[0]) != str(source.get("first_fixture_id")):
        raise ValueError("CHECKPOINT_FIRST_FIXTURE_MISMATCH")
    if str(prefix_ids[-1]) != str(source.get("last_fixture_id")):
        raise ValueError("CHECKPOINT_LAST_FIXTURE_MISMATCH")
    if int(source.get("unique_fixture_ids") or 0) != BASELINE:
        raise ValueError("CHECKPOINT_UNIQUE_COUNT_MISMATCH")

    cohort=rows[BASELINE:TARGET]
    cohort_ids=[str(x.get("fixture_id") or "") for x in cohort]
    overlap=set(prefix_ids) & set(cohort_ids)
    if len(set(cohort_ids)) != len(cohort_ids):
        raise ValueError("OOS_FIXTURE_DUPLICATE")
    if overlap:
        raise ValueError("OOS_BASELINE_OVERLAP")
    non_final=[x for x in cohort if str(x.get("source_terminal_status") or "") != "FT"]
    tuned=[x for x in cohort if x.get("used_for_parameter_tuning") is True]
    mutated=[x for x in cohort if x.get("parameters_mutated_after_freeze") is True]
    if non_final:
        raise ValueError("OOS_NON_FINAL_ROWS_PRESENT")
    if tuned:
        raise ValueError("OOS_PARAMETER_TUNING_PRESENT")
    if mutated:
        raise ValueError("OOS_PARAMETER_MUTATION_PRESENT")

    current=len(cohort)
    return {
      "schema":"MATRIX_FOOTBALL_OOS_4001_5000_STATE_V2",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":"READY_FOR_FINAL_1000_ADJUDICATION" if current==1000 else "ACTIVE_SEALED_PENDING",
      "baseline_checkpoint":BASELINE,
      "target_total_observations":TARGET,
      "target_oos_observations":1000,
      "current_source_rows":len(rows),
      "current_oos_observations":current,
      "remaining_to_1000":1000-current,
      "metrics_opened":False,
      "outcomes_read_for_oos_metrics":0,
      "baseline_anchor":{
        "checkpoint_path":str(CHECKPOINT),
        "checkpoint_sha256":checkpoint.get("checkpoint_sha256"),
        "first_fixture_id":prefix_ids[0],
        "last_fixture_id":prefix_ids[-1],
        "unique_fixture_ids":len(set(prefix_ids)),
        "prefix_fixture_ids_sha256_runtime":sha_ids(prefix_ids),
      },
      "oos_cohort":{
        "index_start_inclusive":4001,
        "index_end_inclusive":5000,
        "append_only":True,
        "prospective_only":True,
        "no_backfill":True,
        "current_unique_fixture_ids":len(set(cohort_ids)),
        "baseline_overlap_count":0,
        "current_first_fixture_id":cohort_ids[0] if cohort_ids else None,
        "current_last_fixture_id":cohort_ids[-1] if cohort_ids else None,
        "current_fixture_ids_sha256":sha_ids(cohort_ids) if cohort_ids else None,
        "all_standard_final_ft":True,
      },
      "frozen_policy":{
        "model_and_probability_generation_rule":"FROZEN_AT_CHECKPOINT_4000",
        "metrics_policy":"SEALED_UNTIL_1000_OOS",
        "parameter_changes_allowed":False,
        "parameter_tuning_allowed":False,
        "refit_allowed":False,
        "odds_used_to_generate_probability":False,
        "missing_is_not_zero":True,
        "no_silent_imputation":True,
        "standard_final_only":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      },
      "adjudication":{
        "comparison_plan":"COMPARE_FIXED_CHECKPOINT_4000_METRICS_VS_NEW_OOS_1000",
        "current_decision":"COLLECT_OOS_NO_TUNING" if current<1000 else "READY_TO_OPEN_PREREGISTERED_OOS_METRICS",
        "promotion_before_1000":"FORBIDDEN",
      },
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default=str(LEDGER))
    p.add_argument("--checkpoint",default=str(CHECKPOINT))
    p.add_argument("--out",default=str(OUT))
    a=p.parse_args()
    result=build(load_jsonl(Path(a.ledger)),load_json(Path(a.checkpoint)))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":result["status"],
      "current_source_rows":result["current_source_rows"],
      "current_oos_observations":result["current_oos_observations"],
      "remaining_to_1000":result["remaining_to_1000"],
      "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
