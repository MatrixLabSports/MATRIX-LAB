from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SYNC=Path("evidence/api_football/prospective_calibration/sync_last.json")
CALIBRATION_LEDGER=Path("evidence/api_football/prospective_calibration/ledger.jsonl")
OUT=Path("evidence/market_portfolio/MATRIX_FOOTBALL_5000_SETTLED_MILESTONE_LAST.json")
TARGET=5000


def _load_json(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    rows=[]
    for n,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not raw.strip():
            continue
        value=json.loads(raw)
        if not isinstance(value,dict):
            raise ValueError(f"EXPECTED_OBJECT_JSONL:{path}:{n}")
        rows.append(value)
    return rows


def _sha(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _state(count:int)->tuple[str,str]:
    if count>=TARGET:
        return "READY_FOR_5000_AUDIT","RUN_FIXED_PREFIX_5000_CALIBRATION_AUDIT_NO_AUTO_PROMOTION"
    return "TRACKING_TO_5000","CONTINUE_FINAL_ONLY_SETTLEMENT_UNTIL_5000"


def build(generated_at:datetime|None=None)->dict[str,Any]:
    sync=_load_json(SYNC)
    rows=_load_jsonl(CALIBRATION_LEDGER)

    if sync.get("ledger_hash_chain_verified") is not True:
        raise ValueError("CALIBRATION_LEDGER_HASH_CHAIN_NOT_VERIFIED")
    if sync.get("parameters_mutated") is not False:
        raise ValueError("PARAMETERS_MUTATED")
    if sync.get("real_money")!="BLOCKED":
        raise ValueError("REAL_MONEY_NOT_BLOCKED")

    sync_count=int(sync.get("calibration_observation_count") or 0)
    settlement_record_count=int(sync.get("settlement_record_count") or 0)
    ledger_count=len(rows)
    if ledger_count!=sync_count:
        raise ValueError(f"SYNC_LEDGER_COUNT_MISMATCH:{sync_count}:{ledger_count}")
    if settlement_record_count!=ledger_count:
        raise ValueError(f"SETTLEMENT_RECORD_COUNT_MISMATCH:{settlement_record_count}:{ledger_count}")

    fixture_ids=[str(r.get("fixture_id") or "") for r in rows]
    if any(not x for x in fixture_ids):
        raise ValueError("MISSING_FIXTURE_ID")
    if len(fixture_ids)!=len(set(fixture_ids)):
        raise ValueError("DUPLICATE_FIXTURE_ID")
    record_hashes=[str(r.get("record_sha256") or "").strip().lower() for r in rows]
    if any(len(x)!=64 or any(ch not in "0123456789abcdef" for ch in x) for x in record_hashes):
        raise ValueError("INVALID_OR_MISSING_RECORD_SHA256")
    if len(record_hashes)!=len(set(record_hashes)):
        raise ValueError("DUPLICATE_RECORD_SHA256")

    for row in rows:
        if row.get("source_terminal_status")!="FT":
            raise ValueError("NON_FT_ROW_IN_CALIBRATION_LEDGER")
        if row.get("used_for_parameter_tuning") is not False:
            raise ValueError("PARAMETER_TUNING_ROW_FOUND")
        if row.get("parameters_mutated_after_freeze") is not False:
            raise ValueError("PARAMETERS_MUTATED_AFTER_FREEZE")
        if row.get("p_matrix_status")!="NOT_GENERATED":
            raise ValueError("P_MATRIX_MUST_NOT_BE_GENERATED")
        if row.get("automatic_wagering") is not False:
            raise ValueError("AUTOMATIC_WAGERING_NOT_FALSE")
        if row.get("real_money")!="BLOCKED":
            raise ValueError("REAL_MONEY_NOT_BLOCKED_IN_ROW")

    status,next_action=_state(ledger_count)
    prefix=rows[:TARGET] if ledger_count>=TARGET else []
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
        "schema":"MATRIX_FOOTBALL_5000_SETTLED_MILESTONE_V1",
        "generated_at_utc":now,
        "status":"PASS",
        "milestone_state":status,
        "target_settled_count":TARGET,
        "current_settled_count":ledger_count,
        "remaining_to_5000":max(0,TARGET-ledger_count),
        "progress_pct":round((ledger_count/TARGET)*100.0,4),
        "next_required_action":next_action,
        "fixed_prefix_5000":{
            "opened":ledger_count>=TARGET,
            "observation_count":TARGET if ledger_count>=TARGET else 0,
            "fixture_ids_sha256":_sha([str(r["fixture_id"]) for r in prefix]) if prefix else None,
            "record_hashes_sha256":_sha([str(r["record_sha256"]) for r in prefix]) if prefix else None,
            "metrics_authorized":ledger_count>=TARGET,
            "automatic_promotion":False,
        },
        "settlement_contract":{
            "final_ft_only":True,
            "append_only":True,
            "duplicate_fixture_ids_forbidden":True,
            "duplicate_record_hashes_forbidden":True,
            "record_sha256_required":True,
            "sync_settlement_count_must_equal_ledger_count":True,
            "hash_chain_verified":True,
            "metrics_before_5000_for_milestone_audit_forbidden":True,
            "historical_backfill":False,
            "post_start_backfill":False,
            "parameter_tuning_allowed":False,
            "refit_allowed":False,
            "automatic_promotion":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "source":{
            "sync_generated_at_utc":sync.get("synced_at_utc"),
            "sync_new_observation_count":int(sync.get("new_observation_count") or 0),
            "settlement_record_count":settlement_record_count,
            "calibration_observation_count":sync_count,
            "ledger_record_hash_count":len(record_hashes),
            "ledger_unique_record_hash_count":len(set(record_hashes)),
            "ledger_sha256":_sha(rows),
        },
    }


def main()->None:
    result=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "milestone_state":result["milestone_state"],
        "current_settled_count":result["current_settled_count"],
        "target_settled_count":result["target_settled_count"],
        "remaining_to_5000":result["remaining_to_5000"],
        "next_required_action":result["next_required_action"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
