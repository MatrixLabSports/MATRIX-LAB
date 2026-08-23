from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
import sqlite3
import threading

import pytest

from app.application.football.bounded_live_executor import (
    BoundedFootballLiveExecutorConfig,
    R8_1_APPROVED_DESIGN_MANIFEST_SHA256,
    R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256,
    R8_1_LEDGER_USER_VERSION,
    R8_1_RUN_STATUS,
    SQLiteBoundedFootballLiveRunManifestStore,
    build_bounded_capture_plan,
    build_bounded_run_manifest,
)


BASE = datetime(2026, 8, 23, 21, 10, tzinfo=UTC)
DESIGN_SHA = R8_1_APPROVED_DESIGN_MANIFEST_SHA256
AUDIT_SHA = R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256
NONCE_SHA = "2" * 64


def config(**overrides):
    values = dict(
        provider_key="api_football",
        subject_key="fixture:1557375",
        modalities=(
            "fixture_status",
            "fixture_statistics",
            "fixture_events",
        ),
        max_capture_rounds=3,
        max_total_provider_calls=9,
        max_runtime_ms=300000,
    )
    values.update(overrides)
    return BoundedFootballLiveExecutorConfig(**values)


def manifest(value=None, *, nonce=NONCE_SHA):
    cfg = config() if value is None else value
    return build_bounded_run_manifest(
        cfg,
        created_at=BASE,
        run_nonce_sha256=nonce,
    )


def test_config_is_finite_single_process_and_execution_disabled():
    value = config()

    assert value.planned_provider_calls == 9
    assert value.capture_interval_ms is None
    assert value.single_process_only is True
    assert value.cross_process_execution_allowed is False
    assert value.automatic_retry is False
    assert value.automatic_provider_switch is False
    assert value.automatic_model_promotion is False
    assert value.automatic_wagering is False
    assert value.production_admissible is False

    payload = value.payload()
    assert payload["execution_authorized"] is False
    assert payload["rights_scope_approved"] is False
    assert payload["human_authorization_granted"] is False
    assert payload["thresholds_empirically_calibrated"] is False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"subject_key": "team:1"},
            "FOOTBALL_FIXTURE_SUBJECT_KEY_REQUIRED",
        ),
        (
            {
                "modalities": (
                    "fixture_events",
                    "fixture_events",
                )
            },
            "DUPLICATE_MODALITY_FORBIDDEN",
        ),
        (
            {"modalities": ("odds",)},
            "ODDS_NOT_AUTHORIZED_IN_R8_1",
        ),
        (
            {"max_attempts_per_slot": 2},
            "R8_1_AUTOMATIC_RETRY_FORBIDDEN",
        ),
        (
            {"capture_interval_ms": 15000},
            "CAPTURE_INTERVAL_REQUIRES_EMPIRICAL_CALIBRATION",
        ),
        (
            {"cross_process_execution_allowed": True},
            "R8_1_CROSS_PROCESS_EXECUTION_FORBIDDEN",
        ),
        (
            {"production_admissible": True},
            "PRODUCTION_ADMISSION_FORBIDDEN",
        ),
    ],
)
def test_config_fails_closed_on_unauthorized_or_uncalibrated_inputs(
    overrides,
    reason,
):
    with pytest.raises(ValueError, match=reason):
        config(**overrides)


def test_config_rejects_plan_that_exceeds_total_call_budget():
    with pytest.raises(
        ValueError,
        match="PLANNED_PROVIDER_CALLS_EXCEED_BUDGET",
    ):
        config(max_capture_rounds=4, max_total_provider_calls=11)


def test_capture_plan_has_exact_bounded_cardinality_and_no_retry():
    value = config(
        modalities=("fixture_status", "fixture_events"),
        max_capture_rounds=4,
        max_total_provider_calls=8,
    )
    slots = build_bounded_capture_plan(value)

    assert len(slots) == 8
    assert slots[0].round_index == 1
    assert slots[-1].round_index == 4
    assert all(slot.attempt_index == 1 for slot in slots)
    assert {
        slot.modality for slot in slots
    } == {"fixture_status", "fixture_events"}


