from pathlib import Path


def test_provider_production_readiness_remains_fail_closed():
    rights = Path(
        "app/core/provider_rights_authorization.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    baseline = Path(
        "app/providers/api_football/rights_baseline.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    shadow = Path(
        "app/providers/api_football/shadow_runtime.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    attempts = Path(
        "app/core/provider_attempt_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    recovery = Path(
        "app/core/provider_interruption_recovery.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "BLOCKED_PENDING_RIGHTS_REVIEW"
        in baseline
    )
    assert (
        "BETTING_PLATFORM"
        in rights
    )
    assert (
        "RIGHTS_HOLDER_EVIDENCE_REQUIRED"
        in rights
    )

    assert "DRY_RUN" in shadow
    assert "SHADOW" in shadow
    assert (
        "network_call_performed=False"
        in shadow
    )
    assert "requests" not in shadow
    assert "socket" not in shadow

    assert (
        "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS"
        in attempts
    )

    assert (
        "INTERRUPTED_UNKNOWN_OUTCOME"
        in recovery
    )
    assert (
        "safe_to_retry=False"
        in recovery
    )
    assert (
        "request_units_refunded=False"
        in recovery
    )

    combined = (
        rights
        + baseline
        + shadow
        + attempts
        + recovery
    )

    assert (
        "real_provider_execution_authorized=True"
        not in combined
    )
    assert (
        "automatic_provider_switch=True"
        not in combined
    )
    assert (
        "automatic_wagering=True"
        not in combined
    )
