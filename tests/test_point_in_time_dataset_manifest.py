from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.application.football.admission_evidence import (
    build_football_admission_evidence,
)
from app.application.football.dataset_manifest import (
    build_football_dataset_manifest,
    verify_football_dataset_manifest,
)
from app.application.football.point_in_time_admission import (
    evaluate_football_admission,
)
from app.application.tennis.admission_evidence import (
    build_tennis_admission_evidence,
)
from app.application.tennis.dataset_manifest import (
    build_tennis_dataset_manifest,
    verify_tennis_dataset_manifest,
)
from app.application.tennis.point_in_time_admission import (
    evaluate_tennis_admission,
)
from app.core.dataset_manifest import DatasetRowEvidence


UTC = timezone.utc
CUTOFF = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
KNOWN_AT = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)


def football_admission(key: str, source_sha: str = "a" * 64):
    decision = evaluate_football_admission(
        fixture_key=key,
        kickoff=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        match_finished=True,
    )
    return build_football_admission_evidence(
        fixture_key=key,
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=source_sha,
        decision=decision,
    )


def tennis_admission(key: str, source_sha: str = "b" * 64):
    decision = evaluate_tennis_admission(
        match_key=key,
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        match_finished=True,
        exact_match_time_verified=True,
        same_tournament_cutoff_sensitive=False,
    )
    return build_tennis_admission_evidence(
        match_key=key,
        cutoff=CUTOFF,
        known_at=KNOWN_AT,
        source_status="PASS",
        source_fingerprint=source_sha,
        decision=decision,
    )


def football_row(key: str, value, source_sha: str = "a" * 64):
    return DatasetRowEvidence(
        sport="football",
        canonical_entity_key=key,
        admission_evidence=football_admission(key, source_sha),
        row_payload={
            "metric": value,
            "missing_metric": None,
        },
    )


def tennis_row(key: str, value, source_sha: str = "b" * 64):
    return DatasetRowEvidence(
        sport="tennis",
        canonical_entity_key=key,
        admission_evidence=tennis_admission(key, source_sha),
        row_payload={
            "metric": value,
            "missing_metric": None,
        },
    )


def test_manifest_is_deterministic_independent_of_input_order():
    a = football_row("F:1", 10)
    b = football_row("F:2", 20)

    first = build_football_dataset_manifest(
        dataset_key="football:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[a, b],
    )
    second = build_football_dataset_manifest(
        dataset_key="football:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[b, a],
    )

    assert first["dataset_fingerprint"] == second["dataset_fingerprint"]


def test_silent_row_mutation_is_detected():
    original = football_row("F:1", 10)
    manifest = build_football_dataset_manifest(
        dataset_key="football:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[original],
    )

    changed = football_row("F:1", 11)

    ok, reasons = verify_football_dataset_manifest(
        manifest=manifest,
        rows=[changed],
    )

    assert ok is False
    assert "ROW_CONTENT_CHANGED" in reasons


def test_missing_is_not_zero():
    original = tennis_row("T:1", 10)
    manifest = build_tennis_dataset_manifest(
        dataset_key="tennis:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[original],
    )

    changed = DatasetRowEvidence(
        sport="tennis",
        canonical_entity_key="T:1",
        admission_evidence=tennis_admission("T:1"),
        row_payload={
            "metric": 10,
            "missing_metric": 0,
        },
    )

    ok, reasons = verify_tennis_dataset_manifest(
        manifest=manifest,
        rows=[changed],
    )

    assert ok is False
    assert "ROW_CONTENT_CHANGED" in reasons


def test_cross_sport_rows_are_blocked():
    with pytest.raises(
        ValueError,
        match="CROSS_SPORT_ROW_CONTAMINATION",
    ):
        build_football_dataset_manifest(
            dataset_key="football:last5",
            as_of="2026-08-20T12:00:00Z",
            rows=[tennis_row("T:1", 10)],
        )


def test_duplicate_canonical_entity_keys_are_blocked():
    with pytest.raises(
        ValueError,
        match="DUPLICATE_CANONICAL_ENTITY_KEY",
    ):
        build_tennis_dataset_manifest(
            dataset_key="tennis:last5",
            as_of="2026-08-20T12:00:00Z",
            rows=[
                tennis_row("T:1", 10),
                tennis_row("T:1", 20),
            ],
        )


def test_unmanifested_row_is_detected():
    a = tennis_row("T:1", 10)
    b = tennis_row("T:2", 20)

    manifest = build_tennis_dataset_manifest(
        dataset_key="tennis:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[a],
    )

    ok, reasons = verify_tennis_dataset_manifest(
        manifest=manifest,
        rows=[a, b],
    )

    assert ok is False
    assert "UNMANIFESTED_ROW_PRESENT" in reasons


def test_missing_current_row_is_detected():
    a = football_row("F:1", 10)
    b = football_row("F:2", 20)

    manifest = build_football_dataset_manifest(
        dataset_key="football:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[a, b],
    )

    ok, reasons = verify_football_dataset_manifest(
        manifest=manifest,
        rows=[a],
    )

    assert ok is False
    assert "ROW_MISSING_FROM_CURRENT_DATASET" in reasons


def test_manifest_tampering_is_detected():
    a = football_row("F:1", 10)

    manifest = build_football_dataset_manifest(
        dataset_key="football:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[a],
    )

    tampered = deepcopy(manifest)
    tampered["as_of"] = "2026-08-21T12:00:00Z"

    ok, reasons = verify_football_dataset_manifest(
        manifest=tampered,
        rows=[a],
    )

    assert ok is False
    assert "MANIFEST_FINGERPRINT_MISMATCH" in reasons


def test_source_change_is_detected_through_admission_chain():
    original = tennis_row("T:1", 10, "b" * 64)

    manifest = build_tennis_dataset_manifest(
        dataset_key="tennis:last5",
        as_of="2026-08-20T12:00:00Z",
        rows=[original],
    )

    changed = tennis_row("T:1", 10, "c" * 64)

    ok, reasons = verify_tennis_dataset_manifest(
        manifest=manifest,
        rows=[changed],
    )

    assert ok is False
    assert "SOURCE_FINGERPRINT_CHANGED" in reasons
    assert "ADMISSION_FINGERPRINT_CHANGED" in reasons
    assert "ROW_CONTENT_CHANGED" in reasons