def test_manifest_is_governance_bound_and_execution_stays_disabled():
    value = manifest()

    assert len(value.run_id) == 64
    assert len(value.manifest_fingerprint) == 64
    assert value.status == R8_1_RUN_STATUS
    assert value.design_manifest_sha256 == DESIGN_SHA
    assert value.independent_audit_sha256 == AUDIT_SHA
    assert value.human_authorization_granted is False
    assert value.rights_scope_approved is False
    assert value.execution_authorized is False
    assert value.repeated_provider_execution_authorized is False
    assert value.production_admissible is False
    assert value.cross_process_execution_allowed is False


def test_run_id_is_deterministic_and_nonce_bound():
    first = manifest()
    replay = manifest()
    changed = manifest(nonce="3" * 64)

    assert first.run_id == replay.run_id
    assert first.manifest_fingerprint == replay.manifest_fingerprint
    assert changed.run_id != first.run_id


def test_manifest_store_exact_replay_is_idempotent(tmp_path):
    store = SQLiteBoundedFootballLiveRunManifestStore(
        tmp_path / "run-manifest.sqlite3"
    )
    value = manifest()

    first = store.record(value)
    replay = store.record(value)
    loaded = store.get_verified(value.run_id)

    assert first.idempotent is False
    assert replay.idempotent is True
    assert loaded == value
    assert store.audit_integrity() is True

    with sqlite3.connect(store.path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_manifest"
        ).fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert count == 1
    assert version == R8_1_LEDGER_USER_VERSION


def test_manifest_same_run_id_cannot_mutate(tmp_path):
    store = SQLiteBoundedFootballLiveRunManifestStore(
        tmp_path / "run-manifest.sqlite3"
    )
    original = manifest()
    store.record(original)

    # R8.1R1 closes this earlier than the store: a durable manifest whose
    # fields no longer match its bound config fingerprint is invalid at
    # construction time.
    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_CONFIG_CONTRACT_FINGERPRINT_MISMATCH",
    ):
        replace(
            original,
            max_runtime_ms=original.max_runtime_ms + 1,
            manifest_fingerprint="",
        )


