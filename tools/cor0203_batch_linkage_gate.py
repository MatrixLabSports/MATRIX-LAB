from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

PLACEHOLDER_TOKENS = {
    "", "TBD", "TBA", "Q", "Q1", "Q2", "Q3", "Q4",
    "QUALIFIER", "LUCKY_LOSER", "LL", "WINNER", "LOSER",
}


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _real_name(value: str) -> bool:
    token = str(value or "").strip().upper()
    if token in PLACEHOLDER_TOKENS:
        return False
    if token.startswith(("WINNER OF ", "LOSER OF ", "QF", "SF")):
        return False
    return True


def validate_batch_linkage(
    *,
    prefeature: Mapping[str, Any],
    events: Mapping[str, Any],
    freeze_at_utc: str,
    expected_starting_count: int,
) -> dict[str, Any]:
    freeze = _utc(freeze_at_utc)

    if prefeature.get("created_before_feature_acquisition") is not True:
        raise ValueError("PREFEATURE_ORDERING_NOT_PROVEN")
    if int(prefeature.get("starting_observation_count", -1)) != int(expected_starting_count):
        raise ValueError("PREFEATURE_START_COUNT_MISMATCH")
    if int(events.get("starting_observation_count", -1)) != int(expected_starting_count):
        raise ValueError("EVENT_BATCH_START_COUNT_MISMATCH")
    if prefeature.get("holdout_id") != events.get("holdout_id"):
        raise ValueError("HOLDOUT_ID_MISMATCH")

    pre_rows = list(prefeature.get("events") or [])
    event_rows = list(events.get("events") or [])
    if not event_rows:
        raise ValueError("EMPTY_EVENT_BATCH")

    pre_by_id = {}
    for row in pre_rows:
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id in pre_by_id:
            raise ValueError("PREFEATURE_DUPLICATE_EVENT_ID")
        pre_by_id[event_id] = row

    seen = set()
    checked = []
    for row in event_rows:
        event_id = str(row.get("event_id") or "")
        if not event_id or event_id in seen:
            raise ValueError("EVENT_BATCH_DUPLICATE_EVENT_ID")
        seen.add(event_id)

        pre = pre_by_id.get(event_id)
        if pre is None:
            raise ValueError("MISSING_PRIOR_PREREGISTRATION:" + event_id)
        if pre.get("features_loaded") is not False:
            raise ValueError("PREFEATURE_FEATURES_ALREADY_LOADED:" + event_id)
        if pre.get("outcome") is not None:
            raise ValueError("PREFEATURE_OUTCOME_NOT_NULL:" + event_id)
        if pre.get("metrics_opened") is not False:
            raise ValueError("PREFEATURE_METRICS_OPENED:" + event_id)

        players = list(row.get("players") or [])
        if len(players) != 2:
            raise ValueError("TWO_PLAYERS_REQUIRED:" + event_id)
        names = [str(p.get("name") or "") for p in players]
        if not all(_real_name(x) for x in names) or names[0] == names[1]:
            raise ValueError("IDENTITY_NOT_FIXED:" + event_id)

        if str(row.get("surface")) != "Hard":
            raise ValueError("SURFACE_OUT_OF_DOMAIN:" + event_id)
        if str(row.get("tour_level")) not in {"C", "ATP Challenger"}:
            raise ValueError("TOUR_LEVEL_OUT_OF_DOMAIN:" + event_id)

        start = _utc(str(row.get("event_start_utc")))
        if freeze >= start:
            raise ValueError("POST_START_FREEZE_FORBIDDEN:" + event_id)

        checked.append(event_id)

    return {
        "schema": "MATRIX_COR0203_BATCH_LINKAGE_GATE_V1",
        "holdout_id": events["holdout_id"],
        "starting_observation_count": int(expected_starting_count),
        "batch_size": len(checked),
        "event_ids": checked,
        "freeze_at_utc": freeze.isoformat(),
        "result": "PASS",
    }
