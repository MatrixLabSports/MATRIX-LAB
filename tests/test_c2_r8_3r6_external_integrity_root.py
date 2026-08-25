from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import base64
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from cryptography.hazmat.primitives import serialization

from app.application.football.bounded_live_control import (
    BoundedExecutorProcessScopeGuard,
    R8_2_CONTROL_LEDGER_USER_VERSION,
    SQLiteBoundedFootballLiveControlStore,
    TransitionEventReference,
)
from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    build_bounded_run_manifest,
)
from app.application.football.external_integrity_root import (
    EphemeralEd25519SigningAuthority,
    LocalDirectoryExternalIntegrityRootStore,
    R83R6ExternalIntegrityRootCoordinator,
    R83R6InjectedCrash,
    R83R6RootReceipt,
    R83R6StoreHead,
    R83R6TrustedPublicKey,
    _canonical,
    _operation_id,
    _sha,
    build_signed_receipt,
    verify_receipt_chain,
)

BASE = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)


def _manifest(nonce: str = "a" * 64, subject: str = "fixture:1557375"):
    config = BoundedFootballLiveExecutorConfig(
        provider_key="fake:football:deterministic",
        subject_key=subject,
        modalities=("fixture_events",),
        max_capture_rounds=4,
        max_total_provider_calls=4,
        max_runtime_ms=300000,
    )
    return build_bounded_run_manifest(
        config,
        created_at=BASE,
        run_nonce_sha256=nonce,
    )


def _runtime(tmp_path: Path, name: str = "control.sqlite3"):
    control_path = tmp_path / name
    control = SQLiteBoundedFootballLiveControlStore(control_path)
    run = _manifest((name.encode().hex() + "a" * 64)[:64])
    guard = BoundedExecutorProcessScopeGuard(control_path)
    lease = guard.acquire(acquired_at=BASE)
    control.register_run(run, guard=guard, lease=lease, registered_at=BASE)
    root = LocalDirectoryExternalIntegrityRootStore(tmp_path / (name + ".root"))
    signer = EphemeralEd25519SigningAuthority.generate()
    bootstrap = R83R6TrustedPublicKey(signer.key_id, signer.public_key_bytes)
    coordinator = R83R6ExternalIntegrityRootCoordinator(
        control_store=control,
        root_store=root,
        signer=signer,
        bootstrap_trusted_key=bootstrap,
    )
    coordinator.ensure_genesis(created_at=BASE + timedelta(seconds=1))
    return control_path, control, run, guard, lease, root, signer, bootstrap, coordinator


def _backup_database(source: Path, target: Path) -> None:
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _restore_database(backup: Path, target: Path) -> None:
    # Restore through SQLite's backup API instead of deleting WAL/SHM files.
    # On Windows, a just-closed WAL handle may still be temporarily locked;
    # logical page restoration exercises the same coherent database rollback
    # semantics without making the adversarial test depend on OS file locking.
    src = sqlite3.connect(backup)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _rehash_local(control: SQLiteBoundedFootballLiveControlStore) -> None:
    with control._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        control._rewrite_anchor(connection)
        connection.execute("COMMIT")


def _receipt_files(root: LocalDirectoryExternalIntegrityRootStore):
    return sorted(root.receipts_path.glob("*.receipt.json"))


def _head_files(root: LocalDirectoryExternalIntegrityRootStore):
    return sorted(root.heads_path.glob("*.head"))


