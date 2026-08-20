def record_tennis_provider_health_decision(
    *,
    decision,
    ledger,
):
    if decision.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
