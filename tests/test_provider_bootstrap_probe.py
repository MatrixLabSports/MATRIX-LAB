import pytest

from app.core.provider_bootstrap_probe import (
    build_bootstrap_probe_policy,
)


def test_bootstrap_probe_is_tiny_manual_and_quarantined():
    policy = build_bootstrap_probe_policy(
        sport="football",
        provider_key="provider-x",
        manual_approval_id="OPS-BOOT-1",
        max_items=3,
        max_requests=5,
    )

    payload = policy.payload()
    assert payload["mode"] == "BOOTSTRAP_PROBE"
    assert payload["downstream_quarantine_required"] is True
    assert payload["automatic_health_promotion"] is False


def test_bootstrap_probe_cannot_expand_beyond_hard_caps():
    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_ITEMS_OUT_OF_BOUNDS",
    ):
        build_bootstrap_probe_policy(
            sport="tennis",
            provider_key="provider-x",
            manual_approval_id="OPS-BOOT-2",
            max_items=6,
            max_requests=5,
        )

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_REQUESTS_OUT_OF_BOUNDS",
    ):
        build_bootstrap_probe_policy(
            sport="tennis",
            provider_key="provider-x",
            manual_approval_id="OPS-BOOT-3",
            max_items=5,
            max_requests=11,
        )
