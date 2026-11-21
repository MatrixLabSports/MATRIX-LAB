from __future__ import annotations
import json
from pathlib import Path

POLICY = Path("app/market/colombia_bookmakers.py")
EVIDENCE = Path("evidence/notifications/telegram/MATRIX_COLOMBIA_BOOKMAKER_OPERA_COVERAGE_20261028.json")

EXPECTED = (
    "betano","betplay","betsson","bwin","codere","luckia","mryoker",
    "rivalo","rushbet","sportium","stake","wplay","yajuego","zamba",
)

def validate() -> dict:
    data=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    rows=data["execution_bookmakers"]
    keys=tuple(x["key"] for x in rows)
    if keys != EXPECTED:
        raise SystemExit("OPERA_BOOKMAKER_COVERAGE_KEY_MISMATCH")
    if data["summary"]["configured_execution_houses"] != 14:
        raise SystemExit("OPERA_BOOKMAKER_CONFIGURED_COUNT_INVALID")
    if data["summary"]["opera_open_observed"] + data["summary"]["opera_not_observed_open"] != 14:
        raise SystemExit("OPERA_BOOKMAKER_COVERAGE_TOTAL_INVALID")
    if data["interpretation"]["configured_does_not_mean_physically_open"] is not True:
        raise SystemExit("OPERA_BOOKMAKER_PHYSICAL_DISTINCTION_MISSING")
    if data["interpretation"]["no_app_installation_required"] is not True:
        raise SystemExit("OPERA_BOOKMAKER_INSTALLATION_POLICY_INVALID")
    if data["governance"]["automatic_wagering"] is not False or data["governance"]["real_money"] != "BLOCKED":
        raise SystemExit("OPERA_BOOKMAKER_SAFETY_GUARD_INVALID")
    return data

if __name__ == "__main__":
    d=validate()
    print(json.dumps({"status":"PASS", **d["summary"]}, sort_keys=True))
