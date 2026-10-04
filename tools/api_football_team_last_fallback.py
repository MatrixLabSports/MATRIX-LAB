from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools.api_football_group_history_capture import (
    BASE_URL,
    ENDPOINT,
    PUBLIC_HEADER_ALLOWLIST,
    TIMEOUT_SECONDS,
    _final_history_row,
    _parse_aware,
    _read_rate,
)

MAX_REQUESTS = 120
MIN_DAILY_REMAINING_RESERVE = 7000


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _dedupe_latest(rows: list[dict[str, Any]], cutoff: datetime) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        kickoff = _parse_aware(row.get("kickoff_utc"))
        fixture_id = str(row.get("fixture_id") or "").strip()
        if not fixture_id or kickoff is None or kickoff >= cutoff:
            continue
        by_id[fixture_id] = row
    merged = list(by_id.values())
    merged.sort(key=lambda row: row["kickoff_utc"], reverse=True)
    return merged[:20]


def _deficient_team_ids(
    *,
    benchmark: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, str]:
    fixtures = benchmark.get("fixtures")
    if not isinstance(fixtures, Mapping):
        raise ValueError("BENCHMARK_FIXTURES_MISSING")
    rows = readiness.get("rows")
    if not isinstance(rows, list):
        raise ValueError("READINESS_ROWS_MISSING")

    needed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("ready_minimum_history") is True:
            continue
        target_key = str(row.get("target_key") or "")
        target = fixtures.get(target_key)
        if not isinstance(target, Mapping):
            continue
        blockers = set(row.get("blockers") or [])
        if "HOME_HISTORY_BELOW_MINIMUM" in blockers:
            home = target.get("home")
            if isinstance(home, Mapping):
                team_id = str(home.get("id") or "").strip()
                team_name = str(home.get("name") or "").strip()
                if team_id and team_name:
                    needed[team_id] = team_name
        if "AWAY_HISTORY_BELOW_MINIMUM" in blockers:
            away = target.get("away")
            if isinstance(away, Mapping):
                team_id = str(away.get("id") or "").strip()
                team_name = str(away.get("name") or "").strip()
                if team_id and team_name:
                    needed[team_id] = team_name
    return needed


