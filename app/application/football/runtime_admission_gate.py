from app.core.authoritative_runtime_admission import (
    evaluate_authoritative_runtime_admission,
)


def evaluate_football_runtime_admission(
    *,
    report,
    audit_ledger,
    run_mode_evidence_store,
):
    return evaluate_authoritative_runtime_admission(
        report=report,
        audit_ledger=audit_ledger,
        run_mode_evidence_store=(
            run_mode_evidence_store
        ),
        expected_sport="football",
    )
