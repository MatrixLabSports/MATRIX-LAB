from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.notifications.telegram_pick_notifier import (
    TelegramDispatchLedger,
    TelegramPickCard,
    format_pick_message,
    send_pick,
)

UTC = timezone.utc
FREEZE = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
START = FREEZE + timedelta(hours=2)


def card(**overrides):
    data = dict(
        pick_id="pick-001",
        mode="SHADOW",
        sport="football",
        event_id="fixture-1",
        event_name="Equipo A vs Equipo B",
        market="1X2",
        selection="Equipo A",
        bookmaker="betplay",
        decimal_odds=2.00,
        p_matrix=0.60,
        implied_probability=0.50,
        expected_value=0.20,
        stake_amount=0.0,
        stake_currency="COP",
        freeze_at_utc=FREEZE,
        event_start_at_utc=START,
        calibration_gate_pass=False,
        real_money_gate_open=False,
        automatic_wagering=False,
        odds_used_as_model_input=False,
        model_binding="MATRIX_TEST_V1",
        price_freeze_sha256="a" * 64,
    )
    data.update(overrides)
    return TelegramPickCard(**data)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise RuntimeError("HTTP_ERROR")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload=None):
        self.payload = payload or {
            "ok": True,
            "result": {"message_id": 77},
        }
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payload)


def test_shadow_pick_is_clearly_marked_no_bet():
    message = format_pick_message(card())
    assert "MATRIX SHADOW" in message
    assert "NO APOSTAR" in message
    assert "Stake: 0" in message
    assert "Probabilidad MATRIX: 60.00%" in message
    assert "Valor esperado: +20.00%" in message


def test_shadow_cannot_carry_real_stake():
    with pytest.raises(ValueError, match="SHADOW_STAKE_MUST_BE_ZERO"):
        card(stake_amount=1000)


def test_controlled_live_requires_calibration_and_real_money_open():
    with pytest.raises(ValueError, match="CONTROLLED_LIVE_REQUIRES_CALIBRATION_PASS"):
        card(
            mode="CONTROLLED_LIVE",
            stake_amount=1000,
            real_money_gate_open=True,
            calibration_gate_pass=False,
        )
    with pytest.raises(ValueError, match="CONTROLLED_LIVE_REQUIRES_REAL_MONEY_OPEN"):
        card(
            mode="CONTROLLED_LIVE",
            stake_amount=1000,
            real_money_gate_open=False,
            calibration_gate_pass=True,
        )


def test_controlled_live_valid_after_all_gates():
    c = card(
        mode="CONTROLLED_LIVE",
        stake_amount=1000,
        real_money_gate_open=True,
        calibration_gate_pass=True,
    )
    message = format_pick_message(c)
    assert "MATRIX CONTROLLED LIVE" in message
    assert "Stake: 1,000 COP" in message


def test_non_execution_bookmaker_cannot_be_sent():
    with pytest.raises(ValueError, match="BOOKMAKER_NOT_EXECUTION_ELIGIBLE"):
        card(bookmaker="pinnacle")


def test_permanent_minimum_odds_is_enforced():
    with pytest.raises(ValueError, match="ODDS_NOT_ABOVE_PERMANENT_MINIMUM"):
        card(decimal_odds=1.50, implied_probability=2/3, expected_value=-0.10)


def test_odds_cannot_be_model_input():
    with pytest.raises(ValueError, match="ODDS_TO_P_MATRIX_FORBIDDEN"):
        card(odds_used_as_model_input=True)


def test_pick_must_be_prematch():
    with pytest.raises(ValueError, match="PICK_NOT_PREMATCH"):
        card(freeze_at_utc=START)


def test_send_pick_uses_official_send_message_endpoint_without_logging_token():
    session = FakeSession()
    result = send_pick(
        card(),
        bot_token="123456:ABCDEF",
        chat_id="-1001234567890",
        session=session,
    )
    assert result.message_id == 77
    assert result.chat_id == "-1001234567890"
    assert result.pick_id == "pick-001"
    assert len(result.message_sha256) == 64
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"].endswith("/bot123456:ABCDEF/sendMessage")
    assert call["json"]["chat_id"] == "-1001234567890"
    assert call["json"]["protect_content"] is True
    assert "MATRIX SHADOW" in call["json"]["text"]


def test_dispatch_ledger_is_append_only_and_deduplicated(tmp_path: Path):
    session = FakeSession()
    c = card()
    result = send_pick(c, bot_token="123456:ABCDEF", chat_id="1", session=session)
    ledger = TelegramDispatchLedger(tmp_path / "telegram.jsonl")
    row = ledger.append(c, result)
    assert row["pick_id"] == "pick-001"
    assert row["automatic_wagering"] is False
    assert len(row["record_sha256"]) == 64
    with pytest.raises(ValueError, match="ALREADY_DISPATCHED"):
        ledger.append(c, result)
