from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.football.live_evidence import (
    FootballLiveEvidence,
    SQLiteFootballLiveEvidenceStore,
)
from app.application.football.live_snapshot import (
    FootballLivePressureFeatures,
    FootballLiveSnapshot,
    derive_live_pressure_features,
    snapshot_from_api_football_bundle,
)
from app.core.governed_provider_request import (
    GovernedProviderRequestClient,
)
from app.core.platform_scope import (
    PRIVATE_INTERNAL_ONLY,
    PlatformScope,
    require_private_internal_only,
)
from app.providers.api_football.live_service import (
    ApiFootballLiveBundle,
    fetch_api_football_live_bundle,
)


@dataclass(frozen=True)
class PrivateFootballLiveResult:
    scope_id: str
    snapshot: FootballLiveSnapshot
    pressure_features: FootballLivePressureFeatures
    evidence: FootballLiveEvidence | None
    real_provider_execution_authorized_by_this_module: bool = False
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False


def evaluate_private_live_bundle(
    *,
    bundle: ApiFootballLiveBundle,
    evidence_store: (
        SQLiteFootballLiveEvidenceStore
        | None
    ) = None,
    scope: PlatformScope = (
        PRIVATE_INTERNAL_ONLY
    ),
) -> PrivateFootballLiveResult:
    verified_scope = (
        require_private_internal_only(
            scope
        )
    )
    snapshot = (
        snapshot_from_api_football_bundle(
            bundle
        )
    )
    features = (
        derive_live_pressure_features(
            snapshot
        )
    )
    evidence = (
        evidence_store.record(
            snapshot=snapshot,
            pressure_features=features,
        )
        if evidence_store is not None
        else None
    )

    return PrivateFootballLiveResult(
        scope_id=verified_scope.scope_id,
        snapshot=snapshot,
        pressure_features=features,
        evidence=evidence,
    )


def capture_private_live_once(
    *,
    governed_client: Any,
    fixture_id: int | str,
    evidence_store: (
        SQLiteFootballLiveEvidenceStore
        | None
    ) = None,
    include_live_odds: bool = True,
    scope: PlatformScope = (
        PRIVATE_INTERNAL_ONLY
    ),
) -> PrivateFootballLiveResult:
    # This function does not construct or authorize a provider client.
    # The caller must supply a client that already passed MATRIX network,
    # request-contract, rights, readiness and rehearsal gates.
    require_private_internal_only(
        scope
    )
    if not isinstance(
        governed_client,
        GovernedProviderRequestClient,
    ):
        raise ValueError(
            "GOVERNED_PROVIDER_REQUEST_CLIENT_REQUIRED"
        )
    bundle = fetch_api_football_live_bundle(
        client=governed_client,
        fixture_id=fixture_id,
        include_live_odds=include_live_odds,
    )
    return evaluate_private_live_bundle(
        bundle=bundle,
        evidence_store=evidence_store,
        scope=scope,
    )
