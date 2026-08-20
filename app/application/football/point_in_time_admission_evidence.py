def record_football_point_in_time_admission(
    *,
    decision,
    ledger,
):
    if decision.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
