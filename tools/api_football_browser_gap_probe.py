from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT = 20
INPUT = Path("evidence/daily_source_counts/2026-10-06/MATRIX_IMMEDIATE_BROWSER_GAP_RECONCILIATION.json")
OUTPUT = Path("evidence/daily_source_counts/2026-10-06/MATRIX_API_FOOTBALL_BROWSER_GAP_PROBE.json")


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.casefold().replace("fc", " ").split())


def call(session: requests.Session, key: str, endpoint: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    url = BASE_URL + endpoint
    response = session.get(url, headers={"x-apisports-key": key}, params=params, timeout=TIMEOUT)
    body = bytes(response.content)
    meta = {
        "endpoint": endpoint,
        "params": params,
        "http_status": int(response.status_code),
        "response_bytes": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }
    if not 200 <= response.status_code < 300:
        return {"errors": [f"HTTP_{response.status_code}"], "response": []}, meta
    parsed = response.json()
    return parsed if isinstance(parsed, dict) else {"errors": ["NON_OBJECT"], "response": []}, meta


def exact_team_id(rows: list[Any], wanted: str) -> int | None:
    wn = norm(wanted)
    exact = []
    loose = []
    for row in rows:
        team = row.get("team") if isinstance(row, dict) else None
        if not isinstance(team, dict):
            continue
        name = str(team.get("name") or "")
        tid = team.get("id")
        if not isinstance(tid, int):
            continue
        nn = norm(name)
        if nn == wn:
            exact.append(tid)
        elif wn in nn or nn in wn:
            loose.append(tid)
    if len(set(exact)) == 1:
        return exact[0]
    if not exact and len(set(loose)) == 1:
        return loose[0]
    return None


def main() -> None:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    gaps = source["football"]["browser_only_future_gaps_confirmed_absent_from_api_future_registry"]
    session = requests.Session()
    records = []
    calls = []
    bound = []

    for gap in gaps:
        home, away = [part.strip() for part in gap["match"].split(" - ", 1)]
        home_payload, meta = call(session, key, "/teams", {"search": home})
        calls.append(meta)
        away_payload, meta = call(session, key, "/teams", {"search": away})
        calls.append(meta)
        home_rows = home_payload.get("response") if isinstance(home_payload.get("response"), list) else []
        away_rows = away_payload.get("response") if isinstance(away_payload.get("response"), list) else []
        home_id = exact_team_id(home_rows, home)
        away_id = exact_team_id(away_rows, away)
        record = {
            "match": gap["match"],
            "start_utc": gap["start_utc"],
            "home_team_id": home_id,
            "away_team_id": away_id,
            "fixture_id": None,
            "status": "BLOCKED_TEAM_BINDING",
        }
        if home_id is not None and away_id is not None:
            fixtures, meta = call(
                session,
                key,
                "/fixtures",
                {"team": home_id, "date": "2026-10-06", "timezone": "America/Bogota"},
            )
            calls.append(meta)
            rows = fixtures.get("response") if isinstance(fixtures.get("response"), list) else []
            matches = []
            for row in rows:
                teams = row.get("teams") if isinstance(row, dict) else None
                fixture = row.get("fixture") if isinstance(row, dict) else None
                if not isinstance(teams, dict) or not isinstance(fixture, dict):
                    continue
                h = teams.get("home") if isinstance(teams.get("home"), dict) else {}
                a = teams.get("away") if isinstance(teams.get("away"), dict) else {}
                if {h.get("id"), a.get("id")} == {home_id, away_id}:
                    matches.append(row)
            if len(matches) == 1:
                row = matches[0]
                fixture = row["fixture"]
                record["fixture_id"] = fixture.get("id")
                record["provider_start"] = fixture.get("date")
                record["provider_status_short"] = (fixture.get("status") or {}).get("short")
                record["league"] = (row.get("league") or {}).get("name")
                record["country"] = (row.get("league") or {}).get("country")
                record["status"] = "PROVIDER_FIXTURE_BOUND"
                bound.append(record["match"])
            else:
                record["status"] = "BLOCKED_NO_EXACT_FIXTURE_ON_DATE"
        records.append(record)

    payload = {
        "schema": "MATRIX_API_FOOTBALL_BROWSER_GAP_PROBE_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_date_bogota": "2026-10-06",
        "input_gap_count": len(gaps),
        "network_calls": len(calls),
        "bound_fixture_count": len(bound),
        "bound_matches": bound,
        "records": records,
        "request_evidence": calls,
        "protections": {
            "name_only_binding_used_for_model": False,
            "automatic_model_feed": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "input_gap_count": payload["input_gap_count"],
        "network_calls": payload["network_calls"],
        "bound_fixture_count": payload["bound_fixture_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
