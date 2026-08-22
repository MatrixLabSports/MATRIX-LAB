from pathlib import Path
from types import SimpleNamespace

import pytest

import app.providers.api_football.bootstrap_client as bootstrap_module
import app.providers.api_football.governed_client as governed_module
from app.core.provider_bootstrap_quarantine import (
    execute_bootstrap_probe,
)


def marker():
    return object()


def bootstrap_kwargs():
    return {
        "config": marker(),
        "authority": SimpleNamespace(
            mode="BOOTSTRAP_PROBE"
        ),
        "network_permit_store": marker(),
        "call_evidence_store": marker(),
        "clock": lambda: "NOW",
        "pinned_transport": marker(),
        "request_contract_registry": marker(),
        "secret_reference": marker(),
        "binding_store": marker(),
        "binding_collector": marker(),
        "attempt_intent_store": marker(),
    }


def test_bootstrap_builder_delegates_to_exact_controlled_topology(
    monkeypatch,
):
    captured = {}

    def controlled(**kwargs):
        captured.update(kwargs)
        return "CONTROLLED-CLIENT"

    monkeypatch.setattr(
        governed_module,
        "_build_controlled_request_client",
        controlled,
    )

    kwargs = bootstrap_kwargs()
    result = (
        bootstrap_module
        .build_bootstrap_api_football_client(
            **kwargs
        )
    )

    assert result == "CONTROLLED-CLIENT"
    assert captured == kwargs


def test_bootstrap_builder_rejects_production_before_delegation(
    monkeypatch,
):
    called = []

    monkeypatch.setattr(
        governed_module,
        "_build_controlled_request_client",
        lambda **kwargs: called.append(kwargs),
    )

    kwargs = bootstrap_kwargs()
    kwargs["authority"] = SimpleNamespace(
        mode="PRODUCTION"
    )

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_CLIENT_REQUIRES_BOOTSTRAP_MODE",
    ):
        bootstrap_module.build_bootstrap_api_football_client(
            **kwargs
        )

    assert called == []


def test_quarantine_helper_is_request_contract_bound():
    calls = []

    class Client:
        def get(self, **kwargs):
            calls.append(kwargs)
            return {
                "response": [{"ok": True}],
                "results": 1,
            }

    summary = execute_bootstrap_probe(
        authority=SimpleNamespace(
            mode="BOOTSTRAP_PROBE"
        ),
        client=Client(),
        endpoint="/status",
        request_contract_id="1" * 64,
    )

    assert calls == [
        {
            "path": "/status",
            "request_contract_id": "1" * 64,
            "params": None,
        }
    ]
    assert summary.status == "QUARANTINED_PROBE_ONLY"
    assert summary.raw_payload_retained is False
    assert summary.production_admissible is False
    assert summary.retroactive_promotion_allowed is False


@pytest.mark.parametrize(
    "request_contract_id",
    [None, "", "x" * 64, "1" * 63],
)
def test_quarantine_helper_rejects_missing_or_invalid_contract_id(
    request_contract_id,
):
    class Client:
        def get(self, **kwargs):
            pytest.fail("network client must not be reached")

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_REQUEST_CONTRACT_ID_REQUIRED",
    ):
        execute_bootstrap_probe(
            authority=SimpleNamespace(
                mode="BOOTSTRAP_PROBE"
            ),
            client=Client(),
            endpoint="/status",
            request_contract_id=request_contract_id,
        )


def test_status_probe_binds_contract_endpoint_before_client_use(
    monkeypatch,
):
    events = []

    class BindingStore:
        def authorize(self, **kwargs):
            events.append(("binding", kwargs))
            return object()

    class Client:
        def get(self, **kwargs):
            events.append(("client", kwargs))
            return {
                "response": [{"ok": True}],
                "results": 1,
            }

    monkeypatch.setattr(
        bootstrap_module,
        "build_bootstrap_api_football_client",
        lambda **kwargs: Client(),
    )

    now = object()
    kwargs = bootstrap_kwargs()
    kwargs["clock"] = lambda: now

    summary = (
        bootstrap_module
        .execute_governed_api_football_bootstrap_probe(
            **kwargs,
            endpoint="/status",
            request_contract_id="1" * 64,
            contract_endpoint_binding_store=BindingStore(),
            endpoint_manifest_id="2" * 64,
            params=None,
        )
    )

    assert events[0] == (
        "binding",
        {
            "request_contract_id": "1" * 64,
            "endpoint_manifest_id": "2" * 64,
            "path": "/status",
            "now": now,
        },
    )
    assert events[1] == (
        "client",
        {
            "path": "/status",
            "request_contract_id": "1" * 64,
            "params": None,
        },
    )
    assert summary.status == "QUARANTINED_PROBE_ONLY"


@pytest.mark.parametrize(
    "endpoint, params, reason",
    [
        (
            "/fixtures",
            None,
            "BOOTSTRAP_STATUS_ENDPOINT_REQUIRED",
        ),
        (
            "/status",
            {"id": 1},
            "BOOTSTRAP_STATUS_PARAMS_FORBIDDEN",
        ),
    ],
)
def test_first_c2_bootstrap_probe_is_status_only_and_parameterless(
    monkeypatch,
    endpoint,
    params,
    reason,
):
    monkeypatch.setattr(
        bootstrap_module,
        "build_bootstrap_api_football_client",
        lambda **kwargs: pytest.fail(
            "client must not be built"
        ),
    )

    kwargs = bootstrap_kwargs()

    with pytest.raises(ValueError, match=reason):
        (
            bootstrap_module
            .execute_governed_api_football_bootstrap_probe(
                **kwargs,
                endpoint=endpoint,
                request_contract_id="1" * 64,
                contract_endpoint_binding_store=object(),
                endpoint_manifest_id="2" * 64,
                params=params,
            )
        )


def test_bootstrap_source_has_no_legacy_provider_or_direct_http_bypass():
    source = Path(
        "app/providers/api_football/bootstrap_client.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for forbidden in (
        "ApiFootballClient",
        "config.api_key",
        "import requests",
        "requests.Session",
        "GovernedProviderHttpSession(",
    ):
        assert forbidden not in source

    for required in (
        "_build_controlled_request_client",
        "request_contract_registry",
        "secret_reference",
        "binding_store",
        "binding_collector",
        "attempt_intent_store",
        "request_contract_id",
        "contract_endpoint_binding_store",
        "BOOTSTRAP_PROBE",
        "execute_bootstrap_probe",
    ):
        assert required in source
