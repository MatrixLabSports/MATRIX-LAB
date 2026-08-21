from datetime import datetime, timezone

import pytest

from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
)
from app.core.provider_network_binding import (
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.request_contracts import (
    build_api_football_request_contracts,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowRuntime,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def runtime(tmp_path, *, mode="SHADOW"):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable="MATRIX_TEST_API_KEY",
        secret_type="API_KEY",
    )

    contracts = build_api_football_request_contracts(
        secret_reference_fingerprint=(
            secret.reference_fingerprint
        ),
        valid_from=NOW,
    )

    endpoint_ids = {
        name: (
            f"{index:064x}"
        )
        for index, name
        in enumerate(
            sorted(contracts),
            1,
        )
    }

    return ApiFootballShadowRuntime(
        mode=mode,
        base_url=(
            "https://api.example.test"
        ),
        registry=(
            SQLiteProviderRequestContractRegistry(
                tmp_path / "contracts.db"
            )
        ),
        contract_endpoint_binding_store=(
            SQLiteProviderContractEndpointBindingStore(
                tmp_path / "endpoint-bindings.db"
            )
        ),
        endpoint_manifest_ids=endpoint_ids,
        binding_store=(
            SQLiteProviderNetworkBindingEvidenceStore(
                tmp_path / "network-bindings.db"
            )
        ),
        attempt_intent_store=(
            SQLiteProviderAttemptIntentStore(
                tmp_path / "attempt-intents.db"
            )
        ),
        secret_reference=secret,
        clock=lambda: NOW,
        valid_from=NOW,
        rights_decision=None,
    )


def test_shadow_runtime_exercises_governed_request_control_plane_without_network(
    tmp_path,
):
    shadow = runtime(
        tmp_path
    )

    assert (
        shadow.readiness.governed_request_client_verified
        is True
    )
    assert (
        shadow.readiness.governed_transport_topology_verified
        is True
    )
    assert (
        shadow.readiness.network_authority_type_verified
        is True
    )
    assert (
        shadow.readiness.external_network_allowed
        is False
    )

    preview = shadow.preview(
        contract_name="fixtures_by_date",
        params={
            "date": "2026-08-20",
            "league": 39,
            "season": 2026,
        },
    )

    assert (
        preview.governed_request_client_used
        is True
    )
    assert (
        preview.governed_transport_topology_verified
        is True
    )
    assert (
        preview.network_call_performed
        is False
    )
    assert (
        preview.network_permit_issued
        is False
    )
    assert preview.secret_resolved is False


def test_shadow_request_values_change_authorization_fingerprint(
    tmp_path,
):
    shadow = runtime(
        tmp_path
    )

    one = shadow.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )
    two = shadow.preview(
        contract_name="fixture_by_id",
        params={"id": 101},
    )

    assert (
        one.authorization_fingerprint
        != two.authorization_fingerprint
    )


def test_shadow_runtime_refuses_production_mode(
    tmp_path,
):
    with pytest.raises(
        ValueError,
        match="INVALID_SHADOW_RUNTIME_MODE",
    ):
        runtime(
            tmp_path,
            mode="PRODUCTION",
        )