def _resign_receipt(
    receipt: R83R6RootReceipt,
    signer: EphemeralEd25519SigningAuthority,
    **changes,
) -> R83R6RootReceipt:
    unsigned = dict(receipt.unsigned_payload())
    unsigned.update(changes)
    unsigned_sha = _sha(unsigned)
    signature_b64 = base64.b64encode(
        signer.sign(_canonical(unsigned).encode("utf-8"))
    ).decode("ascii")
    receipt_id = _sha({
        "schema": "matrix.c2-r8-3r6-receipt-id/1",
        "canonical_payload_sha256": unsigned_sha,
        "signature_b64": signature_b64,
    })
    return R83R6RootReceipt(
        receipt_id=receipt_id,
        root_sequence=int(unsigned["root_sequence"]),
        previous_receipt_id=unsigned["previous_receipt_id"],
        previous_receipt_sha256=unsigned["previous_receipt_sha256"],
        receipt_type=str(unsigned["receipt_type"]),
        operation_id=str(unsigned["operation_id"]),
        project_domain_id=str(unsigned["project_domain_id"]),
        sport_id=str(unsigned["sport_id"]),
        database_instance_id=str(unsigned["database_instance_id"]),
        control_id=unsigned["control_id"],
        run_id=unsigned["run_id"],
        local_transition_event_id=unsigned["local_transition_event_id"],
        local_transition_event_sha256=unsigned["local_transition_event_sha256"],
        local_transition_sequence=unsigned["local_transition_sequence"],
        local_control_state_version=unsigned["local_control_state_version"],
        local_schema_user_version=int(unsigned["local_schema_user_version"]),
        receipt_protocol_version=int(unsigned["receipt_protocol_version"]),
        created_at=str(unsigned["created_at"]),
        signer_key_id=str(unsigned["signer_key_id"]),
        canonical_payload_sha256=unsigned_sha,
        signature_b64=signature_b64,
        root_store_id=str(unsigned["root_store_id"]),
        metadata=unsigned["metadata"],
    )


def _rooted_in_progress(env, seconds: int = 2):
    control, run, guard, lease, coordinator = env[1], env[2], env[3], env[4], env[8]
    return coordinator.transition_run_state(
        run.run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=seconds),
        guard=guard,
        lease=lease,
    )


def test_r8_3r6_fresh_schema_is_v87_and_unbound(tmp_path: Path):
    path = tmp_path / "fresh.sqlite3"
    store = SQLiteBoundedFootballLiveControlStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 87
        assert connection.execute(
            "SELECT COUNT(*) FROM football_bounded_external_root_state"
        ).fetchone()[0] == 1
    state = store.get_external_root_state()
    assert state.root_store_id is None
    assert store.audit_integrity() is True


def test_r8_3r6_receipt_roundtrip_and_signature(tmp_path: Path):
    env = _runtime(tmp_path)
    root, bootstrap = env[5], env[7]
    receipts = root.read_receipts()
    assert R83R6RootReceipt.from_bytes(receipts[0].canonical_bytes()) == receipts[0]
    verify_receipt_chain(
        receipts,
        expected_root_store_id=root.root_store_id,
        expected_database_instance_id=env[1].get_external_root_state().database_instance_id,
        initial_trusted_key=bootstrap,
    )


def test_eir01_old_coherent_db_rollback_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    backup = tmp_path / "old.sqlite3"
    _backup_database(env[0], backup)
    _rooted_in_progress(env)
    env[3].release(env[4])
    _restore_database(backup, env[0])
    rolled = SQLiteBoundedFootballLiveControlStore(env[0])
    coord = R83R6ExternalIntegrityRootCoordinator(
        control_store=rolled,
        root_store=env[5],
        signer=env[6],
        bootstrap_trusted_key=env[7],
    )
    with pytest.raises(ValueError, match="R8_3R6_"):
        coord.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3))


def test_eir02_coherently_reauthored_db_rejected_by_external_root(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    with sqlite3.connect(env[0]) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM football_bounded_external_root_coordination")
        connection.execute("DELETE FROM football_bounded_run_transition_event")
        connection.execute(
            "UPDATE football_bounded_run_control SET state='PLANNED', state_version=0, updated_at=created_at"
        )
        connection.commit()
    _rehash_local(env[1])
    assert env[1].audit_integrity() is True
    with pytest.raises(ValueError, match="R8_3R6_"):
        env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=4))


def test_eir03_forged_new_local_history_without_receipt_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    env[1].transition_run_state(
        env[2].run_id,
        expected_state="PLANNED",
        expected_state_version=0,
        new_state="IN_PROGRESS",
        changed_at=BASE + timedelta(seconds=2),
        guard=env[3],
        lease=env[4],
    )
    assert env[1].audit_integrity() is True
    with pytest.raises(ValueError, match="LOCAL_EXTERNAL_TRANSITION_HISTORY_MISMATCH"):
        env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3))


