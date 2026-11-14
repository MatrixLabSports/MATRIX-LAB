"""MATRIX calendar source reconciliation guard. Offline and fail-closed."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "football_sofascore": "MATRIX_SOFASCORE_FOOTBALL_LINKS_20261031.json",
    "football_flashscore": "MATRIX_FLASHSCORE_FOOTBALL_UNFILTERED_SAMPLE_20261031.json",
    "tennis_sofascore": "MATRIX_SOFASCORE_OPERA_TENNIS_SAMPLE_20261031.json",
    "tennis_flashscore": "MATRIX_FLASHscore_OPERA_TENNIS_DISCOVERY_20261031.json",
}
ALLOWED = {"sofascore.com", "www.sofascore.com", "flashscore.co", "www.flashscore.co"}

def validate_record(record, source):
    if not isinstance(record, dict):
        return "INVALID_RECORD"
    name, url = record.get("name"), record.get("url")
    if not isinstance(name, str) or not name.strip() or not isinstance(url, str):
        return "MISSING_NAME_OR_URL"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED:
        return "UNTRUSTED_URL"
    expected = "/football/match/" if source.startswith("football_sofascore") else (
        "/tennis/match/" if source.startswith("tennis_sofascore") else (
            "/partido/futbol/" if source.startswith("football_") else "/partido/tenis/"))
    if expected not in parsed.path:
        return "WRONG_SPORT_OR_PATH"
    return "PENDING_DATE_KICKOFF_AND_CROSS_SOURCE_CERTIFICATION"

def audit(inbox):
    report = {"schema": "MATRIX_CALENDAR_SOURCE_RECONCILIATION_GUARD_V1",
              "target_date_bogota": "2026-10-31", "status": "FAIL_CLOSED",
              "approved_prematch": 0, "approved_telegram": 0,
              "real_money": "BLOCKED", "automatic_wagering": False, "sources": {}}
    for source, filename in SOURCES.items():
        path = inbox / filename
        if not path.is_file():
            report["sources"][source] = {"status": "MISSING", "total": 0}
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload["observations"]
            if not isinstance(records, list):
                raise ValueError("observations must be list")
        except (ValueError, KeyError, TypeError):
            report["sources"][source] = {"status": "INVALID", "total": 0}
            continue
        reasons, seen = {}, set()
        for record in records:
            reason = validate_record(record, source)
            if reason.startswith("PENDING"):
                key = record["url"].split("#")[0].split("?")[0]
                if key in seen:
                    reason = "DUPLICATE_SOURCE_URL"
                seen.add(key)
            reasons[reason] = reasons.get(reason, 0) + 1
        report["sources"][source] = {"status": "UNVERIFIED", "total": len(records),
                                     "unique_urls": len(seen), "reasons": reasons}
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox", type=Path, default=ROOT / "evidence/browser_capture_inbox")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.inbox)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
