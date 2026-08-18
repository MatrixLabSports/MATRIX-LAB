from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.research.football.dataset import FootballResearchRow


_FORBIDDEN_FEATURE_TOKENS = (
    "label",
    "outcome",
    "postmatch",
    "post_match",
    "full_time_result",
    "final_result",
    "final_score",
    "home_goals_final",
    "away_goals_final",
    "final_total_goals",
)


@dataclass(frozen=True)
class DatasetQualityPolicy:
    min_rows: int = 500
    min_fixtures: int = 500
    min_partition_rows: Mapping[str, int] | None = None
    max_feature_missing_fraction: float = 0.35
    min_positive_rate: float = 0.03
    max_positive_rate: float = 0.97
    require_consistent_feature_schema: bool = True

    def __post_init__(self) -> None:
        for name in ("min_rows", "min_fixtures"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.min_partition_rows is not None:
            for partition, count in self.min_partition_rows.items():
                if partition not in {"train", "validation", "test"}:
                    raise ValueError("min_partition_rows contains an invalid partition")
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("partition minimums must be non-negative integers")
        for name in ("max_feature_missing_fraction", "min_positive_rate", "max_positive_rate"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.min_positive_rate > self.max_positive_rate:
            raise ValueError("min_positive_rate cannot exceed max_positive_rate")


@dataclass(frozen=True)
class FeatureQuality:
    name: str
    missing_count: int
    missing_fraction: float
    observed_types: tuple[str, ...]


@dataclass(frozen=True)
class DatasetQualityReport:
    row_count: int
    fixture_count: int
    partition_counts: dict[str, int]
    market_label: str
    positive_rate: float
    feature_schema_count: int
    feature_quality: tuple[FeatureQuality, ...]
    suspicious_features: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.reasons


def _is_suspicious_feature(name: str, label_names: set[str]) -> bool:
    normalized = name.strip().lower()
    if normalized in {label.lower() for label in label_names}:
        return True
    return any(token in normalized for token in _FORBIDDEN_FEATURE_TOKENS)


def audit_research_dataset(
    rows: Iterable[FootballResearchRow],
    *,
    market_label: str,
    policy: DatasetQualityPolicy = DatasetQualityPolicy(),
) -> DatasetQualityReport:
    items = list(rows)
    if not isinstance(market_label, str) or not market_label.strip():
        raise ValueError("market_label cannot be empty")
    market_label = market_label.strip()
    if not items:
        raise ValueError("dataset audit requires at least one row")

    label_names = {name for row in items for name in row.labels}
    if market_label not in label_names:
        raise ValueError(f"market label not present: {market_label}")

    outcomes: list[bool] = []
    for row in items:
        value = row.labels.get(market_label)
        if not isinstance(value, bool):
            raise ValueError("binary market audit requires boolean labels")
        outcomes.append(value)

    fixture_ids = {row.fixture_id for row in items}
    partition_counts = {
        name: sum(1 for row in items if row.partition == name)
        for name in ("train", "validation", "test")
    }
    feature_sets = {tuple(sorted(row.features)) for row in items}
    all_features = sorted({name for row in items for name in row.features})

    feature_quality: list[FeatureQuality] = []
    for name in all_features:
        values = [row.features.get(name) for row in items]
        missing = sum(value is None for value in values)
        observed_types = tuple(sorted({type(value).__name__ for value in values if value is not None}))
        feature_quality.append(
            FeatureQuality(
                name=name,
                missing_count=missing,
                missing_fraction=missing / len(items),
                observed_types=observed_types,
            )
        )

    suspicious = tuple(sorted(name for name in all_features if _is_suspicious_feature(name, label_names)))
    positive_rate = sum(outcomes) / len(outcomes)
    reasons: list[str] = []

    if len(items) < policy.min_rows:
        reasons.append("insufficient_rows")
    if len(fixture_ids) < policy.min_fixtures:
        reasons.append("insufficient_fixtures")
    if policy.min_partition_rows:
        for partition, minimum in policy.min_partition_rows.items():
            if partition_counts[partition] < minimum:
                reasons.append(f"insufficient_{partition}_rows")
    if policy.require_consistent_feature_schema and len(feature_sets) != 1:
        reasons.append("inconsistent_feature_schema")
    if suspicious:
        reasons.append("suspicious_leakage_feature_names")
    if any(item.missing_fraction > policy.max_feature_missing_fraction for item in feature_quality):
        reasons.append("feature_missingness_above_limit")
    if positive_rate < policy.min_positive_rate or positive_rate > policy.max_positive_rate:
        reasons.append("extreme_class_imbalance")

    return DatasetQualityReport(
        row_count=len(items),
        fixture_count=len(fixture_ids),
        partition_counts=partition_counts,
        market_label=market_label,
        positive_rate=positive_rate,
        feature_schema_count=len(feature_sets),
        feature_quality=tuple(feature_quality),
        suspicious_features=suspicious,
        reasons=tuple(dict.fromkeys(reasons)),
    )