def test_eir04_mutated_external_receipt_payload_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    path = _receipt_files(env[5])[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["backend_profile"] = "FORGED"
    path.write_text(_canonical(payload), encoding="utf-8")
    assert env[5].audit_integrity() is False


def test_eir05_deleted_middle_external_receipt_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    _receipt_files(env[5])[1].unlink()
    assert env[5].audit_integrity() is False


def test_eir06_reordered_external_receipts_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    files = _receipt_files(env[5])
    a, b = files[1].read_bytes(), files[2].read_bytes()
    files[1].write_bytes(b)
    files[2].write_bytes(a)
    assert env[5].audit_integrity() is False


def test_eir07_duplicate_external_receipt_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    last_receipt = _receipt_files(env[5])[-1]
    last_head = _head_files(env[5])[-1]
    (env[5].receipts_path / ("9" * 20 + "-" + last_receipt.name.split("-", 1)[1])).write_bytes(last_receipt.read_bytes())
    (env[5].heads_path / ("9" * 20 + "-" + last_head.name.split("-", 1)[1])).write_bytes(last_head.read_bytes())
    assert env[5].audit_integrity() is False


def test_eir08_fork_same_predecessor_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    head = env[5].head()
    state = env[1].get_external_root_state()
    first = build_signed_receipt(
        store=env[5], signer=env[6], receipt_type="ROOT_ABORTED",
        operation_id="1" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2), metadata={}, expected_head=head,
    )
    second = build_signed_receipt(
        store=env[5], signer=env[6], receipt_type="ROOT_ABORTED",
        operation_id="2" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2), metadata={}, expected_head=head,
    )
    env[5].append(first, expected_head=head)
    with pytest.raises(ValueError, match="COMPARE_AND_APPEND_CONFLICT"):
        env[5].append(second, expected_head=head)


def test_eir09_truncated_external_history_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    _receipt_files(env[5])[-1].unlink()
    with pytest.raises(ValueError, match="CARDINALITY"):
        env[5].read_receipts()


def test_eir10_older_signed_prefix_cannot_hide_newer_head_markers(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    for item in _receipt_files(env[5])[1:]:
        item.unlink()
    with pytest.raises(ValueError, match="CARDINALITY"):
        env[5].read_receipts()


def test_eir11_cross_control_prepared_binding_transplant_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    second = _manifest("b" * 64, subject="fixture:1557376")
    env[1].register_run(second, guard=env[3], lease=env[4], registered_at=BASE)
    event1 = env[1].preview_transition_event(
        env[2].run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2), guard=env[3], lease=env[4],
    )
    prepared = env[8]._prepare(event=event1, created_at=BASE + timedelta(seconds=2))
    event2 = env[1].preview_transition_event(
        second.run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2), guard=env[3], lease=env[4],
    )
    binding = env[8]._binding(prepared, event1)
    with pytest.raises(ValueError, match="PREPARED_BINDING_TRANSITION_MISMATCH"):
        env[1].transition_run_state(
            second.run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=2),
            guard=env[3], lease=env[4], external_root_prepare=binding,
        )
    assert env[1].find_transition_event(event2.event_id) is None


def test_eir12_cross_run_receipt_transplant_rejected(tmp_path: Path):
    # Run identity is part of the expected transition event binding.
    test_eir11_cross_control_prepared_binding_transplant_rejected(tmp_path)


def test_eir13_cross_database_instance_receipt_transplant_rejected(tmp_path: Path):
    env1 = _runtime(tmp_path / "one", "one.sqlite3")
    env2 = _runtime(tmp_path / "two", "two.sqlite3")
    with pytest.raises(ValueError, match="DATABASE_INSTANCE_MISMATCH"):
        verify_receipt_chain(
            env1[5].read_receipts(),
            expected_root_store_id=env1[5].root_store_id,
            expected_database_instance_id=env2[1].get_external_root_state().database_instance_id,
            initial_trusted_key=env1[7],
        )


def test_eir14_cross_project_or_sport_receipt_transplant_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    receipt = env[5].read_receipts()[0]
    forged = _resign_receipt(receipt, env[6], project_domain_id="other.project")
    with pytest.raises(ValueError, match="PROJECT_DOMAIN_MISMATCH"):
        verify_receipt_chain(
            (forged,), expected_root_store_id=env[5].root_store_id,
            expected_database_instance_id=env[1].get_external_root_state().database_instance_id,
            initial_trusted_key=env[7],
        )


