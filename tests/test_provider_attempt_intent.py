from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.governed_provider_http import (
    MatrixPinnedHttpsTransport,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
    build_provider_attempt_intent_evidence,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def _intent():
    return build_provider_attempt_intent_evidence(
        run_id="1" * 64,
        provider_key="api_football",
        queue_item_fingerprint="2" * 64,
        permit_id="3" * 64,
        endpoint_manifest_id="4" * 64,
        security_evidence_id="5" * 64,
        request_contract_id="6" * 64,
        request_contract_fingerprint="7" * 64,
        request_path="/fixtures",
        request_parameter_names=("date",),
        request_parameter_values_fingerprint="8" * 64,
        secret_reference_fingerprint="9" * 64,
        created_at=NOW,
    )


def test_attempt_intent_store_is_immutable_and_rederivable(
    tmp_path,
):
    store = SQLiteProviderAttemptIntentStore(
        tmp_path / "intents.db"
    )

    evidence = _intent()

    store.record(
        evidence
    )

    assert (
        store.get_by_permit(
            evidence.permit_id
        )
        == evidence
    )
    assert (
        store.list_verified_for_run(
            evidence.run_id
        )
        == (
            evidence,
        )
    )
    assert store.audit_integrity() is True


class CrashAfterAttemptIntentTransport(
    MatrixPinnedHttpsTransport
):
    def get_pinned(
        self,
        **kwargs,
    ):
        raise KeyboardInterrupt(
            "simulated-process-interruption"
        )


def test_attempt_intent_is_durable_before_physical_call_can_finish(
    tmp_path,
):
    intent_store = (
        SQLiteProviderAttemptIntentStore(
            tmp_path / "intents.db"
        )
    )
    binding_store = (
        SQLiteProviderNetworkBindingEvidenceStore(
            tmp_path / "bindings.db"
        )
    )
    collector = (
        ProviderNetworkBindingCollector()
    )
    collector.begin(
        "2" * 64
    )

    transport = (
        BindingAuditPinnedHttpsTransport(
            inner=(
                CrashAfterAttemptIntentTransport()
            ),
            binding_store=binding_store,
            collector=collector,
            clock=lambda: NOW,
            attempt_intent_store=(
                intent_store
            ),
        )
    )

    permit = SimpleNamespace(
        run_id="1" * 64,
        provider_key="api_football",
        permit_id="3" * 64,
        endpoint_manifest_id="4" * 64,
        security_evidence_id="5" * 64,
    )

    with pytest.raises(
        KeyboardInterrupt,
        match="simulated-process-interruption",
    ):
        transport.get_pinned(
            url=(
                "https://api.example.test/fixtures"
            ),
            original_host=(
                "api.example.test"
            ),
            resolved_ips=(
                "8.8.8.8",
            ),
            allow_redirects=False,
            verify=True,
            matrix_permit=permit,
            matrix_request_contract_id="6" * 64,
            matrix_request_contract_fingerprint="7" * 64,
            matrix_request_path="/fixtures",
            matrix_request_parameter_names=(
                "date",
            ),
            matrix_request_parameter_values_fingerprint="8" * 64,
            matrix_request_secret_reference_fingerprint="9" * 64,
        )

    intent = intent_store.get_by_permit(
        "3" * 64
    )

    assert intent is not None
    assert (
        intent.queue_item_fingerprint
        == "2" * 64
    )
    assert (
        intent.request_contract_id
        == "6" * 64
    )
