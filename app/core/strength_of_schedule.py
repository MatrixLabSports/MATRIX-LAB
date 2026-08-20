from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from statistics import median
from typing import Any, Iterable, Mapping

from app.core.opponent_quality_evidence import SQLiteOpponentQualityLedger


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _summary(
    events: Iterable[Any],
    *,
    sport: str,
    quality_key: str,
    quality_ledger: SQLiteOpponentQualityLedger,
) -> Mapping[str, Any]:
    values: list[float] = []
    quality_fingerprints: list[str] = []
    total = 0

    for event in events:
        total += 1
        quality = quality_ledger.resolve_as_of(
            sport=sport,
            opponent_canonical_id=event.opponent_canonical_id,
            quality_key=quality_key,
            as_of=event.source_available_at,
        )
        if quality is None:
            continue
        values.append(float(quality["quality_value"]))
        quality_fingerprints.append(quality["quality_fingerprint"])

    return {
        "sample_size": total,
        "quality_observed": len(values),
        "quality_missing": total - len(values),
        "coverage_rate": (len(values) / total if total else None),
        "mean_quality": (sum(values) / len(values) if values else None),
        "median_quality": (median(values) if values else None),
        "quality_fingerprints": sorted(set(quality_fingerprints)),
        "recency_weighting_applied": False,
    }


@dataclass(frozen=True)
class StrengthOfScheduleProfile:
    sport: str
    canonical_id: str
    quality_key: str
    history_fingerprint: str
    windows: Mapping[str, Any]
    season: Mapping[str, Any]
    career: Mapping[str, Any]
    profile_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.strength-of-schedule-profile/1",
            "sport": self.sport,
            "canonical_id": self.canonical_id,
            "quality_key": self.quality_key,
            "history_fingerprint": self.history_fingerprint,
            "windows": self.windows,
            "season": self.season,
            "career": self.career,
            "profile_fingerprint": self.profile_fingerprint,
            "point_in_time_enforced": True,
            "recency_weighting_applied": False,
            "missing_is_zero": False,
            "automatic_model_promotion": False,
        }


def build_strength_of_schedule_profile(
    *,
    history,
    quality_key: str,
    quality_ledger: SQLiteOpponentQualityLedger,
) -> StrengthOfScheduleProfile:
    if history.sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")
    if not isinstance(quality_key, str) or not quality_key:
        raise ValueError("INVALID_QUALITY_KEY")

    windows = {
        str(size): _summary(
            values,
            sport=history.sport,
            quality_key=quality_key,
            quality_ledger=quality_ledger,
        )
        for size, values in history.windows
    }
    season = _summary(
        history.season,
        sport=history.sport,
        quality_key=quality_key,
        quality_ledger=quality_ledger,
    )
    career = _summary(
        history.career,
        sport=history.sport,
        quality_key=quality_key,
        quality_ledger=quality_ledger,
    )

    base = {
        "schema": "matrix.strength-of-schedule-profile/1",
        "sport": history.sport,
        "canonical_id": history.canonical_id,
        "quality_key": quality_key,
        "history_fingerprint": history.history_fingerprint,
        "windows": windows,
        "season": season,
        "career": career,
        "point_in_time_enforced": True,
        "recency_weighting_applied": False,
        "missing_is_zero": False,
        "automatic_model_promotion": False,
    }

    return StrengthOfScheduleProfile(
        sport=history.sport,
        canonical_id=history.canonical_id,
        quality_key=quality_key,
        history_fingerprint=history.history_fingerprint,
        windows=windows,
        season=season,
        career=career,
        profile_fingerprint=_sha(base),
    )
