def append_football_provider_identity_mapping(
    *,
    ledger,
    provider_key,
    provider_entity_id,
    canonical_id,
    entity_type,
    resolution_method,
    observed_at,
    available_at,
):
    mapping = ledger.build_mapping(
        sport="football",
        entity_type=entity_type,
        provider_key=provider_key,
        provider_entity_id=provider_entity_id,
        canonical_id=canonical_id,
        resolution_method=resolution_method,
        observed_at=observed_at,
        available_at=available_at,
    )
    return ledger.append(mapping)
