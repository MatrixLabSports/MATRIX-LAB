from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://api.api-tennis.com/tennis/"
POINT_CODES = {"0": 0, "15": 1, "30": 2, "40": 3, "A": 4, "AD": 4}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _pair(value: object) -> tuple[str, str] | None:
    token = str(value or "").strip().upper()
    m = re.fullmatch(r"\s*([0-9]+|A|AD)\s*-\s*([0-9]+|A|AD)\s*", token)
    if not m:
        return None
    return m.group(1), m.group(2)


def _int_pair(value: object) -> tuple[int, int] | None:
    pair = _pair(value)
    if pair is None:
        return None
    try:
        return int(pair[0]), int(pair[1])
    except ValueError:
        return None


def _set_number(status: object) -> int | None:
    m = re.search(r"\bset\s*(\d+)\b", str(status or ""), flags=re.I)
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


def _point_code(token: str) -> int | None:
    return POINT_CODES.get(token.upper())


def _score_sets(row: Mapping[str, Any]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    raw = row.get("scores")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            set_no = int(item.get("score_set"))
            p1 = int(item.get("score_first"))
            p2 = int(item.get("score_second"))
        except (TypeError, ValueError):
            continue
        if set_no <= 0 or p1 < 0 or p2 < 0:
            continue
        out.append((set_no, p1, p2))
    out.sort(key=lambda x: x[0])
    return out


def normalize_live_event(row: Mapping[str, Any], *, captured_at_utc: str, response_sha256: str) -> dict[str, Any] | None:
    event_key = str(row.get("event_key") or "").strip()
    p1 = str(row.get("event_first_player") or "").strip()
    p2 = str(row.get("event_second_player") or "").strip()
    if not event_key or not p1 or not p2:
        return None
    if str(row.get("event_live") or "").strip() not in {"1", "true", "True"}:
        return None

    event_type = str(row.get("event_type_type") or "").strip()
    status = str(row.get("event_status") or "").strip()
    set_no = _set_number(status)
    serve_raw = str(row.get("event_serve") or "").strip()
    server = 1 if serve_raw == "First Player" else 2 if serve_raw == "Second Player" else None

    point_pair = _pair(row.get("event_game_result"))
    p1_point_raw = point_pair[0] if point_pair else None
    p2_point_raw = point_pair[1] if point_pair else None
    p1_point_code = _point_code(p1_point_raw) if p1_point_raw is not None else None
    p2_point_code = _point_code(p2_point_raw) if p2_point_raw is not None else None

    sets = _score_sets(row)
    current_games = None
    if set_no is not None:
        for s, g1, g2 in sets:
            if s == set_no:
                current_games = (g1, g2)
    if current_games is None and sets:
        current_games = (sets[-1][1], sets[-1][2])

    match_sets = _int_pair(row.get("event_final_result"))
    total_game_diff = sum(g1 - g2 for _, g1, g2 in sets) if sets else None
    current_set_game_diff = current_games[0] - current_games[1] if current_games is not None else None
    set_diff = match_sets[0] - match_sets[1] if match_sets is not None else None

    semantic = {
        "event_key": event_key,
        "event_status": status,
        "event_final_result": row.get("event_final_result"),
        "event_game_result": row.get("event_game_result"),
        "event_serve": serve_raw,
        "scores": row.get("scores") if isinstance(row.get("scores"), list) else [],
        "pointbypoint_tail": (row.get("pointbypoint") or [])[-1:] if isinstance(row.get("pointbypoint"), list) else [],
    }
    state_fingerprint = _sha(semantic)

    singles = "singles" in event_type.casefold()
    quality_valid = bool(
        singles
        and set_no is not None
        and server in {1, 2}
        and current_games is not None
        and p1_point_code is not None
        and p2_point_code is not None
    )

    return {
        "state_key": f"api_tennis:{event_key}:state:{state_fingerprint[:20]}",
        "provider": "api_tennis",
        "provider_event_id": event_key,
        "match_id": event_key,
        "captured_at_utc": captured_at_utc,
        "response_sha256": response_sha256,
        "p1_name": p1,
        "p2_name": p2,
        "p1_provider_id": None if row.get("first_player_key") is None else str(row.get("first_player_key")),
        "p2_provider_id": None if row.get("second_player_key") is None else str(row.get("second_player_key")),
        "tournament": str(row.get("tournament_name") or "").strip() or None,
        "tournament_key": None if row.get("tournament_key") is None else str(row.get("tournament_key")),
        "round": str(row.get("tournament_round") or "").strip() or None,
        "event_type": event_type or None,
        "event_status": status or None,
        "event_live": True,
        "server": server,
        "server_is_p1": None if server is None else server == 1,
        "current_set_index_zero_based": None if set_no is None else set_no - 1,
        "current_set_game_diff_p1": current_set_game_diff,
        "total_game_diff_p1": total_game_diff,
        "set_diff_p1": set_diff,
        "sets_p1": None if match_sets is None else match_sets[0],
        "sets_p2": None if match_sets is None else match_sets[1],
        "point_p1_raw": p1_point_raw,
        "point_p2_raw": p2_point_raw,
        "point_p1_code": p1_point_code,
        "point_p2_code": p2_point_code,
        "point_diff_p1": None if p1_point_code is None or p2_point_code is None else p1_point_code - p2_point_code,
        "games_by_set_p1": [g1 for _, g1, _ in sets],
        "games_by_set_p2": [g2 for _, _, g2 in sets],
        "quality_state_valid": quality_valid,
        "settlement_status": "PENDING_FINAL",
        "label_opened": False,
        "origin": "paid_provider_failover_observed",
        "calibration_admitted": False,
        "calibration_blocker": "CROSS_PROVIDER_EQUIVALENCE_AND_IDENTITY_RECONCILIATION_REQUIRED",
        "automatic_model_feed": False,
    }


def _load_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("states") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(x["state_key"]): dict(x)
        for x in rows
        if isinstance(x, Mapping) and str(x.get("state_key") or "").strip()
    }


