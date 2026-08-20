def record_football_provider_health_decision(
    *,
    decision,
    ledger,
):
    if decision.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
