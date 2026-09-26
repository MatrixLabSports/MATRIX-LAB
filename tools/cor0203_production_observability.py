from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _sum_crosswalk(crosswalk: Mapping[str, Any], key: str) -> int:
    return sum(_int(row.get(key)) for row in crosswalk.get("crosswalk_revisions", []) or [])


def _sum_stage(stage: Mapping[str, Any], key: str) -> int:
    return sum(_int(row.get(key)) for row in stage.get("revisions", []) or [])


def build_observability_snapshot(
    *,
    source_readiness: Mapping[str, Any],
    prereg: Mapping[str, Any],
    crosswalk: Mapping[str, Any],
    stage: Mapping[str, Any],
    runner: Mapping[str, Any],
    integrity: Mapping[str, Any],
) -> dict[str, Any]:
    source_ready = bool(source_readiness.get("ready"))
    source_cause = str(source_readiness.get("cause") or "UNKNOWN")
    source_status = str(source_readiness.get("status") or "UNKNOWN")

    physical = _int(runner.get("ending_physical_count"))
    start_physical = _int(runner.get("starting_physical_count"), physical)
    new_freezes = _int(runner.get("new_freezes"))
    runner_blocked = _int(runner.get("new_blocked"))
    waiting_inputs = len(runner.get("waiting_inputs", []) or [])

    prereg_status = str(prereg.get("status") or "UNKNOWN")
    preregistered = _int(prereg.get("events_registered"))
    prereg_skipped = len(prereg.get("skipped", []) or [])

    crosswalk_passed = _sum_crosswalk(crosswalk, "passed_events")
    crosswalk_blocked = _sum_crosswalk(crosswalk, "blocked_events")

    staged = _sum_stage(stage, "staged_events")
    stage_blocked = _sum_stage(stage, "blocked_events")

    integrity_result = str(integrity.get("result") or "UNKNOWN")
    integrity_passed = _int(integrity.get("passed_observations"))
    integrity_failed = _int(integrity.get("failed_observations"))

    if not source_ready:
        bottleneck_stage = "SOURCE"
        bottleneck_cause = source_cause
        operational_state = "SOURCE_BLOCKED"
    elif waiting_inputs:
        bottleneck_stage = "INPUT_STAGING"
        bottleneck_cause = "WAITING_REQUIRED_INPUTS"
        operational_state = "PIPELINE_BLOCKED"
    elif crosswalk_blocked and crosswalk_passed == 0 and preregistered > 0:
        bottleneck_stage = "IDENTITY_CROSSWALK"
        bottleneck_cause = "ALL_PREREGISTERED_EVENTS_BLOCKED_AT_CROSSWALK"
        operational_state = "PIPELINE_BLOCKED"
    elif stage_blocked and staged == 0 and preregistered > 0:
        bottleneck_stage = "STAGING"
        bottleneck_cause = "ALL_PREREGISTERED_EVENTS_BLOCKED_AT_STAGING"
        operational_state = "PIPELINE_BLOCKED"
    elif integrity_result != "PASS" or integrity_failed:
        bottleneck_stage = "HOLDOUT_INTEGRITY"
        bottleneck_cause = "HOLDOUT_INTEGRITY_FAIL"
        operational_state = "INTEGRITY_BLOCKED"
    elif new_freezes > 0:
        bottleneck_stage = "NONE"
        bottleneck_cause = "NEW_VALID_FREEZES_PRODUCED"
        operational_state = "PRODUCING"
    elif prereg_status == "NO_NEW_EVENTS":
        bottleneck_stage = "INVENTORY"
        bottleneck_cause = "SOURCE_READY_NO_NEW_ELIGIBLE_EVENTS"
        operational_state = "IDLE_VALID"
    else:
        bottleneck_stage = "NONE"
        bottleneck_cause = "NO_MATERIAL_CHANGE"
        operational_state = "READY"

    remaining_window1 = max(0, 200 - physical)
    remaining_total = max(0, 600 - physical)

    return {
        "schema": "MATRIX_COR0203_PRODUCTION_OBSERVABILITY_V1",
        "operational_state": operational_state,
        "bottleneck": {
            "stage": bottleneck_stage,
            "cause": bottleneck_cause,
        },
        "source": {
            "provider": source_readiness.get("provider"),
            "ready": source_ready,
            "status": source_status,
            "cause": source_cause,
            "network_calls": _int(source_readiness.get("network_calls")),
        },
        "cycle": {
            "starting_physical_count": start_physical,
            "ending_physical_count": physical,
            "new_freezes": new_freezes,
            "new_blocked": runner_blocked,
            "waiting_inputs": waiting_inputs,
        },
        "funnel": {
            "preregistration_status": prereg_status,
            "preregistered_events": preregistered,
            "preregistration_skipped": prereg_skipped,
            "crosswalk_passed_events": crosswalk_passed,
            "crosswalk_blocked_events": crosswalk_blocked,
            "staged_events": staged,
            "stage_blocked_events": stage_blocked,
        },
        "holdout": {
            "window1_count": physical,
            "window1_target": 200,
            "window1_remaining": remaining_window1,
            "total_count": physical,
            "total_target": 600,
            "total_remaining": remaining_total,
            "metrics": "SEALED_UNTIL_600",
        },
        "integrity": {
            "result": integrity_result,
            "passed_observations": integrity_passed,
            "failed_observations": integrity_failed,
            "silent_imputation_detected": bool(integrity.get("silent_imputation_detected")),
            "outcomes_read": _int(integrity.get("outcomes_read")),
            "metrics_opened": bool(integrity.get("metrics_opened")),
        },
        "governance": {
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-readiness", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--integrity", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = build_observability_snapshot(
        source_readiness=_load(Path(args.source_readiness)),
        prereg=_load(Path(args.prereg)),
        crosswalk=_load(Path(args.crosswalk)),
        stage=_load(Path(args.stage)),
        runner=_load(Path(args.runner)),
        integrity=_load(Path(args.integrity)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "operational_state": result["operational_state"],
        "bottleneck": result["bottleneck"],
        "holdout": result["holdout"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
