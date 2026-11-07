from datetime import datetime,timedelta,timezone
from tools.matrix_quote_recovery_actuator import _eligible_rows
from tools.telegram_green_signal_alerts import physical_book_over25_offer

def test_only_final_window_candidates_are_actuated():
    now=datetime.now(timezone.utc)
    audit={"records":[
      {"fixture_id":"a","kickoff":(now+timedelta(minutes=90)).isoformat(),"p_matrix":0.65,"state":"BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"},
      {"fixture_id":"b","kickoff":(now+timedelta(minutes=150)).isoformat(),"p_matrix":0.70,"state":"WAITING_FINAL_REVALIDATION_WINDOW"},
      {"fixture_id":"c","kickoff":(now-timedelta(minutes=1)).isoformat(),"p_matrix":0.80,"state":"BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"},
      {"fixture_id":"d","kickoff":(now+timedelta(minutes=60)).isoformat(),"p_matrix":0.59,"state":"BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"},
    ]}
    rows=_eligible_rows(audit,now)
    assert [x["fixture_id"] for x in rows]==["a"]


def test_physical_betano_quote_below_min_reaches_economic_gate(tmp_path):
    now=datetime(2026,10,29,1,0,tzinfo=timezone.utc)
    root=tmp_path/"inventory"
    day=root/"20261029"
    day.mkdir(parents=True)
    p=day/"MATRIX_BETANO_QUOTE_1490582.json"
    p.write_text(__import__("json").dumps({
      "schema":"MATRIX_PHYSICAL_BOOK_QUOTE_V1",
      "fixture_id":"1490582",
      "market":"Más de 2.5 goles",
      "house":"Betano",
      "decimal_odds":1.31,
      "captured_at_utc":"2026-10-29T00:59:00+00:00",
      "kickoff_utc":"2026-10-29T02:30:00+00:00"
    }),encoding="utf-8")
    offer=physical_book_over25_offer("1490582",0.6511733445,now,root=root)
    assert offer is not None
    assert offer["house"]=="Betano"
    assert offer["odds"]==1.31
    assert offer["ev"]==0.6511733445*1.31-1.0
    assert offer["odds"]<=1.50
