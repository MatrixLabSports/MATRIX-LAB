def record_tennis_runtime_admission(
    *,
    decision,
    ledger,
):
    if decision.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
