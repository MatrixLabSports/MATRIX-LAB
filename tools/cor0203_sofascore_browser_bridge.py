from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_prospective_producer import load_state
from tools.cor0203_r706_target_history_audit import audit_player
from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient


CUT_DATE = date(2026, 9, 21)
CUT_TOKEN = "2026-09-21"
PRE_CUT_START = date(2026, 9, 7)
PRE_CUT_STOP = date(2026, 9, 20)


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT:" + str(path))
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _positive_int(value: object, *, field: str) -> int:
    token = str(value or "").strip()
    if not token.isdigit() or int(token) < 0:
        raise ValueError("INVALID_" + field)
    return int(token)


def _profile_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        data = payload
    info = data.get("information")
    if not isinstance(info, Mapping):
        info = {}
    plays = str(info.get("plays") or info.get("hand") or "").strip().casefold()
    hand = "L" if plays.startswith("left") else "R" if plays.startswith("right") else ""
    birthday = str(data.get("birthday") or "").strip()[:10]
    return {
        "id": str(data.get("id") or "").strip(),
        "name": str(data.get("name") or "").strip(),
        "ioc": str(data.get("countryAcr") or "").strip().upper(),
        "dob": birthday,
        "hand": hand,
    }


def _ranking_record(
    rows: list[Mapping[str, Any]],
    *,
    target_name: str,
) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        player = _mapping(row.get("player"))
        name = str(player.get("name") or "").strip()
        if _norm(name) != _norm(target_name):
            continue
        player_id = str(player.get("id") or "").strip()
        if not player_id.isdigit() or int(player_id) <= 0:
            continue
        position = _positive_int(row.get("position"), field="RANK")
        points = _positive_int(row.get("pts"), field="RANK_POINTS")
        matches.append(
            (
                player_id,
                {
                    "place": str(position),
                    "points": str(points),
                    "player": name,
                    "country": str(player.get("countryAcr") or "").strip().upper(),
                    "snapshot_date": CUT_TOKEN,
                    "ranking_source": "RAPIDAPI_TENNIS_EXACT_CUT",
                },
            )
        )
    unique = {(pid, rec["place"], rec["points"], rec["player"], rec["country"]) for pid, rec in matches}
    if len(unique) != 1:
        raise ValueError(
            "EXACT_CUT_RANKING_NOT_UNIQUE_OR_MISSING:"
            + target_name
            + ":"
            + str(len(unique))
        )
    pid, place, points, player, country = next(iter(unique))
    return pid, {
        "place": place,
        "points": points,
        "player": player,
        "country": country,
        "snapshot_date": CUT_TOKEN,
        "ranking_source": "RAPIDAPI_TENNIS_EXACT_CUT",
    }


def _result_players(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for side in (1, 2):
        player = _mapping(row.get(f"player{side}"))
        pid = str(row.get(f"player{side}Id") or player.get("id") or "").strip()
        name = str(player.get("name") or row.get(f"player{side}Name") or "").strip()
        if pid or name:
            values.append((pid, name))
    return values




def _rapid_player_id_from_results(
    result_rows: list[Mapping[str, Any]],
    *,
    target_name: str,
) -> str:
    ids: set[str] = set()
    for row in result_rows:
        for pid, name in _result_players(row):
            if _norm(name) == _norm(target_name) and pid.isdigit() and int(pid) > 0:
                ids.add(pid)
    if len(ids) != 1:
        raise ValueError(
            "PRECUT_RESULT_PLAYER_ID_NOT_UNIQUE_OR_MISSING:"
            + target_name
            + ":"
            + str(sorted(ids))
        )
    return next(iter(ids))


def _exact_ranking_from_history(
    client: RapidApiTennisClient,
    *,
    rapid_player_id: str,
    target_name: str,
    country_hint: str = "",
) -> dict[str, Any]:
    payload = client.ranking_history(player_id=rapid_player_id, months=3)
    rows = payload.get("history") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list) and isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, Mapping):
            rows = data.get("history")
    if not isinstance(rows, list):
        rows = []
    matches: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        day = str(row.get("date") or "").strip()[:10]
        if day != CUT_TOKEN:
            continue
        position = str(row.get("position") or "").strip()
        points = str(
            row.get("pts")
            if row.get("pts") is not None
            else row.get("point")
            if row.get("point") is not None
            else row.get("points")
            if row.get("points") is not None
            else ""
        ).strip()
        if position.isdigit() and int(position) > 0 and points.isdigit() and int(points) >= 0:
            matches.add((position, points))
    if len(matches) != 1:
        raise ValueError(
            "PLAYER_RANKING_HISTORY_EXACT_CUT_NOT_UNIQUE_OR_MISSING:"
            + target_name
            + ":"
            + str(sorted(matches))
        )
    place, points = next(iter(matches))
    return {
        "place": place,
        "points": points,
        "player": target_name,
        "country": country_hint,
        "snapshot_date": CUT_TOKEN,
        "ranking_source": "RAPIDAPI_TENNIS_PLAYER_RANKING_HISTORY_EXACT_CUT",
    }

