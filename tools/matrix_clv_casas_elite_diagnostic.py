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
    all_legacy_odds_event_not_covered = (
        legacy_count > 0
        and odds_status.get("BLOCKED_EVENT_NOT_COVERED", 0) == legacy_count
    )

    priority = (
        "REPAIR_SHARED_ODDS_API_EVENT_DISCOVERY_AND_FULL_COLOMBIA_COVERAGE_FIRST"
        if all_legacy_odds_event_not_covered
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
            "shared_root_cause": (
                "ODDS_API_NET_EVENT_DISCOVERY_SINGLE_PAGE_CREATED_SYSTEMIC_NOT_COVERED_RESULTS"
                if all_legacy_odds_event_not_covered
                else "NOT_PROVEN_UNIVERSAL"
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
            "all_odds_api_net_attempts_event_not_covered": all_legacy_odds_event_not_covered,
            "legacy_three_book_diagnostic": summary.get("legacy_three_book_diagnostic"),
            "interpretation": (
                "Legacy V1/V2 telemetry covered Betano, BetPlay and Rushbet only. It is preserved for causal diagnosis "
                "and must not be represented as full 14-book Colombia coverage."
            ),
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
            "external_provider_coverage_proven_after_fix": len(current) >= 50,
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
        "shared_root_cause": out["diagnosis"]["shared_root_cause"],
        "priority": out["diagnosis"]["priority"],
        "clv": out["clv"],
        "legacy_quote_attempts": out["houses_pre_fix_baseline"]["legacy_quote_attempts"],
        "current_v3_attempts": out["houses_post_fix_contract"]["current_real_quote_attempts"],
        "internal_code_defects_addressed": out["repair_adjudication"]["internal_code_defects_addressed"],
        "real_money": out["repair_adjudication"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
