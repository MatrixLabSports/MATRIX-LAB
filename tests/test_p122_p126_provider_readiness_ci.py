from pathlib import Path


def test_provider_production_readiness_remains_fail_closed():
    rights = Path(
        "app/core/provider_rights_authorization.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    legal = Path(
        "app/core/provider_legal_evidence.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    contract_binding = Path(
        "app/core/provider_contract_endpoint_binding.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    intent = Path(
        "app/core/provider_attempt_intent.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    attempts = Path(
        "app/core/provider_attempt_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    recovery = Path(
        "app/core/provider_interruption_recovery.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    shadow = Path(
        "app/providers/api_football/shadow_runtime.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    baseline = Path(
        "app/providers/api_football/rights_baseline.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "BLOCKED_PENDING_RIGHTS_REVIEW"
        in baseline
    )
    assert (
        "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED"
        in rights
    )
    assert (
        "HUMAN_VERIFIED"
        in legal
    )
    assert (
        "endpoint_manifest_id"
        in contract_binding
    )
    assert (
        "ProviderAttemptIntentEvidence"
        in intent
    )
    assert (
        "NO_PHYSICAL_ATTEMPTS_TO_CERTIFY"
        in attempts
    )
    assert (
        "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS"
        in attempts
    )
    assert (
        "INTERRUPTED_UNKNOWN_OUTCOME"
        in recovery
    )
    assert (
        "recover_all_started_only_network_attempts"
        in recovery
    )

    for token in (
        "GovernedProviderRequestClient",
        "ProviderNetworkAuthority",
        "BindingAuditPinnedHttpsTransport",
        "JitSecretPinnedHttpsTransport",
    ):
        assert token in shadow

    assert (
        "network_call_performed=False"
        in shadow
    )
    assert (
        "secret_resolved=False"
        in shadow
    )

    combined = (
        rights
        + legal
        + contract_binding
        + intent
        + attempts
        + recovery
        + shadow
        + baseline
    )

    assert (
        "real_provider_execution_authorized=True"
        not in combined
    )
    assert (
        "automatic_provider_switch=True"
        not in combined
    )
    assert (
        "automatic_wagering=True"
        not in combined
    )


def test_canonical_ci_semantically_enforces_p122_p126():
    ci = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "_provider_production_readiness_boundary"
        in ci
    )
    assert (
        "_provider_production_readiness_boundary(ROOT)"
        in ci
    )

    for token in (
        "provider_rights_authorization.py",
        "provider_legal_evidence.py",
        "provider_contract_endpoint_binding.py",
        "provider_attempt_intent.py",
        "provider_attempt_certification.py",
        "provider_interruption_recovery.py",
    ):
        assert token in ci


def test_runtime_reconciliation_contains_authoritative_provider_readiness_composition():
    source = Path(
        "app/core/runtime_reconciliation.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "reconcile_runtime_provider_readiness"
        in source
    )
    assert (
        "recover_started_only_network_attempt"
        in source
    )
    assert (
        "scan_started_only_network_attempts"
        in source
    )
    assert (
        "enforce_provider_attempt_certification"
        in source
    )
    assert (
        "PROVIDER_RIGHTS_NOT_AUTHORIZED"
        in source
    )
