from __future__ import annotations

from app.core.runtime_admission_gate import evaluate_reconciled_runtime_admission


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
