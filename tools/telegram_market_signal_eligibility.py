from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(".")
OUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_MARKET_SIGNAL_ELIGIBILITY_LAST.json")

LANE_STATE_PATHS = {
    "MATCH_RESULT_1X2": "evidence/api_football/calibration_v2/lanes/1x2/state.json",
    "UNDER_2_5": "evidence/api_football/calibration_v2/lanes/under_2_5/state.json",
    "DOUBLE_CHANCE_1X": "evidence/api_football/calibration_v2/lanes/double_chance_1x/state.json",
    "DOUBLE_CHANCE_X2": "evidence/api_football/calibration_v2/lanes/double_chance_x2/state.json",
    "DOUBLE_CHANCE_12": "evidence/api_football/calibration_v2/lanes/double_chance_12/state.json",
    "BTTS": "evidence/api_football/calibration_v2/lanes/btts/state.json",
    "CORNERS_OVER_UNDER": "evidence/api_football/calibration_v2/lanes/corners_over_under/state.json",
    "TEAM_TOTAL_SHOTS": "evidence/api_football/calibration_v2/lanes/team_total_shots/state.json",
    "TEAM_SHOTS_ON_TARGET": "evidence/api_football/calibration_v2/lanes/team_shots_on_target/state.json",
    "TEAM_FOULS": "evidence/api_football/calibration_v2/lanes/team_fouls/state.json",
    "TEAM_YELLOW_CARDS": "evidence/api_football/calibration_v2/lanes/team_yellow_cards/state.json",
    "PLAYER_SHOTS": "evidence/api_football/calibration_v2/lanes/player_shots/state.json",
}

PERIOD_KEYS = [
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
]

DISPLAY = {
    "OVER_2_5": "Más de 2.5 goles",
    "UNDER_2_5": "Menos de 2.5 goles",
    "MATCH_RESULT_1X2": "Resultado 1X2",
    "DOUBLE_CHANCE_1X": "Doble oportunidad 1X",
    "DOUBLE_CHANCE_X2": "Doble oportunidad X2",
    "DOUBLE_CHANCE_12": "Doble oportunidad 12",
    "BTTS": "Ambos equipos marcan",
    "CORNERS_OVER_UNDER": "Córners Más/Menos",
    "TEAM_TOTAL_SHOTS": "Tiros totales de equipo",
    "TEAM_SHOTS_ON_TARGET": "Tiros a puerta de equipo",
    "TEAM_FOULS": "Faltas de equipo",
    "TEAM_YELLOW_CARDS": "Tarjetas amarillas de equipo",
    "PLAYER_SHOTS": "Remates de jugador",
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER": "Goles primer tiempo Más/Menos",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER": "Goles segundo tiempo Más/Menos",
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME": "Goles local primer tiempo",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY": "Goles visitante primer tiempo",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME": "Goles local segundo tiempo",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY": "Goles visitante segundo tiempo",
}