def collect(*, operational_date: str, cycles: int, interval_seconds: int, out: Path) -> dict[str, Any]:
    key = os.environ.get("API_TENNIS_KEY", "").strip()
    if not key:
        raise ValueError("API_TENNIS_KEY_NOT_CONFIGURED")
    if cycles < 0 or cycles > 24:
        raise ValueError("CYCLES_OUT_OF_RANGE")
    if interval_seconds < 1:
        raise ValueError("INTERVAL_SECONDS_INVALID")

    existing = _load_existing(out)
    cycle_reports: list[dict[str, Any]] = []
    new_keys: set[str] = set()

    for index in range(cycles):
        captured = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        r = requests.get(
            BASE_URL,
            params={"method": "get_livescore", "APIkey": key, "timezone": "UTC"},
            timeout=(10, 30),
        )
        raw = bytes(r.content)
        raw_sha = hashlib.sha256(raw).hexdigest()
        try:
            payload = r.json()
        except Exception:
            payload = {}
        result = payload.get("result") if isinstance(payload, Mapping) else None
        if r.status_code != 200 or not isinstance(result, list):
            raise RuntimeError(f"API_TENNIS_LIVESCORE_INVALID:http={r.status_code}")

        normalized = []
        for row in result:
            if not isinstance(row, Mapping):
                continue
            state = normalize_live_event(row, captured_at_utc=captured, response_sha256=raw_sha)
            if state is None:
                continue
            normalized.append(state)
            if state["state_key"] not in existing:
                existing[state["state_key"]] = state
                new_keys.add(state["state_key"])

        cycle_reports.append({
            "cycle": index + 1,
            "captured_at_utc": captured,
            "http_status": r.status_code,
            "provider_live_rows": len(result),
            "normalized_live_rows": len(normalized),
            "quality_valid_rows": sum(1 for x in normalized if x["quality_state_valid"]),
            "response_sha256": raw_sha,
        })
        if index < cycles - 1:
            time.sleep(interval_seconds)

    states = sorted(existing.values(), key=lambda x: (x.get("captured_at_utc") or "", str(x.get("match_id") or ""), x["state_key"]))
    matches = {str(x.get("match_id")) for x in states if x.get("match_id") is not None}

    ledger = {
        "schema": "MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1",
        "operational_date_bogota": operational_date,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "api_tennis",
        "provider_endpoint": "get_livescore",
        "role": "PAID_FAILOVER_WHEN_FREE_LIVE_PROVIDER_QUOTA_UNAVAILABLE",
        "requested_cycles": cycles,
        "executed_cycles": len(cycle_reports),
        "new_states_this_run": len(new_keys),
        "unique_match_count": len(matches),
        "unique_state_count": len(states),
        "quality_valid_state_count": sum(1 for x in states if x.get("quality_state_valid") is True),
        "states": states,
        "cycle_reports": cycle_reports,
        "calibration_admission": {
            "admitted": False,
            "reason": "CROSS_PROVIDER_EQUIVALENCE_AND_IDENTITY_RECONCILIATION_REQUIRED",
            "existing_live_tennis_api_gate_unchanged": True,
        },
        "protections": {
            "secrets_persisted": False,
            "target_outcomes_read": False,
            "odds_used_to_generate_probability": False,
            "missing_not_zero": True,
            "silent_imputation": False,
            "automatic_model_feed": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS" if len(cycle_reports) == cycles else "PARTIAL",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ledger


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--cycles", type=int, default=6)
    p.add_argument("--interval-seconds", type=int, default=12)
    p.add_argument("--out")
    a = p.parse_args()
    out = Path(a.out) if a.out else Path(
        f"evidence/live_tennis_lab/{a.date}/MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json"
    )
    result = collect(
        operational_date=a.date,
        cycles=a.cycles,
        interval_seconds=a.interval_seconds,
        out=out,
    )
    print(json.dumps({
        "status": result["status"],
        "provider": result["provider"],
        "executed_cycles": result["executed_cycles"],
        "new_states_this_run": result["new_states_this_run"],
        "unique_match_count": result["unique_match_count"],
        "unique_state_count": result["unique_state_count"],
        "quality_valid_state_count": result["quality_valid_state_count"],
        "calibration_admitted": result["calibration_admission"]["admitted"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
