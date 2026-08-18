from datetime import datetime, timedelta, timezone

import pytest

from app.research.football.dataset import FootballResearchRow
from app.research.football.quality import DatasetQualityPolicy, audit_research_dataset


def make_row(i, *, feature_extra=None, missing=False, partition="train", label=None):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    features = {"competition": "Liga", "form": None if missing else 0.5}
    if feature_extra:
        features.update(feature_extra)
    return FootballResearchRow(
        fixture_id=str(i),
        as_of_utc=t.isoformat(),
        partition=partition,
        features=features,
        labels={"over_2_5": (i % 2 == 0) if label is None else label},
        label_observed_at_utc=(t + timedelta(hours=6)).isoformat(),
    )


def permissive_policy(**kwargs):
    defaults = dict(min_rows=1, min_fixtures=1, max_feature_missing_fraction=1.0, min_positive_rate=0, max_positive_rate=1)
    defaults.update(kwargs)
    return DatasetQualityPolicy(**defaults)


def test_dataset_quality_passes_consistent_small_dataset_under_explicit_policy():
    report = audit_research_dataset(
        [make_row(i) for i in range(10)],
        market_label="over_2_5",
        policy=permissive_policy(),
    )
    assert report.passed
    assert report.row_count == 10
    assert report.fixture_count == 10
    assert report.positive_rate == 0.5
    assert report.feature_schema_count == 1


def test_dataset_quality_detects_suspicious_feature_name_and_schema_drift():
    rows = [make_row(1), make_row(2, feature_extra={"final_total_goals": 3})]
    report = audit_research_dataset(rows, market_label="over_2_5", policy=permissive_policy())
    assert not report.passed
    assert "suspicious_leakage_feature_names" in report.reasons
    assert "inconsistent_feature_schema" in report.reasons
    assert "final_total_goals" in report.suspicious_features


def test_dataset_quality_detects_missingness_and_class_imbalance():
    rows = [make_row(i, missing=i < 9, label=True) for i in range(10)]
    report = audit_research_dataset(
        rows,
        market_label="over_2_5",
        policy=permissive_policy(max_feature_missing_fraction=0.5, min_positive_rate=0.1, max_positive_rate=0.9),
    )
    assert "feature_missingness_above_limit" in report.reasons
    assert "extreme_class_imbalance" in report.reasons


def test_dataset_quality_enforces_partition_minimums():
    rows = [make_row(i, partition="train") for i in range(5)]
    report = audit_research_dataset(
        rows,
        market_label="over_2_5",
        policy=permissive_policy(min_partition_rows={"train": 5, "validation": 1, "test": 1}),
    )
    assert "insufficient_validation_rows" in report.reasons
    assert "insufficient_test_rows" in report.reasons


def test_dataset_quality_requires_boolean_market_label():
    row = make_row(1)
    row = FootballResearchRow(
        fixture_id=row.fixture_id,
        as_of_utc=row.as_of_utc,
        partition=row.partition,
        features=row.features,
        labels={"final_total_goals": 2},
        label_observed_at_utc=row.label_observed_at_utc,
    )
    with pytest.raises(ValueError, match="boolean"):
        audit_research_dataset([row], market_label="final_total_goals", policy=permissive_policy())