def test_eir15_signing_key_id_mutation_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    receipt = env[5].read_receipts()[0]
    forged = _resign_receipt(receipt, env[6], signer_key_id="ed25519:" + "0" * 64)
    with pytest.raises(ValueError, match="SIGNER_KEY_CONTINUITY_MISMATCH"):
        verify_receipt_chain(
            (forged,), expected_root_store_id=env[5].root_store_id,
            expected_database_instance_id=env[1].get_external_root_state().database_instance_id,
            initial_trusted_key=env[7],
        )


def test_eir16_forged_key_rotation_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    new = EphemeralEd25519SigningAuthority.generate()
    head = env[5].head()
    state = env[1].get_external_root_state()
    metadata = {
        "new_key_id": new.key_id,
        "new_public_key_b64": base64.b64encode(new.public_key_bytes).decode("ascii"),
        "new_public_key_fingerprint": new.public_key_fingerprint,
        "new_key_proof_signature_b64": base64.b64encode(b"x" * 64).decode("ascii"),
        "activation_sequence": head.sequence + 2,
        "proof_core": {
            "schema": "matrix.c2-r8-3r6-key-rotation-proof-core/1",
            "root_store_id": env[5].root_store_id,
            "database_instance_id": state.database_instance_id,
            "operation_id": "3" * 64,
            "new_key_id": new.key_id,
            "activation_sequence": head.sequence + 2,
        },
    }
    forged = build_signed_receipt(
        store=env[5], signer=env[6], receipt_type="ROOT_KEY_ROTATION",
        operation_id="3" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE + timedelta(seconds=2), metadata=metadata, expected_head=head,
    )
    env[5].append(forged, expected_head=head)
    with pytest.raises(ValueError, match="NEW_KEY_PROOF_INVALID"):
        verify_receipt_chain(
            env[5].read_receipts(), expected_root_store_id=env[5].root_store_id,
            expected_database_instance_id=state.database_instance_id,
            initial_trusted_key=env[7],
        )


def test_eir17_valid_key_rotation_passes(tmp_path: Path):
    env = _runtime(tmp_path)
    new = EphemeralEd25519SigningAuthority.generate()
    env[8].rotate_key(new_signer=new, changed_at=BASE + timedelta(seconds=2))
    assert env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True


def test_eir18_unsupported_future_receipt_schema_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    payload = json.loads(env[5].read_receipts()[0].canonical_bytes().decode("utf-8"))
    payload["receipt_protocol_version"] = 2
    with pytest.raises(ValueError, match="SCHEMA_VERSION_UNSUPPORTED"):
        R83R6RootReceipt.from_bytes(_canonical(payload).encode("utf-8"))


def test_eir19_receipt_schema_downgrade_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    payload = json.loads(env[5].read_receipts()[0].canonical_bytes().decode("utf-8"))
    payload["receipt_protocol_version"] = 0
    with pytest.raises(ValueError, match="SCHEMA_VERSION_UNSUPPORTED"):
        R83R6RootReceipt.from_bytes(_canonical(payload).encode("utf-8"))


def test_eir20_root_store_identity_substitution_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    other = LocalDirectoryExternalIntegrityRootStore(tmp_path / "other-root")
    coord = R83R6ExternalIntegrityRootCoordinator(
        control_store=env[1], root_store=other, signer=env[6],
        bootstrap_trusted_key=env[7],
    )
    with pytest.raises(ValueError, match="LOCAL_ROOT_STORE_ID_MISMATCH|BOUND_LOCAL_STATE_WITH_EMPTY_EXTERNAL_ROOT"):
        coord.ensure_genesis(created_at=BASE + timedelta(seconds=2))


def test_eir21_clock_rollback_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    head = env[5].head()
    state = env[1].get_external_root_state()
    receipt = build_signed_receipt(
        store=env[5], signer=env[6], receipt_type="ROOT_ABORTED",
        operation_id="4" * 64, database_instance_id=state.database_instance_id,
        created_at=BASE, metadata={}, expected_head=head,
    )
    with pytest.raises(ValueError, match="RECEIPT_TIME_REGRESSION"):
        env[5].append(receipt, expected_head=head)


def test_eir22_external_store_unavailable_before_prepare_fails_closed(tmp_path: Path, monkeypatch):
    env = _runtime(tmp_path)
    original = env[5].append
    def unavailable(*args, **kwargs):
        raise OSError("simulated unavailable")
    monkeypatch.setattr(env[5], "append", unavailable)
    with pytest.raises(OSError, match="unavailable"):
        _rooted_in_progress(env)
    monkeypatch.setattr(env[5], "append", original)
    assert env[1].list_transition_events() == ()


