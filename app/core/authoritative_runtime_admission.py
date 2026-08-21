from __future__ import annotations

from app.core.runtime_admission_gate import evaluate_reconciled_runtime_admission
from app.core.provider_activation_readiness import (
    ProviderActivationReadinessCertification,
    verify_provider_activation_readiness_certification,
)
from app.core.provider_activation_rehearsal import (
    ProviderActivationRehearsalCertification,
    verify_provider_activation_rehearsal_certification,
)


def evaluate_authoritative_runtime_admission(
    *,
    report,
    audit_ledger,
    run_mode_evidence_store,
    expected_sport: str | None = None,
):
    run_id = getattr(report, "run_id", None)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("RUNTIME_REPORT_RUN_ID_REQUIRED")

    mode_evidence = run_mode_evidence_store.get_verified(run_id)
    if mode_evidence is None:
        raise ValueError("RUN_MODE_EVIDENCE_REQUIRED")
    if expected_sport is not None and mode_evidence.sport != expected_sport:
        raise ValueError("RUN_MODE_SPORT_MISMATCH")
    if mode_evidence.mode != "PRODUCTION":
        raise ValueError("BOOTSTRAP_RUNTIME_ADMISSION_FORBIDDEN")

    return evaluate_reconciled_runtime_admission(
        report=report,
        audit_ledger=audit_ledger,
        expected_sport=expected_sport,
    )


def evaluate_authoritative_provider_runtime_admission(
    *,
    report,
    audit_ledger,
    run_mode_evidence_store,
    activation_readiness_certification: (
        ProviderActivationReadinessCertification
    ),
    activation_rehearsal_certification: (
        ProviderActivationRehearsalCertification
    ),
    expected_sport: str | None = None,
):
    readiness = (
        verify_provider_activation_readiness_certification(
            activation_readiness_certification
        )
    )
    rehearsal = (
        verify_provider_activation_rehearsal_certification(
            activation_rehearsal_certification
        )
    )

    if (
        readiness.status
        != "TECHNICALLY_READY_RIGHTS_BLOCKED"
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_READINESS_REQUIRED"
        )

    if (
        rehearsal.status
        != "REHEARSAL_CERTIFIED_FAIL_CLOSED"
    ):
        raise ValueError(
            "PROVIDER_ACTIVATION_REHEARSAL_REQUIRED"
        )

    if (
        readiness.real_provider_execution_authorized
        is not True
        or rehearsal.real_provider_execution_authorized
        is not True
    ):
        raise ValueError(
            "REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED"
        )

    return evaluate_authoritative_runtime_admission(
        report=report,
        audit_ledger=audit_ledger,
        run_mode_evidence_store=(
            run_mode_evidence_store
        ),
        expected_sport=(
            expected_sport
        ),
    )