def _precut_identity_history(
    result_rows: list[Mapping[str, Any]],
    *,
    rapid_player_id: str,
    canonical_name: str,
) -> dict[str, Any]:
    observed_names: set[str] = set()
    source_rows = 0
    source_row_hashes: list[str] = []
    for row in result_rows:
        players = _result_players(row)
        matched = [
            name
            for pid, name in players
            if pid == rapid_player_id or _norm(name) == _norm(canonical_name)
        ]
        if not matched:
            continue
        if any(_norm(name) != _norm(canonical_name) for name in matched if name):
            raise ValueError("PRECUT_HISTORY_NAME_CONFLICT:" + canonical_name)
        observed_names.update(name for name in matched if name)
        source_rows += 1
        identity_only = {
            "match_id": str(row.get("matchId") or row.get("id") or ""),
            "date": str(row.get("date") or row.get("startTime") or ""),
            "players": sorted(
                [{"id": pid, "name": name} for pid, name in players],
                key=lambda x: (x["id"], x["name"]),
            ),
        }
        source_row_hashes.append(_sha(identity_only))
    if source_rows <= 0:
        raise ValueError("NO_PRECUT_PROVIDER_HISTORY:" + canonical_name)
    if not observed_names:
        observed_names.add(canonical_name)
    if any(_norm(name) != _norm(canonical_name) for name in observed_names):
        raise ValueError("PRECUT_HISTORY_OBSERVED_NAME_MISMATCH:" + canonical_name)
    return {
        "cutoff_exclusive_utc": "2026-09-21T00:00:00+00:00",
        "eligible_pre_cut_matches": source_rows,
        "observed_names": sorted(observed_names),
        "rapidapi_player_id": "rapidapi-tennis:player:" + rapid_player_id,
        "source_window": {
            "start": PRE_CUT_START.isoformat(),
            "stop": PRE_CUT_STOP.isoformat(),
        },
        "identity_only_source_row_sha256": sorted(source_row_hashes),
        "outcomes_used_for_metrics": 0,
        "metrics_opened": False,
    }



def _public_exact_cut_override(
    override: Mapping[str, Any] | None,
    *,
    target_name: str,
    country_hint: str,
) -> dict[str, Any]:
    if not isinstance(override, Mapping):
        raise ValueError("PUBLIC_EXACT_CUT_OVERRIDE_MISSING:" + target_name)
    if override.get("integrity_result") != "PASS_PUBLIC_EXACT_CUT_FALLBACK":
        raise ValueError("PUBLIC_EXACT_CUT_OVERRIDE_NOT_PASS:" + target_name)
    if _norm(override.get("player")) != _norm(target_name):
        raise ValueError("PUBLIC_EXACT_CUT_OVERRIDE_NAME_MISMATCH:" + target_name)
    if str(override.get("ranking_date") or "") != CUT_TOKEN:
        raise ValueError("PUBLIC_EXACT_CUT_OVERRIDE_DATE_MISMATCH:" + target_name)
    country = str(override.get("country") or "").strip().upper()
    if country_hint and country and country != country_hint:
        raise ValueError("PUBLIC_EXACT_CUT_OVERRIDE_COUNTRY_MISMATCH:" + target_name)
    paid = _mapping(override.get("paid_provider_attempts"))
    if (
        paid.get("rapidapi_snapshot_exact_cut") != "NOT_FOUND"
        or paid.get("rapidapi_player_ranking_history_exact_cut") != "NOT_FOUND"
    ):
        raise ValueError("PUBLIC_OVERRIDE_PAID_FALLBACK_ORDER_INVALID:" + target_name)
    rank = _positive_int(override.get("singles_rank"), field="PUBLIC_RANK")
    points = _positive_int(override.get("singles_points"), field="PUBLIC_RANK_POINTS")
    return {
        "place": str(rank),
        "points": str(points),
        "player": target_name,
        "country": country or country_hint,
        "snapshot_date": CUT_TOKEN,
        "ranking_source": "PUBLIC_HISTORICAL_EXACT_CUT_CORROBORATED_AFTER_PAID_FAILURE",
        "public_evidence": {
            "schema": str(override.get("schema") or ""),
            "primary_exact_date_source": dict(_mapping(override.get("primary_exact_date_source"))),
            "independent_rank_corroboration": dict(_mapping(override.get("independent_rank_corroboration"))),
        },
    }

