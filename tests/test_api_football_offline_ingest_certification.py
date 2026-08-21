
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import inspect
import sqlite3
from types import SimpleNamespace

import pytest

import app.providers.api_football.offline_ingest_certification as module
from app.core.provider_request_contract import (
    request_parameter_values_fingerprint,
)
from app.core.provider_shadow_rehearsal_evidence import (
    SQLiteProviderShadowRehearsalEvidenceStore,
)
from app.providers.api_football.offline_ingest_certification import (
    AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV,
    SQLiteApiFootballOfflineIngestEvidenceStore,
    certify_api_football_offline_fixture_ingest,
    require_api_football_offline_ingest_certified,
    verify_api_football_offline_ingest_certification,
)


def _fixture():
    return {
        "fixture": {
            "id": 991001,
            "date": (
                "2026-08-21T12:00:00+00:00"
            ),
            "status": {
                "short": "FT",
            },
        },
        "league": {
            "id": 50,
            "name": "Liga",
            "country": "Colombia",
            "season": 2026,
            "round": "1",
        },
        "teams": {
            "home": {
                "id": 1,
                "name": "Home",
            },
            "away": {
                "id": 2,
                "name": "Away",
            },
        },
        "goals": {
            "home": 1,
            "away": 0,
        },
    }


def _payload(
    *,
    date="2026-08-21",
):
    return {
        "get": "fixtures",
        "parameters": {
            "date": date,
        },
        "errors": [],
        "results": 1,
        "paging": {
            "current": 1,
            "total": 1,
        },
        "response": [
            _fixture(),
        ],
    }


def _request_evidence(
    *,
    store_identity: str,
    parameter_values_fingerprint: str,
):
    return SimpleNamespace(
        evidence_id=(
            "shadow-request-evidence-1"
        ),
        provider_key="api_football",
        evidence_type="REQUEST",
        parent_readiness_evidence_id=(
            "shadow-readiness-evidence-1"
        ),
        store_identity=store_identity,
        authority_id=(
            "shadow-authority-1"
        ),
        attestation_key_reference_fingerprint=(
            "a" * 64
        ),
        payload={
            "contract_id": (
                "api-football.fixtures-by-date.2026-08-20.v1"
            ),
            "endpoint_manifest_id": (
                "api-football.fixtures.endpoint.v1"
            ),
            "authorization_fingerprint": (
                "b" * 64
            ),
            "path": "/fixtures",
            "parameter_names": [
                "date",
            ],
            "parameter_values_fingerprint": (
                parameter_values_fingerprint
            ),
            "governed_request_client_used": True,
            "governed_transport_topology_verified": True,
            "network_call_performed": False,
            "network_permit_issued": False,
            "secret_resolved": False,
            "real_provider_execution_authorized": False,
        },
    )


def _readiness_evidence(
    *,
    store_identity: str,
):
    return SimpleNamespace(
        evidence_id=(
            "shadow-readiness-evidence-1"
        ),
        provider_key="api_football",
        evidence_type="READINESS",
        parent_readiness_evidence_id=None,
        store_identity=store_identity,
        authority_id=(
            "shadow-authority-1"
        ),
        attestation_key_reference_fingerprint=(
            "a" * 64
        ),
        payload={
            "schema": (
                "matrix.api-football-shadow-readiness/test"
            ),
        },
    )


def _prepare(
    monkeypatch,
    tmp_path,
    *,
    parameter_values_fingerprint=None,
):
    ingest_path = (
        tmp_path
        / "offline-ingest.sqlite3"
    )

    monkeypatch.setenv(
        AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV,
        str(
            ingest_path.resolve()
        ),
    )

    monkeypatch.setattr(
        module,
        "resolve_secret_runtime",
        lambda reference: (
            "offline-ingest-test-attestation-key"
        ),
    )

    monkeypatch.setattr(
        module,
        "_source_revision",
        lambda: "154fead",
    )

    monkeypatch.setattr(
        module,
        "verify_provider_shadow_rehearsal_attestation",
        lambda evidence: True,
    )

    shadow_store = (
        SQLiteProviderShadowRehearsalEvidenceStore(
            tmp_path
            / "shadow-evidence.sqlite3"
        )
    )

    expected_fp = (
        request_parameter_values_fingerprint(
            {
                "date": "2026-08-21",
            }
        )
        if parameter_values_fingerprint
        is None
        else parameter_values_fingerprint
    )

    request_evidence = (
        _request_evidence(
            store_identity=(
                shadow_store.store_identity
            ),
            parameter_values_fingerprint=(
                expected_fp
            ),
        )
    )

    readiness_evidence = (
        _readiness_evidence(
            store_identity=(
                shadow_store.store_identity
            ),
        )
    )

    def get_verified(
        evidence_id,
    ):
        if (
            evidence_id
            == request_evidence.evidence_id
        ):
            return request_evidence

        if (
            evidence_id
            == readiness_evidence.evidence_id
        ):
            return readiness_evidence

        return None

    monkeypatch.setattr(
        shadow_store,
        "get_verified",
        get_verified,
    )

    ingest_store = (
        SQLiteApiFootballOfflineIngestEvidenceStore(
            ingest_path
        )
    )

    return (
        shadow_store,
        request_evidence,
        ingest_store,
    )


