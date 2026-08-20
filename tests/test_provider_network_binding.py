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


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


class Inner(MatrixPinnedHttpsTransport):
    def get_pinned(self, **kwargs):
        return "ok"


def test_binding_evidence_binds_permit_endpoint_security_and_contract(
    tmp_path,
):
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

    assert (
        transport.get_pinned(
            url="https://api.example.test/v3/fixtures",
            original_host="api.example.test",
            resolved_ips=("8.8.8.8",),
            allow_redirects=False,
            verify=True,
            matrix_permit=permit,
            matrix_request_contract_fingerprint="f" * 64,
        )
        == "ok"
    )

    evidence_ids = collector.finish("a" * 64)
    assert len(evidence_ids) == 1

    evidence = store.get_verified(evidence_ids[0])
    assert evidence is not None
    assert evidence.permit_id == "c" * 64
    assert evidence.endpoint_manifest_id == "d" * 64
    assert evidence.security_evidence_id == "e" * 64
    assert evidence.request_contract_fingerprint == "f" * 64
    assert store.audit_integrity() is True


class FakeAuditLedger:
    def __init__(self):
        self.events = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)

    def list_events(self, run_id):
        return tuple(
            {
                "event_type": event["event_type"],
                "event_payload": event["event_payload"],
            }
            for event in self.events
        )


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

    payload = fetcher.fetch(
        {
            "provider_key": "api_football",
            "queue_item_fingerprint": "3" * 64,
            "estimated_request_cost": 1,
        }
    )

    assert payload == {"ok": True}
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
        return self.payload


class FakeNetworkCallEvidenceStore:
    def audit_integrity(self):
        return True

    def list_verified_events_for_permit(self, permit_id):
        return (
            {
                "permit_id": permit_id,
                "event_type": "NETWORK_CALL_STARTED",
            },
            {
                "permit_id": permit_id,
                "event_type": "NETWORK_CALL_COMPLETED",
            },
        )


def test_network_reconciliation_matches_provider_terminal_to_permit_and_network_call(
    tmp_path,
):
    run_id = "4" * 64
    provider_key = "api_football"
    permit_id = "5" * 64
    endpoint_manifest_id = "6" * 64
    security_evidence_id = "7" * 64

    store = SQLiteProviderNetworkBindingEvidenceStore(
        tmp_path / "binding.db"
    )
    evidence = build_provider_network_binding_evidence(
        run_id=run_id,
        provider_key=provider_key,
        permit_id=permit_id,
        endpoint_manifest_id=endpoint_manifest_id,
        security_evidence_id=security_evidence_id,
        request_contract_fingerprint="8" * 64,
        outcome="COMPLETED",
        created_at=NOW,
    )
    evidence_id = store.record(evidence)

    ledger = SimpleNamespace(
        list_events=lambda actual_run_id: (
            {
                "event_type": "PROVIDER_CALL_COMPLETED",
                "event_payload": {
                    "provider_key": provider_key,
                    "consumed_request_units": 1,
                    "network_binding_evidence_ids": [
                        evidence_id
                    ],
                },
            },
        )
    )

    permit_payload = {
        "permit_id": permit_id,
        "run_id": run_id,
        "provider_key": provider_key,
        "endpoint_manifest_id": endpoint_manifest_id,
        "security_evidence_id": security_evidence_id,
    }

    report = reconcile_provider_network_bindings(
        run_id=run_id,
        audit_ledger=ledger,
        binding_store=store,
        network_permit_store=FakePermitStore(
            permit_payload
        ),
        network_call_evidence_store=FakeNetworkCallEvidenceStore(),
    )

    assert report.ok is True
    assert report.errors == ()
    assert report.binding_evidence_ids == (
        evidence_id,
    )


def test_runtime_reconciliation_source_contains_optional_network_gate():
    from pathlib import Path

    source = Path(
        "app/core/runtime_reconciliation.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "network_binding_store=None" in source
    assert "network_permit_store=None" in source
    assert "network_call_evidence_store=None" in source
    assert "reconcile_provider_network_bindings" in source
    assert "NETWORK_BINDING_COMPONENTS_PARTIAL" in source
