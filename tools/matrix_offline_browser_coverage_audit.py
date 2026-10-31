"""Offline, redacted audit of local browser quote recovery evidence.

No network calls, no Telegram, no betting. Read-only. Missing data is unknown.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FILES = {
    "cdp": "MATRIX_BROWSER_CDP_COLLECTION_LAST.json",
    "recovery": "MATRIX_QUOTE_RECOVERY_ACTUATOR_LAST.json",
    "health": "MATRIX_SELF_HOSTED_BROWSER_HEALTH_LAST.json",
    "betano": "MATRIX_BETANO_EVENT_LINK_PROBE_LAST.json",
}
FIELDS = {
    "cdp": ("status", "generated_at_utc", "authorized_book_pages_captured", "betano_exact_quote_count", "candidate_count_in_final_window"),
    "recovery": ("status", "generated_at_utc", "eligible_candidates_in_window", "window_minutes"),
    "health": ("status", "checked_at_utc", "websocket_present"),
    "betano": ("status", "generated_at_utc", "count", "api_match_context_count", "network_resource_count", "prematch_candidate_probe_count"),
}


def audit(directory: Path) -> dict:
    result = {"schema": "MATRIX_OFFLINE_BROWSER_COVERAGE_AUDIT_V1", "sources": {}, "blockers": [],
              "operational_certified": False, "telegram_delivery_certified": False,
              "real_money": "BLOCKED", "automatic_wagering": False}
    for label, filename in FILES.items():
        path = directory / filename
        if not path.is_file():
            result["blockers"].append(label.upper() + "_FILE_MISSING")
            result["sources"][label] = {"present": False}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("ROOT_NOT_OBJECT")
            result["sources"][label] = {"present": True, **{k: data.get(k) for k in FIELDS[label]}}
            if label == "cdp":
                matches = data.get("matches")
                adapter_counts = {}
                unique_fixtures = set()
                if isinstance(matches, list):
                    for item in matches:
                        if not isinstance(item, dict):
                            continue
                        fixture_id = item.get("fixture_id")
                        if isinstance(fixture_id, (str, int)) and not isinstance(fixture_id, bool):
                            unique_fixtures.add(str(fixture_id))
                        status = item.get("adapter_status")
                        blocker = item.get("blocker")
                        if status in ("CERTIFIED_EXACT_OVER25", "CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION"):
                            key = status
                        else:
                            key = "OTHER_OR_UNKNOWN"
                        if blocker in ("BOOKMAKER_ADAPTER_NOT_CERTIFIED", "ODDS_BELOW_MIN_1_50"):
                            key += ":" + blocker
                        else:
                            key += ":OTHER_OR_UNKNOWN"
                        adapter_counts[key] = adapter_counts.get(key, 0) + 1
                result["sources"][label]["unique_fixture_count"] = len(unique_fixtures) if isinstance(matches, list) else None
                result["sources"][label]["adapter_outcome_counts"] = adapter_counts
            if label == "recovery":
                counts = data.get("counts")
                result["sources"][label]["counts"] = {
                    k: v for k, v in counts.items()
                    if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
                } if isinstance(counts, dict) else None
                statuses = {}
                for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
                    if isinstance(item, dict) and isinstance(item.get("status"), str):
                        status = item["status"]
                        if status in ("NO_SIGNAL_ECONOMIC_GATE", "NO_SIGNAL_STALE", "NO_SIGNAL_NO_QUOTE", "NO_SIGNAL_KICKOFF", "PASS", "BLOCKED"):
                            statuses[status] = statuses.get(status, 0) + 1
                        else:
                            statuses["OTHER_OR_UNKNOWN"] = statuses.get("OTHER_OR_UNKNOWN", 0) + 1
                result["sources"][label]["result_status_counts"] = statuses
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            result["sources"][label] = {"present": True, "parsed": False}
            result["blockers"].append(label.upper() + "_PARSE_FAILED")
    cdp = result["sources"].get("cdp", {})
    if cdp.get("betano_exact_quote_count") == 1 and cdp.get("candidate_count_in_final_window") == 1:
        result["observation"] = "ONE_EXACT_QUOTE_FOR_ONE_FINAL_WINDOW_CANDIDATE; OTHER_EVENT_COVERAGE_NOT_ESTABLISHED"
    result["blockers"].append("CURRENT_PROVIDER_FRESHNESS_UNVERIFIED")
    result["blockers"].append("END_TO_END_TELEGRAM_UNVERIFIED")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("evidence/notifications/telegram"))
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
