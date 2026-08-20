from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.governed_provider_http import (
    GovernedProviderHttpSession,
    SQLiteProviderNetworkCallEvidenceStore,
)


NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


class Authority:
    run_id = "run-1"
    mode = "PRODUCTION"

    def authorize(self, **kwargs):
        return SimpleNamespace(
            permit_id="1" * 64,
            provider_key="api_football",
            run_id="run-1",
            method="GET",
            endpoint_manifest_id="2" * 64,
        )


class PermitStore:
    def __init__(self):
        self.used = []

    def consume(self, *, permit_id, consumed_at):
        self.used.append(permit_id)
        return {}


class Response:
    status_code = 200


class Underlying:
    def __init__(self):
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return Response()


def test_permit_is_consumed_before_real_http_and_evidence_is_safe(tmp_path):
    permits = PermitStore()
    underlying = Underlying()
    evidence = SQLiteProviderNetworkCallEvidenceStore(
        tmp_path / "calls.db"
    )

    session = GovernedProviderHttpSession(
        authority=Authority(),
        network_permit_store=permits,
        call_evidence_store=evidence,
        underlying_session=underlying,
        clock=lambda: NOW,
    )

    response = session.get(
        "https://api.example.test/v3/fixtures",
        params={"date": "2026-08-20"},
        headers={"x-provider-key": "synthetic-fixture-value"},
    )

    assert response.status_code == 200
    assert permits.used == ["1" * 64]
    assert underlying.calls == 1
    assert evidence.audit_integrity()
