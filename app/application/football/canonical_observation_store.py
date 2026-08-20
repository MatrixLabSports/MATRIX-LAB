def append_football_canonical_observation(
    *,
    store,
    record,
    decision,
    admission_evidence_ledger,
):
    if record.sport != "football" or decision.sport != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return store.append_admitted_record(
        record=record,
        decision=decision,
        admission_evidence_ledger=admission_evidence_ledger,
    )
