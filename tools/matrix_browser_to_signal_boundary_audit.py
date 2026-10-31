"""Offline audit of browser discovery versus canonical Telegram candidate roots.

This module deliberately NEVER promotes browser discovery into signal inputs.
"""
import argparse
import json
from pathlib import Path

BROWSER = Path("evidence/browser_capture_inbox")
FOOTBALL = Path("evidence/api_football/daily_prematch_reports")
TENNIS = Path("evidence/tennis_signals")
FOOTBALL_PATTERNS = ("browser_physical_verification/*.json", "shadow_quote_freeze/*.json", "over25_shadow_ev/*.json")


def audit(date, browser=BROWSER, football=FOOTBALL, tennis=TENNIS):
    if len(date) != 10 or date[4] != "-" or date[7] != "-" or not date.replace("-", "").isdigit():
        raise ValueError("DATE_FORMAT_YYYY_MM_DD_REQUIRED")
    tennis_discovery = browser / ("MATRIX_SOFASCORE_TENNIS_" + date.replace("-", "") + "_FULL_LINK_DISCOVERY.json")
    sources = {
        "browser_tennis_discovery": {"path": str(tennis_discovery), "exists": tennis_discovery.is_file()},
        "tennis_canonical": {"path": str(tennis / date), "exists": (tennis / date).is_dir(), "json_count": len(list((tennis / date).glob("*.json")))},
        "football_canonical": {"path": str(football / date), "exists": (football / date).is_dir(), "counts": {pattern: len(list((football / date).glob(pattern))) for pattern in FOOTBALL_PATTERNS}},
    }
    return {
        "schema": "MATRIX_BROWSER_TO_SIGNAL_BOUNDARY_AUDIT_V1",
        "date": date,
        "status": "SOURCE_PATH_AUDIT_ONLY",
        "sources": sources,
        "browser_discovery_is_signal_input": False,
        "auto_promotion_authorized": False,
        "signals_sent": 0,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.date)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
