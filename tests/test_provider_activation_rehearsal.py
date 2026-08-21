from datetime import datetime, timezone
import gc
import sqlite3

import pytest

from app.core.governed_provider_http import (
    SQLiteProviderNetworkCallEvidenceStore,
)
from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    _base as readiness_base,
    _sha as readiness_sha,
)
from app.core.provider_activation_rehearsal import (
    certify_provider_activation_rehearsal,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
    build_provider_attempt_intent_evidence,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
)
from app.core.provider_interruption_recovery import (
    SQLiteProviderInterruptionRecoveryStore,
    build_provider_interruption_evidence,
)
from app.core.provider_network_binding import (
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.provider_shadow_rehearsal_evidence import (
    SQLiteProviderShadowRehearsalEvidenceStore,
    verify_provider_shadow_rehearsal_attestation,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.request_contracts import (
    build_api_football_request_contracts,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowRuntime,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)
ATTESTATION_KEY = "a" * 64


@pytest.fixture(autouse=True)
def _shadow_attestation_key(monkeypatch):
    monkeypatch.setenv(
        "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY",
        ATTESTATION_KEY,
    )


def _readiness():
    blockers = (
        "PRODUCTION_RIGHTS_MUST_REMAIN_BLOCKED",
    )

    base = readiness_base(
        status=(
            "TECHNICALLY_READY_RIGHTS_BLOCKED"
        ),
        network_boundary_certified=True,
        connector_trust_verified=True,
        canonical_secret_resolver=True,
        request_contract_evidence_nonempty=True,
        request_contract_integrity=True,
        contract_endpoint_binding_integrity=True,
        endpoint_manifest_semantics_verified=True,
        legal_evidence_nonempty=True,
        legal_evidence_integrity=True,
        attempt_intent_integrity=True,
        attempt_intent_store_cross_bound=True,
        production_rights_blocked=True,
        blockers=blockers,
    )

    return ProviderActivationReadinessCertification(
        status=(
            "TECHNICALLY_READY_RIGHTS_BLOCKED"
        ),
        network_boundary_certified=True,
        connector_trust_verified=True,
        canonical_secret_resolver=True,
        request_contract_evidence_nonempty=True,
        request_contract_integrity=True,
        contract_endpoint_binding_integrity=True,
        endpoint_manifest_semantics_verified=True,
        legal_evidence_nonempty=True,
        legal_evidence_integrity=True,
        attempt_intent_integrity=True,
        attempt_intent_store_cross_bound=True,
        production_rights_blocked=True,
        real_provider_execution_authorized=False,
        blockers=blockers,
        certification_fingerprint=(
            readiness_sha(
                base
            )
        ),
    )


def _shadow(tmp_path):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable=(
            "MATRIX_TEST_API_KEY"
        ),
        secret_type="API_KEY",
    )

    contracts = build_api_football_request_contracts(
        secret_reference_fingerprint=(
            secret.reference_fingerprint
        ),
        valid_from=NOW,
    )

    endpoint_ids = {
        name: f"{index:064x}"
        for index, name
        in enumerate(
            sorted(
                contracts
            ),
            1,
        )
    }

    evidence_store = (
        SQLiteProviderShadowRehearsalEvidenceStore(
            tmp_path / "shadow-evidence.db"
        )
    )

    runtime = ApiFootballShadowRuntime(
        mode="SHADOW",
        base_url=(
            "https://api.example.test"
        ),
        registry=(
            SQLiteProviderRequestContractRegistry(
                tmp_path / "contracts.db"
            )
        ),
        contract_endpoint_binding_store=(
            SQLiteProviderContractEndpointBindingStore(
                tmp_path / "endpoint-bindings.db"
            )
        ),
        endpoint_manifest_ids=endpoint_ids,
        binding_store=(
            SQLiteProviderNetworkBindingEvidenceStore(
                tmp_path / "network-bindings.db"
            )
        ),
        attempt_intent_store=(
            SQLiteProviderAttemptIntentStore(
                tmp_path / "shadow-attempt-intents.db"
            )
        ),
        secret_reference=secret,
        clock=lambda: NOW,
        valid_from=NOW,
        rights_decision=None,
        shadow_evidence_store=evidence_store,
    )

    return runtime, evidence_store


def _interruption_chain(tmp_path):
    permit_id = "5" * 64
    run_id = "1" * 64
    queue_item_fingerprint = "2" * 64
    endpoint_manifest_id = "4" * 64
    request_contract_id = "6" * 64
    request_contract_fingerprint = "7" * 64

    attempt_store = SQLiteProviderAttemptIntentStore(
        tmp_path / "rehearsal-attempt-intents.db"
    )
    network_call_store = SQLiteProviderNetworkCallEvidenceStore(
        tmp_path / "rehearsal-network-calls.db"
    )
    recovery_store = SQLiteProviderInterruptionRecoveryStore(
        tmp_path / "recovery.db"
    )

    intent = build_provider_attempt_intent_evidence(
        run_id=run_id,
        provider_key="api_football",
        queue_item_fingerprint=(
            queue_item_fingerprint
        ),
        permit_id=permit_id,
        endpoint_manifest_id=(
            endpoint_manifest_id
        ),
        security_evidence_id=(
            "3" * 64
        ),
        request_contract_id=(
            request_contract_id
        ),
        request_contract_fingerprint=(
            request_contract_fingerprint
        ),
        request_path="/fixtures",
        request_parameter_names=(
            "id",
        ),
        request_parameter_values_fingerprint=(
            "8" * 64
        ),
        secret_reference_fingerprint=(
            "9" * 64
        ),
        created_at=NOW,
    )
    attempt_store.record(
        intent
    )

    network_call_store.record(
        permit_id=permit_id,
        event_type="NETWORK_CALL_STARTED",
        event_at=NOW,
        provider_key="api_football",
        run_id=run_id,
        method="GET",
        endpoint_manifest_id=(
            endpoint_manifest_id
        ),
    )

    recovery_store.record(
        build_provider_interruption_evidence(
            run_id=run_id,
            provider_key="api_football",
            queue_item_fingerprint=(
                queue_item_fingerprint
            ),
            permit_id=permit_id,
            pre_network_binding_intent_id=(
                intent.intent_id
            ),
            endpoint_manifest_id=(
                endpoint_manifest_id
            ),
            request_contract_id=(
                request_contract_id
            ),
            request_contract_fingerprint=(
                request_contract_fingerprint
            ),
            reason_code=(
                "PROCESS_INTERRUPTED"
            ),
            created_at=NOW,
        )
    )

    return (
        permit_id,
        attempt_store,
        network_call_store,
        recovery_store,
    )


def _certify(
    *,
    runtime,
    shadow_store,
    permit_id,
    attempt_store,
    network_call_store,
    recovery_store,
):
    return certify_provider_activation_rehearsal(
        activation_readiness=(
            _readiness()
        ),
        shadow_evidence_store=(
            shadow_store
        ),
        shadow_readiness_evidence_id=(
            runtime.readiness_evidence_id
        ),
        interruption_recovery_store=(
            recovery_store
        ),
        interruption_permit_ids=(
            permit_id,
        ),
        attempt_intent_store=(
            attempt_store
        ),
        network_call_evidence_store=(
            network_call_store
        ),
    )


def test_shadow_runtime_persists_cryptographically_attested_readiness_and_request_evidence(
    tmp_path,
):
    runtime, store = _shadow(
        tmp_path
    )

    assert runtime.readiness_evidence_id is not None

    readiness = store.get_verified(
        runtime.readiness_evidence_id
    )
    assert readiness is not None
    assert readiness.evidence_type == "READINESS"
    assert verify_provider_shadow_rehearsal_attestation(
        readiness
    )

    runtime.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )

    requests = store.list_verified_requests(
        runtime.readiness_evidence_id
    )
    assert len(requests) == 1
    assert verify_provider_shadow_rehearsal_attestation(
        requests[0]
    )
    assert requests[0].payload[
        "network_call_performed"
    ] is False
    assert store.audit_integrity()


