"""No money, no Telegram HTTP, no promotion from research-only parity."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import pytest
from tools.matrix_over25_telegram_recovery_truth_guard import evaluate,sha

ROOT=Path(__file__).resolve().parents[1]
FILES=[
"evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_41629729309.json",
"evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json",
"evidence/notifications/telegram/MATRIX_ODDS_API_QUOTA_GUARD_LAST.json",
"evidence/api_football/governance/over_2_5_p_matrix_promotion.json",
]
NOW=datetime(2026,11,3,11,50,tzinfo=timezone.utc)

def docs():
    return [json.loads((ROOT/path).read_text(encoding="utf-8")) for path in FILES]

def test_real_repo_truth_guard_reports_all_physical_blockers_without_emission():
    enriched,quotes,quota,promotion=docs()
    r=evaluate(enriched,quotes,quota,promotion,observed_at=NOW)
    assert r["historical_enriched_three_way_passed"]==8
    assert r["historical_enriched_three_way_total"]==11
    assert r["original_over25_promotion_still_intact"] is True
    assert r["odds_api_quota_status"]=="BLOCKED_EXHAUSTED"
    assert r["bookmaker_quote_verified_count"]==0
    assert r["sharp_120s_verified_count"]==0
    assert "CURRENT_CANONICAL_TELEGRAM_CANDIDATES_NOT_VERIFIED" in r["blockers"]
    assert "NO_AUTHENTIC_EXACT_COLOMBIA_PRICE" in r["blockers"]
    assert "NO_FRESH_PINNACLE_REFERENCE" in r["blockers"]
    assert r["status"]=="NO_GO_FAIL_CLOSED"
    assert r["telegram_messages_sent"]==0
    assert r["signal_generation_authorized"] is False
    assert r["real_money"]=="BLOCKED"
    assert r["source_sha256"]["enriched"]==sha(enriched)

def test_even_perfect_retrospective_and_fake_price_cannot_promote_to_green():
    enriched,quotes,quota,promotion=docs()
    enriched=deepcopy(enriched)
    enriched["historical_three_way_parity_count"]=11
    enriched["blocked_count"]=0
    quotes=deepcopy(quotes)
    quotes["bookmaker_quote_verified_count"]=1
    quotes["sharp_120s_verified_count"]=1
    quotes["browser_first_reconciliation_verified"]=True
    quotes["production_calibration_parity_verified"]=True
    quota=deepcopy(quota)
    quota["decision"]["stage"]="NORMAL_T120"
    quota["decision"]["api_calls_allowed"]=True
    d=evaluate(enriched,quotes,quota,promotion,observed_at=NOW)
    assert "NO_FRESH_PINNACLE_REFERENCE" not in d["blockers"]
    assert "CURRENT_GOVERNED_P_MATRIX_EXPORT_NOT_VERIFIED" in d["blockers"]
    assert "CURRENT_CANONICAL_TELEGRAM_CANDIDATES_NOT_VERIFIED" in d["blockers"]
    assert d["signal_generation_authorized"] is False

def test_never_accepts_claimed_research_signal_authorization():
    arr=docs()
    arr[1]["signal_generation_authorized"]=True
    with pytest.raises(ValueError,match="MUTATION"):
        evaluate(*arr,observed_at=NOW)

def test_tampered_historical_totals_rejected_before_status():
    arr=docs()
    arr[0]["historical_three_way_parity_count"]=11
    with pytest.raises(ValueError,match="COUNTS"):
        evaluate(*arr,observed_at=NOW)
