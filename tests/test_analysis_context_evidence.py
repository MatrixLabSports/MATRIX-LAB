from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from app.core.analysis_context_evidence import (
    SQLiteAnalysisContextEvidenceStore,
    build_analysis_context_bundle,
)
from app.core.sport_load_context import build_sport_load_context


UTC = timezone.utc


def objects():
    history_profile = SimpleNamespace(
        sport="tennis",
        canonical_id="tennis:player:subject",
        history_fingerprint="a" * 64,
        profile_fingerprint="b" * 64,
    )
    sos = SimpleNamespace(
        sport="tennis",
        canonical_id="tennis:player:subject",
        history_fingerprint="a" * 64,
        profile_fingerprint="c" * 64,
    )
    load = build_sport_load_context(
        sport="tennis",
        canonical_id="tennis:player:subject",
        as_of=datetime(2026, 8, 10, 12, tzinfo=UTC),
        event_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        available_at=datetime(2026, 8, 10, 10, tzinfo=UTC),
        previous_event_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        travel_km=500,
        timezone_shift_hours=0,
        altitude_delta_m=0,
        matches_last_7d=2,
        matches_last_14d=3,
        cumulative_minutes_last_7d=180,
        cumulative_minutes_last_14d=270,
    )
    comparable = SimpleNamespace(
        sport="tennis",
        cohort_fingerprint="d" * 64,
    )
    return history_profile, sos, load, comparable


def test_context_bundle_binds_all_lineage():
    history, sos, load, comparable = objects()

    bundle = build_analysis_context_bundle(
        history_profile=history,
        strength_of_schedule_profile=sos,
        load_context=load,
        comparable_cohort=comparable,
    )

    assert bundle.sport == "tennis"
    assert len(bundle.bundle_fingerprint) == 64
    assert bundle.payload()["fatigue_score_computed"] is False


def test_context_bundle_rejects_history_lineage_mismatch():
    history, sos, load, comparable = objects()
    sos = SimpleNamespace(
        sport="tennis",
        canonical_id="tennis:player:subject",
        history_fingerprint="f" * 64,
        profile_fingerprint="c" * 64,
    )

    with pytest.raises(
        ValueError,
        match="HISTORY_LINEAGE_MISMATCH",
    ):
        build_analysis_context_bundle(
            history_profile=history,
            strength_of_schedule_profile=sos,
            load_context=load,
            comparable_cohort=comparable,
        )


def test_context_evidence_is_idempotent_and_tamper_evident(tmp_path):
    history, sos, load, comparable = objects()
    bundle = build_analysis_context_bundle(
        history_profile=history,
        strength_of_schedule_profile=sos,
        load_context=load,
        comparable_cohort=comparable,
    )

    path = tmp_path / "context.db"
    store = SQLiteAnalysisContextEvidenceStore(path)

    first = store.record_bundle(bundle)
    second = store.record_bundle(bundle)

    assert first == second
    assert store.audit_integrity().records == 1

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE analysis_context_evidence
            SET payload_json = ?
            WHERE bundle_fingerprint = ?
            """,
            ('{"tampered":true}\n', bundle.bundle_fingerprint),
        )
        connection.commit()

    assert store.audit_integrity().ok is False
