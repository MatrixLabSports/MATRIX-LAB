"""Offline, read-only diagnostics of known upstream canonical producer workflow gates."""
import argparse
import json
from pathlib import Path

WORKFLOWS = {
    "football": ".github/workflows/football-daily-governed-pipeline.yml",
    "tennis": ".github/workflows/tennis-world-rolling-horizon.yml",
    "telegram": ".github/workflows/telegram-matrix-supervisor-15m.yml",
}
GATES = {
    "football": {
        "paid_subscription_guard": "football_subscription_deadline_guard --require-paid-use --require-key",
        "browser_preregistry": "Enforce canonical browser preregistry freshness before API calls",
    },
    "tennis": {
        "daily_browser_crosscheck": "Require daily SofaScore and Flashscore browser crosscheck",
        "daily_source_count_report": "Require autonomous exact calendar-first source-count report",
        "paid_rapidapi_provider": "MATRIX_TENNIS_PROVIDER: rapidapi_tennis",
    },
    "telegram": {
        "fifteen_minute_schedule": 'cron: "*/15 * * * *"',
        "independent_source_readiness": "football_subscription_deadline_guard --independent-source-readiness",
    },
}


def audit(root=Path(".")):
    results = {}
    for lane, relative in WORKFLOWS.items():
        path = root / relative
        if not path.is_file():
            results[lane] = {"workflow": relative, "exists": False, "gates": {}, "status": "WORKFLOW_MISSING"}
            continue
        source = path.read_text(encoding="utf-8")
        gates = {name: marker in source for name, marker in GATES[lane].items()}
        results[lane] = {
            "workflow": relative, "exists": True, "gates": gates,
            "status": "STATIC_GATES_PRESENT" if all(gates.values()) else "STATIC_GATE_MISSING",
        }
    return {
        "schema": "MATRIX_CANONICAL_PRODUCER_BLOCKER_AUDIT_V1",
        "status": "STATIC_WORKFLOW_SOURCE_AUDIT_ONLY",
        "workflows": results,
        "workflow_runs_inspected": False,
        "runtime_failure_cause_confirmed": False,
        "paid_subscription_validated": False,
        "browser_capture_validated": False,
        "canonical_generation_verified": False,
        "telegram_delivery_verified": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
