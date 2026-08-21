from pathlib import Path

import pytest

from app.core.authoritative_runtime_admission import (
    evaluate_authoritative_provider_runtime_admission,
)
from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    _base as readiness_base,
    _sha as readiness_sha,
)
from app.core.provider_activation_rehearsal import (
    ProviderActivationRehearsalCertification,
    _base as rehearsal_base,
    _sha as rehearsal_sha,
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


def _rehearsal(
    readiness,
):
    blockers = ()
    base = rehearsal_base(
        status=(
            "REHEARSAL_CERTIFIED_FAIL_CLOSED"
        ),
        activation_readiness_fingerprint=(
            readiness.certification_fingerprint
        ),
        shadow_readiness_evidence_id=(
            "1" * 64
        ),
        shadow_mode="SHADOW",
        shadow_request_count=1,
        governed_shadow_verified=True,
        shadow_evidence_integrity=True,
        zero_network_calls=True,
        zero_secret_resolution=True,
        zero_network_permits=True,
        interruption_recovery_fail_closed=True,
        interruption_evidence_integrity=True,
        blockers=blockers,
    )
    return ProviderActivationRehearsalCertification(
        status=(
            "REHEARSAL_CERTIFIED_FAIL_CLOSED"
        ),
        activation_readiness_fingerprint=(
            readiness.certification_fingerprint
        ),
        shadow_readiness_evidence_id=(
            "1" * 64
        ),
        shadow_mode="SHADOW",
        shadow_request_count=1,
        governed_shadow_verified=True,
        shadow_evidence_integrity=True,
        zero_network_calls=True,
        zero_secret_resolution=True,
        zero_network_permits=True,
        interruption_recovery_fail_closed=True,
        interruption_evidence_integrity=True,
        real_provider_execution_authorized=False,
        blockers=blockers,
        certification_fingerprint=(
            rehearsal_sha(
                base
            )
        ),
    )


def test_authoritative_provider_admission_remains_fail_closed():
    readiness = _readiness()
    rehearsal = _rehearsal(
        readiness
    )

    with pytest.raises(
        ValueError,
        match="REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED",
    ):
        evaluate_authoritative_provider_runtime_admission(
            report=object(),
            audit_ledger=object(),
            run_mode_evidence_store=object(),
            activation_readiness_certification=(
                readiness
            ),
            activation_rehearsal_certification=(
                rehearsal
            ),
        )


def test_official_client_source_requires_both_activation_certifications():
    source = Path(
        "app/providers/api_football/governed_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "activation_readiness_certification",
        "activation_rehearsal_certification",
        "require_provider_activation_authorized",
        "require_activation_rehearsal_for_real_execution",
    ):
        assert token in source


def test_canonical_ci_has_semantic_activation_boundary():
    source = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "_provider_network_activation_semantic_boundary(ROOT)"
        in source
    )
    assert "ast.parse" in source
