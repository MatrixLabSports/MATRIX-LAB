import inspect
from pathlib import Path

from app.core.provider_activation_rehearsal import (
    certify_provider_activation_rehearsal,
)
from app.core.provider_shadow_rehearsal_evidence import (
    build_provider_shadow_attestation_key_reference,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowRuntime,
)


def test_p131_signing_root_is_fixed_and_not_caller_parameterized():
    signature = inspect.signature(
        build_provider_shadow_attestation_key_reference
    )
    assert not signature.parameters

    reference = build_provider_shadow_attestation_key_reference()
    assert reference.provider_key == (
        "matrix_shadow_rehearsal"
    )
    assert reference.environment_variable == (
        "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY"
    )


def test_p131_old_signing_authority_capability_surface_is_removed():
    evidence_source = Path(
        "app/core/provider_shadow_rehearsal_evidence.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    runtime_source = Path(
        "app/providers/api_football/shadow_runtime.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for forbidden in (
        "ProviderShadowRehearsalAuthority",
        "_new_provider_shadow_rehearsal_authority",
        "_AUTHORITY_CONSTRUCTION_TOKEN",
        "secrets.token_bytes",
    ):
        assert forbidden not in evidence_source

    assert "shadow_rehearsal_authority" not in runtime_source
    assert not hasattr(
        ApiFootballShadowRuntime,
        "shadow_rehearsal_authority",
    )


def test_p131_rehearsal_requires_network_attempt_cross_binding_sources():
    parameters = inspect.signature(
        certify_provider_activation_rehearsal
    ).parameters

    assert "shadow_evidence_authority" not in parameters
    assert "attempt_intent_store" in parameters
    assert "network_call_evidence_store" in parameters

    source = inspect.getsource(
        certify_provider_activation_rehearsal
    )

    for token in (
        "SQLiteProviderAttemptIntentStore",
        "SQLiteProviderNetworkCallEvidenceStore",
        "reconcile_network_attempt_with_recovery",
        "INTERRUPTION_ATTEMPT_PROVENANCE_NOT_CROSS_BOUND",
    ):
        assert token in source


def test_p131_attestation_key_is_external_reference_not_persisted_material():
    source = Path(
        "app/core/provider_shadow_rehearsal_evidence.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "resolve_secret_runtime",
        "attestation_key_reference_fingerprint",
        '"raw_attestation_key_persisted": False',
        "hmac.compare_digest",
        "matrix.provider-shadow-rehearsal-evidence/3",
    ):
        assert token in source