def test_eir23_crash_after_prepare_recovers_as_abort_without_phantom_transition(tmp_path: Path):
    env = _runtime(tmp_path)
    with pytest.raises(R83R6InjectedCrash, match="AFTER_EXTERNAL_PREPARE"):
        env[8].transition_run_state(
            env[2].run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=2),
            guard=env[3], lease=env[4], crash_point="AFTER_EXTERNAL_PREPARE",
        )
    assert env[1].list_transition_events() == ()
    assert env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True
    assert [r.receipt_type for r in env[5].read_receipts()] == [
        "ROOT_GENESIS", "ROOT_PREPARED", "ROOT_ABORTED"
    ]


def test_eir24_crash_after_local_commit_recovers_matching_external_commit(tmp_path: Path):
    env = _runtime(tmp_path)
    with pytest.raises(R83R6InjectedCrash, match="AFTER_LOCAL_COMMIT"):
        env[8].transition_run_state(
            env[2].run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=2),
            guard=env[3], lease=env[4], crash_point="AFTER_LOCAL_COMMIT",
        )
    assert len(env[1].list_transition_events()) == 1
    assert env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True
    assert env[1].list_external_root_coordination()[0].status == "ACKNOWLEDGED"


def test_eir25_crash_after_external_commit_recovers_local_ack(tmp_path: Path):
    env = _runtime(tmp_path)
    with pytest.raises(R83R6InjectedCrash, match="AFTER_EXTERNAL_COMMIT"):
        env[8].transition_run_state(
            env[2].run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=2),
            guard=env[3], lease=env[4], crash_point="AFTER_EXTERNAL_COMMIT",
        )
    assert env[1].list_external_root_coordination()[0].status == "LOCAL_COMMITTED"
    assert env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3)) is True
    assert env[1].list_external_root_coordination()[0].status == "ACKNOWLEDGED"


def test_eir26_duplicate_prepare_replay_is_idempotent(tmp_path: Path):
    env = _runtime(tmp_path)
    event = env[1].preview_transition_event(
        env[2].run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2), guard=env[3], lease=env[4],
    )
    first = env[8]._prepare(event=event, created_at=BASE + timedelta(seconds=2))
    head = env[5].head()
    second = env[8]._prepare(event=event, created_at=BASE + timedelta(seconds=2))
    assert first == second
    assert env[5].head() == head


def test_eir27_conflicting_prepare_replay_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    event = env[1].preview_transition_event(
        env[2].run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome="STATE_TRANSITION_COMMITTED",
        changed_at=BASE + timedelta(seconds=2), guard=env[3], lease=env[4],
    )
    prepared = env[8]._prepare(event=event, created_at=BASE + timedelta(seconds=2))
    head = env[5].head()
    conflicting = build_signed_receipt(
        store=env[5], signer=env[6], receipt_type="ROOT_PREPARED",
        operation_id=prepared.operation_id,
        database_instance_id=env[1].get_external_root_state().database_instance_id,
        created_at=BASE + timedelta(seconds=3), event=event,
        metadata={"conflict": True}, expected_head=head,
    )
    with pytest.raises(ValueError, match="OPERATION_TYPE_DIVERGENCE"):
        env[5].append(conflicting, expected_head=head)


