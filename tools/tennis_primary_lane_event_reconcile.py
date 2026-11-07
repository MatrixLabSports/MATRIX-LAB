from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.tennis_dual_lane_event_reconcile import surface_family

MODE = "rapidapi_primary_open_reconciliation"


def run(
    rapid_path: Path,
    clay_holdout: Path,
    clay_bootstrap: Path,
    out: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    rapid = json.loads(rapid_path.read_text(encoding="utf-8"))
    hold = json.loads(clay_holdout.read_text(encoding="utf-8"))
    boot = json.loads(clay_bootstrap.read_text(encoding="utf-8"))
    pit_max = int(boot["source"]["source_max_tourney_date"])

    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
    now = now.astimezone(timezone.utc)

    domain = [
        e for e in rapid.get("events", [])
        if isinstance(e, dict)
        and e.get("circuit_detail") == "ATP_CHALLENGER"
        and e.get("event_format") == "SINGLES"
        and surface_family(e.get("surface")) in {"HARD", "CLAY"}
    ]

    bindings: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for event in domain:
        sf = surface_family(event.get("surface"))
        source_id = str(event.get("source_event_id") or "")
        physical_key = str(event.get("physical_event_key") or "")
        p1 = event.get("player1") if isinstance(event.get("player1"), dict) else {}
        p2 = event.get("player2") if isinstance(event.get("player2"), dict) else {}
        player_names = [str(p1.get("name") or "").strip(), str(p2.get("name") or "").strip()]
        player_ids = [str(p1.get("id") or "").strip(), str(p2.get("id") or "").strip()]

        identity_blockers = []
        if not source_id:
            identity_blockers.append("SOURCE_EVENT_ID_MISSING")
        if not physical_key:
            identity_blockers.append("PHYSICAL_EVENT_KEY_MISSING")
        if any(not x for x in player_names):
            identity_blockers.append("PLAYER_NAME_MISSING")
        if any(not x for x in player_ids):
            identity_blockers.append("PLAYER_ID_MISSING")
        if identity_blockers:
            blocked.append({
                "rapid_source_event_id": source_id or None,
                "rapid_physical_event_key": physical_key or None,
                "surface_family": sf,
                "players": player_names,
                "reason": "RAPIDAPI_IDENTITY_INCOMPLETE",
                "blockers": identity_blockers,
            })
            continue

        try:
            start = datetime.fromisoformat(str(event["event_start_utc"]).replace("Z", "+00:00"))
        except Exception:
            blocked.append({
                "rapid_source_event_id": source_id,
                "rapid_physical_event_key": physical_key,
                "reason": "EVENT_START_INVALID",
            })
            continue
        if start.tzinfo is None or start.utcoffset() is None:
            blocked.append({
                "rapid_source_event_id": source_id,
                "rapid_physical_event_key": physical_key,
                "reason": "EVENT_START_NAIVE",
            })
            continue
        start = start.astimezone(timezone.utc)

        blockers: list[str] = []
        if start <= now:
            blockers.append("EVENT_NOT_FUTURE")

        row: dict[str, Any] = {
            "surface_family": sf,
            "rapid_source_event_id": source_id,
            "api_tennis_source_event_id": None,
            "rapid_physical_event_key": physical_key,
            "tournament": event.get("tournament_name"),
            "players_rapid": player_names,
            "players_api": None,
            "rapid_start_utc": event.get("event_start_utc"),
            "api_tennis_start_utc": None,
            "start_time_delta_minutes": None,
            "future_at_reconciliation": start > now,
            "identity_binding": "PASS_RAPIDAPI_PHYSICAL_KEY_PRIMARY",
            "identity_binding_basis": "RAPIDAPI_PROVIDER_IDS_PHYSICAL_EVENT_KEY",
            "surface_binding": "PASS_PROVIDER_DECLARED",
            "source_mode": MODE,
        }

        if sf == "CLAY":
            event_date = int(start.strftime("%Y%m%d"))
            if pit_max < event_date:
                blockers.append("PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT")
            row["lane_id"] = "ATP_CHALLENGER_MEN_SINGLES_CLAY"
            row["holdout_id"] = hold["holdout_id"]
            row["prospective_counter_increment_allowed"] = not blockers
        else:
            row["lane_id"] = "ATP_CHALLENGER_MEN_SINGLES_HARD"
            row["holdout_id"] = "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
            row["prospective_counter_increment_allowed"] = "DELEGATED_TO_EXISTING_COR0203_GATES"

        row["blockers"] = blockers
        bindings.append(row)

    clay = [x for x in bindings if x["surface_family"] == "CLAY"]
    hard = [x for x in bindings if x["surface_family"] == "HARD"]
    payload = {
        "schema": "MATRIX_TENNIS_PRIMARY_LANE_EVENT_RECONCILIATION_V1",
        "generated_at_utc": now.replace(microsecond=0).isoformat(),
        "target_date_bogota": rapid.get("target_date_bogota"),
        "source_mode": MODE,
        "rapidapi_domain_rows": len(domain),
        "api_tennis_domain_rows": 0,
        "api_tennis_status": "RETIRED_COST_UTILITY_DECISION",
        "bound_one_to_one": len(bindings),
        "hard_bound_count": len(hard),
        "clay_bound_count": len(clay),
        "clay_freeze_ready_count": sum(
            1 for x in clay if x["prospective_counter_increment_allowed"] is True
        ),
        "clay_blocked_count": sum(1 for x in clay if x["blockers"]),
        "bindings": bindings,
        "binding_blocked": blocked,
        "protections": {
            "rapidapi_physical_event_key_required": True,
            "rapidapi_provider_player_ids_required": True,
            "surface_declared_required": True,
            "clay_pit_caught_up_required": True,
            "required_open_calendar_reconciliation": ["SofaScore", "Flashscore"],
            "api_tennis_required": False,
            "missing_not_zero": True,
            "silent_imputation": False,
            "odds_to_probability": False,
            "metrics_opened": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_mode": MODE,
        "bound": len(bindings),
        "hard": len(hard),
        "clay": len(clay),
        "clay_freeze_ready": payload["clay_freeze_ready_count"],
        "binding_blocked": len(blocked),
        "api_tennis_status": payload["api_tennis_status"],
    }, sort_keys=True))
    return payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rapid", required=True)
    p.add_argument("--clay-holdout", required=True)
    p.add_argument("--clay-bootstrap", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    run(Path(a.rapid), Path(a.clay_holdout), Path(a.clay_bootstrap), Path(a.out))


if __name__ == "__main__":
    main()
