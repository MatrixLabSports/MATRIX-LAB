from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests

BASE = "https://tennis-api-atp-wta-itf.p.rapidapi.com"
HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
LIVE_PATH = "/tennis/v2/extend/api/events/live"
STATS_PATH = "/tennis/v2/extend/api/event/data/statistics/{p1}/{p2}"
TIMELINE_PATH = "/tennis/v2/extend/api/event/timeline/{event_id}"
DEFAULT_OUT = Path("evidence/tennis_serve_stats_lab/MATRIX_TENNIS_SERVE_STATS_LAB_LAST.json")
MARKET_KEYS = ("ACES", "DOUBLE_FAULTS", "BREAKS_OF_SERVE")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metric_value(period: Mapping[str, Any], category: str, metric: str, player: str) -> float | None:
    node = _mapping(_mapping(_mapping(period.get(category)).get(metric)).get(player))
    value = node.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _extract_stats(payload: Mapping[str, Any]) -> dict[str, Any]:
    statistics = _mapping(payload.get("statistics"))
    period = _mapping(statistics.get("ALL"))
    return {
        "aces": {
            "player1": _metric_value(period, "service", "aces", "player1"),
            "player2": _metric_value(period, "service", "aces", "player2"),
        },
        "double_faults": {
            "player1": _metric_value(period, "service", "doubleFaults", "player1"),
            "player2": _metric_value(period, "service", "doubleFaults", "player2"),
        },
        "breaks_of_serve": {
            "player1": _metric_value(period, "return", "breakPointsScored", "player1"),
            "player2": _metric_value(period, "return", "breakPointsScored", "player2"),
        },
    }


def _timeline_break_count(payload: Mapping[str, Any]) -> int:
    rows = payload.get("results")
    if not isinstance(rows, list):
        return 0
    return sum(
        1
        for row in rows
        if isinstance(row, Mapping)
        and "breaks" in str(row.get("text") or "").casefold()
    )


def run(
    *,
    key: str,
    out: Path = DEFAULT_OUT,
    max_events: int = 8,
    session: Any | None = None,
) -> dict[str, Any]:
    secret = str(key or "").strip()
    if not secret:
        raise ValueError("RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED")
    client = session or requests.Session()
    headers = {
        "X-RapidAPI-Key": secret,
        "X-RapidAPI-Host": HOST,
        "Accept": "application/json",
    }

    live = client.get(BASE + LIVE_PATH, headers=headers, timeout=20)
    live_raw = bytes(live.content)
    try:
        live_payload = live.json()
    except Exception as exc:
        raise RuntimeError("TENNIS_SERVE_STATS_LIVE_NON_JSON") from exc
    if live.status_code != 200 or not isinstance(live_payload, Mapping) or live_payload.get("success") is not True:
        raise RuntimeError(f"TENNIS_SERVE_STATS_LIVE_PROVIDER_FAILURE_{live.status_code}")

    rows = live_payload.get("results")
    if not isinstance(rows, list):
        raise RuntimeError("TENNIS_SERVE_STATS_LIVE_RESULTS_NOT_LIST")

    captures: list[dict[str, Any]] = []
    calls = 1
    observed = {"ACES": 0, "DOUBLE_FAULTS": 0, "BREAKS_OF_SERVE": 0}
    for row in rows[: max(0, max_events)]:
        if not isinstance(row, Mapping):
            continue
        p1 = str(row.get("participant1") or _mapping(row.get("player1")).get("name") or "").strip()
        p2 = str(row.get("participant2") or _mapping(row.get("player2")).get("name") or "").strip()
        event_id = str(row.get("id") or "").strip()
        if not p1 or not p2:
            continue

        stats_url = BASE + STATS_PATH.format(p1=quote(p1, safe=""), p2=quote(p2, safe=""))
        stats_response = client.get(stats_url, headers=headers, timeout=20)
        calls += 1
        stats_raw = bytes(stats_response.content)
        try:
            stats_payload = stats_response.json()
        except Exception:
            stats_payload = {}
        stats = _extract_stats(stats_payload if isinstance(stats_payload, Mapping) else {})
        if all(v is not None for v in stats["aces"].values()):
            observed["ACES"] += 1
        if all(v is not None for v in stats["double_faults"].values()):
            observed["DOUBLE_FAULTS"] += 1
        if all(v is not None for v in stats["breaks_of_serve"].values()):
            observed["BREAKS_OF_SERVE"] += 1

        timeline_break_events = None
        timeline_sha = None
        timeline_status = None
        if event_id:
            tl = client.get(BASE + TIMELINE_PATH.format(event_id=quote(event_id, safe="")), headers=headers, timeout=20)
            calls += 1
            tl_raw = bytes(tl.content)
            timeline_status = int(tl.status_code)
            timeline_sha = _sha(tl_raw)
            try:
                tl_payload = tl.json()
            except Exception:
                tl_payload = {}
            if tl.status_code == 200 and isinstance(tl_payload, Mapping):
                timeline_break_events = _timeline_break_count(tl_payload)

        captures.append({
            "event_id": event_id,
            "participant1": p1,
            "participant2": p2,
            "tour_type": row.get("tourType"),
            "status": row.get("status"),
            "stats_http_status": int(stats_response.status_code),
            "stats_payload_sha256": _sha(stats_raw),
            "statistics": stats,
            "timeline_http_status": timeline_status,
            "timeline_payload_sha256": timeline_sha,
            "timeline_break_events": timeline_break_events,
            "calibration_admitted": False,
        })

    result = {
        "schema": "MATRIX_TENNIS_SERVE_STATS_LAB_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "rapidapi_tennis",
        "live_endpoint": LIVE_PATH,
        "statistics_endpoint_template": STATS_PATH,
        "timeline_endpoint_template": TIMELINE_PATH,
        "live_http_status": int(live.status_code),
        "live_payload_sha256": _sha(live_raw),
        "live_event_count": len(rows),
        "events_probed": len(captures),
        "network_calls": calls,
        "market_lanes": list(MARKET_KEYS),
        "field_observation_counts": observed,
        "captures": captures,
        "source_contract": {
            "aces": "statistics.ALL.service.aces",
            "double_faults": "statistics.ALL.service.doubleFaults",
            "breaks_of_serve": "statistics.ALL.return.breakPointsScored",
            "break_timeline_crosscheck": "event/timeline/{event_id} text contains breaks",
        },
        "p_matrix_status": "NOT_GENERATED_SOURCE_LAB_ONLY",
        "metrics_status": "SEALED",
        "protections": {
            "missing_not_zero": True,
            "silent_imputation": False,
            "provider_values_not_used_as_target_probability": True,
            "odds_used_to_generate_probability": False,
            "calibration_admitted": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS_SOURCE_LAB",
    }
    result["payload_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--max-events", type=int, default=8)
    args = p.parse_args()
    result = run(
        key=os.environ.get("RAPIDAPI_TENNIS_KEY", ""),
        out=Path(args.out),
        max_events=max(0, args.max_events),
    )
    print(json.dumps({
        "status": result["status"],
        "live_event_count": result["live_event_count"],
        "events_probed": result["events_probed"],
        "field_observation_counts": result["field_observation_counts"],
        "network_calls": result["network_calls"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
