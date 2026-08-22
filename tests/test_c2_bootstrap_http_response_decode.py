from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.provider_bootstrap_quarantine import execute_bootstrap_probe

CONTRACT_ID = "1" * 64


class StrictJsonResponse:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def json_strict(self):
        self.calls += 1
        return self.payload


class ResponseClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def authority():
    return SimpleNamespace(mode="BOOTSTRAP_PROBE")


def test_realistic_http_response_is_strictly_decoded_before_summary():
    response = StrictJsonResponse({"response": [], "results": 0})
    client = ResponseClient(response)

    summary = execute_bootstrap_probe(
        authority=authority(),
        client=client,
        endpoint="/status",
        request_contract_id=CONTRACT_ID,
        params=None,
    )

    assert client.calls == [{
        "path": "/status",
        "request_contract_id": CONTRACT_ID,
        "params": None,
    }]
    assert response.calls == 1
    assert summary.status == "QUARANTINED_PROBE_ONLY"
    assert summary.top_level_keys == ("response", "results")
    assert summary.raw_payload_retained is False
    assert summary.production_admissible is False
    assert summary.retroactive_promotion_allowed is False


def test_mapping_test_double_remains_supported():
    client = ResponseClient({"response": [], "results": 0})
    summary = execute_bootstrap_probe(
        authority=authority(),
        client=client,
        endpoint="/status",
        request_contract_id=CONTRACT_ID,
    )
    assert summary.status == "QUARANTINED_PROBE_ONLY"


def test_non_mapping_response_without_strict_decoder_fails_closed():
    client = ResponseClient(object())
    with pytest.raises(ValueError, match="BOOTSTRAP_RESPONSE_JSON_DECODER_REQUIRED"):
        execute_bootstrap_probe(
            authority=authority(),
            client=client,
            endpoint="/status",
            request_contract_id=CONTRACT_ID,
        )


def test_strict_decoder_non_mapping_payload_still_fails_closed():
    response = StrictJsonResponse(["not", "a", "mapping"])
    client = ResponseClient(response)
    with pytest.raises(ValueError, match="BOOTSTRAP_PAYLOAD_MUST_BE_MAPPING"):
        execute_bootstrap_probe(
            authority=authority(),
            client=client,
            endpoint="/status",
            request_contract_id=CONTRACT_ID,
        )
    assert response.calls == 1


def test_strict_decoder_exception_is_not_bypassed_or_retried():
    class FailingResponse:
        def __init__(self):
            self.calls = 0
        def json_strict(self):
            self.calls += 1
            raise RuntimeError("SYNTHETIC_STRICT_PROTOCOL_FAILURE")

    response = FailingResponse()
    client = ResponseClient(response)
    with pytest.raises(RuntimeError, match="SYNTHETIC_STRICT_PROTOCOL_FAILURE"):
        execute_bootstrap_probe(
            authority=authority(),
            client=client,
            endpoint="/status",
            request_contract_id=CONTRACT_ID,
        )
    assert response.calls == 1
    assert len(client.calls) == 1
