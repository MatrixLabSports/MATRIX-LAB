from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

BOGOTA = ZoneInfo("America/Bogota")
TIMEOUT = 25


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def call(url: str, *, headers: dict[str, str], params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    body = bytes(r.content)
    meta = {
        "url": url,
        "params": params,
        "http_status": int(r.status_code),
        "response_bytes": len(body),
        "response_sha256": sha(body),
        "content_type": r.headers.get("content-type"),
    }
    try:
        parsed = r.json()
    except Exception:
        parsed = {"_non_json": True}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    return parsed, meta


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Bogota operational date YYYY-MM-DD")
    args = parser.parse_args()
    target = datetime.strptime(args.date, "%Y-%m-%d").date()

    football_key = os.environ.get("FOOTBALL_DATA_ORG_KEY", "").strip()
    tennis_key = os.environ.get("LIVE_TENNIS_API_KEY", "").strip()
    if not football_key:
        raise SystemExit("FOOTBALL_DATA_ORG_KEY_NOT_CONFIGURED")
    if not tennis_key:
        raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")

    football, football_meta = call(
        "https://api.football-data.org/v4/matches",
        headers={"X-Auth-Token": football_key},
        params={"dateFrom": args.date, "dateTo": args.date},
    )
    football_rows = football.get("matches") if isinstance(football.get("matches"), list) else []
    sanitized_football = []
    competition_counter: Counter[str] = Counter()
    for row in football_rows:
        if not isinstance(row, dict):
            continue
        comp = row.get("competition") if isinstance(row.get("competition"), dict) else {}
        home = row.get("homeTeam") if isinstance(row.get("homeTeam"), dict) else {}
        away = row.get("awayTeam") if isinstance(row.get("awayTeam"), dict) else {}
        comp_name = str(comp.get("name") or "UNKNOWN")
        competition_counter[comp_name] += 1
        sanitized_football.append({
            "provider_match_id": row.get("id"),
            "utc_date": row.get("utcDate"),
            "status": row.get("status"),
            "competition_id": comp.get("id"),
            "competition_code": comp.get("code"),
            "competition": comp_name,
            "home_team_id": home.get("id"),
            "home_team": home.get("name"),
            "away_team_id": away.get("id"),
            "away_team": away.get("name"),
        })

    tennis, tennis_meta = call(
        "https://api.livetennisapi.com/api/public/v1/fixtures",
        headers={"X-API-Key": tennis_key},
        params={"tour": "challenger", "draw": "singles", "gender": "men", "limit": 200, "offset": 0},
    )
    tennis_rows = tennis.get("data") if isinstance(tennis.get("data"), list) else []
    horizon_end = target + timedelta(days=2)
    horizon = []
    target_day = []
    hard_horizon = []
    hard_target_day = []
    for row in tennis_rows:
        if not isinstance(row, dict):
            continue
        start = parse_iso(row.get("start_time"))
        event_date = row.get("event_date")
        local_date = start.astimezone(BOGOTA).date() if start else None
        if local_date is None and isinstance(event_date, str):
            try:
                local_date = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
            except ValueError:
                local_date = None
        clean = {
            "provider_match_id": row.get("id"),
            "event_date": event_date,
            "start_time_utc": row.get("start_time"),
            "bogota_date": local_date.isoformat() if local_date else None,
            "tour": row.get("tour"),
            "tournament": row.get("tournament"),
            "round": row.get("round"),
            "round_code": row.get("round_code"),
            "surface": row.get("surface"),
            "is_qualifying": row.get("is_qualifying"),
            "player1_id": row.get("player1_id"),
            "player1_name": row.get("player1_name"),
            "player2_id": row.get("player2_id"),
            "player2_name": row.get("player2_name"),
            "status": row.get("status"),
        }
        if local_date and target <= local_date <= horizon_end:
            horizon.append(clean)
            if str(row.get("surface") or "").strip().casefold() == "hard":
                hard_horizon.append(clean)
        if local_date == target:
            target_day.append(clean)
            if str(row.get("surface") or "").strip().casefold() == "hard":
                hard_target_day.append(clean)

    payload = {
        "schema": "MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_date_bogota": args.date,
        "timezone": "America/Bogota",
        "providers": {
            "football_data_org": {
                "role": "AUXILIARY_STRUCTURED_COVERAGE_AND_IDENTITY_CROSSCHECK",
                "authenticated": football_meta["http_status"] == 200,
                "request": football_meta,
                "accessible_matches_on_target_date": len(sanitized_football),
                "competition_counts": dict(sorted(competition_counter.items())),
                "matches": sanitized_football,
                "world_complete": False,
            },
            "live_tennis_api": {
                "role": "AUXILIARY_CHALLENGER_DISCOVERY_IDENTITY_AND_GAP_CROSSCHECK",
                "authenticated": tennis_meta["http_status"] == 200,
                "request": tennis_meta,
                "query_scope": {
                    "tour": "challenger",
                    "draw": "singles",
                    "gender": "men",
                    "note": "Provider challenger filter plus men narrows to men's Challenger singles; MATRIX still independently enforces ATP Challenger Hard Singles domain and PIT/history gates."
                },
                "returned_fixture_rows": len(tennis_rows),
                "d0_d2_rows": len(horizon),
                "d0_rows": len(target_day),
                "d0_d2_hard_rows": len(hard_horizon),
                "d0_hard_rows": len(hard_target_day),
                "d0_d2_hard_candidates": hard_horizon,
                "world_complete": False,
            },
        },
        "promotion": {
            "automatic_model_feed": False,
            "automatic_counter_increment": False,
            "reconcile_against_sofascore_flashscore_paid_apis_first": True,
            "canonical_identity_and_physical_dedup_required": True,
            "pit_history_gate_required": True,
        },
        "protections": {
            "secrets_persisted": False,
            "secrets_echoed": False,
            "missing_not_zero": True,
            "silent_imputation": False,
            "odds_to_probability": False,
            "metrics_opened": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS" if football_meta["http_status"] == 200 and tennis_meta["http_status"] == 200 else "BLOCKED",
    }

    out = Path(f"evidence/free_providers/{args.date}/MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "football_matches": len(sanitized_football),
        "tennis_rows_returned": len(tennis_rows),
        "tennis_d0_d2_hard": len(hard_horizon),
        "tennis_d0_hard": len(hard_target_day),
    }, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