def test_shadow_attestation_remains_verifiable_after_runtime_restart(
    tmp_path,
):
    runtime, store = _shadow(
        tmp_path
    )
    runtime.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )

    readiness_id = runtime.readiness_evidence_id
    request_id = runtime.request_evidence_ids[0]
    path = store.path

    del runtime
    del store
    gc.collect()

    reopened = SQLiteProviderShadowRehearsalEvidenceStore(
        path
    )
    readiness = reopened.get_verified(
        readiness_id
    )
    request = reopened.get_verified(
        request_id
    )

    assert readiness is not None
    assert request is not None
    assert verify_provider_shadow_rehearsal_attestation(
        readiness
    )
    assert verify_provider_shadow_rehearsal_attestation(
        request
    )


def test_shadow_runtime_does_not_expose_signing_authority_capability(
    tmp_path,
):
    runtime, _ = _shadow(
        tmp_path
    )

    assert not hasattr(
        runtime,
        "shadow_rehearsal_authority",
    )
    assert not hasattr(
        runtime,
        "_shadow_rehearsal_authority",
    )


def test_rehearsal_certification_cross_binds_recovery_to_attempt_and_started_network_event(
    tmp_path,
):
    runtime, shadow_store = _shadow(
        tmp_path / "shadow"
    )
    runtime.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )

    (
        permit_id,
        attempt_store,
        network_call_store,
        recovery_store,
    ) = _interruption_chain(
        tmp_path / "interrupt"
    )

    certification = _certify(
        runtime=runtime,
        shadow_store=shadow_store,
        permit_id=permit_id,
        attempt_store=attempt_store,
        network_call_store=(
            network_call_store
        ),
        recovery_store=recovery_store,
    )

    assert certification.status == (
        "REHEARSAL_CERTIFIED_FAIL_CLOSED"
    )
    assert certification.shadow_evidence_integrity is True
    assert certification.interruption_evidence_integrity is True
    assert certification.interruption_recovery_fail_closed is True
    assert certification.real_provider_execution_authorized is False


