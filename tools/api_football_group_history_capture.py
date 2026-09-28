from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests


BASE_URL = "https://v3.football.api-sports.io"
ENDPOINT = "/fixtures"
TIMEOUT_SECONDS = 30.0
MAX_REQUESTS = 40
MIN_DAILY_REMAINING_RESERVE = 40
FINAL_STATUSES = {"FT", "AET", "PEN"}
PUBLIC_HEADER_ALLOWLIST = (
    "content-type",
    "date",
    "x-ratelimit-requests-limit",
    "x-ratelimit-requests-remaining",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
)


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


def _parse_aware(value: object) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _final_history_row(raw: Any, *, source_sha256: str, source_reference: str) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    fixture = raw.get("fixture")
    league = raw.get("league")
    teams = raw.get("teams")
    goals = raw.get("goals")
    if not all(isinstance(x, Mapping) for x in (fixture, league, teams, goals)):
        return None
    status = fixture.get("status")
    home = teams.get("home")
    away = teams.get("away")
    if not all(isinstance(x, Mapping) for x in (status, home, away)):
        return None
    status_short = str(status.get("short") or "").upper().strip()
    if status_short not in FINAL_STATUSES:
        return None
    fixture_id = _positive_int(fixture.get("id"))
    home_id = _positive_int(home.get("id"))
    away_id = _positive_int(away.get("id"))
    kickoff = _parse_aware(fixture.get("date"))
    home_goals = goals.get("home")
    away_goals = goals.get("away")
    if (
        fixture_id is None
        or home_id is None
        or away_id is None
        or kickoff is None
        or isinstance(home_goals, bool)
        or isinstance(away_goals, bool)
        or not isinstance(home_goals, int)
        or not isinstance(away_goals, int)
        or home_goals < 0
        or away_goals < 0
    ):
        return None
    home_name = str(home.get("name") or "").strip()
    away_name = str(away.get("name") or "").strip()
    if not home_name or not away_name:
        return None
    return {
        "fixture_id": str(fixture_id),
        "kickoff_utc": kickoff.isoformat(),
        "home_team_id": str(home_id),
        "away_team_id": str(away_id),
        "home_team": home_name,
        "away_team": away_name,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "competition": str(league.get("name") or "").strip() or None,
        "provider_status": status_short,
        "source_payload_sha256": source_sha256,
        "source_reference": source_reference,
    }


def _group_targets(benchmark: Mapping[str, Any]) -> list[dict[str, Any]]:
    fixtures = benchmark.get("fixtures")
    if not isinstance(fixtures, Mapping):
        raise ValueError("BENCHMARK_FIXTURES_MISSING")
    groups: dict[tuple[str, int], dict[str, Any]] = {}
    for target_key, target in fixtures.items():
        if not isinstance(target, Mapping):
            raise ValueError("TARGET_FIXTURE_NOT_OBJECT")
        league = target.get("league")
        if not isinstance(league, Mapping):
            raise ValueError("TARGET_LEAGUE_MISSING")
        league_id = str(league.get("id") or "").strip()
        season_raw = league.get("season")
        kickoff = _parse_aware(target.get("kickoff_utc"))
        if not league_id or isinstance(season_raw, bool) or not isinstance(season_raw, int) or season_raw <= 0 or kickoff is None:
            raise ValueError("TARGET_GROUP_IDENTITY_INCOMPLETE")
        key = (league_id, season_raw)
        group = groups.setdefault(
            key,
            {
                "league_id": league_id,
                "season": season_raw,
                "competition": str(league.get("name") or "").strip(),
                "target_keys": [],
                "earliest_kickoff_utc": kickoff.isoformat(),
            },
        )
        group["target_keys"].append(str(target_key))
        if kickoff < _parse_aware(group["earliest_kickoff_utc"]):
            group["earliest_kickoff_utc"] = kickoff.isoformat()

    ordered = list(groups.values())
    ordered.sort(key=lambda row: (-len(row["target_keys"]), row["earliest_kickoff_utc"], int(row["league_id"])))
    return ordered


def _read_rate(headers: Mapping[str, Any]) -> dict[str, str | None]:
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    return {
        "daily_limit": lower.get("x-ratelimit-requests-limit"),
        "daily_remaining": lower.get("x-ratelimit-requests-remaining"),
        "minute_limit": lower.get("x-ratelimit-limit"),
        "minute_remaining": lower.get("x-ratelimit-remaining"),
    }


