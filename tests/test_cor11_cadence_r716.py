import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_R716.json"


def load():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_r716_cor11_counts_only_real_consecutive_days():
    x = load()
    assert x["current_consecutive_days"] == 5
    assert x["target_days"] == 14
    assert x["remaining_real_days"] == 9
    assert [d["date"] for d in x["days"]] == [
        "2026-09-21",
        "2026-09-22",
        "2026-09-23",
        "2026-09-24",
        "2026-09-25",
    ]
    assert all(d["status"] == "REAL_COMPLIANT_DAY" for d in x["days"])


def test_r716_cor11_anti_fabrication_is_preserved():
    x = load()
    assert x["anti_fabrication"]["synthetic_days"] == 0
    assert x["anti_fabrication"]["backfilled_days"] == 0
    assert x["anti_fabrication"]["utc_rollover_used_as_local_day"] is False
    assert x["status"] == "IN_PROGRESS"
    assert x["real_money"] == "BLOCKED"


def test_r716_day5_has_physical_evidence():
    x = load()
    d = x["days"][-1]
    commits = {e["commit"] for e in d["evidence"]}
    assert "68d029192e4cc3a6f843b41dfde1e5d5f969240a" in commits
    assert "87a8178045a744d37e2f4ac2dd5dc4a04951440d" in commits
    assert "b5c3bf9f1e6fca337addc42398d69bd0870ef482" in commits
    assert d["compliance"]["synthetic_day"] is False
    assert d["compliance"]["backfilled_day"] is False
