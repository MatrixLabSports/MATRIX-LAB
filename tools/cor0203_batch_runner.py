from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.cor0203_batch_preflight import partition_batch
from tools.cor0203_prospective_producer import extend_state, load_state


REV_RE = re.compile(r"_R(\d+)\.json$")


def _rev(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_holdout_state(holdout_dir: Path) -> tuple[int, set[str]]:
    count = 0
    event_ids: set[str] = set()
    for path in sorted(holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"), key=_rev):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        try:
            count = max(count, int(payload.get("ending_observation_count", 0)))
        except (TypeError, ValueError):
            pass
        for obs in payload.get("observations", []) or []:
            event_id = str(obs.get("event_id") or "")
            if event_id:
                event_ids.add(event_id)
    return count, event_ids


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _state_for_period(base_state_path: Path, annual_rows: list[dict[str, str]], target_period: int):
    state, _ = load_state(base_state_path)
    state, used_rows, period_count = extend_state(state, annual_rows, target_period)
    return state, used_rows, period_count


def run_pending_batches(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
    state_b64: Path,
    bundle: Path,
    annual_2026: Path,
    trigger_sha: str,
) -> dict[str, Any]:
    current_count, frozen_event_ids = _existing_holdout_state(holdout_dir)
    annual_rows = list(csv.DictReader(annual_2026.open(encoding="utf-8-sig", newline="")))
    manifests = sorted(runtime_dir.glob("MATRIX_COR0203_PROSPECTIVE_EVENTS_R*.json"), key=_rev)

    summary: dict[str, Any] = {
        "schema": "MATRIX_COR0203_BATCH_RUNNER_SUMMARY_V1",
        "trigger_sha": trigger_sha,
        "starting_physical_count": current_count,
        "manifests_seen": len(manifests),
        "processed_revisions": [],
        "skipped_already_frozen": [],
        "waiting_inputs": [],
        "new_freezes": 0,
        "new_blocked": 0,
    }

    for event_path in manifests:
        revision = _rev(event_path)
        if revision < 0:
            continue

        out_path = holdout_dir / f"MATRIX_COR0203_HOLDOUT_BATCH_R{revision}.json"
        if out_path.exists() and out_path.stat().st_size > 0:
            summary["skipped_already_frozen"].append(revision)
            continue

        pre_path = runtime_dir / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{revision}.json"
        static_path = runtime_dir / f"MATRIX_COR0203_STATIC4_R{revision}.json"
        report_path = runtime_dir / f"MATRIX_COR0203_BATCH_PREFLIGHT_R{revision}.json"
        history_path = runtime_dir / f"MATRIX_COR0203_HISTORY_GATE_R{revision}.json"

        missing = [str(p.name) for p in (pre_path, static_path) if not p.exists()]
        if missing:
            waiting = {
                "schema": "MATRIX_COR0203_BATCH_WAITING_INPUTS_V1",
                "revision": f"R{revision}",
                "event_manifest": event_path.name,
                "missing": missing,
                "physical_count": current_count,
                "trigger_sha": trigger_sha,
                "result": "WAITING_REQUIRED_INPUTS",
            }
            _write_json(report_path, waiting)
            summary["waiting_inputs"].append({"revision": revision, "missing": missing})
            continue

        events = _load_json(event_path)
        event_rows = list(events.get("events") or [])
        periods = {int(row["target_period"]) for row in event_rows}
        if len(periods) != 1:
            raise ValueError(f"ONE_TARGET_PERIOD_PER_BATCH_REQUIRED:R{revision}")
        target_period = next(iter(periods))

        state, used_rows, period_count = _state_for_period(state_b64, annual_rows, target_period)
        freeze_at = _now_utc()

        result = partition_batch(
            prefeature=_load_json(pre_path),
            static4=_load_json(static_path),
            events=events,
            state=state,
            freeze_at_utc=freeze_at,
            expected_starting_count=current_count,
            existing_event_ids=frozen_event_ids,
        )
        filtered = result.pop("filtered_manifest")

        report = {
            **result,
            "revision": f"R{revision}",
            "trigger_sha": trigger_sha,
            "event_manifest": event_path.name,
            "prefeature_manifest": pre_path.name,
            "static4_manifest": static_path.name,
        }
        _write_json(report_path, report)

        history = {
            "schema": "MATRIX_COR0203_BATCH_HISTORY_GATE_V2",
            "revision": f"R{revision}",
            "target_period": target_period,
            "annual_rows_used_preperiod": used_rows,
            "annual_periods_used_preperiod": period_count,
            "players": result["history_players"],
            "valid_event_ids": result["valid_event_ids"],
            "blocked": result["blocked"],
            "result": result["result"],
            "same_period_results_used": False,
            "silent_imputation": False,
        }
        _write_json(history_path, history)

        valid_count = int(result["valid_events"])
        blocked_count = int(result["blocked_events"])
        summary["new_blocked"] += blocked_count

        revision_summary = {
            "revision": revision,
            "input_events": int(result["input_events"]),
            "valid_events": valid_count,
            "blocked_events": blocked_count,
            "starting_physical_count": current_count,
            "freeze_at_utc": freeze_at,
            "result": result["result"],
        }

        if valid_count == 0:
            summary["processed_revisions"].append(revision_summary)
            continue

        filtered_path = Path("/tmp") / f"MATRIX_COR0203_FILTERED_EVENTS_R{revision}.json"
        _write_json(filtered_path, filtered)

        command = [
            sys.executable,
            "-m",
            "tools.cor0203_prospective_producer",
            "--state-b64", str(state_b64),
            "--bundle", str(bundle),
            "--annual-2026", str(annual_2026),
            "--events", str(filtered_path),
            "--freeze-at", freeze_at,
            "--out", str(out_path),
        ]
        subprocess.run(command, check=True)

        out = _load_json(out_path)
        if int(out["starting_observation_count"]) != current_count:
            raise ValueError(f"PRODUCER_START_COUNT_MISMATCH:R{revision}")
        if int(out["added_observations"]) != valid_count:
            raise ValueError(f"PRODUCER_VALID_COUNT_MISMATCH:R{revision}")
        if int(out["ending_observation_count"]) != current_count + valid_count:
            raise ValueError(f"PRODUCER_END_COUNT_MISMATCH:R{revision}")
        if out.get("metrics") != "SEALED_UNTIL_600" or int(out.get("outcomes_read", -1)) != 0:
            raise ValueError(f"HOLDOUT_SEAL_VIOLATION:R{revision}")

        new_ids = {str(row.get("event_id") or "") for row in out.get("observations", [])}
        if "" in new_ids or frozen_event_ids.intersection(new_ids):
            raise ValueError(f"DUPLICATE_FROZEN_EVENT:R{revision}")
        frozen_event_ids.update(new_ids)

        current_count += valid_count
        summary["new_freezes"] += valid_count
        revision_summary["ending_physical_count"] = current_count
        summary["processed_revisions"].append(revision_summary)

    summary["ending_physical_count"] = current_count
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument("--state-b64", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--annual-2026", required=True)
    parser.add_argument("--trigger-sha", required=True)
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    summary = run_pending_batches(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
        state_b64=Path(args.state_b64),
        bundle=Path(args.bundle),
        annual_2026=Path(args.annual_2026),
        trigger_sha=args.trigger_sha,
    )
    _write_json(Path(args.summary_out), summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
