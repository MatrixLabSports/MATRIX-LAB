from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_BROWSER_MODES = {
    "AUTOMATED_BROWSER_UI_EXACT",
    "MACHINE_VERIFIED_BROWSER_UI_EXACT",
}


class BaselineGateError(RuntimeError):
    pass


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_exact_browser_source(sport: str, source: str, payload: dict[str, Any]) -> None:
    count = payload.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise BaselineGateError(f"{sport}:{source}:EXACT_NUMERIC_COUNT_REQUIRED")
    mode = payload.get("count_type")
    if mode not in ALLOWED_BROWSER_MODES:
        raise BaselineGateError(
            f"{sport}:{source}:AUTOMATED_EXACT_BROWSER_PROVENANCE_REQUIRED:{mode}"
        )
    if payload.get("operator_manual_intervention_required") is not False:
        raise BaselineGateError(
            f"{sport}:{source}:MANUAL_INTERVENTION_MUST_BE_FALSE"
        )
    if not payload.get("captured_at_utc"):
        raise BaselineGateError(f"{sport}:{source}:CAPTURED_AT_REQUIRED")
    if not payload.get("url"):
        raise BaselineGateError(f"{sport}:{source}:URL_REQUIRED")


def validate(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != "MATRIX_DAILY_WORLD_CALENDAR_SOURCE_COUNTS_V2":
        raise BaselineGateError("SCHEMA_V2_REQUIRED")
    if report.get("calendar_baseline_complete") is not True:
        raise BaselineGateError("CALENDAR_BASELINE_NOT_COMPLETE")
    if report.get("operator_manual_intervention_required") is not False:
        raise BaselineGateError("REPORT_REQUIRES_MANUAL_INTERVENTION")

    order = report.get("task_order") or []
    expected = [
        "CALENDAR_BASELINE_SOFASCORE_FLASHSCORE_FIRST",
        "PAID_APIS_SECOND",
        "COVERAGE_COMPARE_AND_GAP_DETECTION_THIRD",
        "CANONICAL_RECONCILIATION_DEDUP_AND_GOVERNED_PIPELINE_FOURTH",
    ]
    if order[:4] != expected:
        raise BaselineGateError("TASK_ORDER_INVALID")

    baseline_at = report.get("browser_baseline_completed_at_utc")
    if not baseline_at:
        raise BaselineGateError("BROWSER_BASELINE_TIMESTAMP_REQUIRED")
    baseline_dt = _dt(baseline_at)

    for sport in ("tennis", "football"):
        section = report.get(sport)
        if not isinstance(section, dict):
            raise BaselineGateError(f"{sport}:SECTION_REQUIRED")
        for source in ("sofascore", "flashscore"):
            payload = section.get(source)
            if not isinstance(payload, dict):
                raise BaselineGateError(f"{sport}:{source}:SOURCE_REQUIRED")
            _require_exact_browser_source(sport, source, payload)

    paid = (
        ("tennis", "rapidapi_tennis"),
        ("tennis", "api_tennis"),
        ("football", "api_football"),
    )
    for sport, source in paid:
        payload = report[sport].get(source)
        if not isinstance(payload, dict):
            raise BaselineGateError(f"{sport}:{source}:PAID_SOURCE_REQUIRED")
        started = payload.get("capture_started_at_utc")
        if not started:
            raise BaselineGateError(f"{sport}:{source}:CAPTURE_START_REQUIRED")
        if _dt(started) < baseline_dt:
            raise BaselineGateError(
                f"{sport}:{source}:PAID_API_STARTED_BEFORE_BROWSER_BASELINE"
            )
        count = payload.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise BaselineGateError(f"{sport}:{source}:MACHINE_COUNT_REQUIRED")

    truth = report.get("truth_rules") or {}
    if truth.get("invented_counts_prohibited") is not True:
        raise BaselineGateError("INVENTED_COUNTS_PROHIBITION_REQUIRED")
    if truth.get("partial_accessibility_count_is_never_promoted_to_world_total") is not True:
        raise BaselineGateError("PARTIAL_PROMOTION_PROHIBITION_REQUIRED")

    return {
        "status": "PASS",
        "target_date_bogota": report.get("target_date_bogota"),
        "browser_baseline_completed_at_utc": baseline_at,
        "tennis_sofascore": report["tennis"]["sofascore"]["count"],
        "tennis_flashscore": report["tennis"]["flashscore"]["count"],
        "football_sofascore": report["football"]["sofascore"]["count"],
        "football_flashscore": report["football"]["flashscore"]["count"],
        "manual_intervention_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    try:
        result = validate(report)
    except BaselineGateError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
