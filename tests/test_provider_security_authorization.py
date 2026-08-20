from app.core.provider_preflight_gate import (
    ProviderPreflightDecision,
    SQLiteProviderPreflightEvidenceStore,
    _decision_fingerprint as preflight_fingerprint,
)
from app.core.provider_security_authorization import (
    evaluate_authoritative_provider_security,
)
from app.core.secret_reference import (
    SQLiteSecretReferenceRegistry,
    build_secret_reference,
)


def _preflight(tmp_path):
    values = dict(
        status="EXECUTE",
        executable=True,
        downstream_quarantine_required=False,
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        queue_fingerprint="a" * 64,
        permit_id="b" * 64,
        rights_manifest_fingerprint="c" * 64,
        scheduling_evidence_fingerprint="d" * 64,
        bootstrap_policy_fingerprint=None,
        requested_data_scope=("history",),
        requested_purpose="analysis",
        requested_jurisdiction="CO",
        max_items=1,
        max_requests=1,
        provider_health_status="ELIGIBLE",
        reason_codes=(),
    )

    decision = ProviderPreflightDecision(
        **values,
        decision_fingerprint=preflight_fingerprint(
            **values
        ),
    )

    store = SQLiteProviderPreflightEvidenceStore(
        tmp_path / "preflight.db"
    )
    store.record(decision)

    return decision, store


def _secret(tmp_path):
    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable=(
            "MATRIX_PROVIDER_X_API_KEY"
        ),
        secret_type="API_KEY",
    )
    registry = SQLiteSecretReferenceRegistry(
        tmp_path / "secret-refs.db"
    )
    registry.register(reference)
    return reference, registry


def test_authoritative_security_requires_all_durable_bindings(
    tmp_path,
    monkeypatch,
):
    preflight, preflight_store = _preflight(
        tmp_path
    )
    reference, registry = _secret(
        tmp_path
    )
    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    decision = (
        evaluate_authoritative_provider_security(
            run_id="run-1",
            sport="football",
            provider_key="provider-x",
            mode="PRODUCTION",
            preflight_decision=preflight,
            preflight_evidence_store=(
                preflight_store
            ),
            endpoint_url=(
                "https://api.provider.example/v1/history"
            ),
            secret_reference=reference,
            secret_reference_registry=registry,
        )
    )

    assert decision.status == "EXECUTE"
    assert decision.executable is True
    assert decision.preflight_evidence_id != "0" * 64
    assert (
        decision
        .secret_availability_attestation_fingerprint
        != "0" * 64
    )


def test_forged_in_memory_preflight_without_durable_evidence_quarantines(
    tmp_path,
    monkeypatch,
):
    preflight, _ = _preflight(tmp_path)
    empty_store = SQLiteProviderPreflightEvidenceStore(
        tmp_path / "empty-preflight.db"
    )
    reference, registry = _secret(tmp_path)
    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    decision = (
        evaluate_authoritative_provider_security(
            run_id="run-1",
            sport="football",
            provider_key="provider-x",
            mode="PRODUCTION",
            preflight_decision=preflight,
            preflight_evidence_store=empty_store,
            endpoint_url=(
                "https://api.provider.example/v1/history"
            ),
            secret_reference=reference,
            secret_reference_registry=registry,
        )
    )

    assert decision.status == "QUARANTINE"
    assert (
        "MISSING_DURABLE_PREFLIGHT_EVIDENCE"
        in decision.reason_codes
    )


def test_missing_runtime_secret_quarantines(
    tmp_path,
    monkeypatch,
):
    preflight, preflight_store = _preflight(
        tmp_path
    )
    reference, registry = _secret(tmp_path)
    monkeypatch.delenv(
        "MATRIX_PROVIDER_X_API_KEY",
        raising=False,
    )

    decision = (
        evaluate_authoritative_provider_security(
            run_id="run-1",
            sport="football",
            provider_key="provider-x",
            mode="PRODUCTION",
            preflight_decision=preflight,
            preflight_evidence_store=(
                preflight_store
            ),
            endpoint_url=(
                "https://api.provider.example/v1/history"
            ),
            secret_reference=reference,
            secret_reference_registry=registry,
        )
    )

    assert decision.status == "QUARANTINE"
    assert any(
        reason.startswith(
            "SECRET_RUNTIME_ERROR:"
        )
        for reason in decision.reason_codes
    )


def test_exact_endpoint_target_changes_security_fingerprint(
    tmp_path,
    monkeypatch,
):
    preflight, preflight_store = _preflight(
        tmp_path
    )
    reference, registry = _secret(tmp_path)
    monkeypatch.setenv(
        "MATRIX_PROVIDER_X_API_KEY",
        "runtime-only-value",
    )

    first = evaluate_authoritative_provider_security(
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        preflight_decision=preflight,
        preflight_evidence_store=preflight_store,
        endpoint_url=(
            "https://api.provider.example/v1/history"
        ),
        secret_reference=reference,
        secret_reference_registry=registry,
    )

    second = evaluate_authoritative_provider_security(
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="PRODUCTION",
        preflight_decision=preflight,
        preflight_evidence_store=preflight_store,
        endpoint_url=(
            "https://api.provider.example/v1/fixtures"
        ),
        secret_reference=reference,
        secret_reference_registry=registry,
    )

    assert (
        first.endpoint_target_fingerprint
        != second.endpoint_target_fingerprint
    )
    assert (
        first.decision_fingerprint
        != second.decision_fingerprint
    )
