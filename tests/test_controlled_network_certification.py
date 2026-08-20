from datetime import datetime, timezone

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
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    build_secret_reference,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def test_technical_certification_is_fail_closed_for_real_provider(
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
        request_contract_registry=(
            SQLiteProviderRequestContractRegistry(
                tmp_path / "contracts.db"
            )
        ),
        binding_store=binding_store,
        network_permit_store=(
            SQLiteProviderNetworkPermitStore(
                tmp_path / "permits.db"
            )
        ),
        network_call_evidence_store=(
            SQLiteProviderNetworkCallEvidenceStore(
                tmp_path / "calls.db"
            )
        ),
    )

    assert (
        certification.status
        == "TECHNICALLY_CERTIFIED_FAIL_CLOSED"
    )
    assert certification.pinned_tls_transport is True
    assert certification.default_production_transport is True
    assert certification.jit_secret_resolution is True
    assert (
        certification.real_provider_execution_authorized
        is False
    )


def test_injected_nondefault_transport_cannot_receive_technical_certification(
    tmp_path,
):
    reference = build_secret_reference(
        provider_key="api_football",
        environment_variable="MATRIX_TEST_API_KEY",
        secret_type="API_KEY",
    )

    base = StdlibPinnedHttpsTransport(
        connector=lambda *args: None,
    )
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
        request_contract_registry=(
            SQLiteProviderRequestContractRegistry(
                tmp_path / "contracts.db"
            )
        ),
        binding_store=binding_store,
        network_permit_store=(
            SQLiteProviderNetworkPermitStore(
                tmp_path / "permits.db"
            )
        ),
        network_call_evidence_store=(
            SQLiteProviderNetworkCallEvidenceStore(
                tmp_path / "calls.db"
            )
        ),
    )

    assert certification.status == "NOT_CERTIFIED"
    assert certification.default_production_transport is False
    assert (
        certification.real_provider_execution_authorized
        is False
    )
