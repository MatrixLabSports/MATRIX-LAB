from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import (
    PROVIDER_KEY,
    RANKING_CUT,
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
    build_discovery_registry,
    recover_exact_rankings_from_history,
    recover_exact_rankings_via_profile_alias,
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WORLD_DERIVED_JSON_ROOT_MUST_BE_OBJECT")
    return value


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("WORLD_DERIVED_AS_OF_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)


def _numeric(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def _world_domain_rows(
    inventory: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = []
    for row in inventory.get("events", []) or []:
        if not isinstance(row, Mapping):
            continue
        derivation = row.get("model_derivation")
        if not isinstance(derivation, Mapping):
            continue
        if derivation.get("lane") != "COR02_COR03_ATP_CHALLENGER_HARD":
            continue
        if derivation.get("domain_candidate") is not True:
            continue
        if str(row.get("circuit_detail") or "") != "ATP_CHALLENGER":
            continue
        if str(row.get("event_format") or "") != "SINGLES":
            continue
        rows.append(row)
    return rows


def _fixture_row(row: Mapping[str, Any]) -> dict[str, Any]:
    match_id = _numeric(row.get("match_id"))
    tournament_id = _numeric(row.get("tournament_id"))
    p1 = row.get("player1")
    p2 = row.get("player2")
    if not isinstance(p1, Mapping) or not isinstance(p2, Mapping):
        raise ValueError("WORLD_DERIVED_PLAYER_OBJECT_MISSING")
    p1_id = _numeric(p1.get("id"))
    p2_id = _numeric(p2.get("id"))
    if None in {match_id, tournament_id, p1_id, p2_id}:
        raise ValueError("WORLD_DERIVED_PROVIDER_ID_INVALID")
    start = str(row.get("event_start_utc") or "")
    if not start:
        raise ValueError("WORLD_DERIVED_EVENT_START_MISSING")
    return {
        "id": match_id,
        "matchId": match_id,
        "date": start,
        "startTime": start,
        "player1Id": p1_id,
        "player2Id": p2_id,
        "player1": {
            "id": p1_id,
            "name": str(p1.get("name") or "").strip(),
            "countryAcr": str(p1.get("country") or "").strip(),
        },
        "player2": {
            "id": p2_id,
            "name": str(p2.get("name") or "").strip(),
            "countryAcr": str(p2.get("country") or "").strip(),
        },
        "tournamentId": tournament_id,
        "round": {"name": str(row.get("round") or "").strip()},
    }


def derive_world_cor_discovery(
    *,
    world_inventory: Mapping[str, Any],
    client: RapidApiTennisClient,
    as_of_utc: str,
) -> dict[str, Any]:
    as_of = _parse_utc(as_of_utc)
    if world_inventory.get("status") != "PASS":
        return {
            "schema": "MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_V1",
            "provider": PROVIDER_KEY,
            "status": "WORLD_INVENTORY_NOT_COMPLETE",
            "source_mode": "WORLD_INVENTORY_DERIVED",
            "as_of_utc": as_of.isoformat(),
            "world_inventory_target_date": world_inventory.get(
                "target_date_bogota"
            ),
            "world_inventory_sha256": _sha(world_inventory),
            "world_domain_candidates_input": 0,
            "eligible_candidates": [],
            "provider_rejected": [],
            "network_calls": 0,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }

    world_rows = _world_domain_rows(world_inventory)
    fixture_rows: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for row in world_rows:
        try:
            fixture_rows.append(_fixture_row(row))
        except (TypeError, ValueError) as error:
            malformed.append({
                "source_event_id": row.get("source_event_id"),
                "blockers": [
                    type(error).__name__ + ":" + str(error)
                ],
            })

    tournament_ids = sorted({
        str(row["tournamentId"])
        for row in fixture_rows
        if row.get("tournamentId")
    })
    tournament_info: dict[str, Mapping[str, Any]] = {}
    tournament_errors: dict[str, str] = {}
    for tournament_id in tournament_ids:
        try:
            tournament_info[tournament_id] = client.tournament_info(
                tournament_id
            )
        except (RapidApiTennisDiscoveryError, ValueError) as error:
            tournament_errors[tournament_id] = (
                type(error).__name__ + ":" + str(error)[:400]
            )

    wanted_player_ids = {
        str(row[key])
        for row in fixture_rows
        for key in ("player1Id", "player2Id")
        if row.get(key)
    }
    ranking_error = None
    if wanted_player_ids:
        try:
            rankings = client.ranking_snapshot(
                ranking_date=RANKING_CUT,
                wanted_player_ids=wanted_player_ids,
            )
        except (RapidApiTennisDiscoveryError, ValueError) as error:
            rankings = {}
            ranking_error = type(error).__name__ + ":" + str(error)[:400]
    else:
        rankings = {}

    fixture_identity_by_player = {}
    for row in fixture_rows:
        for side in (1, 2):
            player_id = str(row.get(f"player{side}Id") or "").strip()
            player = row.get(f"player{side}")
            if not player_id or not isinstance(player, Mapping):
                continue
            fixture_identity_by_player[player_id] = {
                "name": str(player.get("name") or "").strip(),
                "country": str(player.get("countryAcr") or "").strip(),
            }

    ranking_history_recovery = {
        "schema": "MATRIX_COR0203_EXACT_CUT_RANK_HISTORY_RECOVERY_V1",
        "ranking_cut": RANKING_CUT.isoformat(),
        "requested_missing_player_ids": [],
        "history_requests": 0,
        "recovered_count": 0,
        "recovered": [],
        "blocked_count": 0,
        "blocked": [],
        "current_rank_used": False,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "real_money": "BLOCKED",
    }
    ranking_profile_alias_recovery = {
        "schema": "MATRIX_COR0203_EXACT_CUT_RANK_PROFILE_ALIAS_V1",
        "ranking_cut": RANKING_CUT.isoformat(),
        "missing_player_ids": [],
        "ranking_snapshot_rows_scanned": 0,
        "profile_requests": 0,
        "recovered_count": 0,
        "recovered": [],
        "blocked_count": 0,
        "blocked": [],
        "join_by_name_only": False,
        "current_rank_used": False,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "real_money": "BLOCKED",
    }
    if wanted_player_ids and ranking_error is None:
        rankings, ranking_history_recovery = recover_exact_rankings_from_history(
            client=client,
            ranking_date=RANKING_CUT,
            wanted_player_ids=wanted_player_ids,
            existing_rankings=rankings,
            fixture_identity_by_player=fixture_identity_by_player,
        )
        rankings, ranking_profile_alias_recovery = recover_exact_rankings_via_profile_alias(
            client=client,
            ranking_date=RANKING_CUT,
            wanted_player_ids=wanted_player_ids,
            existing_rankings=rankings,
            fixture_identity_by_player=fixture_identity_by_player,
        )

    result = build_discovery_registry(
        fixture_payload={
            "data": fixture_rows,
            "pageNo": 1,
            "pageSize": len(fixture_rows),
            "hasNextPage": False,
        },
        tournament_info=tournament_info,
        ranking_by_player=rankings,
        as_of_utc=as_of.isoformat(),
    )

    # Preserve the channel-qualified world identity all the way into the
    # governed lane. RapidAPI can reuse the same numeric matchId across ATP
    # and WTA/ITF transports, so the numeric id alone is not globally unique.
    world_by_match_id = {
        str(row.get("match_id") or ""): row
        for row in world_rows
        if row.get("match_id")
    }
    for candidate in result.get("eligible_candidates", []) or []:
        legacy_event_id = str(
            candidate.get("canonical_source_event_id")
            or candidate.get("event_id")
            or ""
        )
        match_id = legacy_event_id.rsplit(":", 1)[-1]
        world_row = world_by_match_id.get(match_id)
        if not isinstance(world_row, Mapping):
            continue
        world_source_id = str(world_row.get("source_event_id") or "")
        if not world_source_id:
            continue
        candidate["legacy_provider_event_id"] = legacy_event_id
        candidate["event_id"] = world_source_id
        candidate["canonical_source_event_id"] = world_source_id
        candidate["provider_channel"] = str(
            world_row.get("provider_channel") or "ATP"
        )
        candidate["world_source_snapshot_sha256"] = str(
            world_row.get("source_snapshot_sha256") or ""
        )
        candidate["source_reference"] = (
            str(candidate.get("source_reference") or "")
            + ";provider_channel="
            + candidate["provider_channel"]
        )

    for rejected_row in result.get("provider_rejected", []) or []:
        match_id = str(rejected_row.get("match_id") or "")
        world_row = world_by_match_id.get(match_id)
        if isinstance(world_row, Mapping):
            rejected_row["world_source_event_id"] = str(
                world_row.get("source_event_id") or ""
            )
            rejected_row["provider_channel"] = str(
                world_row.get("provider_channel") or "ATP"
            )
    result["schema"] = "MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_V1"
    result["status"] = (
        "PROVIDER_ENRICHMENT_BLOCKED"
        if ranking_error
        else "DISCOVERY_COMPLETED"
    )
    if ranking_error:
        result["eligible_candidates"] = []
        for row in fixture_rows:
            result.setdefault("provider_rejected", []).append({
                "match_id": str(row.get("matchId") or ""),
                "tournament_id": str(row.get("tournamentId") or ""),
                "blockers": ["RANKING_ENRICHMENT_PROVIDER_ERROR"],
            })

    result["source_mode"] = "WORLD_INVENTORY_DERIVED"
    result["world_inventory_target_date"] = world_inventory.get(
        "target_date_bogota"
    )
    result["world_inventory_sha256"] = _sha(world_inventory)
    result["world_inventory_total"] = world_inventory.get(
        "world_calendar_inventory_count"
    )
    result["world_domain_candidates_input"] = len(world_rows)
    result["world_domain_candidate_source_ids"] = [
        str(row.get("source_event_id") or "")
        for row in world_rows
    ]
    result["world_rows_synthesized"] = len(fixture_rows)
    result["world_rows_malformed"] = malformed
    result["tournaments_requested"] = len(tournament_ids)
    result["tournaments_enriched"] = len(tournament_info)
    result["tournament_enrichment_errors"] = tournament_errors
    result["ranking_players_requested"] = len(wanted_player_ids)
    result["ranking_players_found"] = len(rankings)
    result["ranking_history_recovery"] = ranking_history_recovery
    result["ranking_history_recovered_count"] = int(
        ranking_history_recovery.get("recovered_count", 0)
    )
    result["ranking_profile_alias_recovery"] = ranking_profile_alias_recovery
    result["ranking_profile_alias_recovered_count"] = int(
        ranking_profile_alias_recovery.get("recovered_count", 0)
    )
    result["ranking_enrichment_error"] = ranking_error
    result["network_calls"] = client.request_count
    result["automatic_model_feed"] = False
    result["governed_preregistration_required"] = True
    result["metrics_opened"] = False
    result["outcomes_read"] = 0
    result["automatic_model_promotion"] = False
    result["automatic_wagering"] = False
    result["real_money"] = "BLOCKED"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-inventory", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()

    as_of = (
        args.as_of_utc
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    world = _load(Path(args.world_inventory))
    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        result = {
            "schema": "MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_V1",
            "provider": PROVIDER_KEY,
            "status": "SOURCE_NOT_CONFIGURED",
            "source_mode": "WORLD_INVENTORY_DERIVED",
            "as_of_utc": _parse_utc(as_of).isoformat(),
            "world_inventory_target_date": world.get("target_date_bogota"),
            "world_inventory_sha256": _sha(world),
            "world_domain_candidates_input": len(_world_domain_rows(world)),
            "eligible_candidates": [],
            "provider_rejected": [],
            "network_calls": 0,
            "automatic_model_feed": False,
            "governed_preregistration_required": True,
            "metrics_opened": False,
            "outcomes_read": 0,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
    else:
        result = derive_world_cor_discovery(
            world_inventory=world,
            client=RapidApiTennisClient(key),
            as_of_utc=as_of,
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result.get("status"),
        "world_inventory_target_date": result.get(
            "world_inventory_target_date"
        ),
        "world_domain_candidates_input": result.get(
            "world_domain_candidates_input", 0
        ),
        "eligible_input_events": result.get("eligible_input_events", 0),
        "provider_rejected": len(result.get("provider_rejected", []) or []),
        "tournaments_enriched": result.get("tournaments_enriched", 0),
        "ranking_players_found": result.get("ranking_players_found", 0),
        "network_calls": result.get("network_calls", 0),
        "real_money": result.get("real_money"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
