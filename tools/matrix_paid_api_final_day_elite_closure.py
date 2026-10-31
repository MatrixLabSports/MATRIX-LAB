#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))

def build_report():
    football = load("evidence/api_football/market_expansion/market_binding_catalog.json")
    oos = load("evidence/api_football/calibration_v2/OOS_4001_5000_STATE.json")
    tennis_deadline = load("evidence/governance/MATRIX_TENNIS_SUBSCRIPTION_DEADLINE_LAST.json")
    tennis_receipt = load("evidence/tennis/paid_window_harvest/2026-10-28/MATRIX_RAPIDAPI_TENNIS_HARVEST_RECEIPT_LAST.json")
    tennis_canonical = load("evidence/tennis/paid_window_harvest/2026-10-28/MATRIX_TENNIS_27OCT_CANONICAL_INVENTORY.json")
    clv = load("evidence/clv/football/over_2_5/state.json")
    calibration = load("evidence/governance/MATRIX_42_MARKET_ELITE_CALIBRATION_CLOSURE_28OCT2026.json")
    quotes = load("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json")

    return {
        "schema": "MATRIX_PAID_API_FINAL_DAY_ELITE_CLOSURE_V1",
        "source_head": "ac948ce5d6b43c666c1a0c04f88a5ba9805fd4af",
        "governance": {
            "date_bogota": "2026-10-28",
            "real_money": "BLOCKED",
            "automatic_wagering": False,
            "paid_api_renewal_authorized": False,
            "odds_may_not_generate_p_matrix": True,
            "no_backfill": True,
            "missing_not_zero": True,
        },
        "api_football": {
            "provider": football.get("provider"),
            "status": football.get("status"),
            "refresh_status": football.get("refresh_status"),
            "provider_error_classification": football.get("provider_error_classification"),
            "provider_errors": football.get("provider_errors"),
            "adjudication": "EXTERNAL_DAILY_QUOTA_BLOCK_FAIL_CLOSED",
        },
        "rapidapi_tennis": {
            "provider": tennis_receipt["provider"],
            "paid_through": tennis_receipt["subscription_paid_through"],
            "paid_window_active": tennis_deadline["paid_window_active"],
            "network_calls": tennis_receipt["network_calls"],
            "unique_match_count": tennis_receipt["unique_match_count"],
            "provider_inventory_complete": tennis_receipt["provider_inventory_complete"],
            "families": tennis_receipt["families"],
            "surfaces": tennis_receipt["surfaces"],
            "canonical_row_count": tennis_canonical["canonical_row_count"],
            "classification_counts": tennis_canonical["classification_counts"],
            "cor0203_preregister_candidate_count": tennis_canonical["cor0203_preregister_candidate_count"],
            "automatic_model_feed": tennis_canonical["governance"]["automatic_model_feed"],
            "status": "FINAL_PAID_WINDOW_HARVEST_PHYSICALLY_PERSISTED",
        },
        "oos_football": {
            "current": oos["current_oos_observations"],
            "target": oos["target_oos_observations"],
            "remaining": oos["remaining_to_1000"],
            "metrics_opened": oos["metrics_opened"],
            "status": oos["status"],
        },
        "clv": {
            "closing_odds_count": clv["closing_odds_count"],
            "target": 300,
            "remaining": 300 - clv["closing_odds_count"],
            "metrics_opened": clv["metrics_opened"],
            "status": clv["status"],
        },
        "portfolio": calibration["portfolio"],
        "signal_authorized": calibration["adjudication"]["signal_authorized"],
        "telegram_quote_telemetry_status": quotes.get("status"),
        "adjudication": {
            "resolved_today": [
                "BROWSER_FIRST_TENNIS_28OCT_PHYSICALLY_PERSISTED",
                "RAPIDAPI_TENNIS_FINAL_PAID_WINDOW_HARVEST_COMPLETED",
                "TENNIS_PROVIDER_INVENTORY_PERSISTED_WITH_RECEIPT",
                "42_LANE_SUPERVISOR_REVALIDATED_AFTER_TENNIS_HARVEST",
            ],
            "external_blocks": [
                "API_FOOTBALL_DAILY_REQUEST_LIMIT_REACHED",
            ],
            "still_sealed": [
                "FOOTBALL_OOS_METRICS_UNTIL_1000",
                "CLV_METRICS_UNTIL_300",
                "NON_PROMOTED_MARKETS_REMAIN_RESEARCH_ONLY",
            ],
        },
    }

def main():
    out = ROOT / "evidence/governance/MATRIX_PAID_API_FINAL_DAY_ELITE_CLOSURE_28OCT2026.json"
    out.write_text(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
