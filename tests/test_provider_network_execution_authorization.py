from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.provider_network_execution_authorization import (
    ProviderNetworkAuthority,
    SQLiteProviderNetworkPermitStore,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


class EndpointRegistry:
    def authorize_request(self, **kwargs):
        return SimpleNamespace(
            status="AUTHORIZED",
            executable=True,
            manifest_id="1" * 64,
            decision_fingerprint="2" * 64,
        )


class SecurityEvidence:
    def record(self, decision):
        return "3" * 64


class ExecutionPermit:
    def payload(self):
        return {"status": "AUTHORIZED", "fingerprint": "4" * 64}


def test_authority_binds_existing_governance_and_one_use_permit(
    tmp_path,
    monkeypatch,
):
    module = __import__(
        "app.core.provider_network_execution_authorization",
        fromlist=["x"],
    )

    monkeypatch.setattr(
        module,
        "verify_provider_execution_authorization",
        lambda **kwargs: ExecutionPermit(),
    )
    monkeypatch.setattr(
        module,
        "evaluate_authoritative_provider_security",
        lambda **kwargs: SimpleNamespace(
            status="EXECUTE",
            executable=True,
            decision_fingerprint="5" * 64,
        ),
    )

    store = SQLiteProviderNetworkPermitStore(tmp_path / "permit.db")

    authority = ProviderNetworkAuthority(
        run_id="run-1",
        sport="football",
        provider_key="api_football",
        mode="PRODUCTION",
        queue_manifest={"sport": "football"},
        scheduling_authorization_fingerprint="6" * 64,
        scheduling_evidence_ledger=object(),
        health_evidence_ledger=object(),
        preflight_decision=SimpleNamespace(
            status="EXECUTE",
            executable=True,
            run_id="run-1",
            sport="football",
            provider_key="api_football",
            mode="PRODUCTION",
        ),
        preflight_evidence_store=object(),
        security_evidence_store=SecurityEvidence(),
        endpoint_registry=EndpointRegistry(),
        secret_reference=object(),
        secret_reference_fingerprint="7" * 64,
        secret_reference_registry=object(),
        network_permit_store=store,
        clock=lambda: NOW,
        resolver=lambda host, port: ("8.8.8.8",),
    )

    permit = authority.authorize(
        request_nonce="call-1",
        method="GET",
        endpoint_url="https://api.example.test/v3/fixtures",
        query_keys=("date",),
    )

    store.consume(permit_id=permit.permit_id, consumed_at=NOW)

    try:
        store.consume(permit_id=permit.permit_id, consumed_at=NOW)
    except ValueError as error:
        assert str(error) == "NETWORK_PERMIT_ALREADY_CONSUMED"
    else:
        raise AssertionError("permit must be one-use")
