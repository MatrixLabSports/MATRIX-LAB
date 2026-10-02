from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tools.cor0203_rapidapi_tennis_discovery import (
    MAX_WORLD_FIXTURE_PAGES,
    PROVIDER_KEY,
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
)

BOGOTA = ZoneInfo("America/Bogota")
TOURS = ("atp", "wta", "itf")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _positive_id(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = payload.get("data")
    if not isinstance(value, list):
        raise ValueError("WORLD_INVENTORY_PROVIDER_DATA_NOT_LIST")
    return [row for row in value if isinstance(row, Mapping)]


def _parse_start(row: Mapping[str, Any]) -> datetime:
    token = str(
        row.get("startTime")
        or row.get("date")
        or row.get("start")
        or ""
    ).strip()
    if not token:
        raise ValueError("START_MISSING")
    parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("START_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _player(row: Mapping[str, Any], n: int) -> dict[str, Any]:
    obj = _mapping(row.get(f"player{n}"))
    pid = _positive_id(row.get(f"player{n}Id") or obj.get("id"))
    return {
        "id": pid,
        "name": str(
            obj.get("name")
            or row.get(f"player{n}Name")
            or ""
        ).strip(),
        "country": str(
            obj.get("countryAcr")
            or obj.get("country")
            or ""
        ).strip(),
    }


def _tournament(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(row.get("tournament"))


def _court_name(row: Mapping[str, Any]) -> str:
    tournament = _tournament(row)
    court = _mapping(tournament.get("court"))
    return str(
        court.get("name")
        or tournament.get("courtName")
        or tournament.get("surface")
        or row.get("surface")
        or ""
    ).strip()


def _tier(row: Mapping[str, Any]) -> str:
    tournament = _tournament(row)
    return str(
        tournament.get("tier")
        or tournament.get("level")
        or row.get("tier")
        or ""
    ).strip()


def _round(row: Mapping[str, Any]) -> str:
    obj = _mapping(row.get("round"))
    return str(
        obj.get("name")
        or row.get("roundName")
        or row.get("round")
        or ""
    ).strip()


def _player_group(row: Mapping[str, Any]) -> str:
    value = (
        row.get("playerGroup")
        or row.get("player_group")
        or row.get("group")
        or ""
    )
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("value") or ""
    return str(value).strip()


def _status(row: Mapping[str, Any]) -> str:
    value = (
        row.get("status")
        or row.get("matchStatus")
        or row.get("result_type")
        or row.get("resultType")
        or ""
    )
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("value") or ""
    return str(value).strip()


def _model_lane(
    *,
    tour: str,
    player_group: str,
    tier: str,
    surface: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    if tour != "atp":
        blockers.append("TOUR_OUTSIDE_COR0203_ATP")
    group = player_group.casefold()
    if group not in {"singles", "single"}:
        blockers.append("PLAYER_GROUP_NOT_PROVEN_SINGLES")
    if "challenger" not in tier.casefold():
        blockers.append("TOURNAMENT_NOT_PROVEN_CHALLENGER")
    if surface.casefold() not in {"hard", "indoor hard"}:
        blockers.append("SURFACE_OUTSIDE_COR0203_HARD")
    return {
        "lane": "COR02_COR03_ATP_CHALLENGER_HARD",
        "domain_candidate": not blockers,
        "blockers": blockers,
        "note": (
            "Domain candidate only. Governed COR02/COR03 still requires "
            "identity, PIT history, ranking/features, unique physical event, "
            "future prematch freeze and all existing gates."
        ),
    }


def _normalize_event(tour: str, row: Mapping[str, Any]) -> dict[str, Any]:
    start_utc = _parse_start(row)
    start_local = start_utc.astimezone(BOGOTA)
    match_id = _positive_id(row.get("matchId") or row.get("id"))
    tournament = _tournament(row)
    tournament_id = _positive_id(
        row.get("tournamentId") or tournament.get("id")
    )
    p1 = _player(row, 1)
    p2 = _player(row, 2)
    tier = _tier(row)
    surface = _court_name(row)
    player_group = _player_group(row)
    round_name = _round(row)
    physical_components = {
        "tour": tour,
        "tournament_id": tournament_id,
        "round": round_name.casefold(),
        "player_ids": sorted(
            x for x in (p1["id"], p2["id"]) if x is not None
        ),
        "start_utc": start_utc.isoformat(),
    }
    return {
        "source_provider": PROVIDER_KEY,
        "tour": tour.upper(),
        "match_id": match_id,
        "source_event_id": (
            f"rapidapi-tennis:{tour}:match:{match_id}"
            if match_id
            else None
        ),
        "tournament_id": tournament_id,
        "tournament_name": str(
            tournament.get("name")
            or row.get("tournamentName")
            or ""
        ).strip(),
        "tier": tier,
        "surface": surface,
        "round": round_name,
        "player_group": player_group,
        "player1": p1,
        "player2": p2,
        "event_start_utc": start_utc.isoformat(),
        "event_start_bogota": start_local.isoformat(),
        "provider_status": _status(row),
        "physical_event_key": _sha(physical_components),
        "source_snapshot_sha256": _sha(row),
        "model_derivation": _model_lane(
            tour=tour,
            player_group=player_group,
            tier=tier,
            surface=surface,
        ),
    }


def build_world_inventory(
    *,
    client: RapidApiTennisClient,
    target_date_bogota: date,
) -> dict[str, Any]:
    local_start = datetime.combine(
        target_date_bogota,
        time.min,
        tzinfo=BOGOTA,
    )
    local_end = datetime.combine(
        target_date_bogota,
        time(23, 59, 59),
        tzinfo=BOGOTA,
    )
    query_start = target_date_bogota - timedelta(days=1)
    query_stop = target_date_bogota + timedelta(days=1)

    events: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    tour_summaries: dict[str, Any] = {}
    tour_errors: dict[str, str] = {}

    for tour in TOURS:
        before = client.request_count
        try:
            payload = client.fixtures_for_tour(
                tour,
                query_start,
                query_stop,
                filter_value=None,
                max_pages=MAX_WORLD_FIXTURE_PAGES,
            )
            provider_rows = _rows(payload)
        except (RapidApiTennisDiscoveryError, ValueError) as error:
            tour_errors[tour.upper()] = (
                type(error).__name__ + ":" + str(error)[:400]
            )
            tour_summaries[tour.upper()] = {
                "status": "BLOCKED",
                "provider_rows_in_query_window": 0,
                "events_in_bogota_day": 0,
                "network_calls": client.request_count - before,
            }
            continue

        selected = 0
        malformed = 0
        for row in provider_rows:
            try:
                normalized = _normalize_event(tour, row)
                event_local = datetime.fromisoformat(
                    normalized["event_start_bogota"]
                )
            except (TypeError, ValueError) as error:
                malformed += 1
                unplaced.append({
                    "tour": tour.upper(),
                    "source_snapshot_sha256": _sha(row),
                    "reason": type(error).__name__ + ":" + str(error),
                })
                continue
            if event_local.date() != target_date_bogota:
                continue
            events.append(normalized)
            selected += 1

        tour_summaries[tour.upper()] = {
            "status": "PASS",
            "provider_rows_in_query_window": len(provider_rows),
            "events_in_bogota_day": selected,
            "malformed_unplaced_rows": malformed,
            "network_calls": client.request_count - before,
        }

    events.sort(
        key=lambda row: (
            row["event_start_utc"],
            row["tour"],
            row.get("match_id") or "",
            row["physical_event_key"],
        )
    )

    seen_source: set[tuple[str, str]] = set()
    duplicate_source_rows: list[dict[str, Any]] = []
    unique_events: list[dict[str, Any]] = []
    for row in events:
        source_key = (row["tour"], str(row.get("match_id") or ""))
        if source_key[1] and source_key in seen_source:
            duplicate_source_rows.append({
                "tour": row["tour"],
                "match_id": row.get("match_id"),
                "physical_event_key": row["physical_event_key"],
            })
            continue
        if source_key[1]:
            seen_source.add(source_key)
        unique_events.append(row)

    by_tour = Counter(row["tour"] for row in unique_events)
    domain_candidates = [
        row["source_event_id"]
        for row in unique_events
        if row["model_derivation"]["domain_candidate"]
    ]
    complete = not tour_errors and all(
        tour_summaries.get(tour.upper(), {}).get("status") == "PASS"
        for tour in TOURS
    )
    return {
        "schema": "MATRIX_TENNIS_WORLD_INVENTORY_V1",
        "status": "PASS" if complete else "PARTIAL",
        "world_inventory_complete": complete,
        "provider": PROVIDER_KEY,
        "operational_timezone": "America/Bogota",
        "calendar_day_rule": "00:00:00-23:59:59_LOCAL_FULL_DAY",
        "target_date_bogota": target_date_bogota.isoformat(),
        "calendar_day_start_local": local_start.isoformat(),
        "calendar_day_end_local": local_end.isoformat(),
        "calendar_day_start_utc": local_start.astimezone(timezone.utc).isoformat(),
        "calendar_day_end_utc": local_end.astimezone(timezone.utc).isoformat(),
        "provider_query_date_start": query_start.isoformat(),
        "provider_query_date_stop": query_stop.isoformat(),
        "tours_required": ["ATP", "WTA", "ITF"],
        "tour_summaries": tour_summaries,
        "tour_errors": tour_errors,
        "world_calendar_inventory_count": len(unique_events),
        "events_by_tour": {
            "ATP": by_tour.get("ATP", 0),
            "WTA": by_tour.get("WTA", 0),
            "ITF": by_tour.get("ITF", 0),
        },
        "duplicate_source_rows_quarantined": len(duplicate_source_rows),
        "duplicate_source_rows": duplicate_source_rows,
        "unplaced_rows": unplaced,
        "derived_lanes": {
            "COR02_COR03_ATP_CHALLENGER_HARD": {
                "domain_candidate_count": len(domain_candidates),
                "source_event_ids": domain_candidates,
                "feeds_model_automatically": False,
                "governed_pipeline_remains_authoritative": True,
            },
            "WTA": {
                "inventory_count": by_tour.get("WTA", 0),
                "current_governed_model": None,
                "feeds_COR02_COR03": False,
            },
            "ITF": {
                "inventory_count": by_tour.get("ITF", 0),
                "current_governed_model": None,
                "feeds_COR02_COR03": False,
            },
        },
        "events": unique_events,
        "p_matrix": "NOT_GENERATED",
        "metrics_opened": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _target_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(BOGOTA).date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--target-date-bogota")
    parser.add_argument("--fail-on-partial", action="store_true")
    args = parser.parse_args()

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    target = _target_date(args.target_date_bogota)
    if not key:
        report = {
            "schema": "MATRIX_TENNIS_WORLD_INVENTORY_V1",
            "status": "SOURCE_NOT_CONFIGURED",
            "world_inventory_complete": False,
            "provider": PROVIDER_KEY,
            "target_date_bogota": target.isoformat(),
            "tours_required": ["ATP", "WTA", "ITF"],
            "world_calendar_inventory_count": 0,
            "p_matrix": "NOT_GENERATED",
            "metrics_opened": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
    else:
        client = RapidApiTennisClient(key)
        report = build_world_inventory(
            client=client,
            target_date_bogota=target,
        )
        report["provider_network_calls"] = client.request_count

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report.get("status"),
        "target_date_bogota": report.get("target_date_bogota"),
        "world_inventory_complete": report.get("world_inventory_complete"),
        "world_calendar_inventory_count": report.get(
            "world_calendar_inventory_count", 0
        ),
        "events_by_tour": report.get("events_by_tour"),
        "tour_errors": report.get("tour_errors"),
        "provider_network_calls": report.get("provider_network_calls", 0),
        "real_money": report.get("real_money"),
    }, sort_keys=True))
    if args.fail_on_partial and report.get("status") != "PASS":
        raise SystemExit("TENNIS_WORLD_INVENTORY_NOT_COMPLETE")


if __name__ == "__main__":
    main()