def test_rehearsal_rejects_recovery_row_without_attempt_and_network_started_provenance(
    tmp_path,
):
    runtime, shadow_store = _shadow(
        tmp_path / "shadow"
    )
    runtime.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )

    recovery_store = SQLiteProviderInterruptionRecoveryStore(
        tmp_path / "recovery.db"
    )
    attempt_store = SQLiteProviderAttemptIntentStore(
        tmp_path / "attempts.db"
    )
    network_call_store = SQLiteProviderNetworkCallEvidenceStore(
        tmp_path / "network.db"
    )
    permit_id = "5" * 64

    recovery_store.record(
        build_provider_interruption_evidence(
            run_id="1" * 64,
            provider_key="api_football",
            queue_item_fingerprint="2" * 64,
            permit_id=permit_id,
            pre_network_binding_intent_id="3" * 64,
            endpoint_manifest_id="4" * 64,
            request_contract_id="6" * 64,
            request_contract_fingerprint="7" * 64,
            reason_code="PROCESS_INTERRUPTED",
            created_at=NOW,
        )
    )

    certification = _certify(
        runtime=runtime,
        shadow_store=shadow_store,
        permit_id=permit_id,
        attempt_store=attempt_store,
        network_call_store=(
            network_call_store
        ),
        recovery_store=recovery_store,
    )

    assert certification.status == "NOT_CERTIFIED"
    assert (
        "INTERRUPTION_ATTEMPT_PROVENANCE_NOT_CROSS_BOUND"
        in certification.blockers
    )


def test_shadow_evidence_raw_database_tampering_is_detected(
    tmp_path,
):
    runtime, store = _shadow(
        tmp_path
    )
    evidence_id = runtime.readiness_evidence_id
    assert evidence_id is not None

    with sqlite3.connect(
        store.path
    ) as connection:
        connection.execute(
            """
            UPDATE provider_shadow_rehearsal_evidence
            SET payload_json = ?
            WHERE evidence_id = ?
            """,
            (
                '{"tampered":true}\n',
                evidence_id,
            ),
        )
        connection.commit()

    assert store.audit_integrity() is False

    with pytest.raises(
        ValueError,
        match="SHADOW_EVIDENCE_INTEGRITY_FAILURE",
    ):
        store.get_verified(
            evidence_id
        )


def test_shadow_attestation_rejects_changed_durable_key_after_restart(
    tmp_path,
    monkeypatch,
):
    runtime, store = _shadow(
        tmp_path
    )
    evidence = store.get_verified(
        runtime.readiness_evidence_id
    )
    assert evidence is not None
    assert verify_provider_shadow_rehearsal_attestation(
        evidence
    )

    monkeypatch.setenv(
        "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY",
        "b" * 64,
    )

    assert not verify_provider_shadow_rehearsal_attestation(
        evidence
    )


def test_rehearsal_rejects_duck_typed_authoritative_sources(
    tmp_path,
):
    runtime, shadow_store = _shadow(
        tmp_path
    )
    runtime.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )

    class FakeStore:
        def audit_integrity(self):
            return True

        def get_by_permit(self, permit_id):
            return None

    certification = certify_provider_activation_rehearsal(
        activation_readiness=_readiness(),
        shadow_evidence_store=shadow_store,
        shadow_readiness_evidence_id=(
            runtime.readiness_evidence_id
        ),
        interruption_recovery_store=FakeStore(),
        interruption_permit_ids=(
            "5" * 64,
        ),
        attempt_intent_store=FakeStore(),
        network_call_evidence_store=FakeStore(),
    )

    assert certification.status == "NOT_CERTIFIED"
    assert (
        "AUTHORITATIVE_REHEARSAL_EVIDENCE_REQUIRED"
        in certification.blockers
    )
