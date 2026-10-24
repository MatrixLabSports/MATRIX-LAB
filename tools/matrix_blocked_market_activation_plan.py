from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SUPERVISOR = Path("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
OUT = Path("evidence/market_portfolio/MATRIX_BLOCKED_MARKET_ACTIVATION_PLAN_LAST.json")

PRIORITY_ORDER = {
    "TEAM_TOTAL_GOALS_HOME": 1,
    "TEAM_TOTAL_GOALS_AWAY": 2,
    "DOUBLE_CHANCE_12": 3,
    "ASIAN_OR_EUROPEAN_HANDICAP": 4,
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER": 5,
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER": 6,
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME": 7,
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY": 8,
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME": 9,
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY": 10,
    "ACES": 11,
    "DOUBLE_FAULTS": 12,
    "BREAKS_OF_SERVE": 13,
}


def build(supervisor: dict) -> dict:
    rows=[]
    for row in supervisor.get("rows") or []:
        if row.get("operational_state") != "BLOCKED_MODEL":
            continue
        key=str(row.get("market_key") or "")
        price_state=str(row.get("price_state") or "")
        rows.append({
            "priority": PRIORITY_ORDER.get(key, 999),
            "sport": row.get("sport"),
            "market_key": key,
            "display_name": row.get("display_name"),
            "price_state": price_state,
            "price_available_now": price_state == "PRICE_FAMILY_OBSERVED",
            "blockers": row.get("blockers") or [],
            "next_required_action": (
                "BUILD_PROSPECTIVE_MODEL_LAB_NOW"
                if price_state == "PRICE_FAMILY_OBSERVED"
                else "BUILD_SOURCE_OR_PRICE_MAPPING_THEN_MODEL_LAB"
            ),
            "must_continue_collecting": True,
            "production_authorized": False,
        })
    rows.sort(key=lambda x:(x["priority"],x["sport"],x["market_key"]))
    immediate=[x["market_key"] for x in rows if x["price_available_now"]]
    return {
        "schema":"MATRIX_BLOCKED_MARKET_ACTIVATION_PLAN_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_supervisor_generated_at_utc":supervisor.get("generated_at_utc"),
        "blocked_model_count":len(rows),
        "immediate_model_lab_candidates":immediate,
        "immediate_model_lab_candidate_count":len(immediate),
        "rows":rows,
        "policy":{
            "no_silent_drop":True,
            "no_go_does_not_stop_research":True,
            "price_does_not_generate_p_matrix":True,
            "paper_shadow_only_until_validated":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "status":"PASS",
    }


def main() -> None:
    s=json.loads(SUPERVISOR.read_text(encoding="utf-8"))
    out=build(s)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "blocked_model_count":out["blocked_model_count"],
        "immediate_model_lab_candidate_count":out["immediate_model_lab_candidate_count"],
        "immediate_model_lab_candidates":out["immediate_model_lab_candidates"],
        "real_money":out["policy"]["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
