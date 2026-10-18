import json
from pathlib import Path


def test_cor11_cadence_14_of_14_and_blocked():
    p = Path("evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_20261004.json")
    d = json.loads(p.read_text())
    assert d["status"] == "RESOLVED"
    assert d["real_consecutive_days"] == 14
    assert d["target_days"] == 14
    assert d["dates"] == [
        "2026-09-21","2026-09-22","2026-09-23","2026-09-24","2026-09-25","2026-09-26","2026-09-27",
        "2026-09-28","2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-03","2026-10-04"
    ]
    assert d["rules"]["utc_rollover_used"] is False
    assert d["rules"]["backfill"] is False
    assert d["rules"]["synthetic_days"] is False
    assert d["rules"]["real_money"] == "BLOCKED"
    assert d["rules"]["settlement"] == "FINAL_ONLY"
