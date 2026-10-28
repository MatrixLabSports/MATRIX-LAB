import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tools.telegram_green_signal_alerts import recovery_execution_over25_offer

def test_recovery_execution_offer_is_consumable(tmp_path:Path):
    now=datetime.now(timezone.utc)
    ledger=tmp_path/"ledger.jsonl"
    row={
      "schema":"MATRIX_QUOTE_RECOVERY_EXECUTION_EVIDENCE_V1",
      "validated":True,
      "fixture_id":"123",
      "market":"OVER_2_5",
      "bookmaker":"Betano",
      "decimal_odds":1.70,
      "quote_observed_at_utc":(now-timedelta(minutes=2)).isoformat(),
      "kickoff_utc":(now+timedelta(minutes=60)).isoformat(),
      "p_matrix":0.65,
      "revalidated_ev":0.105,
      "source_evidence":"physical-test",
      "record_sha256":"abc",
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }
    ledger.write_text(json.dumps(row)+"\n",encoding="utf-8")
    offer=recovery_execution_over25_offer("123",0.65,now,ledger_path=ledger)
    assert offer is not None
    assert offer["provider"]=="quote-recovery-actuator"
    assert offer["odds"]==1.70
    assert offer["ev"]>0.05

def test_stale_recovery_execution_offer_is_rejected(tmp_path:Path):
    now=datetime.now(timezone.utc)
    ledger=tmp_path/"ledger.jsonl"
    row={
      "validated":True,"fixture_id":"123","market":"OVER_2_5","bookmaker":"Betano",
      "decimal_odds":1.70,"quote_observed_at_utc":(now-timedelta(minutes=31)).isoformat(),
      "kickoff_utc":(now+timedelta(minutes=60)).isoformat(),"record_sha256":"abc"
    }
    ledger.write_text(json.dumps(row)+"\n",encoding="utf-8")
    assert recovery_execution_over25_offer("123",0.65,now,ledger_path=ledger) is None
