from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_batch_linkage_gate import _real_name, _utc
from tools.cor0203_prospective_producer import extend_state, load_state

STATIC_FIELDS = ("hand", "age", "rank", "rank_points")
SURFACE = "Hard"


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _same_scalar(left: Any, right: Any) -> bool:
    if _finite_number(left) and _finite_number(right):
        return abs(float(left) - float(right)) <= 1e-12
    return str(left) == str(right)


def _static4_by_event(static4: Mapping[str, Any], event_rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(static4.get("events"), list):
        result: dict[str, Mapping[str, Any]] = {}
        for row in static4["events"]:
            event_id = str(row.get("event_id") or "")
            if not event_id or event_id in result:
                raise ValueError("STATIC4_DUPLICATE_OR_MISSING_EVENT_ID")
            result[event_id] = row
        return result

    event_id = str(static4.get("event_id") or "")
    if event_id:
        return {event_id: static4}

    if len(event_rows) == 1 and isinstance(static4.get("players"), Mapping):
        return {str(event_rows[0].get("event_id") or ""): static4}

    raise ValueError("STATIC4_EVENT_LINKAGE_MISSING")


def _history_blockers(state: Mapping[str, Any], player: str) -> list[str]:
    blockers: list[str] = []
    history = state.get("history", {})

    matches = list(history.get("matches", {}).get(player, []))
    if not matches:
        blockers.append("FORM_HISTORY_MISSING")

    for section, code in (
        ("overall", "OVERALL_HISTORY_MISSING"),
        ("serve", "SERVE_HISTORY_MISSING"),
        ("ret", "RETURN_HISTORY_MISSING"),
        ("opp_strength", "OPPONENT_STRENGTH_HISTORY_MISSING"),
    ):
        pair = history.get(section, {}).get(player)
        if not isinstance(pair, list) or len(pair) < 2 or not _finite_number(pair[1]) or float(pair[1]) <= 0:
            blockers.append(code)

    surface_pair = history.get("surface", {}).get(player, {}).get(SURFACE)
    if (
        not isinstance(surface_pair, list)
        or len(surface_pair) < 2
        or not _finite_number(surface_pair[1])
        or float(surface_pair[1]) <= 0
    ):
        blockers.append("SURFACE_HISTORY_MISSING")

    if player not in state.get("elo_overall", {}):
        blockers.append("ELO_OVERALL_MISSING")
    if player not in state.get("elo_surface", {}).get(SURFACE, {}):
        blockers.append("ELO_SURFACE_MISSING")
    if player not in state.get("glicko_overall", {}):
        blockers.append("GLICKO_OVERALL_MISSING")
    if player not in state.get("glicko_surface", {}).get(SURFACE, {}):
        blockers.append("GLICKO_SURFACE_MISSING")

    return blockers


def partition_batch(
    *,
    prefeature: Mapping[str, Any],
    static4: Mapping[str, Any],
    events: Mapping[str, Any],
    state: Mapping[str, Any],
    freeze_at_utc: str,
    expected_starting_count: int,
    existing_event_ids: set[str] | None = None,
) -> dict[str, Any]:
    freeze = _utc(freeze_at_utc)
    existing_event_ids = set(existing_event_ids or set())

    if prefeature.get("created_before_feature_acquisition") is not True:
        raise ValueError("PREFEATURE_ORDERING_NOT_PROVEN")
    declared_pre_start = int(prefeature.get("starting_observation_count", -1))
    declared_event_start = int(events.get("starting_observation_count", -1))
    if declared_pre_start != declared_event_start:
        raise ValueError("PREREGISTRATION_EVENT_START_COUNT_MISMATCH")
    if declared_event_start > int(expected_starting_count):
        raise ValueError("DECLARED_START_COUNT_AHEAD_OF_PHYSICAL")
    if prefeature.get("holdout_id") != events.get("holdout_id"):
        raise ValueError("HOLDOUT_ID_MISMATCH")
    if static4.get("holdout_id") not in (None, events.get("holdout_id")):
        raise ValueError("STATIC4_HOLDOUT_ID_MISMATCH")

    pre_rows = list(prefeature.get("events") or [])
    event_rows = list(events.get("events") or [])
    if not event_rows:
        raise ValueError("EMPTY_EVENT_BATCH")

    periods = {int(row["target_period"]) for row in event_rows}
    if len(periods) != 1:
        raise ValueError("ONE_TARGET_PERIOD_PER_BATCH_REQUIRED")

    pre_by_id: dict[str, Mapping[str, Any]] = {}
    for row in pre_rows:
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id in pre_by_id:
            raise ValueError("PREFEATURE_DUPLICATE_EVENT_ID")
        pre_by_id[event_id] = row

    static_by_id = _static4_by_event(static4, event_rows)

    valid_rows: list[Mapping[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    history_players: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    for row in event_rows:
        event_id = str(row.get("event_id") or "")
        blockers: list[str] = []
        if not event_id or event_id in seen:
            blockers.append("EVENT_BATCH_DUPLICATE_OR_MISSING_EVENT_ID")
        if event_id in existing_event_ids:
            blockers.append("EVENT_ALREADY_FROZEN")
        seen.add(event_id)

        pre = pre_by_id.get(event_id)
        if pre is None:
            blockers.append("MISSING_PRIOR_PREREGISTRATION")
        else:
            if pre.get("features_loaded") is not False:
                blockers.append("PREFEATURE_FEATURES_ALREADY_LOADED")
            if pre.get("outcome") is not None:
                blockers.append("PREFEATURE_OUTCOME_NOT_NULL")
            if pre.get("metrics_opened") is not False:
                blockers.append("PREFEATURE_METRICS_OPENED")

        players = list(row.get("players") or [])
        if len(players) != 2:
            blockers.append("TWO_PLAYERS_REQUIRED")
            players = []

        names = [str(p.get("name") or "") for p in players]
        if players and (not all(_real_name(x) for x in names) or names[0] == names[1]):
            blockers.append("IDENTITY_NOT_FIXED")

        if str(row.get("surface")) != SURFACE:
            blockers.append("SURFACE_OUT_OF_DOMAIN")
        if str(row.get("tour_level")) not in {"C", "ATP Challenger"}:
            blockers.append("TOUR_LEVEL_OUT_OF_DOMAIN")

        strong_identity_required = bool(row.get("identity_crosswalk_required"))
        if strong_identity_required:
            if str(row.get("source_provider") or "") != "api_tennis":
                blockers.append("STRONG_IDENTITY_PROVIDER_INVALID")
            source_sha = str(row.get("source_snapshot_sha256") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
                blockers.append("SOURCE_SNAPSHOT_SHA_REQUIRED")
            if not str(row.get("identity_crosswalk_reference") or "").strip():
                blockers.append("IDENTITY_CROSSWALK_REFERENCE_REQUIRED")

        try:
            start = _utc(str(row.get("event_start_utc")))
            if freeze >= start:
                blockers.append("POST_START_FREEZE_FORBIDDEN")
        except (TypeError, ValueError):
            blockers.append("START_AUTHORITY_INVALID")

        static_row = static_by_id.get(event_id)
        static_players = static_row.get("players", {}) if isinstance(static_row, Mapping) else {}
        if not isinstance(static_players, Mapping):
            blockers.append("STATIC4_PLAYERS_INVALID")
            static_players = {}

        for player in players:
            name = str(player.get("name") or "")
            s = static_players.get(name)
            if not isinstance(s, Mapping):
                blockers.append("STATIC4_PLAYER_MISSING:" + name)
                continue
            for field in STATIC_FIELDS:
                if field not in player or field not in s:
                    blockers.append(f"STATIC4_FIELD_MISSING:{name}:{field}")
                    continue
                if not _same_scalar(player[field], s[field]):
                    blockers.append(f"STATIC4_VALUE_MISMATCH:{name}:{field}")

            event_source_id = str(player.get("source_id") or "")
            static_source_id = str(s.get("source_id") or "")
            if strong_identity_required:
                provider_player_id = str(player.get("provider_player_id") or "")
                if not event_source_id:
                    blockers.append("CANONICAL_SOURCE_ID_REQUIRED:" + name)
                if not re.fullmatch(r"api-tennis:player:\d+", provider_player_id):
                    blockers.append("PROVIDER_PLAYER_ID_REQUIRED:" + name)
                if str(player.get("identity_binding") or "") != "API_TENNIS_TO_STATIC_CUT_STRONG_CROSSWALK":
                    blockers.append("STRONG_IDENTITY_BINDING_REQUIRED:" + name)
                if not static_source_id:
                    blockers.append("STATIC4_CANONICAL_SOURCE_ID_REQUIRED:" + name)
                elif event_source_id != static_source_id:
                    blockers.append("STATIC4_SOURCE_ID_MISMATCH:" + name)
                static_provider_id = str(s.get("provider_player_id") or "")
                if static_provider_id != provider_player_id:
                    blockers.append("STATIC4_PROVIDER_ID_MISMATCH:" + name)
            elif event_source_id and static_source_id and event_source_id != static_source_id:
                blockers.append("STATIC4_SOURCE_ID_MISMATCH:" + name)

            p_blockers = _history_blockers(state, name)
            if p_blockers:
                blockers.extend(f"{code}:{name}" for code in p_blockers)
            history_players[name] = {
                "matches": len(state.get("history", {}).get("matches", {}).get(name, [])),
                "overall_n": (
                    state.get("history", {}).get("overall", {}).get(name, [0.0, 0.0])[1]
                    if name in state.get("history", {}).get("overall", {})
                    else 0
                ),
                "surface_n": (
                    state.get("history", {}).get("surface", {}).get(name, {}).get(SURFACE, [0.0, 0.0])[1]
                    if name in state.get("history", {}).get("surface", {})
                    and SURFACE in state.get("history", {}).get("surface", {}).get(name, {})
                    else 0
                ),
                "serve_n": (
                    state.get("history", {}).get("serve", {}).get(name, [0.0, 0.0])[1]
                    if name in state.get("history", {}).get("serve", {})
                    else 0
                ),
                "return_n": (
                    state.get("history", {}).get("ret", {}).get(name, [0.0, 0.0])[1]
                    if name in state.get("history", {}).get("ret", {})
                    else 0
                ),
                "opponent_strength_n": (
                    state.get("history", {}).get("opp_strength", {}).get(name, [0.0, 0.0])[1]
                    if name in state.get("history", {}).get("opp_strength", {})
                    else 0
                ),
                "elo_overall_present": name in state.get("elo_overall", {}),
                "elo_surface_present": name in state.get("elo_surface", {}).get(SURFACE, {}),
                "glicko_overall_present": name in state.get("glicko_overall", {}),
                "glicko_surface_present": name in state.get("glicko_surface", {}).get(SURFACE, {}),
            }

        blockers = sorted(set(blockers))
        if blockers:
            blocked_rows.append({"event_id": event_id, "blockers": blockers})
        else:
            valid_rows.append(row)

    filtered_manifest = dict(events)
    filtered_manifest["events"] = valid_rows
    filtered_manifest["starting_observation_count"] = int(expected_starting_count)

    return {
        "schema": "MATRIX_COR0203_BATCH_PREFLIGHT_V1",
        "holdout_id": events.get("holdout_id"),
        "freeze_at_utc": freeze.isoformat(),
        "declared_starting_observation_count": declared_event_start,
        "starting_observation_count": int(expected_starting_count),
        "count_rebased_at_freeze": declared_event_start != int(expected_starting_count),
        "input_events": len(event_rows),
        "valid_events": len(valid_rows),
        "blocked_events": len(blocked_rows),
        "valid_event_ids": [str(row["event_id"]) for row in valid_rows],
        "blocked": blocked_rows,
        "history_players": history_players,
        "filtered_manifest": filtered_manifest,
        "same_period_results_used": False,
        "silent_imputation_allowed": False,
        "result": "PASS_WITH_BLOCKERS" if blocked_rows and valid_rows else (
            "ALL_BLOCKED" if blocked_rows else "PASS"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-b64", required=True)
    parser.add_argument("--annual-2026", required=True)
    parser.add_argument("--prefeature", required=True)
    parser.add_argument("--static4", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--freeze-at", required=True)
    parser.add_argument("--expected-start", required=True, type=int)
    parser.add_argument("--filtered-out", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--history-out", required=True)
    args = parser.parse_args()

    prefeature = json.loads(Path(args.prefeature).read_text())
    static4 = json.loads(Path(args.static4).read_text())
    events = json.loads(Path(args.events).read_text())

    state, _ = load_state(Path(args.state_b64))
    annual_rows = list(
        csv.DictReader(Path(args.annual_2026).open(encoding="utf-8-sig", newline=""))
    )
    periods = {int(row["target_period"]) for row in events.get("events", [])}
    if len(periods) != 1:
        raise ValueError("ONE_TARGET_PERIOD_PER_BATCH_REQUIRED")
    target_period = next(iter(periods))
    state, used_rows, period_count = extend_state(state, annual_rows, target_period)

    result = partition_batch(
        prefeature=prefeature,
        static4=static4,
        events=events,
        state=state,
        freeze_at_utc=args.freeze_at,
        expected_starting_count=args.expected_start,
    )

    filtered = result.pop("filtered_manifest")
    Path(args.filtered_out).write_text(json.dumps(filtered, indent=2, sort_keys=True) + "\n")
    Path(args.report_out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    history = {
        "schema": "MATRIX_COR0203_BATCH_HISTORY_GATE_V2",
        "target_period": target_period,
        "annual_rows_used_preperiod": used_rows,
        "annual_periods_used_preperiod": period_count,
        "players": result["history_players"],
        "valid_event_ids": result["valid_event_ids"],
        "blocked": result["blocked"],
        "result": result["result"],
        "same_period_results_used": False,
        "silent_imputation": False,
    }
    Path(args.history_out).write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")

    print(json.dumps({
        "input_events": result["input_events"],
        "valid_events": result["valid_events"],
        "blocked_events": result["blocked_events"],
        "result": result["result"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
