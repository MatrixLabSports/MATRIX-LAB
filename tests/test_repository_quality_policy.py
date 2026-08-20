from app.core.repository_quality_policy import (
    build_repository_quality_policy,
)


def test_repository_quality_policy_is_fail_closed():
    policy = build_repository_quality_policy()
    payload = policy.payload()

    assert payload["automatic_deploy"] is False
    assert (
        payload["automatic_model_promotion"]
        is False
    )
    assert payload["automatic_wagering"] is False
    assert (
        "tracked_secret_scan"
        in payload["required_static_checks"]
    )
    assert (
        ".env"
        in payload["forbidden_tracked_names"]
    )
