import pytest

from app.application.football.provider_health_policy import (
    evaluate_football_provider_health,
)
from app.application.tennis.provider_health_policy import (
    evaluate_tennis_provider_health,
)
from app.core.provider_health_policy import ProviderHealthPolicy
from app.core.provider_health_snapshot import ProviderHealthSnapshot


def snapshot(
    *,
    sport="tennis",
    provider_key="P1",
    completed=9,
    failed=1,
    zero_refusals=0,
    consumed=10,
    status="VALID",
    char="1",
):
    terminal = completed + failed
    success_rate = None if terminal == 0 else completed / terminal
    failure_rate = None if terminal == 0 else failed / terminal

    return ProviderHealthSnapshot(
        provider_key=provider_key,
        sport=sport,
        run_ids=("a" * 64,),
        calls_started=terminal,
        calls_completed=completed,
        calls_failed=failed,
        zero_consumption_refusals=zero_refusals,
        consumed_request_units=consumed,
        success_rate=success_rate,
        failure_rate=failure_rate,
        snapshot_status=status,
        reason_codes=(),
        snapshot_fingerprint=char * 64,
    )


def policy(
    *,
    provider_key="P1",
    min_calls=10,
    max_failure=0.20,
    max_zero_refusal=0.20,
    require_known=True,
):
    return ProviderHealthPolicy(
        provider_key=provider_key,
        min_terminal_calls=min_calls,
        max_failure_rate=max_failure,
        max_zero_consumption_refusal_rate=max_zero_refusal,
        require_known_consumption=require_known,
    )


def test_healthy_provider_is_eligible():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(),
        policy=policy(),
    )

    assert decision.decision_status == "ELIGIBLE"
    assert decision.scheduling_eligible is True
    assert decision.reason_codes == ()


def test_insufficient_observations_require_review():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(completed=2, failed=0, consumed=2),
        policy=policy(min_calls=5),
    )

    assert decision.decision_status == "REVIEW_REQUIRED"
    assert decision.scheduling_eligible is False
    assert "INSUFFICIENT_OBSERVATIONS" in decision.reason_codes


def test_failure_rate_breach_is_ineligible():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(completed=7, failed=3),
        policy=policy(max_failure=0.20),
    )

    assert decision.decision_status == "INELIGIBLE"
    assert decision.scheduling_eligible is False
    assert "FAILURE_RATE_EXCEEDED" in decision.reason_codes


def test_zero_consumption_refusal_breach_is_ineligible():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(
            completed=8,
            failed=2,
            zero_refusals=2,
            consumed=8,
        ),
        policy=policy(max_zero_refusal=0.10),
    )

    assert decision.decision_status == "INELIGIBLE"
    assert (
        "ZERO_CONSUMPTION_REFUSAL_RATE_EXCEEDED"
        in decision.reason_codes
    )


def test_unknown_consumption_fails_closed_when_required():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(consumed=None),
        policy=policy(require_known=True),
    )

    assert decision.decision_status == "INELIGIBLE"
    assert "UNKNOWN_REQUEST_CONSUMPTION" in decision.reason_codes


def test_degraded_snapshot_is_ineligible():
    decision = evaluate_tennis_provider_health(
        snapshot=snapshot(status="DEGRADED"),
        policy=policy(),
    )

    assert decision.decision_status == "INELIGIBLE"
    assert "SNAPSHOT_NOT_VALID" in decision.reason_codes


def test_cross_sport_adapter_fails_closed():
    decision = evaluate_football_provider_health(
        snapshot=snapshot(sport="tennis"),
        policy=policy(),
    )

    assert decision.decision_status == "INELIGIBLE"
    assert decision.scheduling_eligible is False
    assert "SPORT_BOUNDARY_VIOLATION" in decision.reason_codes


def test_policy_fingerprint_is_deterministic():
    first = policy().fingerprint()
    second = policy().fingerprint()

    assert first == second
    assert len(first) == 64


def test_decision_fingerprint_changes_with_policy():
    snap = snapshot()

    first = evaluate_tennis_provider_health(
        snapshot=snap,
        policy=policy(max_failure=0.20),
    )
    second = evaluate_tennis_provider_health(
        snapshot=snap,
        policy=policy(max_failure=0.10),
    )

    assert first.decision_fingerprint != second.decision_fingerprint


def test_safety_flags_keep_automatic_switching_disabled():
    payload = evaluate_tennis_provider_health(
        snapshot=snapshot(),
        policy=policy(),
    ).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False


def test_invalid_policy_thresholds_are_rejected():
    with pytest.raises(ValueError, match="INVALID_MAX_FAILURE_RATE"):
        policy(max_failure=1.1)

    with pytest.raises(
        ValueError,
        match="INVALID_MIN_TERMINAL_CALLS",
    ):
        policy(min_calls=0)
