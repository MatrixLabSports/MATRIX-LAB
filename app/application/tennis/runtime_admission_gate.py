from app.core.runtime_admission_gate import (
    evaluate_reconciled_runtime_admission,
)


def evaluate_tennis_runtime_admission(
    *,
    report,
    audit_ledger,
):
    return evaluate_reconciled_runtime_admission(
        report=report,
        audit_ledger=audit_ledger,
        expected_sport="tennis",
    )