def capture_group_history(
    *,
    api_key: str,
    benchmark: Mapping[str, Any],
    out_dir: Path,
    session: Any | None = None,
    max_requests: int = MAX_REQUESTS,
    min_daily_remaining_reserve: int = MIN_DAILY_REMAINING_RESERVE,
    now_fn: Any | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    try:
        key.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("API_FOOTBALL_KEY_MUST_BE_ASCII") from error
    if max_requests <= 0 or max_requests > MAX_REQUESTS:
        raise ValueError("MAX_REQUESTS_OUT_OF_POLICY")
    if min_daily_remaining_reserve < 0:
        raise ValueError("MIN_DAILY_REMAINING_RESERVE_INVALID")

    provider = str(benchmark.get("provider") or "").strip()
    if provider != "api_football":
        raise ValueError("BENCHMARK_PROVIDER_MISMATCH")
    fixtures = benchmark.get("fixtures")
    if not isinstance(fixtures, Mapping):
        raise ValueError("BENCHMARK_FIXTURES_MISSING")

    groups = _group_targets(benchmark)
    client = session or requests.Session()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    now = now_fn or (lambda: datetime.now(timezone.utc).replace(microsecond=0))

    captures: list[dict[str, Any]] = []
    history_by_group: dict[tuple[str, int], list[dict[str, Any]]] = {}
    total_calls = 0
    stopped_reason: str | None = None
    last_rate: dict[str, str | None] = {
        "daily_limit": None,
        "daily_remaining": None,
        "minute_limit": None,
        "minute_remaining": None,
    }

    for group in groups:
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

        league_id = str(group["league_id"])
        season = int(group["season"])
        params = {"league": league_id, "season": season, "timezone": "UTC"}
        started = now()
        response = client.get(
            BASE_URL + ENDPOINT,
            headers={"x-apisports-key": key},
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        observed = now()
        total_calls += 1
        body = bytes(response.content)
        raw_name = f"league_{league_id}_season_{season}.bin"
        raw_path = raw_dir / raw_name
        raw_path.write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()
        public_headers = {
            name.lower(): value
            for name, value in response.headers.items()
            if name.lower() in PUBLIC_HEADER_ALLOWLIST
        }
        last_rate = _read_rate(public_headers)
        if not (200 <= int(response.status_code) < 300):
            raise ValueError(f"API_FOOTBALL_HISTORY_HTTP_STATUS_{response.status_code}")

        parsed = response.json()
        errors = parsed.get("errors") if isinstance(parsed, Mapping) else None
        rows = parsed.get("response") if isinstance(parsed, Mapping) else None
        if errors not in ({}, [], None):
            raise ValueError(f"API_FOOTBALL_HISTORY_PROVIDER_ERRORS:{league_id}:{season}")
        if not isinstance(rows, list):
            raise ValueError(f"API_FOOTBALL_HISTORY_RESPONSE_INVALID:{league_id}:{season}")

        source_reference = f"api_football:/fixtures?league={league_id}&season={season}"
        finals = [
            item
            for raw in rows
            for item in [_final_history_row(raw, source_sha256=sha, source_reference=source_reference)]
            if item is not None
        ]
        finals.sort(key=lambda row: (row["kickoff_utc"], int(row["fixture_id"])))
        history_by_group[(league_id, season)] = finals
        captures.append(
            {
                "league_id": league_id,
                "season": season,
                "competition": group.get("competition"),
                "target_fixture_count": len(group["target_keys"]),
                "request_started_at_utc": started.isoformat(),
                "response_observed_at_utc": observed.isoformat(),
                "http_status": int(response.status_code),
                "raw_path": str(raw_path),
                "raw_sha256": sha,
                "response_bytes": len(body),
                "provider_rows": len(rows),
                "final_history_rows": len(finals),
                "rate_limit": last_rate,
            }
        )

    histories: dict[str, Any] = {}
    readiness_rows: list[dict[str, Any]] = []
    resolved_targets: list[str] = []
    unresolved_targets: list[str] = []

    capture_by_group = {
        (row["league_id"], int(row["season"])): row for row in captures
    }
    for target_key, target in sorted(fixtures.items()):
        league = target["league"]
        group_key = (str(league["id"]), int(league["season"]))
        capture = capture_by_group.get(group_key)
        kickoff = _parse_aware(target["kickoff_utc"])
        assert kickoff is not None
        home = target["home"]
        away = target["away"]
        home_id = str(home["id"])
        away_id = str(away["id"])
        blockers: list[str] = []

        if capture is None:
            blockers.append("HISTORY_GROUP_NOT_CAPTURED")
            observed_at = None
            available_rows: list[dict[str, Any]] = []
        else:
            observed_at = _parse_aware(capture["response_observed_at_utc"])
            if observed_at is None or observed_at >= kickoff:
                blockers.append("HISTORY_CAPTURE_NOT_PREMATCH")
                available_rows = []
            else:
                available_rows = [
                    row
                    for row in history_by_group.get(group_key, [])
                    if _parse_aware(row["kickoff_utc"]) < kickoff
                ]

        home_rows = [
            row for row in available_rows
            if home_id in {row["home_team_id"], row["away_team_id"]}
        ]
        away_rows = [
            row for row in available_rows
            if away_id in {row["home_team_id"], row["away_team_id"]}
        ]
        home_rows.sort(key=lambda row: row["kickoff_utc"], reverse=True)
        away_rows.sort(key=lambda row: row["kickoff_utc"], reverse=True)
        home_rows = home_rows[:20]
        away_rows = away_rows[:20]
        if len(home_rows) < 5:
            blockers.append("HOME_HISTORY_BELOW_MINIMUM")
        if len(away_rows) < 5:
            blockers.append("AWAY_HISTORY_BELOW_MINIMUM")

        histories[target_key] = {
            "home": {
                "team_id": home_id,
                "team_name": home["name"],
                "observed_at_utc": None if observed_at is None else observed_at.isoformat(),
                "completed_before_target": home_rows,
            },
            "away": {
                "team_id": away_id,
                "team_name": away["name"],
                "observed_at_utc": None if observed_at is None else observed_at.isoformat(),
                "completed_before_target": away_rows,
            },
        }
        ready = not blockers
        if ready:
            resolved_targets.append(target_key)
        else:
            unresolved_targets.append(target_key)
        readiness_rows.append(
            {
                "target_key": target_key,
                "fixture_id": target["fixture_id"],
                "kickoff_utc": target["kickoff_utc"],
                "home_history_count": len(home_rows),
                "away_history_count": len(away_rows),
                "ready_minimum_history": ready,
                "blockers": sorted(set(blockers)),
            }
        )

    enriched = dict(benchmark)
    enriched["histories"] = histories
    enriched["unresolved_targets"] = unresolved_targets
    enriched["benchmark_status"] = (
        "READY_MINIMUM_HISTORY"
        if not unresolved_targets
        else "PARTIAL_HISTORY"
        if resolved_targets
        else "HISTORY_BLOCKED"
    )
    enriched["history_capture_reference"] = "MATRIX_API_FOOTBALL_GROUP_HISTORY_CAPTURE_V1"
    enriched["history_network_calls"] = total_calls
    enriched["money_decisions_enabled"] = False
    enriched["analysis_mode"] = "PREMATCH_RESEARCH_ONLY"
    enriched["real_money"] = "BLOCKED"

    summary = {
        "schema": "MATRIX_API_FOOTBALL_GROUP_HISTORY_CAPTURE_V1",
        "provider": "api_football",
        "endpoint": ENDPOINT,
        "requested_group_count": len(groups),
        "captured_group_count": len(captures),
        "network_calls_performed": total_calls,
        "max_requests_policy": max_requests,
        "daily_remaining_reserve_policy": min_daily_remaining_reserve,
        "stopped_reason": stopped_reason,
        "target_fixture_count": len(fixtures),
        "ready_minimum_history_count": len(resolved_targets),
        "blocked_minimum_history_count": len(unresolved_targets),
        "last_rate_limit": last_rate,
        "captures": captures,
        "readiness": readiness_rows,
        "automatic_wagering": False,
        "odds_used": False,
        "real_money": "BLOCKED",
        "status": "PASS",
    }

    _write_json(out_dir / "history_capture_manifest.json", summary)
    _write_json(out_dir / "benchmark_with_history.json", enriched)
    _write_json(
        out_dir / "history_readiness.json",
        {
            "schema": "MATRIX_API_FOOTBALL_HISTORY_READINESS_V1",
            "ready_minimum_history_count": len(resolved_targets),
            "blocked_minimum_history_count": len(unresolved_targets),
            "rows": readiness_rows,
            "real_money": "BLOCKED",
        },
    )
    return summary


def main() -> None:
    prematch = Path("evidence/api_football/prematch")
    out_dir = Path(os.environ.get("MATRIX_API_FOOTBALL_HISTORY_DIR", "evidence/api_football/history"))
    result = capture_group_history(
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        benchmark=_load(prematch / "benchmark.json"),
        out_dir=out_dir,
        max_requests=int(os.environ.get("MATRIX_API_FOOTBALL_HISTORY_MAX_REQUESTS", str(MAX_REQUESTS))),
        min_daily_remaining_reserve=int(
            os.environ.get(
                "MATRIX_API_FOOTBALL_DAILY_RESERVE",
                str(MIN_DAILY_REMAINING_RESERVE),
            )
        ),
    )
    print(json.dumps({
        "requested_group_count": result["requested_group_count"],
        "captured_group_count": result["captured_group_count"],
        "network_calls_performed": result["network_calls_performed"],
        "ready_minimum_history_count": result["ready_minimum_history_count"],
        "blocked_minimum_history_count": result["blocked_minimum_history_count"],
        "daily_remaining": result["last_rate_limit"]["daily_remaining"],
        "stopped_reason": result["stopped_reason"],
        "status": result["status"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
