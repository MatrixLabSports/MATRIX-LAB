from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any, Iterable

from app.core.opponent_quality_evidence import (
    SQLiteOpponentQualityLedger,
)


UTC = timezone.utc


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _iso(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class ComparableOpponentPolicy:
    sport: str
    quality_key: str
    max_absolute_quality_delta: float
    require_same_competition: bool
    policy_fingerprint: str


@dataclass(frozen=True)
class ComparableOpponentCohort:
    sport: str
    target_opponent_canonical_id: str
    as_of: datetime
    target_quality_value: float
    target_quality_fingerprint: str
    selected_event_fingerprints: tuple[str, ...]
    excluded_missing_quality: int
    excluded_quality_delta: int
    excluded_competition: int
    policy_fingerprint: str
    cohort_fingerprint: str


def build_comparable_opponent_policy(
    *,
    sport: str,
    quality_key: str,
    max_absolute_quality_delta: float,
    require_same_competition: bool = False,
) -> ComparableOpponentPolicy:
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")

    if not isinstance(quality_key, str) or not quality_key:
        raise ValueError("INVALID_QUALITY_KEY")

    if (
        isinstance(max_absolute_quality_delta, bool)
        or not isinstance(
            max_absolute_quality_delta,
            (int, float),
        )
    ):
        raise ValueError("INVALID_QUALITY_DELTA")

    delta = float(max_absolute_quality_delta)
    if not math.isfinite(delta) or delta < 0:
        raise ValueError("INVALID_QUALITY_DELTA")

    if not isinstance(require_same_competition, bool):
        raise ValueError("INVALID_COMPETITION_POLICY")

    base = {
        "schema": "matrix.comparable-opponent-policy/1",
        "sport": sport,
        "quality_key": quality_key,
        "max_absolute_quality_delta": delta,
        "require_same_competition": (
            require_same_competition
        ),
        "automatic_threshold_tuning": False,
        "automatic_model_promotion": False,
    }

    return ComparableOpponentPolicy(
        sport=sport,
        quality_key=quality_key,
        max_absolute_quality_delta=delta,
        require_same_competition=(
            require_same_competition
        ),
        policy_fingerprint=_sha(base),
    )


def build_comparable_opponent_cohort(
    *,
    events: Iterable[Any],
    target_opponent_canonical_id: str,
    target_competition_key: str | None,
    as_of: datetime,
    policy: ComparableOpponentPolicy,
    quality_ledger: SQLiteOpponentQualityLedger,
) -> ComparableOpponentCohort:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("INVALID_AS_OF")
    as_of = as_of.astimezone(UTC)

    target = quality_ledger.resolve_as_of(
        sport=policy.sport,
        opponent_canonical_id=(
            target_opponent_canonical_id
        ),
        quality_key=policy.quality_key,
        as_of=as_of,
    )
    if target is None:
        raise ValueError(
            "TARGET_OPPONENT_QUALITY_NOT_AVAILABLE_AS_OF"
        )

    target_value = float(target["quality_value"])

    selected: list[str] = []
    missing = 0
    delta_excluded = 0
    competition_excluded = 0

    for event in events:
        event_at = event.event_at
        if (
            not isinstance(event_at, datetime)
            or event_at.tzinfo is None
            or event_at.utcoffset() is None
        ):
            raise ValueError("INVALID_HISTORY_EVENT_AT")

        event_at = event_at.astimezone(UTC)

        if event_at >= as_of:
            raise ValueError(
                "HISTORY_EVENT_NOT_BEFORE_AS_OF"
            )

        if policy.require_same_competition:
            if target_competition_key is None:
                raise ValueError(
                    "TARGET_COMPETITION_REQUIRED"
                )
            if (
                event.competition_key
                != target_competition_key
            ):
                competition_excluded += 1
                continue

        # Critical anti-leakage rule:
        # quality for the historical opponent must have
        # been available no later than the historical
        # event start, never at a later correction time.
        historical_quality = quality_ledger.resolve_as_of(
            sport=policy.sport,
            opponent_canonical_id=(
                event.opponent_canonical_id
            ),
            quality_key=policy.quality_key,
            as_of=event_at,
        )

        if historical_quality is None:
            missing += 1
            continue

        if (
            abs(
                float(
                    historical_quality[
                        "quality_value"
                    ]
                )
                - target_value
            )
            > policy.max_absolute_quality_delta
        ):
            delta_excluded += 1
            continue

        selected.append(event.event_fingerprint)

    selected_fps = tuple(sorted(selected))

    base = {
        "schema": "matrix.comparable-opponent-cohort/2",
        "sport": policy.sport,
        "target_opponent_canonical_id": (
            target_opponent_canonical_id
        ),
        "as_of": _iso(as_of),
        "target_quality_value": target_value,
        "target_quality_fingerprint": (
            target["quality_fingerprint"]
        ),
        "selected_event_fingerprints": list(
            selected_fps
        ),
        "excluded_missing_quality": missing,
        "excluded_quality_delta": delta_excluded,
        "excluded_competition": competition_excluded,
        "policy_fingerprint": (
            policy.policy_fingerprint
        ),
        "historical_quality_cutoff": "event_at",
        "future_leakage_allowed": False,
        "name_join_used": False,
    }

    return ComparableOpponentCohort(
        sport=policy.sport,
        target_opponent_canonical_id=(
            target_opponent_canonical_id
        ),
        as_of=as_of,
        target_quality_value=target_value,
        target_quality_fingerprint=(
            target["quality_fingerprint"]
        ),
        selected_event_fingerprints=selected_fps,
        excluded_missing_quality=missing,
        excluded_quality_delta=delta_excluded,
        excluded_competition=competition_excluded,
        policy_fingerprint=policy.policy_fingerprint,
        cohort_fingerprint=_sha(base),
    )
