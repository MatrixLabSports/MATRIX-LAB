from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha256_text(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_prematch_queue(
    *,
    registry: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if registry.get("provider") != "api_football":
        raise ValueError("PROVIDER_MISMATCH")
    if registry.get("future_only") is not True:
        raise ValueError("FUTURE_ONLY_REQUIRED")
    protections = registry.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("PROTECTIONS_MISSING")
    if protections.get("outcomes_used") is not False:
        raise ValueError("OUTCOMES_MUST_BE_FALSE")
    if protections.get("odds_used") is not False:
        raise ValueError("ODDS_MUST_BE_FALSE")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")

    captured_at = str(registry.get("captured_at_utc") or "").strip()
    response_sha = str(manifest.get("response_sha256") or "").strip()
    if len(response_sha) != 64:
        raise ValueError("RESPONSE_SHA256_REQUIRED")

    events = registry.get("events")
    if not isinstance(events, list):
        raise ValueError("EVENTS_MUST_BE_LIST")

    fixture_map: dict[str, Any] = {}
    team_demands: dict[str, dict[str, Any]] = {}
    competition_counter: Counter[str] = Counter()
    country_counter: Counter[str] = Counter()

    for row in events:
        if not isinstance(row, Mapping):
            raise ValueError("EVENT_MUST_BE_OBJECT")
        fixture_id = str(row.get("provider_fixture_id") or "").strip()
        league_id = str(row.get("provider_league_id") or "").strip()
        home_id = str(row.get("provider_home_team_id") or "").strip()
        away_id = str(row.get("provider_away_team_id") or "").strip()
        kickoff = str(row.get("event_start_utc") or "").strip()
        home_name = str(row.get("home_team") or "").strip()
        away_name = str(row.get("away_team") or "").strip()
        competition = str(row.get("competition") or "").strip()
        country = str(row.get("country") or "").strip()
        if not all((fixture_id, league_id, home_id, away_id, kickoff, home_name, away_name, competition)):
            raise ValueError("EVENT_IDENTITY_INCOMPLETE")
        target_key = f"api_football:fixture:{fixture_id}"
        if target_key in fixture_map:
            raise ValueError("DUPLICATE_FIXTURE_ID:" + fixture_id)

        fixture_map[target_key] = {
            "fixture_id": fixture_id,
            "observed_at_utc": captured_at,
            "kickoff_utc": kickoff,
            "pre_match_frozen": True,
            "league": {
                "id": league_id,
                "name": competition,
                "country": country,
                "season": row.get("season"),
                "round": row.get("round"),
            },
            "home": {"id": home_id, "name": home_name},
            "away": {"id": away_id, "name": away_name},
            "venue": {
                "id": row.get("venue_id"),
                "name": row.get("venue_name"),
            },
            "source_payload_sha256": response_sha,
        }
        competition_counter[competition] += 1
        country_counter[country or "UNKNOWN"] += 1

        for team_id, team_name in ((home_id, home_name), (away_id, away_name)):
            key = f"api_football:team:{team_id}"
            existing = team_demands.get(key)
            if existing is None:
                team_demands[key] = {
                    "provider": "api_football",
                    "provider_team_id": team_id,
                    "team_name": team_name,
                    "required_before_utc": kickoff,
                    "minimum_history_matches": 5,
                    "preferred_history_matches": 20,
                    "target_fixture_ids": [fixture_id],
                }
            else:
                existing["target_fixture_ids"].append(fixture_id)
                if kickoff < existing["required_before_utc"]:
                    existing["required_before_utc"] = kickoff

    benchmark = {
        "schema": "MATRIX_FOOTBALL_API_FOOTBALL_PREMATCH_BENCHMARK_V1",
        "benchmark_id": f"API_FOOTBALL_FUTURE_{registry.get('target_date')}",
        "benchmark_status": "HISTORY_PENDING",
        "provider": "api_football",
        "captured_at_utc": captured_at,
        "fixture_capture_sha256": response_sha,
        "fixtures": fixture_map,
        "histories": {},
        "unresolved_targets": sorted(fixture_map),
        "money_decisions_enabled": False,
        "analysis_mode": "PREMATCH_RESEARCH_ONLY",
        "real_money": "BLOCKED",
    }

    history_queue = {
        "schema": "MATRIX_FOOTBALL_HISTORY_ACQUISITION_QUEUE_V1",
        "provider": "api_football",
        "created_from_benchmark_id": benchmark["benchmark_id"],
        "captured_at_utc": captured_at,
        "unique_teams": len(team_demands),
        "target_fixtures": len(fixture_map),
        "minimum_history_matches_per_team": 5,
        "preferred_history_matches_per_team": 20,
        "request_strategy": "BOUNDED_BY_UNIQUE_TEAM_AND_CACHE; NO_REQUESTS_EXECUTED_BY_THIS_BUILDER",
        "network_calls_performed": 0,
        "items": [team_demands[key] for key in sorted(team_demands)],
        "protections": {
            "history_must_precede_target": True,
            "same_or_future_target_outcomes_forbidden": True,
            "odds_used": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    inventory = {
        "schema": "MATRIX_FOOTBALL_WORLD_INVENTORY_V1",
        "provider": "api_football",
        "target_date": registry.get("target_date"),
        "captured_at_utc": captured_at,
        "future_fixture_count": len(fixture_map),
        "unique_team_count": len(team_demands),
        "competition_count": len(competition_counter),
        "country_count": len(country_counter),
        "competition_counts": dict(sorted(competition_counter.items())),
        "country_counts": dict(sorted(country_counter.items())),
        "benchmark_sha256": _sha256_text(benchmark),
        "history_queue_sha256": _sha256_text(history_queue),
        "real_money": "BLOCKED",
    }
    return benchmark, history_queue, inventory


def main() -> None:
    root = Path("evidence/api_football/fixtures")
    out = Path("evidence/api_football/prematch")
    benchmark, queue, inventory = build_prematch_queue(
        registry=_load(root / "future_fixture_registry.json"),
        manifest=_load(root / "capture_manifest.json"),
    )
    _write(out / "benchmark.json", benchmark)
    _write(out / "history_acquisition_queue.json", queue)
    _write(out / "world_inventory.json", inventory)
    print(json.dumps({
        "future_fixtures": inventory["future_fixture_count"],
        "unique_teams": inventory["unique_team_count"],
        "competitions": inventory["competition_count"],
        "countries": inventory["country_count"],
        "network_calls_performed": queue["network_calls_performed"],
        "real_money": inventory["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
