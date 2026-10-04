from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.core.execution_evidence import (
    ExecutionEvidence,
    audit_future_execution_compliance,
    verify_screenshot_bytes,
)

UTC = timezone.utc


def valid_record(**overrides):
    raw = b"future execution screenshot bytes"
    data = dict(
        execution_id="exec-1",
        sport="tennis",
        event_id="event-1",
        market_key="match_winner",
        selection_key="player_1",
        bookmaker="BetPlay",
        stake=500.0,
        decimal_odds=1.91,
        evidence_captured_at=datetime(2026, 9, 24, 18, 0, tzinfo=UTC),
        executed_at=datetime(2026, 9, 24, 18, 0, 5, tzinfo=UTC),
        screenshot_sha256=sha256(raw).hexdigest(),
        screenshot_reference="evidence/executions/exec-1.png",
    )
    data.update(overrides)
    return ExecutionEvidence(**data), raw


def test_zero_future_executions_is_not_success():
    result = audit_future_execution_compliance([])
    assert result.acceptance_demonstrated is False
    assert result.compliance_rate is None
    assert result.status == "EVIDENCE_INSUFFICIENT_NO_FUTURE_EXECUTIONS"


def test_valid_future_execution_is_100_percent_compliant():
    record, raw = valid_record()
    assert verify_screenshot_bytes(record, raw) is True
    result = audit_future_execution_compliance([record])
    assert result.acceptance_demonstrated is True
    assert result.compliance_rate == 1.0


@pytest.mark.parametrize("field,value", [("bookmaker", ""), ("stake", 0), ("stake", -1)])
def test_missing_house_or_invalid_stake_fails_closed(field, value):
    with pytest.raises((ValueError, TypeError)):
        valid_record(**{field: value})


def test_tampered_screenshot_fails_verification():
    record, _ = valid_record()
    assert verify_screenshot_bytes(record, b"different bytes") is False


def test_invalid_screenshot_digest_fails_closed():
    with pytest.raises(ValueError):
        valid_record(screenshot_sha256="not-a-digest")
