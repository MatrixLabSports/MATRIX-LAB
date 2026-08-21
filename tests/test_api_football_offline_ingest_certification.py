
from dataclasses import replace
import socket

import pytest

from app.providers.api_football.offline_ingest_certification import (
    certify_api_football_offline_fixture_ingest,
    require_api_football_offline_ingest_certified,
    verify_api_football_offline_ingest_certification,
)
from app.providers.api_football.response_validation import (
    ApiFootballProviderResponseError,
)


def test_offline_fixture_ingest_certifies_zero_network_pipeline(
    monkeypatch,
):
    def forbidden_network(*args, **kwargs):
        raise AssertionError(
            "NETWORK_CALL_FORBIDDEN_DURING_REPLAY"
        )

    monkeypatch.setattr(
        socket,
        "create_connection",
        forbidden_network,
    )

    certification = (
        certify_api_football_offline_fixture_ingest(
            payload={
                "get": "fixtures",
                "parameters": {
                    "date": "2026-08-21",
                },
                "errors": [],
                "results": 0,
                "paging": {
                    "current": 1,
                    "total": 1,
                },
                "response": [],
            },
            date="2026-08-21",
        )
    )

    assert certification.status == "CERTIFIED"
    assert certification.mode == "OFFLINE_REPLAY"
    assert certification.replay_request_count == 2
    assert certification.reconciliation_call_count == 2
    assert certification.repository_idempotent is True
    assert certification.zero_network_calls is True
    assert (
        certification.real_provider_execution_authorized
        is False
    )
    assert certification.automatic_provider_switch is False
    assert certification.automatic_wagering is False
    assert certification.blockers == ()

    assert (
        verify_api_football_offline_ingest_certification(
            certification
        )
        is certification
    )

    require_api_football_offline_ingest_certified(
        certification
    )


def test_offline_fixture_ingest_rejects_provider_error_before_sync():
    with pytest.raises(
        ApiFootballProviderResponseError
    ):
        certify_api_football_offline_fixture_ingest(
            payload={
                "response": [],
                "errors": {
                    "provider": "blocked",
                },
            },
            date="2026-08-21",
        )


def test_offline_certification_detects_tampering():
    certification = (
        certify_api_football_offline_fixture_ingest(
            payload={
                "response": [],
            },
            date="2026-08-21",
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
