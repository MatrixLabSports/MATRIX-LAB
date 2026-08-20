import pytest

from app.core.provider_endpoint_policy import (
    build_provider_endpoint_policy,
)


def test_https_provider_endpoint_is_allowed():
    policy = build_provider_endpoint_policy(
        provider_key="provider-x",
        endpoint_url=(
            "https://api.provider.example/v1/fixtures"
        ),
    )

    assert (
        policy.endpoint_origin
        == "https://api.provider.example"
    )
    assert policy.tls_required is True
    assert (
        policy.certificate_verification_required
        is True
    )


def test_http_provider_endpoint_is_rejected():
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


def test_credentials_in_url_are_rejected():
    with pytest.raises(
        ValueError,
        match=(
            "EMBEDDED_PROVIDER_CREDENTIALS_FORBIDDEN"
        ),
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url=(
                "https://user:pass@api.provider.example/v1"
            ),
        )


def test_secret_query_parameter_is_rejected():
    with pytest.raises(
        ValueError,
        match="SECRET_QUERY_PARAMETER_FORBIDDEN",
    ):
        build_provider_endpoint_policy(
            provider_key="provider-x",
            endpoint_url=(
                "https://api.provider.example/v1"
                "?api_key=secret"
            ),
        )
