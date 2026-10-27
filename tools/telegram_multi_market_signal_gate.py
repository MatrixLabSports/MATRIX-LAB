from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path("evidence/api_football")
OUT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_MULTI_MARKET_SIGNAL_GATE_LAST.json")

def load(p: Path)->dict[str,Any]:
    v=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(f"EXPECTED_OBJECT:{p}")
    return v

def build()->dict[str,Any]:
    checkpoint=load(ROOT/"calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
    promotion=load(ROOT/"governance/over_2_5_p_matrix_promotion.json")
    core=load(ROOT/"governance/MATRIX_FOOTBALL_CORE_MARKETS_STATUS_20261003.json")
    resolution=load(ROOT/"governance/MATRIX_FOOTBALL_MARKET_RESOLUTION_MASTER_20261004.json")
    failed=load(ROOT/"governance/MATRIX_FOOTBALL_FAILED_MARKETS_V3_DECISION_20261003.json")
    one_x_two_audit_path=ROOT/"governance/MATRIX_1X2_PROMOTION_READINESS_LAST.json"
    one_x_two_audit=load(one_x_two_audit_path) if one_x_two_audit_path.exists() else {}

    rows=[]
    def add(market,status,reason,calibration_rows=None,quote_path=False,signal_engine=False,source=None):
        rows.append({
            "market":market,
            "signal_status":status,
            "reason":reason,
            "calibration_rows":calibration_rows,
            "explicit_signal_promotion": status=="SIGNAL_AUTHORIZED",
            "quote_extraction_path_present":bool(quote_path),
            "telegram_signal_engine_present":bool(signal_engine),
            "source_evidence":source,
        })

    over=checkpoint.get("markets",{}).get("over_2_5",{})
    add("OVER_2_5","SIGNAL_AUTHORIZED",
        "Explicit governed P_MATRIX signal-only promotion exists and Telegram has exact Over 2.5 quote/revalidation path.",
        over.get("eligible_rows"),True,True,
        "evidence/api_football/governance/over_2_5_p_matrix_promotion.json")

    dcx2=checkpoint.get("markets",{}).get("double_chance_x2",{})
    dcx2_ready=dcx2_audit.get("status")=="PASS_PROMOTION_READY" and dcx2_audit.get("promotion_allowed") is True
    if dcx2_ready:
        add("DOUBLE_CHANCE_X2","SIGNAL_AUTHORIZED",
            "Dedicated fail-closed Double Chance X2 readiness audit passed all promotion gates.",
            dcx2.get("eligible_rows"),True,True,
            "evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_X2_PROMOTION_READINESS_LAST.json")
    else:
        blockers=dcx2_audit.get("blockers") or ["READINESS_AUDIT_NOT_YET_PERSISTED"]
        add("DOUBLE_CHANCE_X2","RESEARCH_ONLY",
            "Fail-closed Double Chance X2 audit blocks signal authorization: "+",".join(blockers),
            dcx2.get("eligible_rows"),False,False,
            "evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_X2_PROMOTION_READINESS_LAST.json")

    dc1x=checkpoint.get("markets",{}).get("double_chance_1x",{})
    dc1x_ready=dc1x_audit.get("status")=="PASS_PROMOTION_READY" and dc1x_audit.get("promotion_allowed") is True
    if dc1x_ready:
        add("DOUBLE_CHANCE_1X","SIGNAL_AUTHORIZED",
            "Dedicated fail-closed Double Chance 1X readiness audit passed all promotion gates.",
            dc1x.get("eligible_rows"),True,True,
            "evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json")
    else:
        blockers=dc1x_audit.get("blockers") or ["READINESS_AUDIT_NOT_YET_PERSISTED"]
        add("DOUBLE_CHANCE_1X","RESEARCH_ONLY",
            "Fail-closed Double Chance 1X audit blocks signal authorization: "+",".join(blockers),
            dc1x.get("eligible_rows"),False,False,
            "evidence/api_football/governance/MATRIX_DOUBLE_CHANCE_1X_PROMOTION_READINESS_LAST.json")

    under25=checkpoint.get("markets",{}).get("under_2_5",{})
    under25_ready=under25_audit.get("status")=="PASS_PROMOTION_READY" and under25_audit.get("promotion_allowed") is True
    if under25_ready:
        add("UNDER_2_5","SIGNAL_AUTHORIZED",
            "Dedicated fail-closed Under 2.5 readiness audit passed all OOS, P_MATRIX promotion, quote/revalidation and Telegram engine gates.",
            under25.get("eligible_rows"),True,True,
            "evidence/api_football/governance/MATRIX_UNDER25_PROMOTION_READINESS_LAST.json")
    else:
        blockers=under25_audit.get("blockers") or ["READINESS_AUDIT_NOT_YET_PERSISTED"]
        add("UNDER_2_5","RESEARCH_ONLY",
            "Fail-closed Under 2.5 promotion audit blocks signal authorization: "+",".join(blockers),
            under25.get("eligible_rows"),False,False,
            "evidence/api_football/governance/MATRIX_UNDER25_PROMOTION_READINESS_LAST.json")

    one_x_two=checkpoint.get("markets",{}).get("1x2",{})
    one_x_two_ready=one_x_two_audit.get("status")=="PASS_PROMOTION_READY" and one_x_two_audit.get("promotion_allowed") is True
    if one_x_two_ready:
        add("1X2","SIGNAL_AUTHORIZED",
            "Dedicated fail-closed 1X2 readiness audit passed all OOS, P_MATRIX promotion, quote/revalidation and Telegram engine gates.",
            one_x_two.get("eligible_rows"),True,True,
            "evidence/api_football/governance/MATRIX_1X2_PROMOTION_READINESS_LAST.json")
    else:
        blockers=one_x_two_audit.get("blockers") or ["READINESS_AUDIT_NOT_YET_PERSISTED"]
        add("1X2","RESEARCH_ONLY",
            "Fail-closed 1X2 promotion audit blocks signal authorization: "+",".join(blockers),
            one_x_two.get("eligible_rows"),False,False,
            "evidence/api_football/governance/MATRIX_1X2_PROMOTION_READINESS_LAST.json")

    add("DOUBLE_CHANCE_12","NO_GO",
        "Closed: challenger not superior to Poisson at the governed checkpoint.",4000,False,False,
        "evidence/api_football/calibration_v2/MATRIX_FOOTBALL_ALL_MARKETS_V2_MASTER_CERTIFICATION_20261004.json")
    add("BTTS","NO_GO",
        "BTTS V2 and V3 are formally NO_GO; a materially new challenger is required.",None,False,False,
        "evidence/api_football/governance/BTTS_V2_V3_NO_GO_20261003.json")

    for m in ["CORNERS","TEAM_SHOTS_ON_TARGET","TEAM_GOALKEEPER_SAVES","TEAM_YELLOW_CARDS"]:
        decision=(failed.get("decisions") or {}).get(m,{})
        add(m,"NO_GO",f"Historical OOS gate failed: {decision.get('reason') or 'FAILED_VALIDATION'}.",None,False,False,
            "evidence/api_football/governance/MATRIX_FOOTBALL_FAILED_MARKETS_V3_DECISION_20261003.json")

    for m in ["TEAM_TOTAL_SHOTS_HOME","TEAM_TOTAL_SHOTS_AWAY","TEAM_FOULS_TOTAL","PLAYER_SHOTS_V3"]:
        rr=(resolution.get("markets") or {}).get(m,{})
        add(m,"RESEARCH_ONLY",
            f"Prospective research lane exists but is not signal-promoted; current state: {rr.get('status') or 'UNKNOWN'}.",
            rr.get("freeze_observation_count") or rr.get("calibration_observation_count"),False,False,
            "evidence/api_football/governance/MATRIX_FOOTBALL_MARKET_RESOLUTION_MASTER_20261004.json")

    for m in ["FIRST_HALF_TOTAL_GOALS_OVER_UNDER","SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
              "FIRST_HALF_TEAM_TOTAL_GOALS_HOME","FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
              "SECOND_HALF_TEAM_TOTAL_GOALS_HOME","SECOND_HALF_TEAM_TOTAL_GOALS_AWAY"]:
        add(m,"LAB_ONLY","Period-goals lane is LAB-only; no signal promotion or execution quote contract exists.",None,False,False,
            "evidence/api_football/period_goals_lab/MATRIX_PERIOD_GOALS_LAB_LAST.json")

    return {
      "schema":"MATRIX_TELEGRAM_MULTI_MARKET_SIGNAL_GATE_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":"PASS",
      "policy":{
        "silent_market_omission_forbidden":True,
        "signal_requires_explicit_market_promotion":True,
        "signal_requires_market_specific_quote_path":True,
        "signal_requires_positive_ev":True,
        "minimum_decimal_odds_exclusive":1.50,
        "odds_may_not_generate_p_matrix":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
      },
      "checkpoint_adjudication":checkpoint.get("adjudication"),
      "markets":rows,
      "summary":{
        "signal_authorized":sum(x["signal_status"]=="SIGNAL_AUTHORIZED" for x in rows),
        "research_only":sum(x["signal_status"]=="RESEARCH_ONLY" for x in rows),
        "lab_only":sum(x["signal_status"]=="LAB_ONLY" for x in rows),
        "no_go":sum(x["signal_status"]=="NO_GO" for x in rows),
      }
    }

def main():
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],**out["summary"]},sort_keys=True))

if __name__=="__main__":
    main()
