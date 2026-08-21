from __future__ import annotations

from datetime import datetime, timezone

from app.application.football.identity_lifecycle import (
    append_football_identity_supersession,
    append_football_temporal_provider_binding,
    resolve_football_provider_terminal_canonical_as_of,
)
from app.application.tennis.identity_lifecycle import (
    append_tennis_identity_supersession,
    append_tennis_temporal_provider_binding,
    resolve_tennis_provider_terminal_canonical_as_of,
)
from app.core.canonical_identity import SQLiteCanonicalIdentityRegistry
from app.core.canonical_identity_lifecycle import SQLiteCanonicalIdentityLifecycleLedger
from app.core.provider_identity_lifecycle import SQLiteTemporalProviderIdentityLedger

UTC = timezone.utc


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 12, tzinfo=UTC)


def test_football_provider_resolution_composes_known_canonical_supersession(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(tmp_path / "canonical.db")
    first = registry.build_entity(
        sport="football", entity_type="team", canonical_key="TEAM:F:V6:A", display_name="A"
    )
    second = registry.build_entity(
        sport="football", entity_type="team", canonical_key="TEAM:F:V6:B", display_name="B"
    )
    registry.register(first)
    registry.register(second)
    lifecycle = SQLiteCanonicalIdentityLifecycleLedger(
        tmp_path / "identity.db", identity_registry=registry
    )
    provider = SQLiteTemporalProviderIdentityLedger(
        tmp_path / "provider.db", identity_registry=registry
    )
    append_football_identity_supersession(
        ledger=lifecycle,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="team",
        effective_at=at(5),
        known_at=at(6),
        reason_code="VERIFIED_DUPLICATE",
        previous_event_id=None,
        human_reviewed=True,
    )
    append_football_temporal_provider_binding(
        ledger=provider,
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-1",
        canonical_id=first.canonical_id,
        valid_from=at(10),
        valid_to=None,
        known_at=at(10),
        resolution_method="manual_verified",
        reason_code="PROVIDER_MAPPING",
        human_reviewed=True,
    )
    raw = provider.resolve_as_of(
        sport="football",
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-1",
        as_of=at(10),
        event_time=at(10),
    )
    assert raw is not None
    assert raw.canonical_id == first.canonical_id
    terminal = resolve_football_provider_terminal_canonical_as_of(
        provider_ledger=provider,
        canonical_lifecycle_ledger=lifecycle,
        entity_type="team",
        provider_key="provider-a",
        provider_entity_id="team-1",
        as_of=at(10),
        event_time=at(10),
    )
    assert terminal == second.canonical_id


def test_tennis_provider_resolution_composes_known_canonical_supersession(tmp_path):
    registry = SQLiteCanonicalIdentityRegistry(tmp_path / "canonical.db")
    first = registry.build_entity(
        sport="tennis", entity_type="player", canonical_key="PLAYER:T:V6:A", display_name="A"
    )
    second = registry.build_entity(
        sport="tennis", entity_type="player", canonical_key="PLAYER:T:V6:B", display_name="B"
    )
    registry.register(first)
    registry.register(second)
    lifecycle = SQLiteCanonicalIdentityLifecycleLedger(
        tmp_path / "identity.db", identity_registry=registry
    )
    provider = SQLiteTemporalProviderIdentityLedger(
        tmp_path / "provider.db", identity_registry=registry
    )
    append_tennis_identity_supersession(
        ledger=lifecycle,
        canonical_id=first.canonical_id,
        superseded_by_canonical_id=second.canonical_id,
        entity_type="player",
        effective_at=at(5),
        known_at=at(6),
        reason_code="VERIFIED_DUPLICATE",
        previous_event_id=None,
        human_reviewed=True,
    )
    append_tennis_temporal_provider_binding(
        ledger=provider,
        entity_type="player",
        provider_key="provider-t",
        provider_entity_id="player-1",
        canonical_id=first.canonical_id,
        valid_from=at(10),
        valid_to=None,
        known_at=at(10),
        resolution_method="manual_verified",
        reason_code="PROVIDER_MAPPING",
        human_reviewed=True,
    )
    terminal = resolve_tennis_provider_terminal_canonical_as_of(
        provider_ledger=provider,
        canonical_lifecycle_ledger=lifecycle,
        entity_type="player",
        provider_key="provider-t",
        provider_entity_id="player-1",
        as_of=at(10),
        event_time=at(10),
    )
    assert terminal == second.canonical_id
