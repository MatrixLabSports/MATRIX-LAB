"""Read-only readiness truth guard for Over 2.5 alternative-source recovery.

Never promotes research to original calibrated p_matrix, even if historical
parity, positive research EV and exact pricing are available. No sending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="MATRIX_OVER25_TELEGRAM_RECOVERY_TRUTH_GUARD_V1"

def sha(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,
        separators=(",",":")).encode()).hexdigest()

def evaluate(enriched,quotes,quota,promotion,*,observed_at=None):
    if (enriched.get("schema")!="MATRIX_CHAMPIONSHIP_ENRICHED_PROVIDER_HISTORICAL_BRIDGE_V1"
        or quotes.get("schema")!="MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT_V1"
        or quota.get("schema")!="MATRIX_ODDS_API_QUOTA_GUARD_V1"
        or promotion.get("schema")!="MATRIX_FOOTBALL_OVER25_P_MATRIX_MARKET_PROMOTION_V1"):
        raise ValueError("TRUTH_GUARD_SOURCE_SCHEMA_INVALID")
    if (enriched.get("real_money")!="BLOCKED"
        or quotes.get("real_money")!="BLOCKED"
        or enriched.get("automatic_wagering") is not False
        or quotes.get("automatic_wagering") is not False
        or enriched.get("telegram_signal_authorized") is not False
        or quotes.get("signal_generation_authorized") is not False
        or quotes.get("telegram_messages_sent")!=0
        or promotion.get("frozen_parameters")!={"a":0.6,"b":0.0,"c":0.4}):
        raise ValueError("TRUTH_GUARD_PRODUCTION_OR_MODEL_MUTATION")
    original_allowed=(
        promotion.get("promotion_status")=="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
        and promotion.get("engine_executable_for_p_matrix") is True)
    total=enriched.get("original_canonical_targets")
    passed=enriched.get("historical_three_way_parity_count")
    blocked=enriched.get("blocked_count")
    if (not isinstance(total,int) or not isinstance(passed,int)
        or not isinstance(blocked,int) or total!=passed+blocked
        or total<=0):
        raise ValueError("TRUTH_GUARD_HISTORICAL_COUNTS_INVALID")
    quota_decision=quota.get("decision") or {}
    if not isinstance(quota_decision,dict):
        raise ValueError("TRUTH_GUARD_QUOTA_MISSING")
    stage=str(quota_decision.get("stage") or "")
    quote_count=quotes.get("bookmaker_quote_verified_count")
    sharp_count=quotes.get("sharp_120s_verified_count")
    if (not isinstance(quote_count,int) or quote_count<0
        or not isinstance(sharp_count,int) or sharp_count<0):
        raise ValueError("TRUTH_GUARD_QUOTE_COUNTS_INVALID")
    blockers=[]
    if passed<total:
        blockers.append("HISTORICAL_ENRICHED_PIT_SUBSET_INCOMPLETE")
    if enriched.get("prospective_enriched_provider_equivalence_verified") is not True:
        blockers.append("PROSPECTIVE_ENRICHED_PROVIDER_EQUIVALENCE_UNVERIFIED")
    if enriched.get("future_fixture_original_provider_crosswalk_verified") is not True:
        blockers.append("FUTURE_ORIGINAL_FIXTURE_ID_CROSSWALK_UNVERIFIED")
    if stage=="BLOCKED_EXHAUSTED" or quota_decision.get("api_calls_allowed") is False:
        blockers.append("ODDS_PROVIDER_QUOTA_NOT_AVAILABLE")
    if quote_count==0:
        blockers.append("NO_AUTHENTIC_EXACT_COLOMBIA_PRICE")
    if sharp_count==0:
        blockers.append("NO_FRESH_PINNACLE_REFERENCE")
    if quotes.get("production_calibration_parity_verified") is not True:
        blockers.append("CURRENT_MARKET_CALIBRATION_PARITY_UNVERIFIED")
    if quotes.get("browser_first_reconciliation_verified") is not True:
        blockers.append("BOOKMAKER_BROWSER_RECONCILIATION_UNVERIFIED")
    if not original_allowed:
        blockers.append("ORIGINAL_OVER25_PROMOTION_INVALID")
    # Most important: a historical parity study, even 11/11, never
    # substitutes for an authenticated current governed production score.
    blockers.append("CURRENT_GOVERNED_P_MATRIX_EXPORT_NOT_VERIFIED")
    blockers.append("CURRENT_CANONICAL_TELEGRAM_CANDIDATES_NOT_VERIFIED")
    now=observed_at or datetime.now(timezone.utc)
    return {
        "schema":SCHEMA,"verified_at_utc":now.astimezone(timezone.utc).isoformat(),
        "status":"NO_GO_FAIL_CLOSED",
        "historical_enriched_three_way_passed":passed,
        "historical_enriched_three_way_total":total,
        "historical_enriched_three_way_blocked":blocked,
        "original_over25_promotion_still_intact":original_allowed,
        "odds_api_quota_status":stage,
        "bookmaker_quote_verified_count":quote_count,
        "sharp_120s_verified_count":sharp_count,
        "blockers":blockers,
        "source_sha256":{
            "enriched":sha(enriched),"quotes":sha(quotes),
            "quota":sha(quota),"promotion":sha(promotion)},
        "research_history_does_not_promote_provider":True,
        "prospective_model_equivalence_certified":False,
        "telegram_circuit_end_to_end_success_certified":False,
        "p_matrix_production_export_created":False,
        "telegram_messages_sent":0,
        "signal_generation_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--enriched",required=True,type=Path)
    p.add_argument("--quotes",required=True,type=Path)
    p.add_argument("--quota",required=True,type=Path)
    p.add_argument("--promotion",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    if any(part in a.out.parts for part in (
        "daily_prematch_reports","tennis_signals","premium_cards")):
        raise SystemExit("TRUTH_GUARD_CANNOT_WRITE_PRODUCTION_SIGNAL")
    load=lambda file:json.loads(file.read_text(encoding="utf-8"))
    report=evaluate(load(a.enriched),load(a.quotes),load(a.quota),load(a.promotion))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",
                     encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
        "status","historical_enriched_three_way_passed",
        "bookmaker_quote_verified_count","sharp_120s_verified_count",
        "telegram_messages_sent","real_money")},sort_keys=True))

if __name__=="__main__":main()
