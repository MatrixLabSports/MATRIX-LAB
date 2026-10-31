from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_LEDGER = Path("evidence/api_football/prospective_calibration/ledger.jsonl")
SOURCE_SYNC = Path("evidence/api_football/prospective_calibration/sync_last.json")
CHECKPOINT = Path("evidence/api_football/calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
OUT = Path("evidence/api_football/calibration_v2/OOS_4001_5000_STATE.json")
BASELINE = 4000
TARGET = 1000

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def canonical_sha(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def load_jsonl(path: Path) -> list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def main() -> None:
    for p in (SOURCE_LEDGER,SOURCE_SYNC,CHECKPOINT):
        if not p.exists():
            raise SystemExit(f"OOS_SOURCE_MISSING:{p}")
    rows=load_jsonl(SOURCE_LEDGER)
    sync=json.loads(SOURCE_SYNC.read_text(encoding="utf-8"))
    cp=json.loads(CHECKPOINT.read_text(encoding="utf-8"))

    if len(rows) < BASELINE:
        raise SystemExit(f"OOS_BASELINE_NOT_MATURE:{len(rows)}/{BASELINE}")
    if cp.get("checkpoint") != BASELINE:
        raise SystemExit("OOS_CHECKPOINT_BASELINE_MISMATCH")
    if cp.get("governance",{}).get("parameter_tuning_allowed") is not False:
        raise SystemExit("OOS_CHECKPOINT_TUNING_NOT_FROZEN")
    if cp.get("governance",{}).get("refit_allowed") is not False:
        raise SystemExit("OOS_CHECKPOINT_REFIT_NOT_FROZEN")
    if cp.get("governance",{}).get("real_money") != "BLOCKED":
        raise SystemExit("OOS_CHECKPOINT_REAL_MONEY_NOT_BLOCKED")
    if sync.get("ledger_hash_chain_verified") is not True:
        raise SystemExit("OOS_LEDGER_HASH_CHAIN_NOT_VERIFIED")
    if sync.get("parameters_mutated") is not False:
        raise SystemExit("OOS_PARAMETERS_MUTATED")
    if sync.get("real_money") != "BLOCKED":
        raise SystemExit("OOS_REAL_MONEY_NOT_BLOCKED")

    prefix=rows[:BASELINE]
    prefix_ids=[str(r.get("fixture_id") or "") for r in prefix]
    prefix_sha=hashlib.sha256("\n".join(prefix_ids).encode()).hexdigest()
    expected=cp.get("source",{}).get("prefix_fixture_ids_sha256")
    if prefix_sha != expected:
        raise SystemExit(f"OOS_BASELINE_PREFIX_MUTATED:{prefix_sha}!={expected}")

    oos_all=rows[BASELINE:BASELINE+TARGET]
    oos_ids=[str(r.get("fixture_id") or "") for r in oos_all]
    if any(not x for x in oos_ids):
        raise SystemExit("OOS_FIXTURE_ID_MISSING")
    if len(set(oos_ids)) != len(oos_ids):
        raise SystemExit("OOS_DUPLICATE_FIXTURE_ID")
    if set(prefix_ids).intersection(oos_ids):
        raise SystemExit("OOS_BASELINE_OVERLAP")

    violations=[]
    for i,r in enumerate(oos_all,start=BASELINE+1):
        if r.get("parameters_mutated_after_freeze") is not False:
            violations.append({"index":i,"fixture_id":r.get("fixture_id"),"reason":"PARAMETERS_MUTATED_AFTER_FREEZE"})
        if r.get("used_for_parameter_tuning") is not False:
            violations.append({"index":i,"fixture_id":r.get("fixture_id"),"reason":"USED_FOR_PARAMETER_TUNING"})
    if violations:
        raise SystemExit(f"OOS_GOVERNANCE_VIOLATIONS:{violations[:3]}")

    count=len(oos_all)
    status="CLOSED_FIXED_1000" if count >= TARGET else "ACTIVE_SEALED_PENDING"
    metrics_opened=count >= TARGET
    payload={
        "schema":"MATRIX_FOOTBALL_OOS_4001_5000_STATE_V1",
        "generated_at_utc":now_utc(),
        "baseline_checkpoint":BASELINE,
        "target_oos_observations":TARGET,
        "target_total_observations":BASELINE+TARGET,
        "current_source_rows":len(rows),
        "current_oos_observations":count,
        "remaining_to_1000":max(0,TARGET-count),
        "status":status,
        "metrics_opened":metrics_opened,
        "outcomes_read_for_oos_metrics": TARGET if metrics_opened else 0,
        "baseline_anchor":{
            "checkpoint_path":str(CHECKPOINT),
            "checkpoint_sha256":cp.get("checkpoint_sha256"),
            "prefix_fixture_ids_sha256":expected,
            "first_fixture_id":prefix_ids[0],
            "last_fixture_id":prefix_ids[-1],
            "unique_fixture_ids":len(set(prefix_ids)),
        },
        "oos_cohort":{
            "index_start_inclusive":4001,
            "index_end_inclusive":5000,
            "current_first_fixture_id":oos_ids[0] if oos_ids else None,
            "current_last_fixture_id":oos_ids[-1] if oos_ids else None,
            "current_fixture_ids_sha256":hashlib.sha256("\n".join(oos_ids).encode()).hexdigest() if oos_ids else None,
            "current_unique_fixture_ids":len(set(oos_ids)),
            "baseline_overlap_count":0,
            "append_only":True,
            "prospective_only":True,
            "no_backfill":True,
        },
        "frozen_policy":{
            "model_and_probability_generation_rule":"FROZEN_AT_CHECKPOINT_4000",
            "parameter_tuning_allowed":False,
            "refit_allowed":False,
            "parameter_changes_allowed":False,
            "odds_used_to_generate_probability":False,
            "metrics_policy":"SEALED_UNTIL_1000_OOS",
            "missing_is_not_zero":True,
            "no_silent_imputation":True,
            "standard_final_only":True,
            "real_money":"BLOCKED",
            "automatic_wagering":False,
        },
        "adjudication":{
            "current_decision":"COLLECT_OOS_NO_TUNING" if not metrics_opened else "READY_FOR_OOS_1000_EVALUATION",
            "comparison_plan":"COMPARE_FIXED_CHECKPOINT_4000_METRICS_VS_NEW_OOS_1000",
            "promotion_before_1000":"FORBIDDEN",
        },
    }
    payload["state_sha256"]=canonical_sha(payload)

    if OUT.exists():
        old=json.loads(OUT.read_text(encoding="utf-8"))
        if old.get("baseline_anchor",{}).get("checkpoint_sha256") != payload["baseline_anchor"]["checkpoint_sha256"]:
            raise SystemExit("OOS_BASELINE_ANCHOR_CHANGED")
        old_count=int(old.get("current_oos_observations") or 0)
        if count < old_count:
            raise SystemExit(f"OOS_COUNT_REGRESSION:{old_count}->{count}")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "baseline_checkpoint":BASELINE,
        "current_oos_observations":count,
        "remaining_to_1000":max(0,TARGET-count),
        "metrics_opened":metrics_opened,
        "status":status,
        "real_money":"BLOCKED",
        "output":str(OUT),
        "state_sha256":payload["state_sha256"],
    },sort_keys=True))

if __name__ == "__main__":
    main()
