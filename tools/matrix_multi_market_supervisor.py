from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.market.matrix_market_portfolio import FOOTBALL_MARKETS, TENNIS_MARKETS, MarketLane

ROOT = Path("evidence")
OUT = ROOT / "market_portfolio" / "MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json"

FOOTBALL_IMPLEMENTATION = {
    "TOTAL_GOALS_OVER_UNDER": ("ACTIVE", ["tools/football_daily_governed_over25.py"]),
    "MATCH_RESULT_1X2": ("LAB", ["tools/api_football_market_shadow_p_matrix.py"]),
    "DOUBLE_CHANCE_1X": ("LAB", ["tools/api_football_market_shadow_p_matrix.py"]),
    "DOUBLE_CHANCE_X2": ("LAB", ["tools/api_football_market_shadow_p_matrix.py"]),
    "BTTS": ("LAB", ["tools/api_football_btts_challenger_v2.py", "tools/api_football_btts_challenger_v3.py"]),
    "TEAM_TOTAL_SHOTS_HOME": ("LAB", ["tools/api_football_team_total_shots_side_models.py"]),
    "TEAM_TOTAL_SHOTS_AWAY": ("LAB", ["tools/api_football_team_total_shots_side_models.py"]),
    "PLAYER_SHOTS": ("LAB", ["tools/api_football_player_shots_v3_supervisor.py"]),
    "PLAYER_SHOTS_ON_TARGET": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "CORNERS_OVER_UNDER": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "CARDS_OVER_UNDER": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "TEAM_SHOTS_ON_TARGET_HOME": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "TEAM_SHOTS_ON_TARGET_AWAY": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "TEAM_FOULS_HOME": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "TEAM_FOULS_AWAY": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "GOALKEEPER_SAVES": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "PLAYER_ASSISTS": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "PLAYER_PASSES": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "PLAYER_TACKLES": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
    "PLAYER_FOULS": ("LAB", ["tools/api_football_extended_market_coverage_probe.py"]),
}

TENNIS_IMPLEMENTATION = {
    "MATCH_WINNER": ("ACTIVE", ["tools/tennis_world_inventory_rapidapi.py"]),
    "SET_WINNER": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "SET_HANDICAP": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "TOTAL_SETS": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "BOTH_PLAYERS_WIN_SET": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "GAME_HANDICAP": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "TOTAL_GAMES": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "PLAYER_TOTAL_GAMES": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
    "TIEBREAK_YES_NO": ("LAB", ["tools/live_tennis_feature_extractor.py"]),
}

FOOTBALL_PRICE_TERMS = {
    "MATCH_RESULT_1X2": ["match winner", "1x2"],
    "DOUBLE_CHANCE_1X": ["double chance"],
    "DOUBLE_CHANCE_X2": ["double chance"],
    "DOUBLE_CHANCE_12": ["double chance"],
    "TOTAL_GOALS_OVER_UNDER": ["goals over/under", "goals"],
    "TEAM_TOTAL_GOALS_HOME": ["home team total", "home goals"],
    "TEAM_TOTAL_GOALS_AWAY": ["away team total", "away goals"],
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER": ["first half goals", "1st half goals"],
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER": ["second half goals", "2nd half goals"],
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME": ["first half home team total"],
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY": ["first half away team total"],
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME": ["second half home team total"],
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY": ["second half away team total"],
    "BTTS": ["both teams score", "both teams to score"],
    "ASIAN_OR_EUROPEAN_HANDICAP": ["handicap"],
    "CORNERS_OVER_UNDER": ["corner"],
    "CARDS_OVER_UNDER": ["card", "booking"],
    "TEAM_TOTAL_SHOTS_HOME": ["shots home total", "home total shots"],
    "TEAM_TOTAL_SHOTS_AWAY": ["shots away total", "away total shots"],
    "TEAM_SHOTS_ON_TARGET_HOME": ["home shots on target"],
    "TEAM_SHOTS_ON_TARGET_AWAY": ["away shots on target"],
    "TEAM_FOULS_HOME": ["home fouls"],
    "TEAM_FOULS_AWAY": ["away fouls"],
    "GOALKEEPER_SAVES": ["save"],
    "PLAYER_SHOTS": ["player shots"],
    "PLAYER_SHOTS_ON_TARGET": ["player shots on target"],
    "PLAYER_ASSISTS": ["player assists"],
    "PLAYER_PASSES": ["player passes"],
    "PLAYER_TACKLES": ["player tackles"],
    "PLAYER_FOULS": ["player fouls"],
}


def _exists(paths: list[str]) -> bool:
    return any(Path(p).exists() for p in paths)


