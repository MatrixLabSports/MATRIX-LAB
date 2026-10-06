from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from app.notifications.telegram_pick_notifier import TelegramDispatchLedger,TelegramDispatchResult,TelegramPickCard,format_pick_message
UTC=timezone.utc
FREEZE=datetime(2026,10,5,20,0,tzinfo=UTC)
START=FREEZE+timedelta(hours=2)
def card(**overrides):
    data=dict(pick_id="pick-main-001",mode="SHADOW",sport="football",event_id="fixture-1",event_name="Equipo A vs Equipo B",market="1X2",selection="Equipo A",bookmaker="betplay",decimal_odds=2.0,p_matrix=.60,implied_probability=.50,expected_value=.20,stake_amount=0.0,stake_currency="COP",freeze_at_utc=FREEZE,event_start_at_utc=START,calibration_gate_pass=False,real_money_gate_open=False,automatic_wagering=False,odds_used_as_model_input=False,model_binding="MATRIX_TEST_V1",price_freeze_sha256="a"*64)
    data.update(overrides); return TelegramPickCard(**data)
def test_shadow_governance_and_message():
    c=card(); text=format_pick_message(c)
    assert "MATRIX SHADOW" in text and "NO APOSTAR" in text and "Stake: 0" in text
def test_shadow_rejects_money_and_odds_input():
    with pytest.raises(ValueError,match="SHADOW_STAKE_MUST_BE_ZERO"): card(stake_amount=1)
    with pytest.raises(ValueError,match="ODDS_TO_P_MATRIX_FORBIDDEN"): card(odds_used_as_model_input=True)
def test_odds_floor_and_reference_bookmaker():
    with pytest.raises(ValueError,match="ODDS_NOT_ABOVE_PERMANENT_MINIMUM"): card(decimal_odds=1.5,implied_probability=2/3,expected_value=0.0)
    with pytest.raises(ValueError,match="BOOKMAKER_NOT_EXECUTION_ELIGIBLE"): card(bookmaker="pinnacle")
def test_append_only_ledger(tmp_path:Path):
    c=card(); r=TelegramDispatchResult(1,"shadow","pick-main-001","b"*64); ledger=TelegramDispatchLedger(tmp_path/"ledger.jsonl")
    row=ledger.append(c,r); assert row["automatic_wagering"] is False and row["real_money_gate_open"] is False
    with pytest.raises(ValueError,match="ALREADY_DISPATCHED"): ledger.append(c,r)
