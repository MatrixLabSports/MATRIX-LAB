from datetime import datetime,timedelta,timezone
from tools.matrix_quote_recovery_actuator import _eligible_rows

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
