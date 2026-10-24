from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import (
    RANKING_CUT,
    RapidApiTennisClient,
    recover_exact_rankings_from_history,
    recover_exact_rankings_via_profile_alias,
)

LANE_ID = "ATP_CHALLENGER_MEN_SINGLES_CLAY"
HOLDOUT_ID = "ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _aware(value: object) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("EVENT_START_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def build_prefeature(
    *,
    inventory: Mapping[str, Any],
    inventory_sha256: str,
    ranking_by_player: Mapping[str, Mapping[str, Any]],
    now_utc: datetime,
    starting_observation_count: int,
    revision: str = "R1",
) -> dict[str, Any]:
    events = []
    blocked = []
    for raw in inventory.get("events", []) or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("circuit_detail") or "") != "ATP_CHALLENGER":
            continue
        if str(raw.get("event_format") or "") != "SINGLES":
            continue
        if str(raw.get("surface") or "").strip().casefold() != "clay":
            continue
        start = _aware(raw.get("event_start_utc"))
        p1 = raw.get("player1") if isinstance(raw.get("player1"), Mapping) else {}
        p2 = raw.get("player2") if isinstance(raw.get("player2"), Mapping) else {}
        p1id = str(p1.get("id") or "").strip()
        p2id = str(p2.get("id") or "").strip()
        source_id = str(raw.get("source_event_id") or "").strip()
        if start <= now_utc:
            blocked.append({"source_event_id": source_id, "reason": "EVENT_NOT_FUTURE"})
            continue
        r1 = ranking_by_player.get(p1id)
        r2 = ranking_by_player.get(p2id)
        blockers = []
        if not isinstance(r1, Mapping):
            blockers.append("RANKING_CUT_MISSING_PLAYER1")
        if not isinstance(r2, Mapping):
            blockers.append("RANKING_CUT_MISSING_PLAYER2")
        if blockers:
            blocked.append({"source_event_id": source_id, "reason": ",".join(blockers)})
            continue
        physical_key = str(raw.get("physical_event_key") or "").strip()
        if not physical_key:
            blocked.append({"source_event_id": source_id, "reason": "PHYSICAL_EVENT_KEY_MISSING"})
            continue
        event_id = "CLAY-" + source_id.replace(":", "-") + "-" + physical_key[:12]
        events.append({
            "event_id": event_id,
            "canonical_source_event_id": source_id,
            "competition": raw.get("tournament_name"),
            "competition_id": (
                "rapidapi-tennis:tournament:" + str(raw.get("tournament_id") or "")
            ),
            "event_start_utc": start.isoformat(),
            "features_loaded": False,
            "historical_identity_crosswalk_status": "PENDING",
            "identity_crosswalk_required": True,
            "identity_source": (
                f"world_inventory:{source_id};ranking_cut={RANKING_CUT.isoformat()}"
            ),
            "metrics_opened": False,
            "outcome": None,
            "physical_event_key": physical_key,
            "player_identities": [
                {
                    "display_name": str(p1.get("name") or "").strip(),
                    "provider": "rapidapi_tennis",
                    "provider_player_id": "rapidapi-tennis:player:" + p1id,
                    "provider_ranking": dict(r1),
                },
                {
                    "display_name": str(p2.get("name") or "").strip(),
                    "provider": "rapidapi_tennis",
                    "provider_player_id": "rapidapi-tennis:player:" + p2id,
                    "provider_ranking": dict(r2),
                },
            ],
            "players": [
                str(p1.get("name") or "").strip(),
                str(p2.get("name") or "").strip(),
            ],
            "round": str(raw.get("round") or "UNKNOWN"),
            "schedule_source": "rapidapi_world_inventory:" + source_id,
            "source_provider": "rapidapi_tennis",
            "source_snapshot_sha256": inventory_sha256,
            "surface": "Clay",
            "target_period": 20260921,
            "tour_level": "C",
        })
    return {
        "schema": "MATRIX_TENNIS_CLAY_PREFEATURE_REGISTRY_V1",
        "revision": revision,
        "lane_id": LANE_ID,
        "holdout_id": HOLDOUT_ID,
        "starting_observation_count": int(starting_observation_count),
        "created_before_feature_acquisition": True,
        "discovery_provider": "rapidapi_tennis",
        "ranking_cut": RANKING_CUT.strftime("%Y%m%d"),
        "events": events,
        "blocked_discovery": blocked,
        "metrics_opened": False,
        "outcomes_read": 0,
        "historical_backfill": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--revision", default="R1")
    a = p.parse_args()

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")

    inventory_path = Path(a.inventory)
    state = _load(Path(a.state))
    inventory = _load(inventory_path)
    rows = [
        row for row in inventory.get("events", []) or []
        if isinstance(row, Mapping)
        and str(row.get("circuit_detail") or "") == "ATP_CHALLENGER"
        and str(row.get("event_format") or "") == "SINGLES"
        and str(row.get("surface") or "").strip().casefold() == "clay"
    ]
    wanted = {
        str(player.get("id") or "").strip()
        for row in rows
        for player in (
            row.get("player1") if isinstance(row.get("player1"), Mapping) else {},
            row.get("player2") if isinstance(row.get("player2"), Mapping) else {},
        )
        if str(player.get("id") or "").strip().isdigit()
    }
    fixture_identity = {}
    for row in rows:
        for key_name in ("player1", "player2"):
            player = row.get(key_name) if isinstance(row.get(key_name), Mapping) else {}
            pid = str(player.get("id") or "").strip()
            if pid:
                fixture_identity[pid] = {
                    "name": str(player.get("name") or "").strip(),
                    "country": str(player.get("country") or "").strip(),
                }

    client = RapidApiTennisClient(key)
    rankings = client.ranking_snapshot(
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted,
    )
    rankings, hist = recover_exact_rankings_from_history(
        client=client,
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted,
        existing_rankings=rankings,
        fixture_identity_by_player=fixture_identity,
    )
    rankings, aliases = recover_exact_rankings_via_profile_alias(
        client=client,
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted,
        existing_rankings=rankings,
        fixture_identity_by_player=fixture_identity,
    )
    payload = build_prefeature(
        inventory=inventory,
        inventory_sha256=_sha_bytes(inventory_path.read_bytes()),
        ranking_by_player=rankings,
        now_utc=datetime.now(timezone.utc),
        starting_observation_count=int(state.get("observation_count") or 0),
        revision=str(a.revision),
    )
    payload["provider_network_calls"] = client.request_count
    payload["ranking_players_requested"] = len(wanted)
    payload["ranking_players_found"] = len(rankings)
    payload["ranking_history_recovery"] = hist
    payload["ranking_profile_alias_recovery"] = aliases

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "future_events": len(payload["events"]),
        "blocked_discovery": len(payload["blocked_discovery"]),
        "ranking_players_requested": len(wanted),
        "ranking_players_found": len(rankings),
        "provider_network_calls": client.request_count,
        "real_money": "BLOCKED",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
