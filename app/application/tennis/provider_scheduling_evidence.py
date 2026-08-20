def record_tennis_provider_scheduling_authorization(
    *,
    authorization,
    scheduling_evidence_ledger,
    health_evidence_ledger,
):
    if authorization.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return scheduling_evidence_ledger.record_authorization(
        authorization=authorization,
        health_evidence_ledger=health_evidence_ledger,
    )
