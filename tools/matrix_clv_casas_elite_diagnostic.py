from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS
from tools.telegram_quote_attempt_telemetry import (
    AUTHORIZED,
    LEGACY_SCHEMAS,
    SCHEMA,
    load_verified,
    summarize_cumulative,
)

ROOT = Path("evidence")
CLV_STATE = ROOT / "clv/football/over_2_5/state.json"
QUOTE_LEDGER = ROOT / "notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPTS.jsonl"
COMMITTEE_CONFIG = Path("config/MATRIX_TELEGRAM_ELITE_COMMITTEE_V1.json")
CATALOG = ROOT / "odds_api_net/colombia_catalog/manifest.json"
OUT = ROOT / "notifications/telegram/MATRIX_DIAGNOSTICO_CLV_Y_CASAS_27OCT2026.json"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def build() -> dict:
    clv = load(CLV_STATE)
    rows = load_verified(QUOTE_LEDGER)
    summary = summarize_cumulative(rows, minimum_target=50, maximum_target=100)
    committee = load(COMMITTEE_CONFIG)
    catalog = load(CATALOG)
    legacy = [r for r in rows if str(r.get("schema") or "") in LEGACY_SCHEMAS]
    current = [r for r in rows if str(r.get("schema") or "") == SCHEMA]

    odds_status = Counter(
        str(((r.get("evidence_snapshot") or {}).get("odds_api_net_diagnostic") or {}).get("status") or "NONE")
        for r in legacy
    )
    api_status = Counter(
        str(((r.get("evidence_snapshot") or {}).get("api_football_offer_diagnostic") or {}).get("status") or "NONE")
        for r in legacy
    )
    final_status = Counter(str(r.get("final_discard_reason") or "NONE") for r in legacy)

    telegram_src = Path("tools/telegram_green_signal_alerts.py").read_text(encoding="utf-8")
    clv_src = Path("tools/football_clv_odds_api_net_capture.py").read_text(encoding="utf-8")
    telemetry_src = Path("tools/telegram_quote_attempt_telemetry.py").read_text(encoding="utf-8")

    code_checks = {
        "telegram_event_pagination_cursor": 'next_cursor = ep.get("next_cursor")' in telegram_src and 'params["cursor"] = cursor' in telegram_src,
        "clv_event_pagination_cursor": 'next_cursor = ep.get("next_cursor")' in clv_src and 'params["cursor"] = cursor' in clv_src,
        "telegram_pagination_fail_closed": "BLOCKED_EVENT_SEARCH_PAGINATION_LIMIT" in telegram_src,
        "all_colombia_execution_books_requested": "ODDS_API_NET_SNAPSHOT_BOOKMAKER_KEYS" in telegram_src,
        "immutable_telemetry_v3": 'SCHEMA="MATRIX_TELEGRAM_QUOTE_ATTEMPT_V3"' in telemetry_src,
        "immutable_telemetry_all_execution_books": set(AUTHORIZED) == set(EXECUTION_BOOKMAKERS),
    }

    legacy_count = len(legacy)
    legacy_not_covered = int(odds_status.get("BLOCKED_EVENT_NOT_COVERED", 0))
    legacy_provider_error = int(odds_status.get("BLOCKED_EVENT_SEARCH_PROVIDER_ERROR", 0))
    historical_discovery_defect_dominant = legacy_count > 0 and legacy_not_covered / legacy_count >= 0.95
    current_provider_error_rows = sum(
        1
        for r in current
        if str(((r.get("evidence_snapshot") or {}).get("odds_api_net_diagnostic") or {}).get("status") or "")
        == "BLOCKED_EVENT_SEARCH_PROVIDER_ERROR"
    )
    catalog_attempts = list(catalog.get("attempts") or [])
    catalog_all_429 = bool(catalog_attempts) and all(int(x.get("http_status") or 0) == 429 for x in catalog_attempts)

    priority = (
        "INTERNAL_DISCOVERY_DEFECT_REPAIRED_NOW_PROVIDER_GATE_IS_PRIMARY_BLOCKER"
        if historical_discovery_defect_dominant and current_provider_error_rows > 0 and catalog_all_429
        else "REMEASURE_BEFORE_FURTHER_REPAIR"
    )

    return {
        "schema": "MATRIX_DIAGNOSTICO_CLV_Y_CASAS_27OCT2026_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "committee": {
            "name": committee.get("name"),
            "role_count": len(committee.get("roles") or []),
        },
        "diagnosis": {
            "historical_internal_root_cause": (
                "ODDS_API_NET_EVENT_DISCOVERY_SINGLE_PAGE_WAS_DOMINANT_PRE_FIX_FAILURE_MODE"
                if historical_discovery_defect_dominant
                else "NOT_PROVEN_DOMINANT"
            ),
            "current_external_root_cause": (
                "ODDS_API_NET_PROVIDER_GATE_HTTP_429_AND_EVENT_SEARCH_PROVIDER_ERROR"
                if current_provider_error_rows > 0 and catalog_all_429
                else "PENDING_PHYSICAL_REMEASUREMENT"
            ),
            "priority": priority,
            "why_first": (
                "The same event-discovery transport feeds multibook execution recovery and sharp-reference recovery. "
                "Fixing it can improve both bookmaker coverage and CLV without relaxing probability, EV, freshness, kickoff, or real-money gates."
            ),
        },
        "clv": {
            "closing_odds_count": clv.get("closing_odds_count"),
            "target": clv.get("minimum_clv_closing_observations"),
            "remaining": clv.get("remaining_to_open_metrics"),
            "decision_count": clv.get("decision_count"),
            "missed_after_kickoff": (clv.get("closing_cycle") or {}).get("missed_after_kickoff"),
            "metrics_opened": clv.get("metrics_opened"),
            "transport": clv.get("closing_reference_transport"),
            "strict_fresh_gate_seconds": (clv.get("closing_freshness_policy") or {}).get("strict_fresh_gate_seconds"),
            "direct_pinnacle_api_connection": clv.get("direct_pinnacle_api_connection"),
        },
        "houses_pre_fix_baseline": {
            "legacy_quote_attempts": legacy_count,
            "odds_api_net_status_counts": dict(sorted(odds_status.items())),
            "api_football_status_counts": dict(sorted(api_status.items())),
            "final_discard_reason_counts": dict(sorted(final_status.items())),
            "event_not_covered_count": legacy_not_covered,
            "provider_error_count": legacy_provider_error,
            "event_not_covered_fraction": (legacy_not_covered / legacy_count if legacy_count else None),
            "historical_discovery_defect_dominant": historical_discovery_defect_dominant,
            "legacy_three_book_diagnostic": summary.get("legacy_three_book_diagnostic"),
            "interpretation": (
                "Legacy V1/V2 telemetry covered Betano, BetPlay and Rushbet only. It is preserved for causal diagnosis "
                "and must not be represented as full 14-book Colombia coverage."
            ),
        },
        "provider_gate_physical_proof": {
            "catalog_http_status": catalog.get("http_status"),
            "catalog_network_calls_performed": catalog.get("network_calls_performed"),
            "catalog_attempt_http_statuses": [x.get("http_status") for x in catalog_attempts],
            "catalog_all_attempts_http_429": catalog_all_429,
            "catalog_provider_rows": catalog.get("provider_rows"),
            "catalog_portfolio_status": catalog.get("portfolio_status"),
            "current_v3_provider_error_rows": current_provider_error_rows,
            "interpretation": "HTTP_429_PROVIDER_GATE_PREVENTS_PHYSICAL_BOOK_SUPPORT_ADJUDICATION; ZERO_CATALOG_ROWS_MUST_NOT_BE_INTERPRETED_AS_ZERO_SUPPORTED_BOOKS",
        },
        "houses_post_fix_contract": {
            "current_schema": SCHEMA,
            "current_real_quote_attempts": len(current),
            "execution_book_count": len(AUTHORIZED),
            "execution_books": list(AUTHORIZED),
            "minimum_new_full_portfolio_revalidations_before_new_coverage_conclusion": 50,
            "recommendation_authorized_now": summary.get("sample_gate_status") == "READY_FOR_CAUSAL_RECOMMENDATION",
        },
        "code_checks": code_checks,
        "repair_adjudication": {
            "internal_code_defects_addressed": all(code_checks.values()),
            "external_provider_coverage_proven_after_fix": len(current) >= 50 and not catalog_all_429,
            "next_measurement": "ACCUMULATE_V3_REAL_REVALIDATIONS_AND_COMPARE_EVENT_MATCH_RATE_BOOK_COVERAGE_AND_FRESH_SHARP_RATE",
            "no_gate_relaxation": True,
            "no_backfill": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> None:
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "historical_internal_root_cause": out["diagnosis"]["historical_internal_root_cause"],
        "current_external_root_cause": out["diagnosis"]["current_external_root_cause"],
        "priority": out["diagnosis"]["priority"],
        "clv": out["clv"],
        "legacy_quote_attempts": out["houses_pre_fix_baseline"]["legacy_quote_attempts"],
        "current_v3_attempts": out["houses_post_fix_contract"]["current_real_quote_attempts"],
        "internal_code_defects_addressed": out["repair_adjudication"]["internal_code_defects_addressed"],
        "real_money": out["repair_adjudication"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
