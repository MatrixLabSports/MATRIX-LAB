from datetime import datetime, timezone

import pytest

from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.providers.api_football.request_contracts import (
    register_api_football_contract_endpoint_bindings,
    register_api_football_request_contracts,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def test_api_football_contracts_cross_bind_endpoint_manifest(
    tmp_path,
):
    request_registry = (
        SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        )
    )

    contracts = register_api_football_request_contracts(
        registry=request_registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    endpoint_manifest_ids = {
        name: (
            f"{index:064x}"
        )
        for index, name
        in enumerate(
            sorted(contracts),
            1,
        )
    }

    binding_registry = (
        SQLiteProviderContractEndpointBindingStore(
            tmp_path / "bindings.db"
        )
    )

    bindings = (
        register_api_football_contract_endpoint_bindings(
            contracts=contracts,
            endpoint_manifest_ids=(
                endpoint_manifest_ids
            ),
            registry=binding_registry,
            valid_from=NOW,
        )
    )

    fixture = bindings[
        "fixtures_by_date"
    ]

    verified = binding_registry.authorize(
        request_contract_id=(
            fixture.request_contract_id
        ),
        endpoint_manifest_id=(
            fixture.endpoint_manifest_id
        ),
        path=fixture.path,
        now=NOW,
    )

    assert verified == fixture
    assert (
        binding_registry.audit_integrity()
        is True
    )


def test_contract_endpoint_binding_rejects_manifest_mismatch(
    tmp_path,
):
    request_registry = (
        SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        )
    )

    contracts = register_api_football_request_contracts(
        registry=request_registry,
        secret_reference_fingerprint="1" * 64,
        valid_from=NOW,
    )

    endpoint_manifest_ids = {
        name: (
            f"{index:064x}"
        )
        for index, name
        in enumerate(
            sorted(contracts),
            1,
        )
    }

    binding_registry = (
        SQLiteProviderContractEndpointBindingStore(
            tmp_path / "bindings.db"
        )
    )

    bindings = (
        register_api_football_contract_endpoint_bindings(
            contracts=contracts,
            endpoint_manifest_ids=(
                endpoint_manifest_ids
            ),
            registry=binding_registry,
            valid_from=NOW,
        )
    )

    fixture = bindings[
        "fixture_by_id"
    ]

    with pytest.raises(
        ValueError,
        match=(
            "CONTRACT_ENDPOINT_BINDING_MISMATCH"
        ),
    ):
        binding_registry.authorize(
            request_contract_id=(
                fixture.request_contract_id
            ),
            endpoint_manifest_id=(
                "f" * 64
            ),
            path=fixture.path,
            now=NOW,
        )
