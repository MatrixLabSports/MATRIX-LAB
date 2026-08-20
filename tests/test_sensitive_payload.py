import pytest

from app.core.sensitive_payload import (
    assert_no_sensitive_fields,
    sanitize_sensitive_payload,
)


def test_nested_sensitive_values_are_redacted():
    payload = {
        "headers": {
            "Authorization": "Bearer abc",
        },
        "credentials": {
            "api_key": "super-secret",
        },
        "safe": {
            "provider_key": "provider-x",
        },
    }

    sanitized = sanitize_sensitive_payload(
        payload
    )

    assert (
        sanitized["headers"][
            "Authorization"
        ]
        == "[REDACTED]"
    )
    assert (
        sanitized["credentials"][
            "api_key"
        ]
        == "[REDACTED]"
    )
    assert (
        sanitized["safe"][
            "provider_key"
        ]
        == "provider-x"
    )

    assert_no_sensitive_fields(
        sanitized
    )


def test_unredacted_sensitive_field_fails_closed():
    with pytest.raises(
        ValueError,
        match="UNREDACTED_SENSITIVE_FIELD",
    ):
        assert_no_sensitive_fields(
            {
                "access_token": "abc",
            }
        )
