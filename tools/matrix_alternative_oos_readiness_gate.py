"""Research-only readiness gate for independent football-data.org Over 2.5.

This computes screening deficits, not scientific certification or permission
to produce Telegram signals. No model parameters are changed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

SCORECARD = Path("evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json")
SCOPE = Path("evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_SCOPE_RESEARCH_PROGRESS_LAST.json")
OUT = Path("evidence/football_world_inventory/MATRIX_ALTERNATIVE_OOS_READINESS_GATE_LAST.json")
REQUIRED_PER_LEAGUE = 30  # Research screen, NOT scientific certification.


def evaluate(scorecard: dict, scope: dict) -> dict:
    if scorecard.get("schema") != "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_V1":
        raise ValueError("SCORECARD_SCHEMA_INVALID")
    if scope.get("schema") != "MATRIX_OVER25_ORIGINAL_SCOPE_RESEARCH_PROGRESS_V1":
        raise ValueError("SCOPE_SCHEMA_INVALID")
    for obj in (scorecard, scope):
        if (obj.get("production_p_matrix_authorized") is not False
            or obj.get("telegram_signal_authorized") is not False
            or obj.get("real_money") != "BLOCKED"):
            raise ValueError("RESEARCH_GOVERNANCE_NOT_FAIL_CLOSED")
    leagues = scope.get("original_six_league_ids")
    if not isinstance(leagues, list) or len(leagues) != 6 or len({str(x) for x in leagues}) != 6:
        raise ValueError("SIX_LEAGUE_SCOPE_INVALID")
    mapping = scope.get("provider_competition_map_source_to_original") or {}
    entries = scorecard.get("provider_competitions") or []
    by_provider = {}
    for row in entries:
        cid = str(row["source_competition_id"])
        n = row.get("independent_out_of_sample_rows")
        if (cid in by_provider or type(n) is not int or n < 0
            or row.get("scientific_original_six_league_equivalence_certified") is not False):
            raise ValueError("SCORECARD_ROW_UNTRUSTED")
        by_provider[cid] = n
    reported_total = scorecard.get("total_verified_settled_rows")
    if type(reported_total) is not int or sum(by_provider.values()) != reported_total:
        raise ValueError("OOS_TOTAL_RECONCILIATION_FAILED")
    results = []
    for lid in sorted(str(x) for x in leagues):
        mapped = sorted(str(cid) for cid, orig in mapping.items() if str(orig) == lid)
        count = sum(by_provider.get(cid, 0) for cid in mapped)
        results.append({
            "original_league_id": lid,
            "alternative_competitions": mapped,
            "independent_settled_research_rows": count,
            "remaining_for_30_row_research_screen": max(0, REQUIRED_PER_LEAGUE-count),
            "research_screen_reached": bool(mapped) and count >= REQUIRED_PER_LEAGUE,
            "original_pit_feature_parity_certified": False,
        })
    return {
        "schema": "MATRIX_ALTERNATIVE_OOS_READINESS_GATE_V1",
        "status": "RESEARCH_SCREEN_ONLY_NO_PRODUCTION_AUTHORIZATION",
        "research_screen_minimum_per_league": REQUIRED_PER_LEAGUE,
        "all_six_research_screens_reached": all(x["research_screen_reached"] for x in results),
        "six_league_research_rows": results,
        "scorecard_all_competitions_rows": reported_total,
        "scientific_independent_model_certified": False,
        "original_model_parity_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    if set(args.out.parts) & {"telegram", "notifications", "governance", "daily_prematch_reports"}:
        raise SystemExit("RESEARCH_GATE_MUST_NOT_WRITE_PRODUCTION")
    data = evaluate(json.loads((args.root/SCORECARD).read_text(encoding="utf-8")),
                    json.loads((args.root/SCOPE).read_text(encoding="utf-8")))
    dst = args.out if args.out.is_absolute() else args.root/args.out
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"status":data["status"],
                      "all_six_research_screens_reached":data["all_six_research_screens_reached"],
                      "production_authorized":False}))


if __name__ == "__main__":
    main()
