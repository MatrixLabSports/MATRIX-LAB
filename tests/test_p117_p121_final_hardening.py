from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.controlled_network_certification import (
    certify_controlled_network_boundary,
)
from app.core.governed_provider_http import (
    SQLiteProviderNetworkCallEvidenceStore,
)
from app.core.governed_provider_request import (
    JitSecretPinnedHttpsTransport,
)
from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_network_execution_authorization import (
    SQLiteProviderNetworkPermitStore,
)
from app.core.provider_request_contract import (
    RequestParameterRule,
    SQLiteProviderRequestContractRegistry,
    build_provider_request_contract,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.governed_client import (
    build_governed_api_football_client,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def test_request_authorization_changes_when_query_value_changes(
    tmp_path,
):
    reference = build_secret_reference(
        provider_key="api_football",
        environment_variable="MATRIX_TEST_API_KEY",
        secret_type="API_KEY",
    )
    registry = SQLiteProviderRequestContractRegistry(
        tmp_path / "contracts.db"
    )
    contract = build_provider_request_contract(
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        parameter_rules=(
            RequestParameterRule(
                name="date",
                value_type="DATE",
                required=True,
            ),
        ),
        auth_header_name="x-apisports-key",
        secret_reference_fingerprint=reference.reference_fingerprint,
        valid_from=NOW,
    )
    registry.register(contract)

    one = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        params={"date": "2026-08-20"},
        secret_reference_fingerprint=reference.reference_fingerprint,
        now=NOW,
    )
    two = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        params={"date": "2026-08-21"},
        secret_reference_fingerprint=reference.reference_fingerprint,
        now=NOW,
    )

    assert one.parameter_names == two.parameter_names == ("date",)
    assert (
        one.parameter_values_fingerprint
        != two.parameter_values_fingerprint
    )
    assert (
        one.authorization_fingerprint
        != two.authorization_fingerprint
    )
    assert "2026-08-20" not in repr(one.payload())


def test_official_production_provider_path_has_no_legacy_client():
    source = Path(
        "app/providers/api_football/governed_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "ApiFootballClient" not in source
    assert "app.providers.api_football.client" not in source
    assert "GovernedProviderRequestClient" in source
    assert "JitSecretPinnedHttpsTransport" in source
    assert "BindingAuditPinnedHttpsTransport" in source
    assert "require_real_provider_execution_authorized" in source


def test_real_provider_execution_gate_is_executable_and_false(
    tmp_path,
):
    reference = build_secret_reference(
        provider_key="api_football",
        environment_variable="MATRIX_TEST_API_KEY",
        secret_type="API_KEY",
    )
    base = StdlibPinnedHttpsTransport()
    jit = JitSecretPinnedHttpsTransport(
        inner=base,
        secret_reference=reference,
        auth_header_name="x-apisports-key",
        resolver=lambda ref: "not-used",
    )
    binding_store = SQLiteProviderNetworkBindingEvidenceStore(
        tmp_path / "binding.db"
    )
    transport = BindingAuditPinnedHttpsTransport(
        inner=jit,
        binding_store=binding_store,
        collector=ProviderNetworkBindingCollector(),
        clock=lambda: NOW,
    )
    certification = certify_controlled_network_boundary(
        transport=transport,
        request_contract_registry=SQLiteProviderRequestContractRegistry(
            tmp_path / "cert-contracts.db"
        ),
        binding_store=binding_store,
        network_permit_store=SQLiteProviderNetworkPermitStore(
            tmp_path / "permits.db"
        ),
        network_call_evidence_store=SQLiteProviderNetworkCallEvidenceStore(
            tmp_path / "calls.db"
        ),
    )

    with pytest.raises(
        ValueError,
        match="REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED",
    ):
        build_governed_api_football_client(
            config=SimpleNamespace(
                base_url="https://api.example.test",
                timeout_seconds=5,
            ),
            authority=SimpleNamespace(
                mode="PRODUCTION"
            ),
            network_permit_store=None,
            call_evidence_store=None,
            clock=lambda: NOW,
            pinned_transport=base,
            network_certification=certification,
        )


def test_ci_explicitly_quarantines_legacy_bootstrap_path():
    ci = Path(
        "scripts/matrix_ci_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    governed = Path(
        "app/providers/api_football/governed_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    bootstrap = Path(
        "app/providers/api_football/bootstrap_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "OFFICIAL_PROVIDER_LEGACY_BYPASS" in ci
    assert "BOOTSTRAP_PROVIDER_CLIENT_IMPORT" in ci
    assert "bootstrap_client.py" in ci
    assert "app.providers.api_football.client" not in governed
    assert "app.providers.api_football.client" in bootstrap
    assert "BOOTSTRAP_PROBE" in bootstrap