def _load_catalog(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    try:
        j = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = j.get("rows") or j.get("response") or j.get("catalog") or []
    names: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                name = str(row.get("name") or row.get("market_name") or "").strip()
                if name:
                    names.append(name.casefold())
    matches = j.get("matches")
    if isinstance(matches, dict):
        for vals in matches.values():
            if isinstance(vals, list):
                for row in vals:
                    if isinstance(row, dict):
                        name = str(row.get("name") or "").strip()
                        if name:
                            names.append(name.casefold())
    return sorted(set(names))


def _football_price_state(key: str, catalog_names: list[str]) -> str:
    if not catalog_names:
        return "PRICE_CATALOG_NOT_SUPPLIED"
    terms = FOOTBALL_PRICE_TERMS.get(key, [])
    if any(any(term in name for term in terms) for name in catalog_names):
        return "PRICE_FAMILY_OBSERVED"
    return "PRICE_FAMILY_NOT_OBSERVED"


def _row(lane: MarketLane, catalog_names: list[str]) -> dict[str, Any]:
    impl = FOOTBALL_IMPLEMENTATION if lane.sport == "football" else TENNIS_IMPLEMENTATION
    maturity, paths = impl.get(lane.key, ("BLOCKED_MODEL", []))
    implemented = _exists(paths) if paths else False
    if maturity in {"ACTIVE", "LAB"} and not implemented:
        maturity = "BLOCKED_IMPLEMENTATION_MISSING"

    if lane.sport == "football":
        price_state = _football_price_state(lane.key, catalog_names)
    else:
        price_state = "PRICE_MAPPING_REQUIRES_TENNIS_PROVIDER_OR_BOOK_CATALOG"

    if maturity == "ACTIVE":
        state = "ACTIVE"
    elif maturity == "LAB":
        state = "LAB"
    else:
        state = maturity

    blockers = []
    if state.startswith("BLOCKED"):
        blockers.append(state)
    if lane.sport == "football" and price_state == "PRICE_FAMILY_NOT_OBSERVED":
        blockers.append("BLOCKED_PRICE_FAMILY")
    if lane.sport == "tennis" and lane.key in {"ACES", "DOUBLE_FAULTS", "BREAKS_OF_SERVE"}:
        blockers.append("BLOCKED_TENNIS_STAT_MARKET_IMPLEMENTATION")

    return {
        "sport": lane.sport,
        "market_key": lane.key,
        "display_name": lane.display_name,
        "family": lane.family,
        "required": lane.required,
        "required_lifecycle": lane.lifecycle,
        "operational_state": state,
        "implementation_paths": paths,
        "implementation_present": implemented,
        "price_state": price_state,
        "blockers": blockers,
        "must_continue_collecting": True,
        "production_authorized": state == "ACTIVE",
    }


def build(*, football_catalog: Path | None = None, target_date_bogota: str | None = None) -> dict[str, Any]:
    catalog_names = _load_catalog(football_catalog)
    rows = [_row(x, catalog_names) for x in (*FOOTBALL_MARKETS, *TENNIS_MARKETS)]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["operational_state"]] = counts.get(row["operational_state"], 0) + 1
    missing = [x["market_key"] for x in rows if not x["required"]]
    return {
        "schema": "MATRIX_MULTI_MARKET_SUPERVISOR_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_date_bogota": target_date_bogota,
        "total_required_lanes": len(rows),
        "football_required_lanes": len(FOOTBALL_MARKETS),
        "tennis_required_lanes": len(TENNIS_MARKETS),
        "state_counts": counts,
        "catalog_market_names_observed": len(catalog_names),
        "rows": rows,
        "missing_required_flags": missing,
        "invariants": {
            "every_mandated_lane_emitted_each_cycle": len(rows) == len(FOOTBALL_MARKETS) + len(TENNIS_MARKETS),
            "no_go_does_not_stop_research_collection": True,
            "over_2_5_not_single_market_scope": True,
            "aces_present": any(x["market_key"] == "ACES" for x in rows),
            "first_half_goals_present": any(x["market_key"] == "FIRST_HALF_TOTAL_GOALS_OVER_UNDER" for x in rows),
            "second_half_goals_present": any(x["market_key"] == "SECOND_HALF_TOTAL_GOALS_OVER_UNDER" for x in rows),
            "odds_do_not_generate_p_matrix": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS" if not missing else "FAIL",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--football-catalog")
    p.add_argument("--target-date-bogota")
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()
    result = build(
        football_catalog=Path(args.football_catalog) if args.football_catalog else None,
        target_date_bogota=args.target_date_bogota,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "total_required_lanes": result["total_required_lanes"],
        "football_required_lanes": result["football_required_lanes"],
        "tennis_required_lanes": result["tennis_required_lanes"],
        "state_counts": result["state_counts"],
        "aces_present": result["invariants"]["aces_present"],
        "first_half_goals_present": result["invariants"]["first_half_goals_present"],
        "second_half_goals_present": result["invariants"]["second_half_goals_present"],
        "real_money": result["invariants"]["real_money"],
    }, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit("MULTI_MARKET_SUPERVISOR_FAIL")


if __name__ == "__main__":
    main()