def test_offline_fixture_ingest_certifies_realistic_nonempty_replay(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    certification = (
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
            clock=lambda: datetime(
                2026,
                8,
                21,
                14,
                0,
                tzinfo=timezone.utc,
            ),
        )
    )

    assert certification.status == "CERTIFIED"
    assert certification.received_count == 1
    assert certification.accepted_count == 1
    assert certification.rejected_count == 0
    assert certification.repository_idempotent is True
    assert certification.zero_network_topology_verified is True
    assert certification.zero_network_calls is True
    assert (
        certification.parameter_values_fingerprint
        == request_parameter_values_fingerprint(
            {
                "date": "2026-08-21",
            }
        )
    )
    assert certification.source_revision == "154fead"
    assert certification.real_provider_execution_authorized is False
    assert certification.automatic_provider_switch is False
    assert certification.automatic_wagering is False

    assert (
        ingest_store.get_verified(
            certification.evidence_id
        )
        == certification
    )

    require_api_football_offline_ingest_certified(
        certification,
        evidence_store=(
            ingest_store
        ),
    )


def test_certifier_rejects_payload_date_mismatch(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match=(
            "OFFLINE_INGEST_PAYLOAD_DATE_MISMATCH"
        ),
    ):
        certify_api_football_offline_fixture_ingest(
            payload=_payload(
                date="2026-08-20",
            ),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
        )


def test_certifier_rederives_shadow_parameter_fingerprint(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
        parameter_values_fingerprint=(
            "f" * 64
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "OFFLINE_INGEST_SHADOW_PARAMETER_VALUES_FINGERPRINT_MISMATCH"
        ),
    ):
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
        )


def test_certifier_requires_durable_shadow_reload(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        shadow_store,
        "get_verified",
        lambda evidence_id: None,
    )

    with pytest.raises(
        ValueError,
        match=(
            "OFFLINE_INGEST_SHADOW_REQUEST_EVIDENCE_NOT_FOUND"
        ),
    ):
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
        )


def test_certifier_requires_authoritative_ingest_store(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        _,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    rogue_store = (
        SQLiteApiFootballOfflineIngestEvidenceStore(
            tmp_path
            / "rogue.sqlite3"
        )
    )

    with pytest.raises(
        ValueError,
        match=(
            "OFFLINE_INGEST_AUTHORITATIVE_STORE_REQUIRED"
        ),
    ):
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                rogue_store
            ),
        )


def test_source_revision_is_not_caller_controlled():
    signature = inspect.signature(
        certify_api_football_offline_fixture_ingest
    )

    assert (
        "source_revision"
        not in signature.parameters
    )


def test_offline_certification_detects_object_tampering(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    certification = (
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
        )
    )

    tampered = replace(
        certification,
        automatic_wagering=True,
    )

    with pytest.raises(
        ValueError,
        match=(
            "OFFLINE_INGEST_CERTIFICATION_INTEGRITY_FAILURE"
        ),
    ):
        verify_api_football_offline_ingest_certification(
            tampered
        )


def test_offline_store_detects_persistent_tampering(
    monkeypatch,
    tmp_path,
):
    (
        shadow_store,
        request_evidence,
        ingest_store,
    ) = _prepare(
        monkeypatch,
        tmp_path,
    )

    certification = (
        certify_api_football_offline_fixture_ingest(
            payload=_payload(),
            date="2026-08-21",
            shadow_evidence_store=(
                shadow_store
            ),
            shadow_request_evidence_id=(
                request_evidence.evidence_id
            ),
            evidence_store=(
                ingest_store
            ),
        )
    )

    with sqlite3.connect(
        ingest_store.path
    ) as connection:
        connection.execute(
            """
            UPDATE api_football_offline_ingest_evidence
            SET payload_json = ?
            WHERE evidence_id = ?
            """,
            (
                "{}",
                certification.evidence_id,
            ),
        )
        connection.commit()

    assert (
        ingest_store.audit_integrity()
        is False
    )