def test_manifest_store_detects_payload_tampering(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET manifest_json = ?
            WHERE run_id = ?
            """,
            ("{}\n", value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_manifest_store_detects_row_deletion_against_anchor(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            DELETE FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (value.run_id,),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_manifest_store_rejects_unknown_schema_version(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 999")
        connection.commit()

    with pytest.raises(
        ValueError,
        match="R8_1_RUN_MANIFEST_SCHEMA_VERSION_MISMATCH",
    ):
        SQLiteBoundedFootballLiveRunManifestStore(path)


def test_manifest_constructor_rejects_any_execution_promotion():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="R8_1_EXECUTION_MUST_REMAIN_UNAUTHORIZED",
    ):
        replace(original, execution_authorized=True)

    with pytest.raises(
        ValueError,
        match="PRODUCTION_ADMISSION_FORBIDDEN",
    ):
        replace(original, production_admissible=True)


def test_manifest_store_detects_rehashed_boolean_type_tamper(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            """
            SELECT manifest_json
            FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (value.run_id,),
        ).fetchone()[0]
        payload = json.loads(raw)
        payload["execution_authorized"] = 0
        forged_json = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        import hashlib

        forged_sha = hashlib.sha256(
            forged_json.encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET manifest_json = ?, manifest_sha256 = ?
            WHERE run_id = ?
            """,
            (forged_json, forged_sha, value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_manifest_store_detects_rehashed_row_column_drift(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET config_fingerprint = ?
            WHERE run_id = ?
            """,
            ("f" * 64, value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_concurrent_exact_manifest_replay_remains_single_row(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    left = SQLiteBoundedFootballLiveRunManifestStore(path)
    right = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    results = []
    errors = []
    lock = threading.Lock()

    def worker(store):
        try:
            result = store.record(value)
            with lock:
                results.append(result)
        except Exception as error:
            with lock:
                errors.append(error)

    threads = [
        threading.Thread(target=worker, args=(left,)),
        threading.Thread(target=worker, args=(right,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert sorted(result.idempotent for result in results) == [False, True]

    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_manifest"
        ).fetchone()[0]
    assert count == 1
    assert left.audit_integrity() is True


def test_concurrent_distinct_manifests_preserve_anchor_integrity(tmp_path):
    path = tmp_path / "run-manifest.sqlite3"
    left = SQLiteBoundedFootballLiveRunManifestStore(path)
    right = SQLiteBoundedFootballLiveRunManifestStore(path)
    values = [
        manifest(nonce="4" * 64),
        manifest(nonce="5" * 64),
    ]
    errors = []
    lock = threading.Lock()

    def worker(store, value):
        try:
            store.record(value)
        except Exception as error:
            with lock:
                errors.append(error)

    threads = [
        threading.Thread(target=worker, args=(left, values[0])),
        threading.Thread(target=worker, args=(right, values[1])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    with sqlite3.connect(path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_manifest"
        ).fetchone()[0]
    assert count == 2
    assert left.audit_integrity() is True


def test_manifest_direct_construction_rederives_finite_plan_contract():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_PLANNED_PROVIDER_CALLS_MISMATCH",
    ):
        replace(
            original,
            planned_provider_calls=original.max_total_provider_calls + 100,
            manifest_fingerprint="",
        )


def test_manifest_direct_construction_rederives_modality_contract():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="ODDS_NOT_AUTHORIZED_IN_R8_1",
    ):
        replace(
            original,
            modalities=("odds",),
            planned_provider_calls=1,
            manifest_fingerprint="",
        )

    with pytest.raises(
        ValueError,
        match="DUPLICATE_MODALITY_FORBIDDEN",
    ):
        replace(
            original,
            modalities=("fixture_events", "fixture_events"),
            planned_provider_calls=6,
            manifest_fingerprint="",
        )


def test_manifest_direct_construction_rederives_football_subject_contract():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="FOOTBALL_FIXTURE_SUBJECT_KEY_REQUIRED",
    ):
        replace(
            original,
            subject_key="team:1",
            manifest_fingerprint="",
        )


def test_manifest_direct_construction_rederives_config_fingerprint():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_CONFIG_CONTRACT_FINGERPRINT_MISMATCH",
    ):
        replace(
            original,
            config_fingerprint="f" * 64,
            manifest_fingerprint="",
        )


def test_store_detects_rehashed_ignored_control_field_tamper(tmp_path):
    path = tmp_path / "semantic-roundtrip.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            """
            SELECT manifest_json
            FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (value.run_id,),
        ).fetchone()[0]
        payload = json.loads(raw)
        payload["stop_conditions"] = ["FORGED_STOP_CONDITION"]
        forged_json = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        import hashlib

        forged_sha = hashlib.sha256(
            forged_json.encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET manifest_json = ?, manifest_sha256 = ?
            WHERE run_id = ?
            """,
            (forged_json, forged_sha, value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_store_detects_rehashed_extra_field_tamper(tmp_path):
    path = tmp_path / "semantic-extra.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            """
            SELECT manifest_json
            FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (value.run_id,),
        ).fetchone()[0]
        payload = json.loads(raw)
        payload["unexpected_field"] = "forged"
        forged_json = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        import hashlib

        forged_sha = hashlib.sha256(
            forged_json.encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET manifest_json = ?, manifest_sha256 = ?
            WHERE run_id = ?
            """,
            (forged_json, forged_sha, value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


def test_manifest_recovery_requirements_are_fail_closed():
    original = manifest()

    with pytest.raises(
        ValueError,
        match="R8_1_CRASH_RECOVERY_REQUIRED",
    ):
        replace(
            original,
            crash_recovery_required=False,
            manifest_fingerprint="",
        )

    with pytest.raises(
        ValueError,
        match="R8_1_IDEMPOTENT_RESUME_REQUIRED",
    ):
        replace(
            original,
            idempotent_resume_required=False,
            manifest_fingerprint="",
        )


def test_manifest_governance_authority_is_release_bound():
    original = manifest()

    assert (
        original.design_manifest_sha256
        == R8_1_APPROVED_DESIGN_MANIFEST_SHA256
    )
    assert (
        original.independent_audit_sha256
        == R8_1_APPROVED_INDEPENDENT_AUDIT_SHA256
    )

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_DESIGN_AUTHORITY_SHA_MISMATCH",
    ):
        replace(
            original,
            design_manifest_sha256="a" * 64,
            manifest_fingerprint="",
        )

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_INDEPENDENT_AUDIT_AUTHORITY_SHA_MISMATCH",
    ):
        replace(
            original,
            independent_audit_sha256="b" * 64,
            manifest_fingerprint="",
        )


def test_run_nonce_is_durable_and_run_id_is_rederived():
    original = manifest()

    assert original.run_nonce_sha256 == NONCE_SHA
    assert original.payload()["run_nonce_sha256"] == NONCE_SHA

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_RUN_ID_PROVENANCE_MISMATCH",
    ):
        replace(
            original,
            run_id="f" * 64,
            manifest_fingerprint="",
        )

    with pytest.raises(
        ValueError,
        match="RUN_MANIFEST_RUN_ID_PROVENANCE_MISMATCH",
    ):
        replace(
            original,
            run_nonce_sha256="e" * 64,
            manifest_fingerprint="",
        )


def test_builder_does_not_accept_caller_supplied_governance_authority():
    with pytest.raises(TypeError):
        build_bounded_run_manifest(
            config(),
            created_at=BASE,
            run_nonce_sha256=NONCE_SHA,
            design_manifest_sha256="a" * 64,
            independent_audit_sha256="b" * 64,
        )


def test_store_detects_rehashed_nonce_tamper_without_matching_run_id(tmp_path):
    path = tmp_path / "nonce-provenance.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    value = manifest()
    store.record(value)

    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            """
            SELECT manifest_json
            FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (value.run_id,),
        ).fetchone()[0]
        payload = json.loads(raw)
        payload["run_nonce_sha256"] = "d" * 64
        forged_json = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
        import hashlib

        forged_sha = hashlib.sha256(
            forged_json.encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE football_bounded_run_manifest
            SET manifest_json = ?, manifest_sha256 = ?
            WHERE run_id = ?
            """,
            (forged_json, forged_sha, value.run_id),
        )
        connection.commit()

    assert store.audit_integrity() is False


@pytest.mark.parametrize(
    "subject_key",
    [
        "fixture:",
        "fixture:abc",
        "fixture:-1",
        "fixture:+1",
        "fixture:0",
        "fixture:001557375",
        "fixture: 1557375",
        "fixture:1.0",
        "fixture:1/2",
    ],
)
def test_fixture_subject_requires_canonical_positive_decimal_grammar(
    subject_key,
):
    with pytest.raises(
        ValueError,
        match="FOOTBALL_FIXTURE_SUBJECT_KEY_CANONICAL_GRAMMAR_REQUIRED",
    ):
        config(subject_key=subject_key)


@pytest.mark.parametrize(
    "subject_key",
    ["fixture:1", "fixture:1557375"],
)
def test_fixture_subject_accepts_canonical_positive_decimal_ids(
    subject_key,
):
    value = config(subject_key=subject_key)
    assert value.subject_key == subject_key


def test_config_normalizes_outer_whitespace_before_fixture_grammar():
    value = config(subject_key="  fixture:1557375  ")
    assert value.subject_key == "fixture:1557375"


def test_manifest_direct_aliases_are_canonicalized_to_rederived_config():
    original = manifest()

    provider_alias = replace(
        original,
        provider_key=" api_football ",
        manifest_fingerprint="",
    )
    subject_alias = replace(
        original,
        subject_key=" fixture:1557375 ",
        manifest_fingerprint="",
    )

    assert provider_alias.provider_key == original.provider_key
    assert provider_alias.subject_key == original.subject_key
    assert provider_alias.run_id == original.run_id
    assert provider_alias.config_fingerprint == original.config_fingerprint
    assert provider_alias.manifest_fingerprint == original.manifest_fingerprint
    assert provider_alias == original

    assert subject_alias.provider_key == original.provider_key
    assert subject_alias.subject_key == original.subject_key
    assert subject_alias.run_id == original.run_id
    assert subject_alias.config_fingerprint == original.config_fingerprint
    assert subject_alias.manifest_fingerprint == original.manifest_fingerprint
    assert subject_alias == original


def test_canonicalized_alias_persistence_is_exact_idempotent_replay(tmp_path):
    path = tmp_path / "canonical-alias.sqlite3"
    store = SQLiteBoundedFootballLiveRunManifestStore(path)
    original = manifest()
    alias = replace(
        original,
        subject_key=" fixture:1557375 ",
        provider_key=" api_football ",
        manifest_fingerprint="",
    )

    first = store.record(alias)
    replay = store.record(original)
    loaded = store.get_verified(original.run_id)

    assert first.idempotent is False
    assert replay.idempotent is True
    assert loaded == original
    assert store.audit_integrity() is True

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT manifest_json
            FROM football_bounded_run_manifest
            WHERE run_id = ?
            """,
            (original.run_id,),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM football_bounded_run_manifest"
        ).fetchone()[0]

    payload = json.loads(row[0])
    assert payload["provider_key"] == "api_football"
    assert payload["subject_key"] == "fixture:1557375"
    assert count == 1