def run_capture(
    *,
    api_key: str,
    benchmark: Mapping[str, Any],
    readiness: Mapping[str, Any],
    out_dir: Path,
    session: Any | None = None,
    max_requests: int = MAX_REQUESTS,
    min_daily_remaining_reserve: int = MIN_DAILY_REMAINING_RESERVE,
    now_fn: Any | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    if not (1 <= max_requests <= MAX_REQUESTS):
        raise ValueError("MAX_REQUESTS_OUT_OF_POLICY")
    if min_daily_remaining_reserve < 0:
        raise ValueError("MIN_DAILY_REMAINING_RESERVE_INVALID")

    fixtures = benchmark.get("fixtures")
    histories = benchmark.get("histories")
    if not isinstance(fixtures, Mapping) or not isinstance(histories, Mapping):
        raise ValueError("BENCHMARK_CONTENT_MISSING")
    if benchmark.get("provider") != "api_football":
        raise ValueError("BENCHMARK_PROVIDER_MISMATCH")
    if benchmark.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")

    needed = _deficient_team_ids(benchmark=benchmark, readiness=readiness)

    out_dir.mkdir(parents=True, exist_ok=True)
    if not needed:
        rows = readiness.get("rows")
        if not isinstance(rows, list):
            raise ValueError("READINESS_ROWS_MISSING")
        ready_count = sum(
            1 for row in rows
            if isinstance(row, Mapping) and row.get("ready_minimum_history") is True
        )
        blocked_count = sum(
            1 for row in rows
            if isinstance(row, Mapping) and row.get("ready_minimum_history") is not True
        )
        enriched = json.loads(json.dumps(benchmark))
        enriched["benchmark_status"] = (
            "READY_MINIMUM_HISTORY" if blocked_count == 0 else "PARTIAL_HISTORY"
        )
        enriched["team_last_fallback_network_calls"] = 0
        enriched["money_decisions_enabled"] = False
        enriched["analysis_mode"] = "PREMATCH_RESEARCH_ONLY"
        enriched["real_money"] = "BLOCKED"
        manifest = {
            "schema": "MATRIX_API_FOOTBALL_TEAM_LAST_FALLBACK_V1",
            "provider": "api_football",
            "deficient_unique_team_count": 0,
            "captured_team_count": 0,
            "network_calls_performed": 0,
            "max_requests_policy": max_requests,
            "daily_remaining_reserve_policy": min_daily_remaining_reserve,
            "stopped_reason": "NO_DEFICIENT_TEAMS",
            "provider_error_team_count": 0,
            "target_fixture_count": len(fixtures),
            "ready_minimum_history_count": ready_count,
            "blocked_minimum_history_count": blocked_count,
            "last_rate_limit": {
                "daily_limit": None,
                "daily_remaining": None,
                "minute_limit": None,
                "minute_remaining": None,
            },
            "captures": [],
            "automatic_wagering": False,
            "odds_used": False,
            "real_money": "BLOCKED",
            "status": "PASS",
        }
        _write_json(out_dir / "manifest.json", manifest)
        _write_json(out_dir / "benchmark_after_team_last.json", enriched)
        _write_json(
            out_dir / "history_readiness_after_team_last.json",
            {
                "schema": "MATRIX_API_FOOTBALL_HISTORY_READINESS_AFTER_TEAM_LAST_V1",
                "ready_minimum_history_count": ready_count,
                "blocked_minimum_history_count": blocked_count,
                "rows": rows,
                "real_money": "BLOCKED",
            },
        )
        return manifest

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    now = now_fn or (lambda: datetime.now(timezone.utc).replace(microsecond=0))

    team_history: dict[str, list[dict[str, Any]]] = {}
    team_observed: dict[str, str] = {}
    captures: list[dict[str, Any]] = []
    total_calls = 0
    stopped_reason: str | None = None
    last_rate = {
        "daily_limit": None,
        "daily_remaining": None,
        "minute_limit": None,
        "minute_remaining": None,
    }

    for team_id, team_name in sorted(needed.items(), key=lambda item: int(item[0])):
        if total_calls >= max_requests:
            stopped_reason = "REQUEST_BUDGET_EXHAUSTED"
            break
        if last_rate["daily_remaining"] is not None:
            try:
                remaining = int(last_rate["daily_remaining"])
            except ValueError:
                remaining = 10**9
            if remaining <= min_daily_remaining_reserve:
                stopped_reason = "DAILY_RESERVE_REACHED"
                break

        started = now()
        response = client.get(
            BASE_URL + ENDPOINT,
            headers={"x-apisports-key": key},
            params={"team": team_id, "last": 20, "timezone": "UTC"},
            timeout=TIMEOUT_SECONDS,
        )
        observed = now()
        total_calls += 1
        body = bytes(response.content)
        raw_path = raw_dir / f"team_{team_id}_last_20.bin"
        raw_path.write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()

        public_headers = {
            name.lower(): value
            for name, value in response.headers.items()
            if name.lower() in PUBLIC_HEADER_ALLOWLIST
        }
        last_rate = _read_rate(public_headers)
        if not (200 <= int(response.status_code) < 300):
            raise ValueError(f"API_FOOTBALL_TEAM_LAST_HTTP_STATUS_{response.status_code}:{team_id}")

        parsed = response.json()
        errors = parsed.get("errors") if isinstance(parsed, Mapping) else None
        rows = parsed.get("response") if isinstance(parsed, Mapping) else None
        provider_error = errors not in ({}, [], None)
        if rows is None and provider_error:
            rows = []
        if not isinstance(rows, list):
            raise ValueError(f"API_FOOTBALL_TEAM_LAST_RESPONSE_INVALID:{team_id}")

        source_reference = f"api_football:/fixtures?team={team_id}&last=20"
        finals = [] if provider_error else [
            item
            for raw in rows
            for item in [_final_history_row(raw, source_sha256=sha, source_reference=source_reference)]
            if item is not None
        ]
        finals.sort(key=lambda row: row["kickoff_utc"], reverse=True)
        team_history[team_id] = finals
        team_observed[team_id] = observed.isoformat()
        captures.append({
            "provider_team_id": team_id,
            "team_name": team_name,
            "request_started_at_utc": started.isoformat(),
            "response_observed_at_utc": observed.isoformat(),
            "http_status": int(response.status_code),
            "raw_path": str(raw_path),
            "raw_sha256": sha,
            "response_bytes": len(body),
            "provider_rows": len(rows),
            "final_history_rows": len(finals),
            "provider_error": provider_error,
            "provider_errors": errors if provider_error else None,
            "rate_limit": last_rate,
            "status": "PROVIDER_ERROR_BLOCKED" if provider_error else "CAPTURED",
        })

    enriched = dict(benchmark)
    enriched_histories = json.loads(json.dumps(histories))
    readiness_rows: list[dict[str, Any]] = []
    ready_targets: list[str] = []
    blocked_targets: list[str] = []

    for target_key, target in sorted(fixtures.items()):
        kickoff = _parse_aware(target.get("kickoff_utc"))
        if kickoff is None:
            raise ValueError("TARGET_KICKOFF_INVALID")
        existing = enriched_histories.get(target_key)
        if not isinstance(existing, Mapping):
            existing = {
                "home": {"completed_before_target": []},
                "away": {"completed_before_target": []},
            }

        side_results: dict[str, dict[str, Any]] = {}
        blockers: list[str] = []
        for side in ("home", "away"):
            team = target.get(side)
            if not isinstance(team, Mapping):
                raise ValueError("TARGET_TEAM_MISSING")
            team_id = str(team.get("id") or "").strip()
            team_name = str(team.get("name") or "").strip()
            existing_side = existing.get(side) if isinstance(existing, Mapping) else None
            old_rows = []
            if isinstance(existing_side, Mapping):
                raw_old = existing_side.get("completed_before_target")
                if isinstance(raw_old, list):
                    old_rows = [row for row in raw_old if isinstance(row, dict)]

            fallback_rows = team_history.get(team_id, [])
            observed_at = team_observed.get(team_id)
            if observed_at is not None:
                observed_dt = _parse_aware(observed_at)
                if observed_dt is None or observed_dt >= kickoff:
                    fallback_rows = []
                    blockers.append(f"{side.upper()}_TEAM_LAST_NOT_PREMATCH")

            combined = _dedupe_latest(old_rows + fallback_rows, kickoff)
            if len(combined) < 5:
                blockers.append(f"{side.upper()}_HISTORY_BELOW_MINIMUM")
            side_results[side] = {
                "team_id": team_id,
                "team_name": team_name,
                "observed_at_utc": observed_at or (
                    existing_side.get("observed_at_utc")
                    if isinstance(existing_side, Mapping)
                    else None
                ),
                "completed_before_target": combined,
                "history_count": len(combined),
            }

        enriched_histories[target_key] = side_results
        ready = not blockers
        row = {
            "target_key": target_key,
            "fixture_id": target.get("fixture_id"),
            "kickoff_utc": target.get("kickoff_utc"),
            "home_history_count": side_results["home"]["history_count"],
            "away_history_count": side_results["away"]["history_count"],
            "ready_minimum_history": ready,
            "blockers": sorted(set(blockers)),
        }
        readiness_rows.append(row)
        if ready:
            ready_targets.append(target_key)
        else:
            blocked_targets.append(target_key)

    enriched["histories"] = enriched_histories
    enriched["unresolved_targets"] = blocked_targets
    enriched["benchmark_status"] = (
        "READY_MINIMUM_HISTORY"
        if not blocked_targets
        else "PARTIAL_HISTORY"
        if ready_targets
        else "HISTORY_BLOCKED"
    )
    enriched["team_last_fallback_network_calls"] = total_calls
    enriched["money_decisions_enabled"] = False
    enriched["analysis_mode"] = "PREMATCH_RESEARCH_ONLY"
    enriched["real_money"] = "BLOCKED"

    manifest = {
        "schema": "MATRIX_API_FOOTBALL_TEAM_LAST_FALLBACK_V1",
        "provider": "api_football",
        "deficient_unique_team_count": len(needed),
        "captured_team_count": len(captures),
        "network_calls_performed": total_calls,
        "max_requests_policy": max_requests,
        "daily_remaining_reserve_policy": min_daily_remaining_reserve,
        "stopped_reason": stopped_reason,
        "provider_error_team_count": sum(1 for row in captures if row["provider_error"]),
        "target_fixture_count": len(fixtures),
        "ready_minimum_history_count": len(ready_targets),
        "blocked_minimum_history_count": len(blocked_targets),
        "last_rate_limit": last_rate,
        "captures": captures,
        "automatic_wagering": False,
        "odds_used": False,
        "real_money": "BLOCKED",
        "status": "PASS",
    }

    _write_json(out_dir / "manifest.json", manifest)
    _write_json(out_dir / "benchmark_after_team_last.json", enriched)
    _write_json(
        out_dir / "history_readiness_after_team_last.json",
        {
            "schema": "MATRIX_API_FOOTBALL_HISTORY_READINESS_AFTER_TEAM_LAST_V1",
            "ready_minimum_history_count": len(ready_targets),
            "blocked_minimum_history_count": len(blocked_targets),
            "rows": readiness_rows,
            "real_money": "BLOCKED",
        },
    )
    return manifest


def main() -> None:
    history_root = Path("evidence/api_football/history")
    out_dir = Path("evidence/api_football/team_last_fallback")
    result = run_capture(
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        benchmark=_load(history_root / "benchmark_with_history.json"),
        readiness=_load(history_root / "history_readiness.json"),
        out_dir=out_dir,
        max_requests=int(os.environ.get("MATRIX_API_FOOTBALL_TEAM_LAST_MAX_REQUESTS", str(MAX_REQUESTS))),
        min_daily_remaining_reserve=int(os.environ.get("MATRIX_API_FOOTBALL_DAILY_RESERVE", str(MIN_DAILY_REMAINING_RESERVE))),
    )
    print(json.dumps({
        "deficient_unique_team_count": result["deficient_unique_team_count"],
        "captured_team_count": result["captured_team_count"],
        "network_calls_performed": result["network_calls_performed"],
        "provider_error_team_count": result["provider_error_team_count"],
        "ready_minimum_history_count": result["ready_minimum_history_count"],
        "blocked_minimum_history_count": result["blocked_minimum_history_count"],
        "daily_remaining": result["last_rate_limit"]["daily_remaining"],
        "status": result["status"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
