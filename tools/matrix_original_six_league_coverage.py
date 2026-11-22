"""Strict original six-league scope progress over independent free-provider OOS.

Competition correspondence is not fixture identity or enriched-feature parity.
This read-only tracker cannot promote official probabilities or send Telegram.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

REGISTRY = Path("evidence/api_football/governance/alternative_producer_original_six_league_registry.json")
SCORECARD = Path("evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json")
OUT = Path("evidence/football_world_inventory/MATRIX_ORIGINAL_SIX_LEAGUE_FREE_SOURCE_SCOPE_PROGRESS_LAST.json")
# Native football-data.org competition IDs to original API-Football league IDs.
# Competition-level link only. No claim about fixtures, features or calibration.
CORRESPONDENCE = {
    "39": ("2021", "PL"),
    "61": ("2015", "FL1"),
    "78": ("2002", "BL1"),
    "135": ("2019", "SA"),
    "140": ("2014", "PD"),
    "239": (None, None),  # Colombian Primera A is not covered by this source.
}
MIN_RESEARCH_SETTLEMENTS = 30

def audit(root: Path) -> dict:
    registry_bytes = (root / REGISTRY).read_bytes()
    score_bytes = (root / SCORECARD).read_bytes()
    registry = json.loads(registry_bytes)
    score = json.loads(score_bytes)
    original = registry.get("original_six_league_ids")
    if (registry.get("schema") != "MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        or registry.get("scope_approved") is not True
        or original != ["39","61","78","135","140","239"]
        or score.get("schema") != "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_V1"
        or score.get("provider") != "FOOTBALL_DATA_ORG"
        or score.get("production_p_matrix_authorized") is not False
        or score.get("telegram_signal_authorized") is not False
        or score.get("real_money") != "BLOCKED"):
        raise ValueError("SIX_LEAGUE_SOURCE_OR_GOVERNANCE_INVALID")
    groups = {}
    for item in score.get("provider_competitions", []):
        ident = str(item["source_competition_id"])
        n = item["independent_out_of_sample_rows"]
        if ident in groups or type(n) is not int or n < 0:
            raise ValueError("DUPLICATE_OR_INVALID_NATIVE_LEAGUE_SETTLEMENT")
        groups[ident] = n
    if sum(groups.values()) != score.get("total_verified_settled_rows"):
        raise ValueError("OVERALL_RESEARCH_SETTLEMENT_COUNT_INCONSISTENT")
    names = {str(row["id"]): str(row["name"]) for row in registry["leagues"]}
    rows = []
    assigned = set()
    for original_id in original:
        native_id, code = CORRESPONDENCE[original_id]
        count = groups.get(native_id, 0) if native_id else 0
        if native_id:
            assigned.add(native_id)
        rows.append({
            "original_league_id": original_id,
            "original_league_name": names[original_id],
            "free_provider_competition_id": native_id,
            "free_provider_competition_code": code,
            "competition_level_scope_link_only": native_id is not None,
            "free_source_coverage_missing": native_id is None,
            "independent_verified_settled_rows": count,
            "minimum_research_rows": MIN_RESEARCH_SETTLEMENTS,
            "remaining_settled_rows_for_screening": max(0, MIN_RESEARCH_SETTLEMENTS - count),
            "minimum_research_sample_reached": count >= MIN_RESEARCH_SETTLEMENTS,
            "fixture_identity_crosswalk_certified": False,
            "original_enriched_feature_equivalence_certified": False,
            "official_p_matrix_authorized": False,
        })
    in_scope = sum(groups.get(k, 0) for k in assigned)
    outside = sum(groups.values()) - in_scope
    return {
        "schema": "MATRIX_ORIGINAL_SIX_LEAGUE_FREE_SOURCE_SCOPE_PROGRESS_V1",
        "status": "SIX_LEAGUE_OOS_AND_SOURCE_PARITY_PENDING",
        "provider": "FOOTBALL_DATA_ORG",
        "original_six_league_count": 6,
        "free_source_mapped_competition_count": 5,
        "free_source_uncovered_original_leagues": ["239"],
        "all_provider_research_settlements": score["total_verified_settled_rows"],
        "original_scope_corresponding_five_league_settlements": in_scope,
        "out_of_original_scope_research_settlements": outside,
        "original_six_leagues": rows,
        "original_six_league_minimum_research_samples_all_met": False,
        "match_level_crosswalk_verified": False,
        "enriched_feature_parity_verified": False,
        "scientific_oos_certified": False,
        "source_registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "source_scorecard_sha256": hashlib.sha256(score_bytes).hexdigest(),
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if any(x in args.out.parts for x in ("telegram", "governance", "daily_prematch_reports")):
        raise SystemExit("ORIGINAL_SCOPE_PROGRESS_CANNOT_WRITE_PRODUCTION")
    row = audit(args.root)
    target = args.out if args.out.is_absolute() else args.root / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(row, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"mapped_five_league_settled": row["original_scope_corresponding_five_league_settlements"],
                      "outside_original_scope": row["out_of_original_scope_research_settlements"],
                      "uncovered_original_league": "239",
                      "telegram_authorized": False}, sort_keys=True))

if __name__ == "__main__":
    main()
