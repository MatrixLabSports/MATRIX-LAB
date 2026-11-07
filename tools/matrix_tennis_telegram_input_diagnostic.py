"""Read-only diagnostic of canonical tennis input for Telegram.

No API keys, requests, bets, fabricated fixtures, or signals.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("evidence/tennis_signals")


def inspect(root: Path, day: str) -> dict:
    folder = root / day
    result = {"date_bogota": day, "canonical_path": str(folder),
              "directory_exists": folder.is_dir(), "json_files": 0,
              "rows_total": 0, "rows_governed": 0, "rows_with_physical_quote": 0,
              "rows_with_numeric_model_and_odds": 0, "rows_positive_ev_and_odds_gt_1_50": 0,
              "status": "NO_CANONICAL_TENNIS_INPUT"}
    if not folder.is_dir():
        return result
    for path in sorted(folder.glob("*.json")):
        result["json_files"] += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            result["rows_total"] += 1
            if str(row.get("governance_status") or "").upper() not in {"VALIDATED", "STRONG", "PROMOTED"}:
                continue
            result["rows_governed"] += 1
            if row.get("physical_quote_verified") is not True:
                continue
            result["rows_with_physical_quote"] += 1
            try:
                p, odds, ev = (float(row[k]) for k in ("p_matrix", "decimal_odds", "ev"))
            except (ValueError, TypeError, KeyError):
                continue
            result["rows_with_numeric_model_and_odds"] += 1
            if 0 < p < 1 and odds > 1.50 and ev > 0:
                result["rows_positive_ev_and_odds_gt_1_50"] += 1
    result["status"] = "INPUT_PRESENT_REQUIRES_END_TO_END_VERIFICATION"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("America/Bogota")).date().isoformat())
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    print(json.dumps(inspect(Path(args.root), args.date), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
