from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE = "https://tennis-api-atp-wta-itf.p.rapidapi.com"
HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
LIVE_PATH = "/tennis/v2/extend/api/events/live"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_tournament(row: Mapping[str, Any]) -> dict[str, Any]:
    t = row.get("tournament")
    if not isinstance(t, Mapping):
        return {}
    allow = ("id", "name", "date", "level", "surface", "country")
    return {k: t.get(k) for k in allow if k in t}


def _candidate(row: Mapping[str, Any]) -> bool:
    t = _safe_tournament(row)
    level = str(t.get("level") or "").strip().lower()
    surface = str(t.get("surface") or "").strip().lower()
    tour_type = str(row.get("tourType") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    return (
        tour_type == "atp"
        and "challenger" in level
        and surface == "clay"
        and status == "inplay"
    )


def _quality_valid(row: Mapping[str, Any]) -> bool:
    if not _candidate(row):
        return False
    score = str(row.get("score") or "").strip()
    points = row.get("points")
    indicator = str(row.get("indicator") or "").strip()
    event_id = str(row.get("id") or "").strip()
    p1 = str(row.get("participant1") or "").strip()
    p2 = str(row.get("participant2") or "").strip()
    return bool(
        event_id
        and p1
        and p2
        and score
        and points is not None
        and indicator in {"1,0", "0,1"}
    )


def _sanitize(row: Mapping[str, Any], captured_at_utc: str, response_sha256: str) -> dict[str, Any]:
    return {
        "provider": "rapidapi_tennis",
        "captured_at_utc": captured_at_utc,
        "response_sha256": response_sha256,
        "event_id": str(row.get("id") or ""),
        "match_id": str(row.get("matchId") or ""),
        "status": row.get("status"),
        "score": row.get("score"),
        "points": row.get("points"),
        "indicator": row.get("indicator"),
        "tour_type": row.get("tourType"),
        "start_timestamp": row.get("startTimestamp"),
        "p1_name": row.get("participant1"),
        "p2_name": row.get("participant2"),
        "league": row.get("league"),
        "tournament": _safe_tournament(row),
        "challenger_men_clay_candidate": _candidate(row),
        "quality_state_valid_shadow": _quality_valid(row),
        "calibration_admitted": False,
        "settlement_status": "PENDING_FINAL",
    }


def run(*, key: str, cycles: int, interval_seconds: int, out: Path, session: Any | None = None) -> dict[str, Any]:
    secret = str(key or "").strip()
    if not secret:
        raise ValueError("RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED")
    client = session or requests.Session()
    headers = {"X-RapidAPI-Key": secret, "X-RapidAPI-Host": HOST}
    observations: dict[str, dict[str, Any]] = {}
    cycle_rows = []
    network_calls = 0
    public_rate_headers: dict[str, str] = {}

    for i in range(max(1, cycles)):
        captured = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        r = client.get(BASE + LIVE_PATH, headers=headers, timeout=20)
        network_calls += 1
        body = bytes(r.content)
        try:
            payload = r.json()
        except Exception as exc:
            raise RuntimeError("RAPIDAPI_TENNIS_LIVE_NON_JSON") from exc
        if r.status_code != 200:
            raise RuntimeError(f"RAPIDAPI_TENNIS_LIVE_HTTP_{r.status_code}")
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise RuntimeError("RAPIDAPI_TENNIS_LIVE_PROVIDER_FAILURE")
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise RuntimeError("RAPIDAPI_TENNIS_LIVE_RESULTS_NOT_LIST")

        for k, v in getattr(r, "headers", {}).items():
            name = str(k).lower()
            if name.startswith("x-ratelimit-") or name.startswith("x-rapidapi-"):
                if "key" not in name and "token" not in name:
                    public_rate_headers[name] = str(v)

        candidates = 0
        valid = 0
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            item = _sanitize(row, captured, _sha(body))
            key_id = f"{item['event_id']}|{captured}"
            observations[key_id] = item
            if item["challenger_men_clay_candidate"]:
                candidates += 1
            if item["quality_state_valid_shadow"]:
                valid += 1
        cycle_rows.append({
            "cycle": i + 1,
            "captured_at_utc": captured,
            "live_event_count": len(rows),
            "challenger_men_clay_candidates": candidates,
            "quality_valid_shadow_candidates": valid,
            "response_sha256": _sha(body),
        })
        if i < cycles - 1:
            time.sleep(max(1, interval_seconds))

    rows = list(observations.values())
    candidates = [x for x in rows if x["challenger_men_clay_candidate"]]
    valid = [x for x in rows if x["quality_state_valid_shadow"]]
    result = {
        "schema": "MATRIX_RAPIDAPI_TENNIS_LIVE_SHADOW_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "rapidapi_tennis",
        "endpoint": LIVE_PATH,
        "network_calls": network_calls,
        "cycle_summaries": cycle_rows,
        "live_observation_rows": len(rows),
        "challenger_men_clay_candidate_rows": len(candidates),
        "quality_valid_shadow_candidate_rows": len(valid),
        "candidate_event_ids": sorted({x["event_id"] for x in candidates if x["event_id"]}),
        "quality_valid_shadow_event_ids": sorted({x["event_id"] for x in valid if x["event_id"]}),
        "public_rate_headers": public_rate_headers,
        "observations": rows,
        "calibration_admission": {
            "admitted_to_existing_live_gate": False,
            "reason": "SHADOW_ONLY_REQUIRES_PROVIDER_CROSSWALK_AND_SETTLEMENT_PROOF",
        },
        "protections": {
            "api_tennis_retired_source_used": False,
            "prematch_hard_mutated": False,
            "prematch_clay_mutated": False,
            "metrics_opened": False,
            "probability_output_status": "SEALED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "secrets_persisted": False,
        },
    }
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    result["sha256_without_self"] = hashlib.sha256(raw).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=4)
    p.add_argument("--interval-seconds", type=int, default=15)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = run(
        key=os.environ.get("RAPIDAPI_TENNIS_KEY", ""),
        cycles=a.cycles,
        interval_seconds=a.interval_seconds,
        out=Path(a.out),
    )
    print(json.dumps({
        "network_calls": result["network_calls"],
        "live_observation_rows": result["live_observation_rows"],
        "challenger_men_clay_candidate_rows": result["challenger_men_clay_candidate_rows"],
        "quality_valid_shadow_candidate_rows": result["quality_valid_shadow_candidate_rows"],
        "candidate_event_ids": result["candidate_event_ids"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
