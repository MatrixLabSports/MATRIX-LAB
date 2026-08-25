from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3
from pathlib import Path
from threading import Barrier, Thread

import pytest

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    R8_2_CONTROL_LEDGER_USER_VERSION,
    SQLiteBoundedFootballLiveControlStore,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    build_bounded_run_manifest,
)
from app.application.football.external_integrity_root import (
    EphemeralEd25519SigningAuthority,
    LocalDirectoryExternalIntegrityRootStore,
    R83R6ExternalIntegrityRootCoordinator,
    R83R6StoreHead,
    R83R6TrustedPublicKey,
    build_signed_receipt,
)

BASE = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)


def _manifest(nonce: str = "c" * 64):
    cfg = BoundedFootballLiveExecutorConfig(
        provider_key="fake:football:deterministic",
        subject_key="fixture:1557375",
        modalities=("fixture_events",),
        max_capture_rounds=4,
        max_total_provider_calls=4,
        max_runtime_ms=300000,
    )
    return build_bounded_run_manifest(cfg, created_at=BASE, run_nonce_sha256=nonce)


def _control(tmp_path: Path):
    path = tmp_path / "control.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    run = _manifest()
    guard = BoundedExecutorProcessScopeGuard(path)
    lease = guard.acquire(acquired_at=BASE)
    store.register_run(run, guard=guard, lease=lease, registered_at=BASE)
    return path, store, run, guard, lease


def _coordinator(tmp_path: Path, store: SQLiteBoundedFootballLiveControlStore):
    root = LocalDirectoryExternalIntegrityRootStore(tmp_path / "external-root")
    signer = EphemeralEd25519SigningAuthority.generate()
    bootstrap = R83R6TrustedPublicKey(signer.key_id, signer.public_key_bytes)
    coordinator = R83R6ExternalIntegrityRootCoordinator(
        control_store=store,
        root_store=root,
        signer=signer,
        bootstrap_trusted_key=bootstrap,
    )
    return root, signer, bootstrap, coordinator


def test_v86_nonempty_transition_history_migrates_to_v87_without_loss(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    store.transition_run_state(
        run.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=1),
        guard=guard,
        lease=lease,
    )
    before = store.list_transition_events()
    guard.release(lease)

    # Reconstruct the exact pre-R8.3R6 v86 structural state.
    with store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE football_bounded_external_root_coordination")
        connection.execute("DROP TABLE football_bounded_external_root_state")
        connection.execute("PRAGMA user_version = 86")
        from app.application.football.bounded_live_control import _sha
        connection.execute(
            "UPDATE football_bounded_control_anchor SET payload_sha256 = ? WHERE singleton_id = 1",
            (_sha(store._anchor_payload_v86(connection)),),
        )
        connection.execute("COMMIT")

    reopened = SQLiteBoundedFootballLiveControlStore(path)
    assert reopened.audit_integrity() is True
    assert reopened.list_transition_events() == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 87
    assert reopened.get_external_root_state().root_store_id is None


def test_v86_anchor_mismatch_rejected_before_v87_promotion(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    guard.release(lease)
    with store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE football_bounded_external_root_coordination")
        connection.execute("DROP TABLE football_bounded_external_root_state")
        connection.execute("PRAGMA user_version = 86")
        connection.execute(
            "UPDATE football_bounded_control_anchor SET payload_sha256 = ? WHERE singleton_id = 1",
            ("0" * 64,),
        )
        connection.execute("COMMIT")
    with pytest.raises(ValueError, match="R8_3R6_V86_CONTROL_ANCHOR_MISMATCH"):
        SQLiteBoundedFootballLiveControlStore(path)


def test_genesis_anchors_existing_pre_genesis_transitions_without_fabricated_receipts(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    store.transition_run_state(
        run.run_id, expected_state="PLANNED", expected_state_version=0,
        new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=1),
        guard=guard, lease=lease,
    )
    preexisting = store.list_transition_events()
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    genesis = coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=2))
    assert [r.receipt_type for r in root.read_receipts()] == ["ROOT_GENESIS"]
    assert len(genesis.metadata["genesis_transition_events"]) == len(preexisting)
    assert coordinator.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True


def test_local_phase_b_rolls_back_event_state_and_coordination_together(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))
    event = store.preview_transition_event(
        run.run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2), guard=guard, lease=lease,
    )
    prepared = coordinator._prepare(event=event, created_at=BASE + timedelta(seconds=2))
    binding = coordinator._binding(prepared, event)
    from app.application.football.bounded_live_control import R83R5InjectedControlTransitionCrash
    with pytest.raises(R83R5InjectedControlTransitionCrash, match="AFTER_STATE_UPDATE_BEFORE_COMMIT"):
        store.transition_run_state(
            run.run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=2),
            guard=guard, lease=lease,
            crash_point="AFTER_STATE_UPDATE_BEFORE_COMMIT",
            external_root_prepare=binding,
        )
    assert store.get_run(run.run_id).state == "PLANNED"
    assert store.list_transition_events() == ()
    assert store.list_external_root_coordination() == ()
    assert coordinator.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True
    assert [r.receipt_type for r in root.read_receipts()] == [
        "ROOT_GENESIS", "ROOT_PREPARED", "ROOT_ABORTED"
    ]


