def append_tennis_canonical_observation(
    *,
    store,
    record,
    decision,
    admission_evidence_ledger,
):
    if record.sport != "tennis" or decision.sport != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=admission_evidence_ledger,
    )
