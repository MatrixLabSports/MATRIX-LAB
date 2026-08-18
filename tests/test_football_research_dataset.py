import json
from pathlib import Path

import pytest

from app.research.football.dataset import (
    FootballDatasetBuilder,
    FootballResearchRow,
    TemporalLeakageGuard,
    TemporalSplitPolicy,
)


def row(fixture, as_of, label_at, *, partition="train", provider="api_football"):
    return FootballResearchRow(
        fixture_id=fixture,
        as_of_utc=as_of,
        partition=partition,
        features={"xg_diff": 0.2, "minute": 30},
        labels={"home_win": True},
        label_observed_at_utc=label_at,
        source_provider=provider,
    )


def test_research_row_rejects_label_known_before_cutoff():
    with pytest.raises(ValueError, match="posterior"):
        row("1", "2026-01-01T10:00:00+00:00", "2026-01-01T10:00:00+00:00")


def test_temporal_split_policy_partitions_in_time_order():
    policy = TemporalSplitPolicy(
        "2026-06-30T23:59:59+00:00",
        "2026-07-31T23:59:59+00:00",
    )
    assert policy.partition_for("2026-06-01T00:00:00+00:00") == "train"
    assert policy.partition_for("2026-07-15T00:00:00+00:00") == "validation"
    assert policy.partition_for("2026-08-01T00:00:00+00:00") == "test"


def test_guard_rejects_same_fixture_across_partitions():
    rows = [
        row("1", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00", partition="train"),
        row("1", "2026-07-01T10:00:00+00:00", "2026-07-01T12:00:00+00:00", partition="validation"),
    ]
    with pytest.raises(ValueError, match="múltiples particiones"):
        TemporalLeakageGuard.validate_rows(rows)


def test_builder_keeps_all_snapshots_of_fixture_in_first_partition():
    policy = TemporalSplitPolicy("2026-06-30T23:59:59+00:00", "2026-07-31T23:59:59+00:00")
    builder = FootballDatasetBuilder(dataset_name="live_goals", split_policy=policy)
    rows = [
        row("1", "2026-06-30T23:00:00+00:00", "2026-07-01T01:00:00+00:00"),
        row("1", "2026-07-01T00:10:00+00:00", "2026-07-01T01:00:00+00:00"),
    ]
    assigned = builder.assign_partitions(rows)
    assert [item.partition for item in assigned] == ["train", "train"]


def test_dataset_version_is_immutable_and_checksum_verified(tmp_path):
    policy = TemporalSplitPolicy("2026-06-30T23:59:59+00:00", "2026-07-31T23:59:59+00:00")
    builder = FootballDatasetBuilder(dataset_name="live_goals", split_policy=policy)
    rows = [
        row("1", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00"),
        row("2", "2026-07-15T10:00:00+00:00", "2026-07-15T12:00:00+00:00"),
        row("3", "2026-08-15T10:00:00+00:00", "2026-08-15T12:00:00+00:00"),
    ]
    manifest = builder.write_version(
        rows,
        output_root=tmp_path,
        dataset_version="v1",
        created_at_utc="2026-08-17T12:00:00+00:00",
    )
    version = tmp_path / "live_goals" / "v1"
    verified = builder.verify_version(version)
    assert manifest.data_sha256 == verified.data_sha256
    assert manifest.partition_counts == {"test": 1, "train": 1, "validation": 1}
    assert manifest.fixture_count == 3
    with pytest.raises(FileExistsError, match="inmutable"):
        builder.write_version(rows, output_root=tmp_path, dataset_version="v1")


def test_dataset_verification_detects_tampering(tmp_path):
    policy = TemporalSplitPolicy("2026-06-30T23:59:59+00:00", "2026-07-31T23:59:59+00:00")
    builder = FootballDatasetBuilder(dataset_name="live_goals", split_policy=policy)
    builder.write_version(
        [row("1", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00")],
        output_root=tmp_path,
        dataset_version="v1",
    )
    version = tmp_path / "live_goals" / "v1"
    with (version / "rows.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps({"tampered": True}) + "\n")
    with pytest.raises(ValueError, match="checksum"):
        builder.verify_version(version)


def test_dataset_manifest_preserves_research_metadata(tmp_path):
    policy = TemporalSplitPolicy("2026-06-30T23:59:59+00:00", "2026-07-31T23:59:59+00:00")
    builder = FootballDatasetBuilder(dataset_name="prematch", split_policy=policy)
    manifest = builder.write_version(
        [row("1", "2026-06-01T10:00:00+00:00", "2026-06-01T12:00:00+00:00")],
        output_root=tmp_path,
        dataset_version="v1",
        metadata={"dataset_kind": "prematch_form", "result_buffer_hours": 6},
    )
    verified = builder.verify_version(tmp_path / "prematch" / "v1")
    assert manifest.metadata == {"dataset_kind": "prematch_form", "result_buffer_hours": 6}
    assert verified.metadata == manifest.metadata
