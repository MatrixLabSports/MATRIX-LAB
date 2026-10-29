"""Build a fail-closed per-fixture temporal quarantine from a clock crosscheck."""
import argparse
import json
from pathlib import Path


def build(data):
    rows = []
    reasons = {"CLOCK_STRING_MATCH": "TIMEZONE_NOT_CERTIFIED",
               "CLOCK_STRING_MISMATCH": "CROSS_SOURCE_CLOCK_CONFLICT",
               "NOT_COMPARABLE": "CROSS_SOURCE_CLOCK_UNAVAILABLE"}
    for item in data["rows"]:
        state = item["display_clock_comparison"]
        if state not in reasons:
            raise ValueError("UNKNOWN_CLOCK_STATE")
        postponed = "Aplazado" in item["sofascore"]
        reason = "POSTPONED_IN_SOFASCORE" if postponed else reasons[state]
        rows.append({"flashscore_observation": item["flashscore"],
                     "sofascore_observation": item["sofascore"],
                     "clock_status": state, "block_reason": reason,
                     "flashscore_display_clock": item.get("flashscore_normalized_clock"),
                     "sofascore_display_clock": item.get("sofascore_normalized_clock"),
                     "flashscore_clock_visible": item.get("flashscore_normalized_clock") is not None,
                     "sofascore_postponed": postponed,
                     "eligible_for_freeze": False,
                     "eligible_for_telegram_signal": False})
    return {"schema": "MATRIX_TEMPORAL_QUARANTINE_V1",
            "target_date_bogota": data["target_date_bogota"],
            "rows": rows,
            "counts": {"total": len(rows), "eligible_for_freeze": 0,
                       "eligible_for_telegram_signal": 0},
            "policy": {"timezone_certified": False, "real_money": "BLOCKED",
                       "automatic_wagering": False}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="evidence/calendar_reconciliation/MATRIX_FOOTBALL_CLOCK_STRING_CROSSCHECK_LAST.json")
    p.add_argument("--output", default="evidence/calendar_reconciliation/MATRIX_FOOTBALL_TEMPORAL_QUARANTINE_LAST.json")
    a = p.parse_args()
    result = build(json.loads(Path(a.source).read_text(encoding="utf-8")))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    assert json.loads(out.read_text(encoding="utf-8")) == result
    print(json.dumps(result["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
