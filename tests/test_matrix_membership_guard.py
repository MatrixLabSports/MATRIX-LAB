from datetime import datetime, timezone
from tools.matrix_membership_guard import membership_state

NOW=datetime(2026,10,28,10,0,tzinfo=timezone.utc)

def rec(exp,payment="VERIFIED"):
    return {"expires_at_utc":exp,"payment_status":payment}

def test_membership_states():
    assert membership_state(rec("2026-10-31T10:00:00Z"),NOW)=="ACTIVE"
    assert membership_state(rec("2026-10-30T09:00:00Z"),NOW)=="EXPIRING_48H"
    assert membership_state(rec("2026-10-29T09:00:00Z"),NOW)=="EXPIRING_24H"
    assert membership_state(rec("2026-10-28T09:59:59Z"),NOW)=="EXPIRED"
    assert membership_state(rec("2026-10-31T10:00:00Z","PENDING"),NOW)=="PENDING_PAYMENT"
