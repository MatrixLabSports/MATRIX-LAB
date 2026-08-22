import pytest

from app.core.platform_scope import (
    PRIVATE_INTERNAL_ONLY,
    PlatformScope,
    require_private_internal_only,
)


def test_private_internal_scope_is_explicit():
    payload = PRIVATE_INTERNAL_ONLY.payload()
    assert payload["private_internal_only"] is True
    assert payload["commercial_use"] is False
    assert payload["public_redistribution"] is False
    assert payload["data_resale"] is False
    assert payload["customer_display"] is False
    assert payload["sublicensing"] is False
    assert payload["internal_analytics"] is True
    assert payload["internal_modeling"] is True
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_wagering"] is False


def test_scope_fails_closed_if_commercialized():
    bad = PlatformScope(
        **{
            **PRIVATE_INTERNAL_ONLY.__dict__,
            "commercial_use": True,
        }
    )
    with pytest.raises(
        ValueError,
        match="PRIVATE_INTERNAL_ONLY_SCOPE_REQUIRED",
    ):
        require_private_internal_only(bad)
