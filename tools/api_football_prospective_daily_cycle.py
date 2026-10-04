from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.api_football_build_prematch_queue import build_prematch_queue
from tools.api_football_canonicalize_analysis_inputs import (
    build_canonical_analysis_bundle,
    write_chunked_canonical_bundle,
)
from tools.api_football_future_fixture_capture import (
    default_target_date,
    run_capture as capture_future_fixtures,
)
from tools.api_football_group_history_capture import capture_group_history
from tools.api_football_over25_high_scoring_league_radar import write_outputs as write_over25_league_radar
from tools.api_football_prospective_market_freeze import persist_incremental_freeze
from tools.api_football_team_last_fallback import run_capture as capture_team_last


GROUP_HISTORY_MAX_REQUESTS = 40
TEAM_LAST_MAX_REQUESTS = 120
DAILY_REMAINING_RESERVE = 1500


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_daily_cycle(
    *,
    root: Path,
    api_key: str,
    target_date: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")

    started = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    cycle_id = started.strftime("%Y%m%dT%H%M%SZ")
    cycle_root = root / "evidence/api_football/prospective_daily" / target_date / cycle_id
    if cycle_root.exists():
        raise ValueError("DAILY_CYCLE_PATH_ALREADY_EXISTS:" + cycle_root.as_posix())

    fixtures_dir = cycle_root / "fixtures"
    prematch_dir = cycle_root / "prematch"
    history_dir = cycle_root / "history"
    team_last_dir = cycle_root / "team_last_fallback"
    canonical_dir = cycle_root / "canonical_analysis"
    radar_dir = cycle_root / "radar_over25_high_scoring_leagues"

    fixture_manifest = capture_future_fixtures(
        api_key=key,
        out_dir=fixtures_dir,
        target_date=target_date,
        captured_at_utc=started.isoformat(),
    )
    registry = _load(fixtures_dir / "future_fixture_registry.json")
    if fixture_manifest["eligible_future_fixtures"] <= 0:
        raise ValueError("NO_ELIGIBLE_FUTURE_FIXTURES")

    benchmark, queue, inventory = build_prematch_queue(
        registry=registry,
        manifest=fixture_manifest,
    )
    _write(prematch_dir / "benchmark.json", benchmark)
    _write(prematch_dir / "history_acquisition_queue.json", queue)
    _write(prematch_dir / "world_inventory.json", inventory)

    radar_audit_path = root / "evidence/api_football/league_over25_audit/audit_last.json"
    if radar_audit_path.exists():
        radar_manifest = write_over25_league_radar(
            audit_path=radar_audit_path,
            registry_path=fixtures_dir / "future_fixture_registry.json",
            out_dir=radar_dir,
        )
    else:
        radar_manifest = {
            "status":"AUDIT_NOT_AVAILABLE",
            "selected_league_count":0,
            "priority_radar_fixture_count":0,
            "matrix_mutation_performed":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }

    history_summary = capture_group_history(
        api_key=key,
        benchmark=benchmark,
        out_dir=history_dir,
        max_requests=GROUP_HISTORY_MAX_REQUESTS,
        min_daily_remaining_reserve=DAILY_REMAINING_RESERVE,
    )
    history_benchmark = _load(history_dir / "benchmark_with_history.json")
    history_readiness = _load(history_dir / "history_readiness.json")

    team_last_summary = capture_team_last(
        api_key=key,
        benchmark=history_benchmark,
        readiness=history_readiness,
        out_dir=team_last_dir,
        max_requests=TEAM_LAST_MAX_REQUESTS,
        min_daily_remaining_reserve=DAILY_REMAINING_RESERVE,
    )
    enriched_benchmark = _load(team_last_dir / "benchmark_after_team_last.json")

    analysis_as_of = datetime.now(timezone.utc).replace(microsecond=0)
    canonical_bundle, canonical_manifest = build_canonical_analysis_bundle(
        benchmark=enriched_benchmark,
        analysis_as_of=analysis_as_of,
    )
    persisted_canonical = write_chunked_canonical_bundle(
        out=canonical_dir,
        bundle=canonical_bundle,
        manifest=canonical_manifest,
    )

    freeze_at = datetime.now(timezone.utc).replace(microsecond=0)
    freeze_sync = persist_incremental_freeze(
        root,
        freeze_at,
        canonical_root=canonical_dir,
        history_root=history_dir,
    )

    finished = datetime.now(timezone.utc).replace(microsecond=0)
    summary = {
        "schema": "MATRIX_FOOTBALL_PROSPECTIVE_DAILY_CYCLE_V1",
        "cycle_id": cycle_id,
        "target_date_bogota": target_date,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "cycle_root": cycle_root.relative_to(root).as_posix(),
        "provider": "api_football",
        "provider_entitlement_required": "PRO_OR_COMPATIBLE",
        "fixture_capture": {
            "network_calls": 1,
            "fixtures_received": fixture_manifest["fixtures_received"],
            "eligible_future_fixtures": fixture_manifest["eligible_future_fixtures"],
            "response_sha256": fixture_manifest["response_sha256"],
        },
        "prematch": {
            "future_fixture_count": inventory["future_fixture_count"],
            "unique_team_count": inventory["unique_team_count"],
            "competition_count": inventory["competition_count"],
            "country_count": inventory["country_count"],
        },
        "over25_high_scoring_league_radar": {
            "status": radar_manifest.get("status"),
            "selected_league_count": int(radar_manifest.get("selected_league_count", 0)),
            "priority_radar_fixture_count": int(radar_manifest.get("priority_radar_fixture_count", 0)),
            "matrix_mutation_performed": bool(radar_manifest.get("matrix_mutation_performed", False)),
            "role": "DISCOVERY_SIDECAR_ONLY",
        },
        "history": {
            "group_network_calls": history_summary["network_calls_performed"],
            "group_ready_minimum_history_count": history_summary["ready_minimum_history_count"],
            "group_blocked_minimum_history_count": history_summary["blocked_minimum_history_count"],
            "team_last_network_calls": team_last_summary["network_calls_performed"],
            "team_last_ready_minimum_history_count": team_last_summary["ready_minimum_history_count"],
            "team_last_blocked_minimum_history_count": team_last_summary["blocked_minimum_history_count"],
        },
        "canonical": {
            "analysis_as_of_utc": persisted_canonical["analysis_as_of_utc"],
            "total_fixture_count": persisted_canonical["total_fixture_count"],
            "ready_input_count": persisted_canonical["ready_input_count"],
            "blocked_future_input_count": persisted_canonical["blocked_future_input_count"],
            "not_future_at_analysis_count": persisted_canonical["not_future_at_analysis_count"],
            "bundle_sha256": persisted_canonical["bundle_sha256"],
            "p_matrix_status": persisted_canonical["p_matrix_status"],
        },
        "freeze": freeze_sync,
        "network_calls_performed": (
            1
            + int(history_summary["network_calls_performed"])
            + int(team_last_summary["network_calls_performed"])
        ),
        "odds_used_to_generate_probability": False,
        "outcomes_used_to_generate_probability": False,
        "p_matrix_status": "NOT_GENERATED",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS",
    }
    _write(cycle_root / "cycle_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", default="")
    args = parser.parse_args()
    target_date = str(args.target_date or "").strip() or default_target_date()
    result = run_daily_cycle(
        root=Path("."),
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        target_date=target_date,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
