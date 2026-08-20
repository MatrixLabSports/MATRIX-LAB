import pytest

from app.core.sensitive_payload import (
    assert_no_sensitive_fields,
    sanitize_sensitive_payload,
)


def test_nested_sensitive_aliases_are_redacted():
    payload = {
        "headers": {
            "Authorization": "Bearer abc",
            "X-API-Key": "super-secret",
        },
        "safe": {
            "provider_key": "provider-x",
        },
    }

    sanitized = sanitize_sensitive_payload(payload)

    assert (
        sanitized["headers"]["Authorization"]
        == "[REDACTED]"
    )
    assert (
        sanitized["headers"]["X-API-Key"]
        == "[REDACTED]"
    )

    assert_no_sensitive_fields(sanitized)


def test_url_query_secret_is_redacted():
    value = (
        "https://example.test/v1"
        "?x-api-key=abc&date=2026-08-20"
    )

    sanitized = sanitize_sensitive_payload(value)

    assert "abc" not in sanitized
    assert "%5BREDACTED%5D" in sanitized


def test_bearer_text_is_redacted_even_without_sensitive_key():
    assert (
        sanitize_sensitive_payload("Bearer abcdef")
        == "[REDACTED]"
    )


def test_unredacted_sensitive_alias_fails_closed():
    with pytest.raises(
        ValueError,
        match="UNREDACTED_SENSITIVE_FIELD",
    ):
        assert_no_sensitive_fields(
            {"x-auth-token": "abc"}
        )


def test_unredacted_sensitive_url_fails_closed():
    with pytest.raises(
        ValueError,
        match="UNREDACTED_SENSITIVE_TEXT",
    ):
        assert_no_sensitive_fields(
            "https://example.test/v1"
            "?access_token=abc"
        )
