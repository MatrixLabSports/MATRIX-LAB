from dataclasses import replace

import pytest

from app.application.football.provider_scheduling_authorization import (
    authorize_football_provider_scheduling,
)
from app.application.tennis.provider_scheduling_authorization import (
    authorize_tennis_provider_scheduling,
)
from app.core.provider_health_policy import ProviderHealthDecision


def decision(
    provider_key="P1",
    *,
    sport="tennis",
    status="ELIGIBLE",
    eligible=True,
    char="1",
):
    return ProviderHealthDecision(
        provider_key=provider_key,
        sport=sport,
        decision_status=status,
        scheduling_eligible=eligible,
        terminal_calls=10,
        failure_rate=0.0,
        zero_consumption_refusal_rate=0.0,
        policy_fingerprint="a" * 64,
        snapshot_fingerprint="b" * 64,
        reason_codes=(),
        decision_fingerprint=char * 64,
    )


def item(
    provider_key="P1",
    *,
    sport="tennis",
    char="1",
):
    return {
        "sport": sport,
        "subject_key": "PLAYER:1",
        "provider_key": provider_key,
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": 1,
        "source_fingerprint": "c" * 64,
    }


def manifest(*items, sport="tennis"):
    return {
        "sport": sport,
        "queue": list(items),
    }


def test_all_eligible_providers_authorize_execution():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(
            item("P1", char="1"),
            item("P2", char="2"),
        ),
        health_decisions={
            "P1": decision("P1", char="1"),
            "P2": decision("P2", char="2"),
        },
    )

    assert result.authorization_status == "AUTHORIZED"
    assert result.execution_eligible is True
    assert result.eligible_provider_keys == ("P1", "P2")
    assert result.blocked_provider_keys == ()
    assert result.missing_provider_keys == ()


def test_ineligible_provider_blocks_entire_execution():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={
            "P1": decision(
                "P1",
                status="INELIGIBLE",
                eligible=False,
            )
        },
    )

    assert result.authorization_status == "BLOCKED"
    assert result.execution_eligible is False
    assert result.blocked_provider_keys == ("P1",)
    assert any(
        reason.startswith("PROVIDER_NOT_ELIGIBLE:P1:")
        for reason in result.reason_codes
    )


def test_review_required_provider_blocks_entire_execution():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={
            "P1": decision(
                "P1",
                status="REVIEW_REQUIRED",
                eligible=False,
            )
        },
    )

    assert result.authorization_status == "BLOCKED"
    assert result.execution_eligible is False


def test_missing_decision_fails_closed():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={},
    )

    assert result.authorization_status == "BLOCKED"
    assert result.execution_eligible is False
    assert result.missing_provider_keys == ("P1",)
    assert "MISSING_HEALTH_DECISION:P1" in result.reason_codes


def test_cross_sport_decision_is_blocked():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={
            "P1": decision("P1", sport="football")
        },
    )

    assert result.authorization_status == "BLOCKED"
    assert result.execution_eligible is False
    assert "SPORT_BOUNDARY_VIOLATION:P1" in result.reason_codes


def test_cross_sport_manifest_is_rejected_by_adapter():
    with pytest.raises(ValueError, match="SPORT_BOUNDARY_VIOLATION"):
        authorize_football_provider_scheduling(
            queue_manifest=manifest(
                item("P1", sport="tennis"),
                sport="tennis",
            ),
            health_decisions={
                "P1": decision("P1", sport="tennis")
            },
        )


def test_empty_queue_is_explicitly_safe():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(),
        health_decisions={},
    )

    assert result.authorization_status == "EMPTY_QUEUE"
    assert result.execution_eligible is True
    assert result.provider_keys == ()


def test_provider_decision_key_mismatch_fails_closed():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={
            "P1": decision("P2")
        },
    )

    assert result.authorization_status == "BLOCKED"
    assert "PROVIDER_DECISION_MISMATCH:P1" in result.reason_codes


def test_authorization_fingerprint_is_deterministic():
    kwargs = {
        "queue_manifest": manifest(item("P1")),
        "health_decisions": {"P1": decision("P1")},
    }

    first = authorize_tennis_provider_scheduling(**kwargs)
    second = authorize_tennis_provider_scheduling(**kwargs)

    assert first.authorization_fingerprint == second.authorization_fingerprint
    assert len(first.authorization_fingerprint) == 64


def test_payload_keeps_automatic_switching_disabled():
    result = authorize_tennis_provider_scheduling(
        queue_manifest=manifest(item("P1")),
        health_decisions={"P1": decision("P1")},
    )

    payload = result.payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
