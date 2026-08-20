from datetime import datetime, timedelta, timezone

from app.core.governed_provider_http import (
    SQLiteProviderNetworkCallEvidenceStore,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)

COMMON = {
    "permit_id": "1" * 64,
    "provider_key": "api_football",
    "run_id": "run-1",
    "method": "GET",
    "endpoint_manifest_id": "2" * 64,
}


def test_network_call_lifecycle_requires_start_and_terminal(tmp_path):
    store = SQLiteProviderNetworkCallEvidenceStore(
        tmp_path / "calls.db"
    )

    store.record(
        **COMMON,
        event_type="NETWORK_CALL_STARTED",
        event_at=NOW,
    )

    assert store.audit_integrity() is False

    store.record(
        **COMMON,
        event_type="NETWORK_CALL_COMPLETED",
        event_at=NOW + timedelta(milliseconds=5),
        status_code=200,
        elapsed_ms=5,
    )

    assert store.audit_integrity() is True


def test_network_call_lifecycle_rejects_multiple_terminal_events(
    tmp_path,
):
    store = SQLiteProviderNetworkCallEvidenceStore(
        tmp_path / "calls.db"
    )

    store.record(
        **COMMON,
        event_type="NETWORK_CALL_STARTED",
        event_at=NOW,
    )

    store.record(
        **COMMON,
        event_type="NETWORK_CALL_COMPLETED",
        event_at=NOW + timedelta(milliseconds=5),
        status_code=200,
        elapsed_ms=5,
    )

    store.record(
        **COMMON,
        event_type="NETWORK_CALL_FAILED",
        event_at=NOW + timedelta(milliseconds=6),
        elapsed_ms=6,
        exception_class="SyntheticError",
    )

    assert store.audit_integrity() is False
