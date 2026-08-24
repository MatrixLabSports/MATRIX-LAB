from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from app.application.football.bounded_fake_provider_executor import (
    DeterministicFakeFootballLiveProvider,
    R8_3_CRASH_POINTS,
    R8_3_FAKE_PROVIDER_KEY,
    R83InjectedCrash,
    SQLiteR83FakeExecutorJournal,
    build_r8_3_offline_fake_execution_authority,
    execute_offline_fake_bounded_run,
)
from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    SQLiteBoundedFootballLiveControlStore,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    build_bounded_run_manifest,
)
from app.application.football.repeatable_live_ingestion import (
    SQLiteFootballLiveObservationStore,
)


BASE = datetime(2026, 8, 24, 2, 30, tzinfo=UTC)


class StepClock:
    def __init__(self, start: datetime = BASE, step_ms: int = 20) -> None:
        self.value = start - timedelta(milliseconds=step_ms)
        self.step = timedelta(milliseconds=step_ms)

    def __call__(self) -> datetime:
        self.value += self.step
        return self.value


class RegressingClock:
    def __init__(self) -> None:
        self.values = [
            BASE,
            BASE + timedelta(milliseconds=20),
            BASE - timedelta(milliseconds=1),
        ]

    def __call__(self) -> datetime:
        if self.values:
            return self.values.pop(0)
        return BASE + timedelta(seconds=1)


def make_manifest(
    *,
    nonce: str = "1" * 64,
    rounds: int = 1,
    modalities: tuple[str, ...] = (
        "fixture_status",
        "fixture_statistics",
        "fixture_events",
    ),
    max_calls: int | None = None,
    subject: str = "fixture:1557375",
):
    planned = rounds * len(modalities)
    config = BoundedFootballLiveExecutorConfig(
        provider_key=R8_3_FAKE_PROVIDER_KEY,
        subject_key=subject,
        modalities=modalities,
        max_capture_rounds=rounds,
        max_total_provider_calls=planned if max_calls is None else max_calls,
        max_runtime_ms=300000,
    )
    return build_bounded_run_manifest(
        config,
        created_at=BASE,
        run_nonce_sha256=nonce,
    )


def make_runtime(tmp_path: Path, manifest):
    control = SQLiteBoundedFootballLiveControlStore(tmp_path / "control.sqlite3")
    evidence = SQLiteFootballLiveObservationStore(tmp_path / "evidence.sqlite3")
    journal = SQLiteR83FakeExecutorJournal(tmp_path / "journal.sqlite3")
    guard = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease = guard.acquire(acquired_at=BASE)
    authority = build_r8_3_offline_fake_execution_authority(manifest)
    return control, evidence, journal, guard, lease, authority


def observation_count(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM football_live_observation"
            ).fetchone()[0]
        )


