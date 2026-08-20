import pytest

from app.core.provider_endpoint_policy import (
    build_provider_endpoint_policy,
)


def test_endpoint_policy_binds_exact_target_not_only_origin():
    first = build_provider_endpoint_policy(
        provider_key="provider-x",
        endpoint_url=(
            "https://api.provider.example/v1/fixtures"
            "?date=2026-08-20&league=1"
        ),
    )
    second = build_provider_endpoint_policy(
        provider_key="provider-x",
        endpoint_url=(
            "https://api.provider.example/v1/results"
            "?date=2026-08-20&league=1"
        ),
    )

    assert first.endpoint_origin == second.endpoint_origin
    assert (
        first.endpoint_target_fingerprint
        != second.endpoint_target_fingerprint
    )
    assert first.policy_fingerprint != second.policy_fingerprint


def test_plain_http_is_rejected():
    with pytest.raises(
        ValueError,
        match="PROVIDER_ENDPOINT_TLS_REQUIRED",
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url=(
                "http://api.provider.example/v1"
            ),
        )


def test_non_global_ip_literal_is_rejected():
    with pytest.raises(
        ValueError,
        match="NON_GLOBAL_PROVIDER_IP_FORBIDDEN",
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url="https://10.0.0.1/v1",
        )


def test_secret_query_aliases_are_rejected():
    with pytest.raises(
        ValueError,
        match="SECRET_QUERY_PARAMETER_FORBIDDEN",
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url=(
                "https://api.provider.example/v1"
                "?x-api-key=secret"
            ),
        )


def test_fragments_are_rejected():
    with pytest.raises(
        ValueError,
        match="PROVIDER_ENDPOINT_FRAGMENT_FORBIDDEN",
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url=(
                "https://api.provider.example/v1#token"
            ),
        )
