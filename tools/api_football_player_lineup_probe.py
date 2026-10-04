from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT_SECONDS = 20.0
DEFAULT_WINDOW_MINUTES = 90
DEFAULT_MAX_FIXTURES = 6
DEFAULT_DAILY_RESERVE = 5000


def _utc(value: object) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _candidate_events(now: datetime, window_minutes: int, max_fixtures: int) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted(Path("evidence/api_football/prospective_daily").glob("*/*/fixtures/future_fixture_registry.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        captured = str(payload.get("captured_at_utc") or "")
        for event in payload.get("events") or []:
            if not isinstance(event, Mapping):
                continue
            fid = str(event.get("provider_fixture_id") or "").strip()
            start_raw = event.get("event_start_utc")
            if not fid or not start_raw:
                continue
            start = _utc(start_raw)
            if not (now < start <= now + timedelta(minutes=window_minutes)):
                continue
            row = dict(event)
            row["_registry_path"] = str(path)
            row["_registry_captured_at_utc"] = captured
            prior = latest.get(fid)
            if prior is None or str(prior.get("_registry_captured_at_utc") or "") < captured:
                latest[fid] = row
    rows = sorted(latest.values(), key=lambda r: (_utc(r["event_start_utc"]), int(r["provider_fixture_id"])))
    return rows[:max_fixtures]


def _parse_lineups(payload: Mapping[str, Any]) -> dict[str, Any]:
    teams = []
    for team_row in payload.get("response") or []:
        if not isinstance(team_row, Mapping):
            continue
        team = team_row.get("team") if isinstance(team_row.get("team"), Mapping) else {}
        start_xi = team_row.get("startXI") if isinstance(team_row.get("startXI"), list) else []
        substitutes = team_row.get("substitutes") if isinstance(team_row.get("substitutes"), list) else []

        def player_rows(values: list[Any]) -> list[dict[str, Any]]:
            out = []
            for item in values:
                if not isinstance(item, Mapping):
                    continue
                p = item.get("player") if isinstance(item.get("player"), Mapping) else {}
                pid = p.get("id")
                if pid is None:
                    continue
                out.append({
                    "player_id": str(pid),
                    "player_name": p.get("name"),
                    "number": p.get("number"),
                    "pos": p.get("pos"),
                    "grid": p.get("grid"),
                })
            return out

        starters = player_rows(start_xi)
        bench = player_rows(substitutes)
        teams.append({
            "team_id": str(team.get("id") or ""),
            "team_name": team.get("name"),
            "formation": team_row.get("formation"),
            "coach_id": str((team_row.get("coach") or {}).get("id") or "") if isinstance(team_row.get("coach"), Mapping) else "",
            "starting_xi": starters,
            "substitutes": bench,
            "starting_xi_count": len(starters),
            "substitute_count": len(bench),
        })
    return {
        "team_count": len(teams),
        "starting_xi_count": sum(x["starting_xi_count"] for x in teams),
        "substitute_count": sum(x["substitute_count"] for x in teams),
        "teams": teams,
    }


def run(
    api_key: str,
    out_root: Path,
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    max_fixtures: int = DEFAULT_MAX_FIXTURES,
    daily_reserve: int = DEFAULT_DAILY_RESERVE,
    session: Any | None = None,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    if not 1 <= max_fixtures <= 12:
        raise ValueError("MAX_FIXTURES_OUT_OF_POLICY")
    if not 15 <= window_minutes <= 240:
        raise ValueError("WINDOW_MINUTES_OUT_OF_POLICY")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    candidates = _candidate_events(now, window_minutes, max_fixtures)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / "runs" / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()

    rows = []
    last_daily_remaining = None
    for event in candidates:
        if last_daily_remaining is not None and int(last_daily_remaining) <= daily_reserve:
            break
        fid = str(event["provider_fixture_id"])
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        response = client.get(
            BASE_URL + "/fixtures/lineups",
            headers={"x-apisports-key": key},
            params={"fixture": fid},
            timeout=TIMEOUT_SECONDS,
        )
        body = bytes(response.content)
        raw_path = raw_dir / f"fixture_{fid}_lineups.bin"
        raw_path.write_bytes(body)
        raw_sha = hashlib.sha256(body).hexdigest()
        last_daily_remaining = response.headers.get("x-ratelimit-requests-remaining")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        errors = payload.get("errors") if isinstance(payload, Mapping) else None
        provider_ok = 200 <= int(response.status_code) < 300 and errors in ({}, [], None)
        parsed = _parse_lineups(payload) if provider_ok and isinstance(payload, Mapping) else {
            "team_count": 0, "starting_xi_count": 0, "substitute_count": 0, "teams": []
        }
        kickoff = _utc(event["event_start_utc"])
        rows.append({
            "fixture_id": fid,
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "competition": event.get("competition"),
            "kickoff_utc": kickoff.isoformat(),
            "observed_at_utc": observed_at.isoformat(),
            "observation_pre_kickoff": observed_at < kickoff,
            "minutes_before_kickoff": (kickoff - observed_at).total_seconds() / 60.0,
            "http_status": int(response.status_code),
            "provider_ok": provider_ok,
            "provider_errors": errors,
            "raw_path": str(raw_path),
            "raw_sha256": raw_sha,
            "lineup_present": parsed["starting_xi_count"] > 0,
            **parsed,
        })

    lineup_rows = [r for r in rows if r["lineup_present"] and r["observation_pre_kickoff"]]
    manifest = {
        "schema": "MATRIX_API_FOOTBALL_PREMATCH_LINEUP_PROBE_V1",
        "run_id": run_id,
        "observed_at_utc": now.isoformat(),
        "provider": "api_football",
        "endpoint": "/fixtures/lineups",
        "candidate_window_minutes": window_minutes,
        "candidate_count": len(candidates),
        "network_calls": len(rows),
        "last_daily_remaining": last_daily_remaining,
        "daily_reserve_policy": daily_reserve,
        "fixtures": rows,
        "prematch_lineup_observed_count": len(lineup_rows),
        "prematch_lineup_source_certified_this_run": bool(lineup_rows),
        "expected_minutes_certified": False,
        "player_shots_prospective_unlocked": False,
        "odds_used_to_generate_probability": False,
        "outcomes_used_to_generate_probability": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS_WITH_PREMATCH_LINEUP_EVIDENCE" if lineup_rows else "PASS_NO_PREMATCH_LINEUP_OBSERVED",
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    pointer = {
        "schema": "MATRIX_API_FOOTBALL_PREMATCH_LINEUP_PROBE_POINTER_V1",
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "status": manifest["status"],
        "prematch_lineup_observed_count": len(lineup_rows),
        "expected_minutes_certified": False,
        "player_shots_prospective_unlocked": False,
        "real_money": "BLOCKED",
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "last_run.json").write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    result = run(
        os.environ.get("API_FOOTBALL_KEY", ""),
        Path(os.environ.get(
            "MATRIX_PLAYER_LINEUP_PROBE_DIR",
            "evidence/api_football/market_expansion/player_lineup_probe",
        )),
        window_minutes=int(os.environ.get("MATRIX_LINEUP_WINDOW_MINUTES", str(DEFAULT_WINDOW_MINUTES))),
        max_fixtures=int(os.environ.get("MATRIX_LINEUP_MAX_FIXTURES", str(DEFAULT_MAX_FIXTURES))),
        daily_reserve=int(os.environ.get("MATRIX_API_FOOTBALL_DAILY_RESERVE", str(DEFAULT_DAILY_RESERVE))),
    )
    print(json.dumps({
        "status": result["status"],
        "candidate_count": result["candidate_count"],
        "network_calls": result["network_calls"],
        "prematch_lineup_observed_count": result["prematch_lineup_observed_count"],
        "expected_minutes_certified": result["expected_minutes_certified"],
        "player_shots_prospective_unlocked": result["player_shots_prospective_unlocked"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
