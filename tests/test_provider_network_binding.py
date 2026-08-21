from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.governed_provider_http import (
    MatrixPinnedHttpsTransport,
)
from app.core.provider_call_audit import (
    ProviderCallAuditFetcher,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
    build_provider_network_binding_evidence,
    reconcile_provider_network_bindings,
)
from app.core.provider_request_contract import (
    RequestParameterRule,
    SQLiteProviderRequestContractRegistry,
    build_provider_request_contract,
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


class Inner(MatrixPinnedHttpsTransport):
    def get_pinned(self, **kwargs):
        return "ok"


def _contract(tmp_path):
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
    decision = registry.authorize(
        contract_id=contract.contract_id,
        provider_key="api_football",
        sport="football",
        method="GET",
        path="/v3/fixtures",
        params={"date": "2026-08-20"},
        secret_reference_fingerprint=reference.reference_fingerprint,
        now=NOW,
    )
    return reference, registry, contract, decision


def test_binding_evidence_self_binds_queue_contract_and_values(
    tmp_path,
):
    reference, _, contract, decision = _contract(tmp_path)
    collector = ProviderNetworkBindingCollector()
    collector.begin("a" * 64)

    store = SQLiteProviderNetworkBindingEvidenceStore(
        tmp_path / "binding.db"
    )
    transport = BindingAuditPinnedHttpsTransport(
        inner=Inner(),
        binding_store=store,
        collector=collector,
        clock=lambda: NOW,
    )

    permit = SimpleNamespace(
        run_id="b" * 64,
        provider_key="api_football",
        permit_id="c" * 64,
        endpoint_manifest_id="d" * 64,
        security_evidence_id="e" * 64,
    )

    assert transport.get_pinned(
        url="https://api.example.test/v3/fixtures",
        original_host="api.example.test",
        resolved_ips=("8.8.8.8",),
        allow_redirects=False,
        verify=True,
        matrix_permit=permit,
        matrix_request_contract_id=contract.contract_id,
        matrix_request_contract_fingerprint=decision.authorization_fingerprint,
        matrix_request_path="/v3/fixtures",
        matrix_request_parameter_names=decision.parameter_names,
        matrix_request_parameter_values_fingerprint=(
            decision.parameter_values_fingerprint
        ),
        matrix_request_secret_reference_fingerprint=(
            reference.reference_fingerprint
        ),
    ) == "ok"

    evidence_ids = collector.finish("a" * 64)
    evidence = store.get_verified(evidence_ids[0])

    assert evidence is not None
    assert evidence.queue_item_fingerprint == "a" * 64
    assert evidence.request_contract_id == contract.contract_id
    assert (
        evidence.request_parameter_values_fingerprint
        == decision.parameter_values_fingerprint
    )
    assert store.audit_integrity() is True


class FakeAuditLedger:
    def __init__(self):
        self.events = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)


class FakeFetcher:
    def fetch(self, queue_item):
        return {"ok": True}


class FakeCollector:
    def begin(self, queue_item_fingerprint):
        self.queue_item_fingerprint = queue_item_fingerprint

    def finish(self, queue_item_fingerprint):
        assert queue_item_fingerprint == self.queue_item_fingerprint
        return ("1" * 64,)


def test_p63_terminal_event_carries_network_binding_ids():
    ledger = FakeAuditLedger()
    fetcher = ProviderCallAuditFetcher(
        fetcher=FakeFetcher(),
        audit_ledger=ledger,
        run_id="2" * 64,
        clock=lambda: NOW,
        network_binding_collector=FakeCollector(),
    )

    assert fetcher.fetch(
        {
            "provider_key": "api_football",
            "queue_item_fingerprint": "3" * 64,
            "estimated_request_cost": 1,
        }
    ) == {"ok": True}

    terminal = ledger.events[-1]["event_payload"]
    assert terminal["network_binding_evidence_ids"] == [
        "1" * 64
    ]


class FakePermitStore:
    def __init__(self, payload):
        self.payload = payload

    def audit_integrity(self):
        return True

    def get_verified(self, permit_id):
        assert permit_id == self.payload["permit_id"]
        return dict(self.payload)


class FakeNetworkCallEvidenceStore:
    def audit_integrity(self):
        return True

    def list_verified_events_for_permit(self, permit_id):
        return (
            {
                "permit_id": permit_id,
                "event_type": "NETWORK_CALL_STARTED",
                "run_id": "4" * 64,
                "provider_key": "api_football",
                "endpoint_manifest_id": "6" * 64,
            },
            {
                "permit_id": permit_id,
                "event_type": "NETWORK_CALL_COMPLETED",
                "run_id": "4" * 64,
                "provider_key": "api_football",
                "endpoint_manifest_id": "6" * 64,
            },
        )


def test_network_reconciliation_rederives_contract_and_consumed_permit(
    tmp_path,
):
    reference, registry, contract, decision = _contract(tmp_path)

    store = SQLiteProviderNetworkBindingEvidenceStore(
        tmp_path / "binding-reconcile.db"
    )
    evidence = build_provider_network_binding_evidence(
        run_id="4" * 64,
        provider_key="api_football",
        queue_item_fingerprint="9" * 64,
        permit_id="5" * 64,
        endpoint_manifest_id="6" * 64,
        security_evidence_id="7" * 64,
        request_contract_id=contract.contract_id,
        request_contract_fingerprint=decision.authorization_fingerprint,
        request_path="/v3/fixtures",
        request_parameter_names=decision.parameter_names,
        request_parameter_values_fingerprint=(
            decision.parameter_values_fingerprint
        ),
        secret_reference_fingerprint=reference.reference_fingerprint,
        outcome="COMPLETED",
        created_at=NOW,
    )
    evidence_id = store.record(evidence)

    ledger = SimpleNamespace(
        list_events=lambda run_id: (
            {
                "event_type": "PROVIDER_CALL_COMPLETED",
                "event_payload": {
                    "provider_key": "api_football",
                    "queue_item_fingerprint": "9" * 64,
                    "consumed_request_units": 1,
                    "network_binding_evidence_ids": [evidence_id],
                },
            },
        )
    )
    permit = {
        "permit_id": "5" * 64,
        "run_id": "4" * 64,
        "sport": "football",
        "provider_key": "api_football",
        "method": "GET",
        "endpoint_manifest_id": "6" * 64,
        "security_evidence_id": "7" * 64,
        "consumed_at": NOW.isoformat(),
    }

    report = reconcile_provider_network_bindings(
        run_id="4" * 64,
        audit_ledger=ledger,
        binding_store=store,
        network_permit_store=FakePermitStore(permit),
        network_call_evidence_store=FakeNetworkCallEvidenceStore(),
        request_contract_registry=registry,
    )

    assert report.ok is True
    assert report.errors == ()

    unconsumed = dict(permit)
    unconsumed["consumed_at"] = None

    report = reconcile_provider_network_bindings(
        run_id="4" * 64,
        audit_ledger=ledger,
        binding_store=store,
        network_permit_store=FakePermitStore(unconsumed),
        network_call_evidence_store=FakeNetworkCallEvidenceStore(),
        request_contract_registry=registry,
    )

    assert report.ok is False
    assert "NETWORK_PERMIT_NOT_CONSUMED" in report.errors
