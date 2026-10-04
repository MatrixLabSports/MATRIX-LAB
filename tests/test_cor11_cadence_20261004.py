import json
from pathlib import Path


def test_cor11_cadence_14_of_14_and_blocked():
    p = Path("evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_20261004.json")
    d = json.loads(p.read_text())
    assert d["status"] == "RESOLVED"
    assert d["cadence_days_observed"] == 14
    assert d["cadence_days_required"] == 14
    assert d["consecutive_local_dates"] == [
        "2026-09-21","2026-09-22","2026-09-23","2026-09-24","2026-09-25","2026-09-26","2026-09-27",
        "2026-09-28","2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-03","2026-10-04"
    ]
    assert d["controls"]["no_utc_rollover"] is True
    assert d["controls"]["no_backfill"] is True
    assert d["controls"]["no_synthetic_days"] is True
    assert d["controls"]["real_money"] == "BLOCKED"
