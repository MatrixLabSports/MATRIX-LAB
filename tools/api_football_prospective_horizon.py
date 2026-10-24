from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tools.api_football_prospective_daily_cycle import run_daily_cycle

BOGOTA = ZoneInfo("America/Bogota")
MAX_DAYS = 3


def _day_window(target_date: str) -> dict[str, str]:
    local_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    start_local = datetime.combine(local_date, datetime.min.time(), tzinfo=BOGOTA)
    end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
    return {
        "calendar_day_start_local": start_local.isoformat(),
        "calendar_day_end_local": end_local.isoformat(),
        "calendar_day_start_utc": start_local.astimezone(timezone.utc).isoformat(),
        "calendar_day_end_utc": end_local.astimezone(timezone.utc).isoformat(),
    }


def _parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NOW_UTC_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)


def _retriable_budget_block(path: Path, summary: dict[str, Any]) -> bool:
    canonical = summary.get("canonical")
    freeze = summary.get("freeze")
    if not isinstance(canonical, dict) or not isinstance(freeze, dict):
        return False
    if int(canonical.get("ready_input_count", 0) or 0) != 0:
        return False
    if int(freeze.get("new_event_count", 0) or 0) != 0:
        return False

    for relative in (
        Path("history/history_capture_manifest.json"),
        Path("team_last_fallback/manifest.json"),
    ):
        manifest = path.parent / relative
        if not manifest.exists():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("stopped_reason") == "DAILY_RESERVE_REACHED":
            return True
    return False


def _completed_today(root: Path, target_date: str, local_today) -> dict[str, Any] | None:
    base = root / "evidence/api_football/prospective_daily" / target_date
    if not base.exists():
        return None
    for path in sorted(base.glob("*/cycle_summary.json"), reverse=True):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            started = datetime.fromisoformat(d["started_at_utc"]).astimezone(BOGOTA)
        except Exception:
            continue
        if (
            d.get("status") == "PASS"
            and d.get("target_date_bogota") == target_date
            and started.date() == local_today
        ):
            if _retriable_budget_block(path, d):
                continue
            return {"path": path.as_posix(), "summary": d}
    return None


def run_horizon(
    *,
    root: Path,
    api_key: str,
    days: int = 3,
    target_date: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    days = max(1, min(int(days), MAX_DAYS))
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_today = now.astimezone(BOGOTA).date()
    targets = (
        [target_date]
        if target_date
        else [(local_today + timedelta(days=i)).isoformat() for i in range(days)]
    )

    entries: list[dict[str, Any]] = []
    total_new_freezes = 0
    total_network_calls = 0

    for target in targets:
        done = _completed_today(root, target, local_today)
        if done is not None:
            summary = done["summary"]
            entries.append({
                "target_date_bogota": target,
                **_day_window(target),
                "status": "ALREADY_COMPLETED_TODAY",
                "cycle_summary_path": done["path"],
                "new_freezes": int(summary.get("freeze", {}).get("new_event_count", 0) or 0),
                "network_calls": 0,
            })
            continue

        try:
            summary = run_daily_cycle(
                root=root,
                api_key=api_key,
                target_date=target,
            )
        except ValueError as exc:
            if str(exc) == "NO_ELIGIBLE_FUTURE_FIXTURES":
                entries.append({
                    "target_date_bogota": target,
                    **_day_window(target),
                    "status": "HEALTHY_SKIP_NO_ELIGIBLE_FUTURE_FIXTURES",
                    "new_freezes": 0,
                    "network_calls": 1,
                })
                total_network_calls += 1
                continue
            raise

        new_freezes = int(summary.get("freeze", {}).get("new_event_count", 0) or 0)
        calls = int(summary.get("network_calls_performed", 0) or 0)
        total_new_freezes += new_freezes
        total_network_calls += calls
        entries.append({
            "target_date_bogota": target,
            **_day_window(target),
            "status": "PASS",
            "cycle_summary_path": (
                root / summary["cycle_root"] / "cycle_summary.json"
            ).as_posix(),
            "fixtures_received": int(summary["fixture_capture"]["fixtures_received"]),
            "eligible_future_fixtures": int(summary["fixture_capture"]["eligible_future_fixtures"]),
            "ready_input_count": int(summary["canonical"]["ready_input_count"]),
            "new_freezes": new_freezes,
            "network_calls": calls,
        })

    payload = {
        "schema": "MATRIX_FOOTBALL_PROSPECTIVE_HORIZON_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "local_date_bogota": local_today.isoformat(),
        "operational_timezone": "America/Bogota",
        "calendar_day_rule": "00:00:00-23:59:59_LOCAL_FULL_DAY",
        "days_requested": len(targets),
        "targets": entries,
        "new_freezes_total": total_new_freezes,
        "network_calls_total": total_network_calls,
        "p_matrix_status": "NOT_GENERATED",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS",
    }
    out = root / "evidence/api_football/prospective_horizon/last_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--now-utc", default="")
    args = parser.parse_args()
    payload = run_horizon(
        root=Path("."),
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        days=args.days,
        target_date=(args.target_date.strip() or None),
        now_utc=_parse_utc(args.now_utc) if args.now_utc else None,
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
