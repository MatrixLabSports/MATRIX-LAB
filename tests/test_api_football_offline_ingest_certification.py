from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import socket
import sqlite3

import pytest

import app.providers.api_football.offline_ingest_certification as module
from app.providers.api_football.offline_ingest_certification import (
    SQLiteApiFootballOfflineIngestEvidenceStore,
    certify_api_football_offline_fixture_ingest,
    require_api_football_offline_ingest_certified,
    verify_api_football_offline_ingest_certification,
)


def _fixture():
    return {
        "fixture": {
            "id": 991001,
            "date": "2026-08-21T12:00:00+00:00",
            "status": {"short": "FT"},
        },
        "league": {
            "id": 50,
            "name": "Liga",
            "country": "Colombia",
            "season": 2026,
            "round": "1",
        },
        "teams": {
            "home": {"id": 1, "name": "Home"},
            "away": {"id": 2, "name": "Away"},
        },
        "goals": {"home": 1, "away": 0},
    }


def _shadow_evidence():
    return SimpleNamespace(
        evidence_id="shadow-request-evidence-1",
        provider_key="api_football",
        evidence_type="REQUEST",
        parent_readiness_evidence_id="shadow-readiness-evidence-1",
        payload={
            "contract_id": "api-football.fixtures-by-date.2026-08-20.v1",
            "endpoint_manifest_id": "api-football.fixtures.endpoint.v1",
            "authorization_fingerprint": "a" * 64,
            "path": "/fixtures",
            "parameter_names": ["date"],
            "parameter_values_fingerprint": "b" * 64,
            "governed_request_client_used": True,
            "governed_transport_topology_verified": True,
            "network_call_performed": False,
            "network_permit_issued": False,
            "secret_resolved": False,
            "real_provider_execution_authorized": False,
        },
    )


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(
        module,
        "verify_provider_shadow_rehearsal_attestation",
        lambda evidence: True,
    )
    monkeypatch.setattr(
        module,
        "resolve_secret_runtime",
        lambda reference: "offline-ingest-test-attestation-key",
    )
    return SQLiteApiFootballOfflineIngestEvidenceStore(
        tmp_path / "offline-ingest.sqlite3"
    )


def test_offline_fixture_ingest_certifies_realistic_nonempty_replay(
    monkeypatch,
    tmp_path,
):
    def forbidden_network(*args, **kwargs):
        raise AssertionError("NETWORK_CALL_FORBIDDEN_DURING_REPLAY")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    store = _prepare(monkeypatch, tmp_path)

    certification = certify_api_football_offline_fixture_ingest(
        payload={
            "get": "fixtures",
            "parameters": {"date": "2026-08-21"},
            "errors": [],
            "results": 1,
            "paging": {"current": 1, "total": 1},
            "response": [_fixture()],
        },
        date="2026-08-21",
        shadow_request_evidence=_shadow_evidence(),
        evidence_store=store,
        source_revision="c41c297",
        clock=lambda: datetime(
            2026, 8, 21, 14, 0, tzinfo=timezone.utc
        ),
    )

    assert certification.status == "CERTIFIED"
    assert certification.received_count == 1
    assert certification.accepted_count == 1
    assert certification.rejected_count == 0
    assert certification.repository_idempotent is True
    assert certification.zero_network_topology_verified is True
    assert certification.zero_network_calls is True
    assert certification.request_contract_id.endswith("2026-08-20.v1")
    assert certification.endpoint_manifest_id == "api-football.fixtures.endpoint.v1"
    assert certification.shadow_request_evidence_id == "shadow-request-evidence-1"
    assert len(certification.code_fingerprint) == 64
    assert certification.real_provider_execution_authorized is False
    assert certification.automatic_provider_switch is False
    assert certification.automatic_wagering is False

    assert store.get_verified(certification.evidence_id) == certification
    assert store.audit_integrity() is True
    require_api_football_offline_ingest_certified(
        certification,
        evidence_store=store,
    )


def test_offline_certification_rejects_forged_shadow_provenance(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        module,
        "verify_provider_shadow_rehearsal_attestation",
        lambda evidence: False,
    )
    monkeypatch.setattr(
        module,
        "resolve_secret_runtime",
        lambda reference: "key",
    )
    store = SQLiteApiFootballOfflineIngestEvidenceStore(
        tmp_path / "evidence.sqlite3"
    )

    with pytest.raises(
        ValueError,
        match="OFFLINE_INGEST_SHADOW_ATTESTATION_INVALID",
    ):
        certify_api_football_offline_fixture_ingest(
            payload={"response": []},
            date="2026-08-21",
            shadow_request_evidence=_shadow_evidence(),
            evidence_store=store,
            source_revision="c41c297",
        )


def test_offline_certification_detects_object_tampering(
    monkeypatch,
    tmp_path,
):
    store = _prepare(monkeypatch, tmp_path)
    certification = certify_api_football_offline_fixture_ingest(
        payload={"response": [_fixture()]},
        date="2026-08-21",
        shadow_request_evidence=_shadow_evidence(),
        evidence_store=store,
        source_revision="c41c297",
    )

    tampered = replace(certification, automatic_wagering=True)
    with pytest.raises(
        ValueError,
        match="OFFLINE_INGEST_CERTIFICATION_INTEGRITY_FAILURE",
    ):
        verify_api_football_offline_ingest_certification(tampered)


def test_offline_store_detects_persistent_tampering(
    monkeypatch,
    tmp_path,
):
    store = _prepare(monkeypatch, tmp_path)
    certification = certify_api_football_offline_fixture_ingest(
        payload={"response": [_fixture()]},
        date="2026-08-21",
        shadow_request_evidence=_shadow_evidence(),
        evidence_store=store,
        source_revision="c41c297",
    )

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            '''
            UPDATE api_football_offline_ingest_evidence
            SET payload_json = ?
            WHERE evidence_id = ?
            ''',
            ("{}", certification.evidence_id),
        )
        connection.commit()

    assert store.audit_integrity() is False
