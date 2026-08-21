
from __future__ import annotations

from datetime import datetime

from app.core.canonical_identity_lifecycle import (
    CanonicalIdentityLifecycleEvent,
    SQLiteCanonicalIdentityLifecycleLedger,
)
from app.core.provider_identity_lifecycle import (
    SQLiteTemporalProviderIdentityLedger,
    TemporalProviderIdentityBinding,
)


def append_football_identity_alias(
    *,
    ledger: SQLiteCanonicalIdentityLifecycleLedger,
    canonical_id: str,
    entity_type: str,
    alias: str,
    effective_at: datetime,
    known_at: datetime,
    reason_code: str,
    previous_event_id: str | None = None,
) -> CanonicalIdentityLifecycleEvent:
    return ledger.append(
        ledger.build_event(
            sport="football",
            entity_type=entity_type,
            canonical_id=canonical_id,
            event_type="ALIAS_ADDED",
            effective_at=effective_at,
            known_at=known_at,
            reason_code=reason_code,
            human_reviewed=False,
            previous_event_id=previous_event_id,
            alias=alias,
        )
    )


def append_football_identity_rename(
    *,
    ledger: SQLiteCanonicalIdentityLifecycleLedger,
    canonical_id: str,
    entity_type: str,
    display_name: str,
    effective_at: datetime,
    known_at: datetime,
    reason_code: str,
    previous_event_id: str | None,
    human_reviewed: bool,
) -> CanonicalIdentityLifecycleEvent:
    return ledger.append(
        ledger.build_event(
            sport="football",
            entity_type=entity_type,
            canonical_id=canonical_id,
            event_type="DISPLAY_NAME_CHANGED",
            effective_at=effective_at,
            known_at=known_at,
            reason_code=reason_code,
            human_reviewed=human_reviewed,
            previous_event_id=previous_event_id,
            display_name=display_name,
        )
    )


def append_football_identity_supersession(
    *,
    ledger: SQLiteCanonicalIdentityLifecycleLedger,
    canonical_id: str,
    superseded_by_canonical_id: str,
    entity_type: str,
    effective_at: datetime,
    known_at: datetime,
    reason_code: str,
    previous_event_id: str | None,
    human_reviewed: bool,
) -> CanonicalIdentityLifecycleEvent:
    return ledger.append(
        ledger.build_event(
            sport="football",
            entity_type=entity_type,
            canonical_id=canonical_id,
            event_type="SUPERSEDED",
            effective_at=effective_at,
            known_at=known_at,
            reason_code=reason_code,
            human_reviewed=human_reviewed,
            previous_event_id=previous_event_id,
            superseded_by_canonical_id=(
                superseded_by_canonical_id
            ),
        )
    )


def append_football_temporal_provider_binding(
    *,
    ledger: SQLiteTemporalProviderIdentityLedger,
    entity_type: str,
    provider_key: str,
    provider_entity_id: str,
    canonical_id: str,
    valid_from: datetime,
    valid_to: datetime | None,
    known_at: datetime,
    resolution_method: str,
    reason_code: str,
    human_reviewed: bool,
    predecessor_binding_id: str | None = None,
    corrects_binding_id: str | None = None,
) -> TemporalProviderIdentityBinding:
    return ledger.append(
        ledger.build_binding(
            sport="football",
            entity_type=entity_type,
            provider_key=provider_key,
            provider_entity_id=provider_entity_id,
            canonical_id=canonical_id,
            valid_from=valid_from,
            valid_to=valid_to,
            known_at=known_at,
            resolution_method=resolution_method,
            reason_code=reason_code,
            human_reviewed=human_reviewed,
            predecessor_binding_id=(
                predecessor_binding_id
            ),
            corrects_binding_id=(
                corrects_binding_id
            ),
        )
    )


def remap_football_provider_identity(
    *,
    ledger: SQLiteTemporalProviderIdentityLedger,
    entity_type: str,
    provider_key: str,
    provider_entity_id: str,
    new_canonical_id: str,
    remap_at: datetime,
    known_at: datetime,
    resolution_method: str,
    reason_code: str,
    human_reviewed: bool,
) -> tuple[
    TemporalProviderIdentityBinding,
    TemporalProviderIdentityBinding,
]:
    return ledger.remap(
        sport="football",
        entity_type=entity_type,
        provider_key=provider_key,
        provider_entity_id=provider_entity_id,
        new_canonical_id=new_canonical_id,
        remap_at=remap_at,
        known_at=known_at,
        resolution_method=resolution_method,
        reason_code=reason_code,
        human_reviewed=human_reviewed,
    )


def resolve_football_provider_terminal_canonical_as_of(
    *,
    provider_ledger: SQLiteTemporalProviderIdentityLedger,
    canonical_lifecycle_ledger: SQLiteCanonicalIdentityLifecycleLedger,
    entity_type: str,
    provider_key: str,
    provider_entity_id: str,
    as_of: datetime,
    event_time: datetime,
) -> str | None:
    binding = provider_ledger.resolve_as_of(
        sport="football",
        entity_type=entity_type,
        provider_key=provider_key,
        provider_entity_id=provider_entity_id,
        as_of=as_of,
        event_time=event_time,
    )

    if binding is None:
        return None

    return canonical_lifecycle_ledger.resolve_terminal_canonical_id_as_of(
        canonical_id=binding.canonical_id,
        as_of=as_of,
        event_time=event_time,
    )
