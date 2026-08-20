def record_tennis_point_in_time_admission(
    *,
    decision,
    ledger,
):
    if decision.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")
    return ledger.record_decision(decision)
