from types import SimpleNamespace

from app.core.provider_security_gate import (
    evaluate_provider_security,
)
from app.core.secret_reference import (
    build_secret_reference,
)


def preflight(
    *,
    status="EXECUTE",
    executable=True,
):
    return SimpleNamespace(
        status=status,
        executable=executable,
        run_id="run-1",
        sport="tennis",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        decision_fingerprint=(
            "a" * 64
        ),
    )


def test_security_gate_allows_only_bound_secure_preflight():
    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable=(
            "MATRIX_PROVIDER_X_API_KEY"
        ),
        secret_type="API_KEY",
    )

    decision = (
        evaluate_provider_security(
            run_id="run-1",
            sport="tennis",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            preflight_decision=(
                preflight()
            ),
            endpoint_url=(
                "https://api.provider.example/v1"
            ),
            secret_reference=reference,
        )
    )

    assert (
        decision.status
        == "EXECUTE"
    )
    assert (
        decision.executable
        is True
    )


def test_security_gate_rejects_non_executable_preflight():
    reference = build_secret_reference(
        provider_key="provider-x",
        environment_variable=(
            "MATRIX_PROVIDER_X_API_KEY"
        ),
        secret_type="API_KEY",
    )

    decision = (
        evaluate_provider_security(
            run_id="run-1",
            sport="tennis",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            preflight_decision=preflight(
                status="QUARANTINE",
                executable=False,
            ),
            endpoint_url=(
                "https://api.provider.example/v1"
            ),
            secret_reference=reference,
        )
    )

    assert (
        decision.status
        == "QUARANTINE"
    )
    assert (
        "PREFLIGHT_NOT_EXECUTABLE"
        in decision.reason_codes
    )