def test_eir28_duplicate_commit_replay_is_idempotent(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    receipts = env[5].read_receipts()
    prepared = next(r for r in receipts if r.receipt_type == "ROOT_PREPARED")
    committed = next(r for r in receipts if r.receipt_type == "ROOT_COMMITTED")
    event = env[1].get_transition_event(committed.local_transition_event_id)
    head = env[5].head()
    replay = env[8]._append_terminal_for_prepare(
        prepared=prepared, receipt_type="ROOT_COMMITTED",
        created_at=BASE + timedelta(seconds=3), event=event,
    )
    assert replay == committed
    assert env[5].head() == head


def test_eir29_conflicting_commit_replay_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    prepared = next(r for r in env[5].read_receipts() if r.receipt_type == "ROOT_PREPARED")
    event = env[1].list_transition_events()[0]
    forged_event = replace(event, event_id="f" * 64, event_sha256="e" * 64)
    with pytest.raises(ValueError, match="CONFLICTING_COMMIT_REPLAY"):
        env[8]._append_terminal_for_prepare(
            prepared=prepared, receipt_type="ROOT_COMMITTED",
            created_at=BASE + timedelta(seconds=3), event=forged_event,
        )


def test_eir30_deleted_local_root_coordination_metadata_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    with sqlite3.connect(env[0]) as connection:
        connection.execute("DELETE FROM football_bounded_external_root_coordination")
        connection.commit()
    _rehash_local(env[1])
    assert env[1].audit_integrity() is True
    with pytest.raises(ValueError, match="LOCAL_ROOT_COORDINATION_MISSING"):
        env[8].verify_and_reconcile(recovery_at=BASE + timedelta(seconds=4))


@pytest.mark.parametrize("outcome", ["STATE_TRANSITION_FAILED", "STATE_TRANSITION_ABANDONED"])
def test_eir31_hidden_failed_or_abandoned_transition_rejected(tmp_path: Path, outcome: str):
    env = _runtime(tmp_path)
    backup = tmp_path / "pre-attempt.sqlite3"
    _backup_database(env[0], backup)
    env[8].record_transition_attempt_outcome(
        env[2].run_id, expected_state="PLANNED", expected_state_version=0,
        attempted_new_state="IN_PROGRESS", outcome=outcome,
        changed_at=BASE + timedelta(seconds=2), guard=env[3], lease=env[4],
    )
    env[3].release(env[4])
    _restore_database(backup, env[0])
    rolled = SQLiteBoundedFootballLiveControlStore(env[0])
    coord = R83R6ExternalIntegrityRootCoordinator(
        control_store=rolled, root_store=env[5], signer=env[6],
        bootstrap_trusted_key=env[7],
    )
    with pytest.raises(ValueError, match="R8_3R6_"):
        coord.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=3))


def test_eir32_terminal_stop_db_rollback_rejected(tmp_path: Path):
    env = _runtime(tmp_path)
    _rooted_in_progress(env)
    backup = tmp_path / "in-progress.sqlite3"
    _backup_database(env[0], backup)
    env[8].transition_run_state(
        env[2].run_id, expected_state="IN_PROGRESS", expected_state_version=1,
        new_state="ABORTED", changed_at=BASE + timedelta(seconds=3),
        guard=env[3], lease=env[4],
    )
    env[3].release(env[4])
    _restore_database(backup, env[0])
    rolled = SQLiteBoundedFootballLiveControlStore(env[0])
    coord = R83R6ExternalIntegrityRootCoordinator(
        control_store=rolled, root_store=env[5], signer=env[6],
        bootstrap_trusted_key=env[7],
    )
    with pytest.raises(ValueError, match="R8_3R6_"):
        coord.verify_and_reconcile(recovery_at=BASE + timedelta(seconds=4))


def test_eir33_signing_key_unavailable_fails_closed(tmp_path: Path):
    env = _runtime(tmp_path)
    new_signer = EphemeralEd25519SigningAuthority.generate()
    env[8].rotate_key(new_signer=new_signer, changed_at=BASE + timedelta(seconds=2))
    restarted = R83R6ExternalIntegrityRootCoordinator(
        control_store=env[1], root_store=env[5], signer=env[6],
        bootstrap_trusted_key=env[7],
    )
    with pytest.raises(ValueError, match="ACTIVE_SIGNING_KEY_UNAVAILABLE"):
        restarted.transition_run_state(
            env[2].run_id, expected_state="PLANNED", expected_state_version=0,
            new_state="IN_PROGRESS", changed_at=BASE + timedelta(seconds=3),
            guard=env[3], lease=env[4],
        )
    assert env[1].list_transition_events() == ()


def test_eir34_private_key_material_not_persisted_or_rendered(tmp_path: Path):
    env = _runtime(tmp_path)
    private_raw = env[6]._private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    needles = {
        private_raw,
        private_raw.hex().encode("ascii"),
        base64.b64encode(private_raw),
    }
    assert "<redacted>" in repr(env[6])
    assert all(needle.decode("latin1", errors="ignore") not in repr(env[6]) for needle in needles)
    persisted = env[0].read_bytes() + b"".join(path.read_bytes() for path in env[5].path.rglob("*") if path.is_file())
    for needle in needles:
        assert needle not in persisted
