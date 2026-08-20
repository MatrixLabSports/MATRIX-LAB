def record_football_runtime_admission(
    *,
    decision,
    ledger,
):
    if decision.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
