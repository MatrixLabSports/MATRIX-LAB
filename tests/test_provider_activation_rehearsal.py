from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    _base as readiness_base,
    _sha as readiness_sha,
)
from app.core.provider_activation_rehearsal import (
    certify_provider_activation_rehearsal,
)
from app.core.provider_interruption_recovery import (
    ProviderRecoveredAttemptState,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowReadiness,
    ApiFootballShadowRequest,
)


def readiness():
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
        legal_evidence_integrity=True,
        attempt_intent_integrity=True,
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
            legal_evidence_integrity=True,
            attempt_intent_integrity=True,
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


def test_rehearsal_certifies_governed_shadow_and_fail_closed_interruption():
    shadow_readiness = (
        ApiFootballShadowReadiness(
            mode="SHADOW",
            contract_count=1,
            endpoint_binding_count=1,
            rights_authorized=False,
            governed_request_client_verified=True,
            governed_transport_topology_verified=True,
            network_authority_type_verified=True,
            external_network_allowed=False,
            real_provider_execution_authorized=False,
            blockers=(
                "REAL_PROVIDER_EXECUTION_DISABLED",
            ),
        )
    )

    shadow_request = (
        ApiFootballShadowRequest(
            mode="SHADOW",
            contract_name="fixture_by_id",
            contract_id="1" * 64,
            endpoint_manifest_id="2" * 64,
            authorization_fingerprint="3" * 64,
            path="/fixtures",
            parameter_names=(
                "id",
            ),
            parameter_values_fingerprint=(
                "4" * 64
            ),
            governed_request_client_used=True,
            governed_transport_topology_verified=True,
            network_call_performed=False,
            network_permit_issued=False,
            secret_resolved=False,
            real_provider_execution_authorized=False,
        )
    )

    interrupted = (
        ProviderRecoveredAttemptState(
            permit_id="5" * 64,
            state=(
                "INTERRUPTED_UNKNOWN_OUTCOME"
            ),
            safe_to_retry=False,
            recovery_id="6" * 64,
            errors=(),
        )
    )

    certification = (
        certify_provider_activation_rehearsal(
            activation_readiness=(
                readiness()
            ),
            shadow_readiness=(
                shadow_readiness
            ),
            shadow_requests=(
                shadow_request,
            ),
            interruption_states=(
                interrupted,
            ),
        )
    )

    assert (
        certification.status
        == "REHEARSAL_CERTIFIED_FAIL_CLOSED"
    )
    assert (
        certification.zero_network_calls
        is True
    )
    assert (
        certification.zero_secret_resolution
        is True
    )
    assert (
        certification.zero_network_permits
        is True
    )
    assert (
        certification.interruption_recovery_fail_closed
        is True
    )
    assert (
        certification.real_provider_execution_authorized
        is False
    )
