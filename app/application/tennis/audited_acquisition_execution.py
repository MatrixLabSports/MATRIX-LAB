from app.core.audited_acquisition_execution import (
    execute_audited_acquisition_queue,
)


def execute_audited_tennis_acquisition_queue(
    *,
    queue_manifest,
    policy_fingerprint,
    audit_ledger,
    fetcher,
    raw_ledger,
    checkpoints,
    limits,
    clock,
    request_budget=None,
):
    if queue_manifest.get("sport") != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return execute_audited_acquisition_queue(
        queue_manifest=queue_manifest,
        policy_fingerprint=policy_fingerprint,
        audit_ledger=audit_ledger,
        fetcher=fetcher,
        raw_ledger=raw_ledger,
        checkpoints=checkpoints,
        limits=limits,
        clock=clock,
        request_budget=request_budget,
    )
