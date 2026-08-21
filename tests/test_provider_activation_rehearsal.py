from datetime import datetime, timezone
import sqlite3

import pytest

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
    ProviderShadowRehearsalAuthority,
    SQLiteProviderShadowRehearsalEvidenceStore,
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

    return (
        ProviderActivationReadinessCertification(
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
    )


def _shadow(tmp_path):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable=(
            "MATRIX_TEST_API_KEY"
        ),
        secret_type="API_KEY",
    )

    contracts = (
        build_api_football_request_contracts(
            secret_reference_fingerprint=(
                secret.reference_fingerprint
            ),
            valid_from=NOW,
        )
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
        endpoint_manifest_ids=(
            endpoint_ids
        ),
        binding_store=(
            SQLiteProviderNetworkBindingEvidenceStore(
                tmp_path / "network-bindings.db"
            )
        ),
        attempt_intent_store=(
            SQLiteProviderAttemptIntentStore(
                tmp_path / "attempt-intents.db"
            )
        ),
        secret_reference=secret,
        clock=lambda: NOW,
        valid_from=NOW,
        rights_decision=None,
        shadow_evidence_store=(
            evidence_store
        ),
    )

    return runtime, evidence_store


def test_shadow_runtime_persists_verified_readiness_and_request_evidence(
    tmp_path,
):
    runtime, store = _shadow(
        tmp_path
    )

    assert (
        runtime.readiness_evidence_id
        is not None
    )
    assert (
        store.get_verified(
            runtime.readiness_evidence_id
        ).evidence_type
        == "READINESS"
    )

    runtime.preview(
        contract_name=(
            "fixture_by_id"
        ),
        params={
            "id": 100,
        },
    )

    assert (
        len(
            runtime.request_evidence_ids
        )
        == 1
    )
    requests = (
        store.list_verified_requests(
            runtime.readiness_evidence_id
        )
    )
    assert len(requests) == 1
    assert (
        requests[
            0
        ].payload[
            "network_call_performed"
        ]
        is False
    )
    assert store.audit_integrity()


def test_rehearsal_certification_uses_only_durable_verified_stores(
    tmp_path,
):
    runtime, shadow_store = (
        _shadow(
            tmp_path
        )
    )

    runtime.preview(
        contract_name=(
            "fixture_by_id"
        ),
        params={
            "id": 100,
        },
    )

    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    permit_id = "5" * 64

    recovery_store.record(
        build_provider_interruption_evidence(
            run_id="1" * 64,
            provider_key="api_football",
            queue_item_fingerprint=(
                "2" * 64
            ),
            permit_id=permit_id,
            pre_network_binding_intent_id=(
                "3" * 64
            ),
            endpoint_manifest_id=(
                "4" * 64
            ),
            request_contract_id=(
                "6" * 64
            ),
            request_contract_fingerprint=(
                "7" * 64
            ),
            reason_code=(
                "PROCESS_INTERRUPTED"
            ),
            created_at=NOW,
        )
    )

    certification = (
        certify_provider_activation_rehearsal(
            activation_readiness=(
                _readiness()
            ),
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_evidence_authority=(
                runtime.shadow_rehearsal_authority
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
        )
    )

    assert (
        certification.status
        == "REHEARSAL_CERTIFIED_FAIL_CLOSED"
    )
    assert (
        certification.shadow_evidence_integrity
        is True
    )
    assert (
        certification.interruption_evidence_integrity
        is True
    )
    assert (
        certification.real_provider_execution_authorized
        is False
    )


def test_shadow_evidence_raw_database_tampering_is_detected(
    tmp_path,
):
    runtime, store = _shadow(
        tmp_path
    )

    evidence_id = (
        runtime.readiness_evidence_id
    )

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

    assert (
        store.audit_integrity()
        is False
    )

    with pytest.raises(
        ValueError,
        match="SHADOW_EVIDENCE_INTEGRITY_FAILURE",
    ):
        store.get_verified(
            evidence_id
        )


def test_rehearsal_rejects_authority_from_another_shadow_runtime(
    tmp_path,
):
    runtime, shadow_store = (
        _shadow(
            tmp_path
            / "one"
        )
    )
    other_runtime, _ = (
        _shadow(
            tmp_path
            / "two"
        )
    )

    runtime.preview(
        contract_name=(
            "fixture_by_id"
        ),
        params={
            "id": 100,
        },
    )

    recovery_store = (
        SQLiteProviderInterruptionRecoveryStore(
            tmp_path / "recovery.db"
        )
    )

    permit_id = "5" * 64

    recovery_store.record(
        build_provider_interruption_evidence(
            run_id="1" * 64,
            provider_key="api_football",
            queue_item_fingerprint=(
                "2" * 64
            ),
            permit_id=permit_id,
            pre_network_binding_intent_id=(
                "3" * 64
            ),
            endpoint_manifest_id=(
                "4" * 64
            ),
            request_contract_id=(
                "6" * 64
            ),
            request_contract_fingerprint=(
                "7" * 64
            ),
            reason_code=(
                "PROCESS_INTERRUPTED"
            ),
            created_at=NOW,
        )
    )

    certification = (
        certify_provider_activation_rehearsal(
            activation_readiness=(
                _readiness()
            ),
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_evidence_authority=(
                other_runtime.shadow_rehearsal_authority
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
        )
    )

    assert (
        certification.status
        == "NOT_CERTIFIED"
    )
    assert (
        "AUTHORITATIVE_REHEARSAL_EVIDENCE_REQUIRED"
        in certification.blockers
    )


def test_rehearsal_rejects_duck_typed_interruption_store(
    tmp_path,
):
    runtime, shadow_store = (
        _shadow(
            tmp_path
        )
    )

    runtime.preview(
        contract_name=(
            "fixture_by_id"
        ),
        params={
            "id": 100,
        },
    )

    class FakeRecoveryStore:
        def audit_integrity(
            self,
        ):
            return True

        def get_by_permit(
            self,
            permit_id,
        ):
            return type(
                "FakeEvidence",
                (),
                {
                    "status": (
                        "INTERRUPTED_UNKNOWN_OUTCOME"
                    ),
                    "safe_to_retry": False,
                    "request_units_refunded": False,
                },
            )()

    certification = (
        certify_provider_activation_rehearsal(
            activation_readiness=(
                _readiness()
            ),
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_evidence_authority=(
                runtime.shadow_rehearsal_authority
            ),
            shadow_readiness_evidence_id=(
                runtime.readiness_evidence_id
            ),
            interruption_recovery_store=(
                FakeRecoveryStore()
            ),
            interruption_permit_ids=(
                "5" * 64,
            ),
        )
    )

    assert (
        certification.status
        == "NOT_CERTIFIED"
    )
    assert (
        "AUTHORITATIVE_REHEARSAL_EVIDENCE_REQUIRED"
        in certification.blockers
    )


def test_shadow_rehearsal_authority_cannot_be_publicly_constructed():
    with pytest.raises(
        ValueError,
        match="SHADOW_REHEARSAL_AUTHORITY_CONSTRUCTION_FORBIDDEN",
    ):
        ProviderShadowRehearsalAuthority(
            _construction_token=(
                object()
            ),
            provider_key=(
                "api_football"
            ),
            store_identity=(
                "1" * 64
            ),
        )