def reservation_rows(path: Path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT round_index, modality, sequence_number, state
            FROM football_bounded_sequence_reservation
            ORDER BY round_index, modality
            """
        ).fetchall()


def test_one_round_three_modalities_happy_path(tmp_path: Path):
    manifest = make_manifest()
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()

    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
    )

    assert result.run_state == "COMPLETED"
    assert result.fake_calls_attempted == 3
    assert result.fake_calls_succeeded == 3
    assert result.fake_calls_failed == 0
    assert result.committed_slots == 3
    assert observation_count(tmp_path / "evidence.sqlite3") == 3
    assert control.audit_integrity() is True
    assert evidence.audit_integrity() is True
    assert journal.audit_integrity() is True
    guard.release(lease)


def test_two_round_three_modalities_happy_path(tmp_path: Path):
    manifest = make_manifest(rounds=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()

    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
    )

    assert result.run_state == "COMPLETED"
    assert result.fake_calls_attempted == 6
    assert result.started_rounds == 2
    assert len(result.correlation_id_by_round) == 2
    assert result.correlation_id_by_round[1] != result.correlation_id_by_round[2]
    assert observation_count(tmp_path / "evidence.sqlite3") == 6
    guard.release(lease)


def test_exact_fake_call_budget_boundary_passes(tmp_path: Path):
    manifest = make_manifest(rounds=1, max_calls=3)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=DeterministicFakeFootballLiveProvider(),
        clock=StepClock(),
    )
    assert result.fake_calls_attempted == 3
    assert result.run_state == "COMPLETED"
    guard.release(lease)


def test_round_limit_is_finite_and_exact(tmp_path: Path):
    manifest = make_manifest(rounds=2, modalities=("fixture_events",))
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
    )
    assert provider.calls == [(1, "fixture_events", 1), (2, "fixture_events", 2)]
    assert result.stop_reason_codes == ("CAPTURE_ROUND_LIMIT_REACHED",)
    guard.release(lease)


def test_scripted_fake_provider_failure_abandons_slot_and_aborts(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider(
        failure_slots=frozenset({(1, "fixture_events")})
    )
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
    )
    assert result.run_state == "ABORTED"
    assert result.fake_calls_attempted == 1
    assert result.fake_calls_failed == 1
    assert result.abandoned_slots == 1
    assert "SCRIPTED_FAKE_PROVIDER_FAILURE" in result.stop_reason_codes
    assert reservation_rows(tmp_path / "control.sqlite3")[0][3] == "ABANDONED"
    guard.release(lease)


def test_terminal_fixture_stops_future_calls(tmp_path: Path):
    manifest = make_manifest(rounds=3, max_calls=9)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider(
        terminal_status_rounds=frozenset({1})
    )
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
    )
    assert result.run_state == "COMPLETED"
    assert result.fake_calls_attempted == 1
    assert provider.calls == [(1, "fixture_status", 1)]
    assert "FIXTURE_TERMINAL_STATUS_WHEN_CONFIGURED" in result.stop_reason_codes
    guard.release(lease)


def test_clock_regression_fails_closed(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    with pytest.raises(ValueError, match="R8_3_CLOCK_REGRESSION"):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=DeterministicFakeFootballLiveProvider(),
            clock=RegressingClock(),
        )
    assert control.get_run(manifest.run_id).state in {"PLANNED", "IN_PROGRESS"}
    guard.release(lease)


def test_control_integrity_tamper_fails_closed(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",))
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    with sqlite3.connect(tmp_path / "control.sqlite3") as connection:
        connection.execute(
            "UPDATE football_bounded_control_anchor SET payload_sha256 = ? WHERE singleton_id = 1",
            ("0" * 64,),
        )
        connection.commit()
    with pytest.raises(ValueError, match="R8_3_SEQUENCE_ALLOCATOR_INTEGRITY_FAILURE"):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=DeterministicFakeFootballLiveProvider(),
            clock=StepClock(),
        )
    guard.release(lease)


def test_process_guard_loss_fails_closed(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",))
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    guard.release(lease)
    with pytest.raises(ValueError):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=DeterministicFakeFootballLiveProvider(),
            clock=StepClock(),
        )


@pytest.mark.parametrize("crash_point", R8_3_CRASH_POINTS)
def test_resume_after_each_crash_injection_point(tmp_path: Path, crash_point: str):
    manifest = make_manifest(
        nonce=(str(R8_3_CRASH_POINTS.index(crash_point) + 1) * 64)[:64],
        modalities=("fixture_events",),
        max_calls=2,
    )
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()

    with pytest.raises(R83InjectedCrash, match=crash_point):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=provider,
            clock=clock,
            crash_point=crash_point,
        )

    guard.release(lease)
    new_guard = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    new_lease = new_guard.acquire(acquired_at=clock())

    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=new_guard,
        lease=new_lease,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )

    assert result.run_state == "COMPLETED"
    assert control.audit_integrity() is True
    assert evidence.audit_integrity() is True
    assert journal.audit_integrity() is True
    assert reservation_rows(tmp_path / "control.sqlite3")[0][2] == 1
    new_guard.release(new_lease)


def test_committed_slot_is_not_recalled_on_resume(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()

    with pytest.raises(R83InjectedCrash):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=provider,
            clock=clock,
            crash_point="AFTER_SLOT_COMMIT_BEFORE_NEXT_SLOT",
        )
    assert provider.call_count == 1
    guard.release(lease)
    guard2 = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease2 = guard2.acquire(acquired_at=clock())
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard2,
        lease=lease2,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )
    assert result.run_state == "COMPLETED"
    assert provider.call_count == 1
    guard2.release(lease2)


def test_crash_after_normalized_persist_does_not_recall_fake_provider(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()
    with pytest.raises(R83InjectedCrash):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=provider,
            clock=clock,
            crash_point="AFTER_NORMALIZED_PERSIST_BEFORE_SLOT_COMMIT",
        )
    assert provider.call_count == 1
    assert observation_count(tmp_path / "evidence.sqlite3") == 1
    guard.release(lease)
    guard2 = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease2 = guard2.acquire(acquired_at=clock())
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard2,
        lease=lease2,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )
    assert result.run_state == "COMPLETED"
    assert provider.call_count == 1
    guard2.release(lease2)


def test_uncertain_call_retry_is_counted_durably(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()
    with pytest.raises(R83InjectedCrash):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=provider,
            clock=clock,
            crash_point="AFTER_FAKE_CALL_BEFORE_NORMALIZED_PERSIST",
        )
    assert journal.counts(manifest.run_id)["uncertain"] == 1
    guard.release(lease)
    guard2 = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease2 = guard2.acquire(acquired_at=clock())
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard2,
        lease=lease2,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )
    assert result.fake_calls_attempted == 2
    assert result.fake_calls_succeeded == 1
    assert result.fake_calls_uncertain == 1
    assert provider.call_count == 2
    guard2.release(lease2)


def test_no_sequence_reuse_after_abandoned_run(tmp_path: Path):
    first = make_manifest(nonce="a" * 64, modalities=("fixture_events",), max_calls=2)
    control, evidence, journal, guard, lease, authority = make_runtime(tmp_path, first)
    result = execute_offline_fake_bounded_run(
        manifest=first,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=DeterministicFakeFootballLiveProvider(
            failure_slots=frozenset({(1, "fixture_events")})
        ),
        clock=StepClock(),
    )
    assert result.run_state == "ABORTED"
    guard.release(lease)

    second = make_manifest(nonce="b" * 64, modalities=("fixture_events",), max_calls=1)
    authority2 = build_r8_3_offline_fake_execution_authority(second)
    guard2 = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease2 = guard2.acquire(acquired_at=BASE + timedelta(seconds=10))
    result2 = execute_offline_fake_bounded_run(
        manifest=second,
        authority=authority2,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard2,
        lease=lease2,
        fake_provider=DeterministicFakeFootballLiveProvider(),
        clock=StepClock(BASE + timedelta(seconds=10)),
    )
    assert result2.sequence_numbers_by_slot["1:fixture_events"] == 2
    guard2.release(lease2)


def test_correlation_id_is_shared_only_within_round(tmp_path: Path):
    manifest = make_manifest(rounds=2)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=DeterministicFakeFootballLiveProvider(),
        clock=StepClock(),
    )
    with sqlite3.connect(tmp_path / "evidence.sqlite3") as connection:
        rows = connection.execute(
            "SELECT correlation_id, modality FROM football_live_observation ORDER BY rowid"
        ).fetchall()
    assert len({row[0] for row in rows[:3]}) == 1
    assert len({row[0] for row in rows[3:]}) == 1
    assert rows[0][0] != rows[3][0]
    assert len(result.correlation_id_by_round) == 2
    guard.release(lease)


def test_authority_rejects_subject_mutation(tmp_path: Path):
    manifest = make_manifest(subject="fixture:1557375")
    authority = build_r8_3_offline_fake_execution_authority(manifest)
    other = make_manifest(nonce="f" * 64, subject="fixture:1557376")
    with pytest.raises(ValueError, match="R8_3_SUBJECT_KEY_CHANGED"):
        authority.validate_manifest(other)


def test_authority_rejects_real_provider_manifest():
    config = BoundedFootballLiveExecutorConfig(
        provider_key="api_football",
        subject_key="fixture:1557375",
        modalities=("fixture_events",),
        max_capture_rounds=1,
        max_total_provider_calls=1,
        max_runtime_ms=300000,
    )
    manifest = build_bounded_run_manifest(
        config,
        created_at=BASE,
        run_nonce_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="R8_3_FAKE_PROVIDER_KEY_REQUIRED"):
        build_r8_3_offline_fake_execution_authority(manifest)


def test_manual_stop_aborts_without_fake_call(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",))
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=StepClock(),
        manual_stop_requested=lambda round_index, modality: True,
    )
    assert result.run_state == "ABORTED"
    assert result.fake_calls_attempted == 0
    assert "MANUAL_STOP_REQUEST" in result.stop_reason_codes
    guard.release(lease)


def test_fake_journal_tamper_is_detected(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",))
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=DeterministicFakeFootballLiveProvider(),
        clock=StepClock(),
    )
    with sqlite3.connect(tmp_path / "journal.sqlite3") as connection:
        connection.execute(
            "UPDATE r8_3_fake_call_attempt SET sequence_number = 99"
        )
        connection.commit()
    assert journal.audit_integrity() is False
    guard.release(lease)


def test_completed_run_replay_performs_no_additional_fake_call(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=1)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()
    first = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=clock,
    )
    assert first.run_state == "COMPLETED"
    assert provider.call_count == 1
    second = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard,
        lease=lease,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )
    assert second.run_state == "COMPLETED"
    assert provider.call_count == 1
    assert second.fake_calls_attempted == 1
    guard.release(lease)


def test_uncertain_retry_budget_exhaustion_aborts_without_second_fake_call(
    tmp_path: Path,
):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=1)
    control, evidence, journal, guard, lease, authority = make_runtime(
        tmp_path, manifest
    )
    provider = DeterministicFakeFootballLiveProvider()
    clock = StepClock()
    with pytest.raises(R83InjectedCrash):
        execute_offline_fake_bounded_run(
            manifest=manifest,
            authority=authority,
            control_store=control,
            evidence_store=evidence,
            journal=journal,
            guard=guard,
            lease=lease,
            fake_provider=provider,
            clock=clock,
            crash_point="AFTER_FAKE_CALL_BEFORE_NORMALIZED_PERSIST",
        )
    assert provider.call_count == 1
    guard.release(lease)
    guard2 = BoundedExecutorProcessScopeGuard(tmp_path / "control.sqlite3")
    lease2 = guard2.acquire(acquired_at=clock())
    result = execute_offline_fake_bounded_run(
        manifest=manifest,
        authority=authority,
        control_store=control,
        evidence_store=evidence,
        journal=journal,
        guard=guard2,
        lease=lease2,
        fake_provider=provider,
        clock=clock,
        resume=True,
    )
    assert result.run_state == "ABORTED"
    assert "TOTAL_FAKE_CALL_BUDGET_REACHED" in result.stop_reason_codes
    assert provider.call_count == 1
    assert journal.counts(manifest.run_id)["attempted"] == 1
    lease2_state = control.get_reservation(
        manifest.run_id,
        round_index=1,
        modality="fixture_events",
    )
    assert lease2_state.state == "ABANDONED"
    guard2.release(lease2)


def test_journal_noncanonical_modalities_rejected_even_after_local_rehash(
    tmp_path: Path,
):
    manifest = make_manifest(modalities=("fixture_events",))
    _, _, journal, guard, lease, authority = make_runtime(tmp_path, manifest)
    journal.register_run(
        manifest=manifest,
        authority=authority,
        registered_at=BASE,
    )
    with journal._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE r8_3_fake_run_meta SET modalities_json = ? WHERE run_id = ?",
            ('[\n  "fixture_events"\n]', manifest.run_id),
        )
        journal._rewrite_anchor(connection)
        connection.execute("COMMIT")
    assert journal.audit_integrity() is False
    guard.release(lease)


def test_journal_correlation_tamper_rejected_even_after_local_rehash(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",))
    _, _, journal, guard, lease, authority = make_runtime(tmp_path, manifest)
    journal.register_run(
        manifest=manifest,
        authority=authority,
        registered_at=BASE,
    )
    journal.begin_attempt(
        run_id=manifest.run_id,
        round_index=1,
        modality="fixture_events",
        sequence_number=1,
        correlation_id=(
            __import__(
                "app.application.football.bounded_fake_provider_executor",
                fromlist=["_round_correlation_id"],
            )._round_correlation_id(manifest.run_id, 1)
        ),
        attempted_at=BASE + timedelta(milliseconds=20),
    )
    with journal._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE r8_3_fake_call_attempt SET correlation_id = ?",
            ("f" * 64,),
        )
        journal._rewrite_anchor(connection)
        connection.execute("COMMIT")
    assert journal.audit_integrity() is False
    guard.release(lease)


def test_journal_attempt_index_gap_rejected_even_after_local_rehash(tmp_path: Path):
    manifest = make_manifest(modalities=("fixture_events",), max_calls=2)
    _, _, journal, guard, lease, authority = make_runtime(tmp_path, manifest)
    journal.register_run(
        manifest=manifest,
        authority=authority,
        registered_at=BASE,
    )
    correlation = __import__(
        "app.application.football.bounded_fake_provider_executor",
        fromlist=["_round_correlation_id"],
    )._round_correlation_id(manifest.run_id, 1)
    journal.begin_attempt(
        run_id=manifest.run_id,
        round_index=1,
        modality="fixture_events",
        sequence_number=1,
        correlation_id=correlation,
        attempted_at=BASE + timedelta(milliseconds=20),
    )
    with journal._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE r8_3_fake_call_attempt SET attempt_index = 2"
        )
        journal._rewrite_anchor(connection)
        connection.execute("COMMIT")
    assert journal.audit_integrity() is False
    guard.release(lease)