def build_bridge(
    *,
    source_snapshot: Mapping[str, Any],
    client: RapidApiTennisClient,
    state_path: Path,
    as_of_utc: str,
    ranking_override: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if source_snapshot.get("integrity_result") != "PASS_SOURCE_SCHEDULE_IDENTITY":
        raise ValueError("SOFASCORE_SOURCE_INTEGRITY_NOT_PASS")
    protections = _mapping(source_snapshot.get("protections"))
    if (
        protections.get("odds_used") is not False
        or protections.get("outcomes_read") is not False
        or protections.get("post_start_data_used") is not False
        or protections.get("silent_imputation") is not False
    ):
        raise ValueError("SOFASCORE_SOURCE_PROTECTION_FLAG_INVALID")

    match = _mapping(source_snapshot.get("match"))
    competition = _mapping(source_snapshot.get("competition"))
    start = datetime.fromisoformat(
        str(match.get("event_start_utc") or "").replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    if start <= as_of:
        raise ValueError("SOFASCORE_EVENT_NOT_FUTURE")

    player_specs = [
        _mapping(match.get("player1")),
        _mapping(match.get("player2")),
    ]
    if len(player_specs) != 2 or any(not p.get("name") for p in player_specs):
        raise ValueError("SOFASCORE_TWO_PLAYERS_REQUIRED")

    ranking_rows = client.ranking_snapshot_rows(ranking_date=CUT_DATE)
    pre_cut_results = client.results_for_range(PRE_CUT_START, PRE_CUT_STOP)
    result_rows = [
        row for row in (pre_cut_results.get("data") or [])
        if isinstance(row, Mapping)
    ]
    state, state_sha = load_state(state_path)

    authority_records: list[dict[str, Any]] = []
    discovery_players: list[dict[str, Any]] = []
    verification_players: list[dict[str, Any]] = []

    for spec in player_specs:
        name = str(spec.get("name") or "").strip()
        sofa_id = str(spec.get("sofascore_player_id") or "").strip()
        if not sofa_id.isdigit() or int(sofa_id) <= 0:
            raise ValueError("SOFASCORE_PLAYER_ID_INVALID:" + name)

        try:
            rapid_id, ranking = _ranking_record(ranking_rows, target_name=name)
        except ValueError as ranking_error:
            if not str(ranking_error).startswith("EXACT_CUT_RANKING_NOT_UNIQUE_OR_MISSING:"):
                raise
            rapid_id = _rapid_player_id_from_results(
                result_rows,
                target_name=name,
            )
            profile_probe = _profile_identity(client.player_profile(player_id=rapid_id))
            try:
                ranking = _exact_ranking_from_history(
                    client,
                    rapid_player_id=rapid_id,
                    target_name=name,
                    country_hint=profile_probe["ioc"],
                )
            except ValueError as history_rank_error:
                if not str(history_rank_error).startswith(
                    "PLAYER_RANKING_HISTORY_EXACT_CUT_NOT_UNIQUE_OR_MISSING:"
                ):
                    raise
                ranking = _public_exact_cut_override(
                    ranking_override,
                    target_name=name,
                    country_hint=profile_probe["ioc"],
                )
        profile_payload = client.player_profile(player_id=rapid_id)
        profile = _profile_identity(profile_payload)
        if profile["id"] and profile["id"] != rapid_id:
            raise ValueError("RAPIDAPI_PROFILE_ID_MISMATCH:" + name)
        if _norm(profile["name"]) != _norm(name):
            raise ValueError("RAPIDAPI_PROFILE_NAME_MISMATCH:" + name)
        if profile["hand"] not in {"R", "L"}:
            raise ValueError("RAPIDAPI_PROFILE_HAND_MISSING:" + name)
        if len(profile["dob"]) != 10:
            raise ValueError("RAPIDAPI_PROFILE_DOB_MISSING:" + name)
        if ranking["country"] and profile["ioc"] and ranking["country"] != profile["ioc"]:
            raise ValueError("RAPIDAPI_PROFILE_IOC_MISMATCH:" + name)

        history_ready = audit_player(state, name)
        if history_ready.get("fully_history_ready") is not True:
            raise ValueError("R706_HISTORY_NOT_READY:" + name)
        required = history_ready.get("required_components")
        if not isinstance(required, Mapping) or not required or not all(
            value is True for value in required.values()
        ):
            raise ValueError("R706_REQUIRED_COMPONENT_MISSING:" + name)

        provider_history = _precut_identity_history(
            result_rows,
            rapid_player_id=rapid_id,
            canonical_name=name,
        )

        sofa_provider_id = "sofascore:player:" + sofa_id
        bio = {
            "name": name,
            "ioc": profile["ioc"] or ranking["country"],
            "dob": profile["dob"].replace("-", ""),
            "hand": profile["hand"],
            "master_id": "RAPIDAPI_PROFILE_" + rapid_id,
            "provider_profile_sha256": _sha(profile_payload),
        }
        authority_records.append(
            {
                "provider_player_id": sofa_provider_id,
                "provider_display_name": name,
                "provider_ioc_raw": ranking["country"],
                "provider_ioc_canonical": ranking["country"],
                "provider_rank": ranking["place"],
                "provider_rank_points": ranking["points"],
                "ranking_cut": CUT_TOKEN,
                "canonical_name": name,
                "canonical_source_id": "R706_STATE_SOFASCORE_PLAYER_" + sofa_id,
                "authority_basis": "SEALED_R706_STATE_PLUS_PRECUT_PROVIDER_HISTORY_AND_PROFILE",
                "sealed_r706_history": {
                    **history_ready,
                    "state_sha256": state_sha,
                },
                "pre_cut_provider_history": {
                    **provider_history,
                    "provider_player_id": sofa_provider_id,
                },
                "biographical_candidates": [bio],
                "biography_source": "RAPIDAPI_PROFILE_IMMUTABLE_DOB_HAND",
                "competitive_source": "RAPIDAPI_TENNIS_EXACT_2026_09_21_RANKING",
                "schedule_identity_source": "SOFASCORE_BROWSER_OPERA",
                "rapidapi_player_id": "rapidapi-tennis:player:" + rapid_id,
                "profile_competitive_fields_discarded": [
                    "currentRank",
                    "points",
                    "progress",
                ],
            }
        )
        discovery_players.append(
            {
                "name": name,
                "provider_player_id": sofa_provider_id,
                "provider_ranking": ranking,
                "ranking_provenance": {
                    "source_provider": "rapidapi_tennis",
                    "rapidapi_player_id": "rapidapi-tennis:player:" + rapid_id,
                    "snapshot_date": CUT_TOKEN,
                },
            }
        )
        verification_players.append(
            {
                "name": name,
                "sofascore_player_id": sofa_id,
                "rapidapi_player_id": rapid_id,
                "rank": int(ranking["place"]),
                "rank_points": int(ranking["points"]),
                "dob": profile["dob"],
                "hand": profile["hand"],
                "ioc": ranking["country"],
                "r706_history_ready": True,
                "pre_cut_provider_matches": provider_history["eligible_pre_cut_matches"],
            }
        )

    identity_payload = {
        "competition_id": (
            "sofascore:tournament:"
            + str(competition.get("sofascore_tournament_id") or "")
            + ":edition:"
            + str(competition.get("sofascore_edition_id") or "")
        ),
        "player_ids": sorted(
            str(p.get("sofascore_player_id") or "") for p in player_specs
        ),
        "round": str(match.get("round") or "First"),
        "event_start_utc": start.isoformat(),
    }
    deterministic_key = _sha(identity_payload)
    source_event_id = "sofascore-browser:match:" + deterministic_key

    evidence_bundle = {
        "source_snapshot": source_snapshot,
        "identity_payload": identity_payload,
        "players": verification_players,
        "as_of_utc": as_of.isoformat(),
    }
    source_sha = _sha(evidence_bundle)

    candidate = {
        "event_id": source_event_id,
        "canonical_source_event_id": source_event_id,
        "competition_id": identity_payload["competition_id"],
        "competition": str(competition.get("name") or "Wuning 3 Challenger"),
        "round": str(match.get("round") or "First"),
        "surface": "Hard",
        "tour_level": "C",
        "event_start_utc": start.isoformat(),
        "target_period": 20260921,
        "source_provider": "sofascore_browser",
        "source_reference": (
            str(source_snapshot.get("source_url") or "")
            + ";physical_snapshot="
            + str(
                source_snapshot.get("artifact_name")
                or "MATRIX_SOFASCORE_WUNING3_FAJING_SUN_AORAN_WANG_20261005.json"
            )
            + ";ranking_cut=2026-09-21;ranking_provider=rapidapi_tennis"
        ),
        "source_snapshot_sha256": source_sha,
        "players": discovery_players,
        "player_identities": [
            {
                "display_name": row["name"],
                "provider_player_id": row["provider_player_id"],
                "provider": "sofascore_browser",
                "provider_ranking": row["provider_ranking"],
            }
            for row in discovery_players
        ],
        "historical_identity_crosswalk_status": "PENDING",
    }
    discovery = {
        "schema": "MATRIX_COR0203_SOFASCORE_BROWSER_DISCOVERY_V1",
        "provider": "sofascore_browser",
        "status": "DISCOVERY_COMPLETED",
        "as_of_utc": as_of.isoformat(),
        "fixture_rows": 1,
        "eligible_input_events": 1,
        "eligible_candidates": [candidate],
        "provider_rejected": [],
        "ranking_cut": CUT_TOKEN,
        "automatic_model_feed": False,
        "governed_preregistration_required": True,
        "metrics_opened": False,
        "outcomes_read": 0,
        "odds_used": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    authority = {
        "schema": "MATRIX_COR0203_SOFASCORE_IDENTITY_AUTHORITY_20261005_V1",
        "ranking_cut": CUT_TOKEN,
        "records": authority_records,
        "sources": [
            {
                "provider": "sofascore_browser",
                "role": "schedule_identity",
                "source": str(source_snapshot.get("source_url") or ""),
            },
            {
                "provider": "rapidapi_tennis",
                "role": "exact_cut_ranking_profile_and_pre_cut_identity_history",
            },
            {
                "provider": "sealed_r706",
                "role": "model_history_readiness",
                "state_sha256": state_sha,
            },
        ],
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "silent_imputation": False,
        "real_money": "BLOCKED",
    }
    verification = {
        "schema": "MATRIX_COR0203_SOFASCORE_BRIDGE_VERIFICATION_V1",
        "as_of_utc": as_of.isoformat(),
        "source_event_id": source_event_id,
        "source_snapshot_sha256": source_sha,
        "event_start_utc": start.isoformat(),
        "players": verification_players,
        "ranking_cut": CUT_TOKEN,
        "ranking_rows_scanned": len(ranking_rows),
        "pre_cut_result_rows_scanned": len(result_rows),
        "network_calls": client.request_count,
        "metrics_opened": False,
        "outcomes_used_for_metrics": 0,
        "odds_used": False,
        "post_cut_competitive_data_used": False,
        "silent_imputation": False,
        "real_money": "BLOCKED",
        "integrity_result": "PASS",
    }
    return discovery, authority, verification


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-snapshot", required=True)
    parser.add_argument("--state-b64", default="evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64")
    parser.add_argument("--out-discovery", required=True)
    parser.add_argument("--out-authority", required=True)
    parser.add_argument("--out-verification", required=True)
    parser.add_argument("--ranking-override")
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    as_of = args.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    discovery, authority, verification = build_bridge(
        source_snapshot=_load(Path(args.source_snapshot)),
        client=RapidApiTennisClient(key),
        state_path=Path(args.state_b64),
        as_of_utc=as_of,
        ranking_override=(
            _load(Path(args.ranking_override))
            if args.ranking_override
            else None
        ),
    )
    _write(Path(args.out_discovery), discovery)
    _write(Path(args.out_authority), authority)
    _write(Path(args.out_verification), verification)
    print(
        json.dumps(
            {
                "status": discovery["status"],
                "eligible_input_events": discovery["eligible_input_events"],
                "source_event_id": discovery["eligible_candidates"][0]["event_id"],
                "players": verification["players"],
                "network_calls": verification["network_calls"],
                "integrity_result": verification["integrity_result"],
                "real_money": "BLOCKED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