def load(path: str) -> dict[str, Any]:
    p=ROOT/path
    return json.loads(p.read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    checkpoint=load("evidence/api_football/calibration_v2/CHECKPOINT_4000_MARKET_CALIBRATION_20261023.json")
    promotion=load("evidence/api_football/governance/over_2_5_p_matrix_promotion.json")
    portfolio=load("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
    registry=load("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
    nine=load("evidence/lab_gates/MATRIX_NINE_LAB_GATE_REGISTRY_LAST.json")

    portfolio_rows={x["market_key"]:x for x in portfolio.get("rows",[]) if isinstance(x,dict)}
    preg=registry.get("registry") if isinstance(registry.get("registry"),dict) else registry
    if isinstance(preg,dict) and "schema" in preg and "lanes" in preg:
        preg=preg.get("lanes") or {}
    if not isinstance(preg,dict):
        preg={}

    rows=[]
    rows.append({
        "market_key":"OVER_2_5",
        "display_name":DISPLAY["OVER_2_5"],
        "telegram_signal_state":"SIGNAL_ACTIVE",
        "reason":"MARKET_SCOPED_PROMOTION_PHYSICALLY_PRESENT",
        "settlement_evidence":checkpoint.get("markets",{}).get("over_2_5",{}).get("eligible_rows"),
        "promotion_status":promotion.get("promotion_status"),
        "production_authorized":True,
        "price_requirement":"EXACT_2_5_AUTHORIZED_BOOK_ODDS_GT_1_50",
    })

    for key in ["MATCH_RESULT_1X2","UNDER_2_5","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2"]:
        state=load(LANE_STATE_PATHS[key])
        ckey={"MATCH_RESULT_1X2":"1x2","UNDER_2_5":"under_2_5","DOUBLE_CHANCE_1X":"double_chance_1x","DOUBLE_CHANCE_X2":"double_chance_x2"}[key]
        rows.append({
            "market_key":key,
            "display_name":DISPLAY[key],
            "telegram_signal_state":"PROMOTION_REQUIRED",
            "reason":"CALIBRATED_OR_DERIVED_BUT_NO_SEPARATE_TELEGRAM_SIGNAL_PROMOTION",
            "settlement_evidence":state.get("settlement_count"),
            "checkpoint_eligible_rows":checkpoint.get("markets",{}).get(ckey,{}).get("eligible_rows"),
            "lane_status":state.get("status"),
            "production_authorized":False,
            "required_before_activation":[
                "PREREGISTERED_MARKET_SIGNAL_RULE",
                "MARKET_SCOPED_PROMOTION_ARTIFACT",
                "EXACT_EXECUTABLE_PRICE_MAPPING",
                "CLV_RISK_AND_EXECUTION_EVIDENCE",
            ],
        })

    for key in ["DOUBLE_CHANCE_12","BTTS","CORNERS_OVER_UNDER","TEAM_TOTAL_SHOTS","TEAM_SHOTS_ON_TARGET","TEAM_FOULS","TEAM_YELLOW_CARDS","PLAYER_SHOTS"]:
        state=load(LANE_STATE_PATHS[key])
        rows.append({
            "market_key":key,
            "display_name":DISPLAY[key],
            "telegram_signal_state":"BLOCKED",
            "reason":state.get("blocker") or state.get("status"),
            "lane_status":state.get("status"),
            "settlement_evidence":state.get("settlement_count"),
            "production_authorized":False,
        })

    lab_lanes=(nine.get("lanes") or {})
    for key in PERIOD_KEYS:
        gate=lab_lanes.get(key) or {}
        rows.append({
            "market_key":key,
            "display_name":DISPLAY[key],
            "telegram_signal_state":"BLOCKED_LAB",
            "reason":"LAB_GATE_NOT_PRODUCTION_AUTHORIZED",
            "prospective_unique_count":gate.get("prospective_unique_count",0),
            "gate_100":(gate.get("gates") or {}).get("100"),
            "gate_300":(gate.get("gates") or {}).get("300"),
            "gate_600":(gate.get("gates") or {}).get("600"),
            "production_authorized":False,
        })

    active=[x["market_key"] for x in rows if x["telegram_signal_state"]=="SIGNAL_ACTIVE"]
    pending=[x["market_key"] for x in rows if x["telegram_signal_state"]=="PROMOTION_REQUIRED"]
    blocked=[x["market_key"] for x in rows if x["telegram_signal_state"].startswith("BLOCKED")]
    return {
        "schema":"MATRIX_TELEGRAM_MARKET_SIGNAL_ELIGIBILITY_V1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS",
        "summary":{
            "signal_active_count":len(active),
            "promotion_required_count":len(pending),
            "blocked_count":len(blocked),
            "signal_active_markets":active,
            "promotion_required_markets":pending,
        },
        "governance":{
            "no_market_activated_without_explicit_promotion":True,
            "calibration_does_not_equal_signal_authorization":True,
            "odds_do_not_generate_p_matrix":True,
            "minimum_decimal_odds_exclusive":1.50,
            "ev_must_be_positive":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "checkpoint_adjudication":checkpoint.get("adjudication"),
        "rows":rows,
    }


def main() -> None:
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],**out["summary"]},sort_keys=True))


if __name__=="__main__":
    main()