def test_external_root_state_binding_exact_replay_is_idempotent_and_divergence_rejected(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    genesis = coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))
    before = store.get_external_root_state()
    replay = store.bind_external_root_genesis(
        root_store_id=root.root_store_id,
        bootstrap_signer_key_id=bootstrap.key_id,
        bootstrap_public_key_fingerprint=bootstrap.fingerprint,
        genesis_receipt_id=genesis.receipt_id,
        genesis_receipt_sha256=genesis.receipt_sha256,
    )
    assert replay == before
    with pytest.raises(ValueError, match="GENESIS_BINDING_DIVERGENCE"):
        store.bind_external_root_genesis(
            root_store_id="f" * 64,
            bootstrap_signer_key_id=bootstrap.key_id,
            bootstrap_public_key_fingerprint=bootstrap.fingerprint,
            genesis_receipt_id=genesis.receipt_id,
            genesis_receipt_sha256=genesis.receipt_sha256,
        )


def test_root_store_metadata_tamper_fails_closed(tmp_path: Path):
    root = LocalDirectoryExternalIntegrityRootStore(tmp_path / "root")
    payload = root.metadata_path.read_text(encoding="utf-8").replace(
        "LOCAL_EXTERNAL_RESEARCH", "CONTROLLED_LIVE_ADMISSIBLE"
    )
    root.metadata_path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="BACKEND_PROFILE_MISMATCH|METADATA_"):
        LocalDirectoryExternalIntegrityRootStore(
            root.path, expected_root_store_id=root.root_store_id
        )


def test_root_tables_ddl_tamper_fails_local_integrity(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    guard.release(lease)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("ALTER TABLE football_bounded_external_root_state RENAME TO old_root_state")
        connection.execute(
            "CREATE TABLE football_bounded_external_root_state (singleton_id INTEGER PRIMARY KEY, database_instance_id TEXT NOT NULL, root_protocol_version INTEGER NOT NULL, root_store_id TEXT, bootstrap_signer_key_id TEXT, bootstrap_public_key_fingerprint TEXT, genesis_receipt_id TEXT, genesis_receipt_sha256 TEXT)"
        )
        connection.execute(
            "INSERT INTO football_bounded_external_root_state SELECT * FROM old_root_state"
        )
        connection.execute("DROP TABLE old_root_state")
        connection.commit()
    assert store.audit_integrity() is False


def test_reopen_same_root_store_preserves_identity(tmp_path: Path):
    root = LocalDirectoryExternalIntegrityRootStore(tmp_path / "root")
    reopened = LocalDirectoryExternalIntegrityRootStore(
        root.path, expected_root_store_id=root.root_store_id
    )
    assert reopened.root_store_id == root.root_store_id
    assert reopened.backend_profile == "LOCAL_EXTERNAL_RESEARCH"
    assert reopened.controlled_live_admissible is False


def test_append_recovers_exact_durable_receipt_after_crash_before_head_marker(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))

    state = store.get_external_root_state()
    old_head = root.head()
    event = store.preview_transition_event(
        run.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        attempted_new_state="IN_PROGRESS",
        outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2),
        guard=guard,
        lease=lease,
    )
    prepared = build_signed_receipt(
        store=root,
        signer=signer,
        receipt_type="ROOT_PREPARED",
        operation_id="9" * 64,
        database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2),
        control_id=event.control_id,
        run_id=event.run_id,
        event=event,
        metadata={"phase": "prepare"},
        expected_head=old_head,
    )

    # Simulate a process/power failure after the canonical receipt is durable
    # but before its monotonic head marker is published.
    receipt_path = root.receipts_path / root._receipt_filename(
        prepared.root_sequence, prepared.receipt_id
    )
    receipt_path.write_bytes(prepared.canonical_bytes())
    assert root.audit_integrity() is False

    recovered = root.append(prepared, expected_head=old_head)
    assert recovered == prepared
    assert root.audit_integrity() is True
    assert root.head() == R83R6StoreHead(
        prepared.root_sequence, prepared.receipt_id, prepared.receipt_sha256
    )
    assert len(root.read_receipts()) == old_head.sequence + 1


def test_compare_and_append_is_single_winner_under_concurrent_fork(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))
    state = store.get_external_root_state()
    head = root.head()
    first = build_signed_receipt(
        store=root, signer=signer, receipt_type="ROOT_ABORTED",
        operation_id="1" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2), metadata={}, expected_head=head,
    )
    second = build_signed_receipt(
        store=root, signer=signer, receipt_type="ROOT_ABORTED",
        operation_id="2" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2), metadata={}, expected_head=head,
    )
    barrier = Barrier(3)
    outcomes: list[str] = []
    def worker(receipt):
        barrier.wait()
        try:
            root.append(receipt, expected_head=head)
            outcomes.append("PASS")
        except ValueError:
            outcomes.append("REJECT")
    a = Thread(target=worker, args=(first,))
    b = Thread(target=worker, args=(second,))
    a.start(); b.start(); barrier.wait(); a.join(); b.join()
    assert sorted(outcomes) == ["PASS", "REJECT"]
    assert root.head().sequence == head.sequence + 1


def test_restart_after_rotation_with_bootstrap_trust_and_active_signer_passes(tmp_path: Path):
    path, store, run, guard, lease = _control(tmp_path)
    root, signer, bootstrap, coordinator = _coordinator(tmp_path, store)
    coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))
    new_signer = EphemeralEd25519SigningAuthority.generate()
    coordinator.rotate_key(new_signer=new_signer, changed_at=BASE + timedelta(seconds=2))
    restarted = R83R6ExternalIntegrityRootCoordinator(
        control_store=store,
        root_store=root,
        signer=new_signer,
        bootstrap_trusted_key=bootstrap,
    )
    assert restarted.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True
    restarted.transition_run_state(
        run.run_id, expected_state="PLANNED", expected_state_version=0,
        new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=4),
        guard=guard, lease=lease,
    )
    assert store.get_run(run.run_id).state == "IN_PROGRESS"


def test_current_user_version_constant_is_87():
    assert R8_2_CONTROL_LEDGER_USER_VERSION == 87
