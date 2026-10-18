from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle

ENGINE_ID = "calibrated_log_pool_v1_over_2_5"
EXPECTED_PARAMS = {"a": 0.6, "b": 0.0, "c": 0.4}
DEFAULT_SOURCE_CYCLE = Path(
    "evidence/api_football/prospective_daily/2026-10-06/20261006T120503Z"
)
EXPECTED_READY_INPUTS = 138
EXPECTED_GOVERNED_ROWS = 132


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return value


def _sha(payload: Any) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _utc(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def _market_row(governance: Mapping[str, Any], market: str) -> Mapping[str, Any]:
    rows = governance.get("markets")
    if not isinstance(rows, list):
        raise ValueError("MARKET_GOVERNANCE_ROWS_MISSING")
    for row in rows:
        if isinstance(row, Mapping) and row.get("market") == market:
            return row
    raise ValueError(f"MARKET_NOT_FOUND:{market}")


def _global_over25_cell(summary: Mapping[str, Any]) -> Mapping[str, Any]:
    rows = summary.get("football_global_cells")
    if not isinstance(rows, list):
        raise ValueError("GLOBAL_STRENGTH_FOOTBALL_CELLS_MISSING")
    for row in rows:
        if isinstance(row, Mapping) and row.get("market") == "OVER_2_5":
            return row
    raise ValueError("GLOBAL_OVER25_CELL_MISSING")


def build_market_scoped_promotion(
    root: Path,
    *,
    source_cycle: Path = DEFAULT_SOURCE_CYCLE,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)

    final = _load(root / "evidence/api_football/challenger/final_holdout_adjudication.json")
    final_over = final["metrics"]["over_2_5"]
    if final_over.get("market_superiority") is not True:
        raise ValueError("OVER25_FINAL_HOLDOUT_NOT_SUPERIOR")
    if final_over.get("beats_poisson_brier") is not True or final_over.get("beats_poisson_log_loss") is not True:
        raise ValueError("OVER25_FINAL_HOLDOUT_PROPER_SCORE_GATE_FAILED")
    if int(final.get("holdout_row_count") or 0) != 357:
        raise ValueError("FINAL_HOLDOUT_ROW_COUNT_CHANGED")
    if final.get("parameter_refit_performed") is not False or final.get("parameter_search_performed") is not False:
        raise ValueError("FINAL_HOLDOUT_PARAMETER_MUTATION_DETECTED")

    governance = _load(root / "evidence/api_football/market_governance/market_governance.json")
    over_gov = _market_row(governance, "over_2_5")
    if over_gov.get("market_holdout_gate_passed") is not True:
        raise ValueError("OVER25_MARKET_GOVERNANCE_HOLDOUT_GATE_FAILED")
    if over_gov.get("challenger_name") != "calibrated_log_pool_v1":
        raise ValueError("OVER25_MODEL_ID_CHANGED")
    frozen = over_gov.get("frozen_parameters")
    if not isinstance(frozen, Mapping):
        raise ValueError("OVER25_FROZEN_PARAMETERS_MISSING")
    actual_params = {k: float(frozen[k]) for k in ("a", "b", "c")}
    if actual_params != EXPECTED_PARAMS:
        raise ValueError("OVER25_FROZEN_PARAMETERS_CHANGED")

    checkpoint = _load(
        root / "evidence/api_football/calibration_v2/checkpoint_200_1x2_over_2_5_20261006.json"
    )
    cp = checkpoint["market_adjudication"]["over_2_5"]
    if cp.get("gate_passed") is not True:
        raise ValueError("OVER25_PROSPECTIVE_CHECKPOINT_200_FAILED")
    if cp.get("beats_poisson_brier") is not True or cp.get("beats_poisson_log_loss") is not True:
        raise ValueError("OVER25_PROSPECTIVE_PROPER_SCORE_GATE_FAILED")
    if int(cp["challenger"]["sample_size"]) != 200:
        raise ValueError("OVER25_CHECKPOINT_SAMPLE_CHANGED")

    strength = _load(root / "evidence/global_strength_map/summary.json")
    strong = _global_over25_cell(strength)
    metrics = strong.get("metrics")
    if strong.get("strength_class") != "STRONG" or not isinstance(metrics, Mapping):
        raise ValueError("OVER25_GLOBAL_STRENGTH_NOT_STRONG")
    if int(metrics.get("n") or 0) < 200:
        raise ValueError("OVER25_GLOBAL_STRENGTH_SAMPLE_TOO_SMALL")
    for key in ("paired_brier", "paired_log_loss"):
        interval = metrics[key]["ci95"]
        if not isinstance(interval, list) or len(interval) != 2 or float(interval[1]) >= 0:
            raise ValueError(f"OVER25_GLOBAL_CI_NOT_FULLY_FAVORABLE:{key}")

    lane = _load(root / "evidence/api_football/calibration_v2/lanes/over_2_5/state.json")
    if lane.get("parameter_tuning_allowed") is not False:
        raise ValueError("OVER25_PARAMETER_TUNING_MUST_REMAIN_DISABLED")
    if lane.get("no_backfill") is not True:
        raise ValueError("OVER25_NO_BACKFILL_PROTECTION_MISSING")
    if lane.get("metrics_opened") is not False:
        raise ValueError("OVER25_LANE_METRICS_MUST_REMAIN_SEALED")
    if lane.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_REMAIN_BLOCKED")

    uniqueness = _load(root / "evidence/api_football/physical_uniqueness/audit_last.json")
    if uniqueness.get("result") != "PASS" or uniqueness.get("blockers") != []:
        raise ValueError("FOOTBALL_PHYSICAL_UNIQUENESS_NOT_PASS")
    if int(uniqueness.get("duplicate_fixture_id_groups") or 0) != 0:
        raise ValueError("FOOTBALL_DUPLICATE_FIXTURE_IDS_PRESENT")

    freeze_manifest = _load(root / "evidence/api_football/prospective_market_freeze/manifest.json")
    protections = freeze_manifest.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("FREEZE_PROTECTIONS_MISSING")
    required_false = (
        "missing_feature_imputation",
        "odds_used_to_generate_probability",
        "outcomes_read_at_freeze",
        "p_matrix_generated",
        "automatic_wagering",
    )
    if any(protections.get(k) is not False for k in required_false):
        raise ValueError("FREEZE_PROTECTION_CHANGED")
    if protections.get("freeze_strictly_before_kickoff") is not True:
        raise ValueError("FREEZE_PREMATCH_PROTECTION_MISSING")
    if protections.get("original_357_holdout_excluded") is not True:
        raise ValueError("ORIGINAL_HOLDOUT_EXCLUSION_MISSING")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("FREEZE_REAL_MONEY_MUST_REMAIN_BLOCKED")

    cycle_root = root / source_cycle
    canonical, canonical_manifest = load_chunked_canonical_bundle(cycle_root / "canonical_analysis")
    inputs = canonical.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != EXPECTED_READY_INPUTS:
        raise ValueError("SOURCE_CYCLE_READY_INPUT_COUNT_CHANGED")
    if int(canonical_manifest.get("ready_input_count") or 0) != EXPECTED_READY_INPUTS:
        raise ValueError("SOURCE_CYCLE_MANIFEST_READY_COUNT_CHANGED")

    freeze = _load(root / "evidence/api_football/prospective_market_freeze/freeze.json")
    freeze_rows = freeze.get("rows")
    if not isinstance(freeze_rows, list):
        raise ValueError("FREEZE_ROWS_MISSING")
    by_id = {
        str(row.get("fixture_id")): row
        for row in freeze_rows
        if isinstance(row, Mapping) and row.get("fixture_id") is not None
    }
    canonical_ids = {str(row["fixture_id"]) for row in inputs}
    matched = [by_id[fid] for fid in canonical_ids if fid in by_id]
    if len(matched) != EXPECTED_GOVERNED_ROWS:
        raise ValueError(
            f"OVER25_SOURCE_CYCLE_FREEZE_INTERSECTION_CHANGED:{len(matched)}"
        )

    parameter_sha256 = _sha(EXPECTED_PARAMS)
    matrix_rows: list[dict[str, Any]] = []
    for row in matched:
        if row.get("outcome") is not None:
            raise ValueError(f"FREEZE_OUTCOME_MUTATED:{row.get('fixture_id')}")
        if row.get("p_matrix") is not None:
            raise ValueError(f"LEGACY_P_MATRIX_ALREADY_SET:{row.get('fixture_id')}")
        if row.get("odds_used_to_generate_probability") is not False:
            raise ValueError(f"ODDS_TO_PROBABILITY_DETECTED:{row.get('fixture_id')}")
        freeze_at = _utc(row["freeze_at_utc"])
        kickoff = _utc(row["kickoff_utc"])
        if freeze_at >= kickoff:
            raise ValueError(f"NON_PREMATCH_FREEZE:{row.get('fixture_id')}")
        probs = row.get("frozen_research_probabilities")
        if not isinstance(probs, Mapping):
            raise ValueError(f"FROZEN_PROBABILITIES_MISSING:{row.get('fixture_id')}")
        p = float(probs["over_2_5"])
        if not 0.0 < p < 1.0:
            raise ValueError(f"INVALID_OVER25_PROBABILITY:{row.get('fixture_id')}")
        matrix_rows.append(
            {
                "fixture_id": str(row["fixture_id"]),
                "competition_id": row.get("competition_id"),
                "competition_name": row.get("competition_name"),
                "home_team_id": row.get("home_team_id"),
                "home_team_name": row.get("home_team_name"),
                "away_team_id": row.get("away_team_id"),
                "away_team_name": row.get("away_team_name"),
                "kickoff_utc": row.get("kickoff_utc"),
                "freeze_at_utc": row.get("freeze_at_utc"),
                "market": "OVER_2_5",
                "p_matrix": p,
                "source_frozen_probability_over_2_5": p,
                "source_freeze_row_sha256": _sha(row),
                "engine_id": ENGINE_ID,
                "parameter_sha256": parameter_sha256,
                "odds_used_to_generate_probability": False,
                "target_outcome_used": False,
                "bet_decision": None,
            }
        )
    matrix_rows.sort(key=lambda r: (str(r["kickoff_utc"]), int(r["fixture_id"])))
    matched_ids = {r["fixture_id"] for r in matrix_rows}
    blocked_ids = sorted(canonical_ids - matched_ids, key=int)

    promotion = {
        "schema": "MATRIX_FOOTBALL_OVER25_P_MATRIX_MARKET_PROMOTION_V1",
        "adjudicated_at_utc": now.isoformat(),
        "market": "OVER_2_5",
        "engine_id": ENGINE_ID,
        "promotion_status": "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
        "promotion_scope": "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
        "engine_executable_for_p_matrix": True,
        "governed_p_matrix_engine_available": True,
        "frozen_parameters": EXPECTED_PARAMS,
        "parameter_sha256": parameter_sha256,
        "parameter_refit_performed": False,
        "parameter_search_performed": False,
        "evidence_gates": {
            "final_holdout_357": {
                "passed": True,
                "challenger_brier": final_over["challenger"]["brier_score"],
                "poisson_brier": final_over["poisson"]["brier_score"],
                "challenger_log_loss": final_over["challenger"]["log_loss"],
                "poisson_log_loss": final_over["poisson"]["log_loss"],
                "holdout_seal_sha256": final["holdout_seal_sha256_verified"],
            },
            "prospective_checkpoint_200": {
                "passed": True,
                "delta_brier": cp["delta_brier_challenger_minus_poisson"],
                "delta_log_loss": cp["delta_log_loss_challenger_minus_poisson"],
                "sample_size": cp["challenger"]["sample_size"],
            },
            "global_strength": {
                "passed": True,
                "strength_class": strong["strength_class"],
                "n": metrics["n"],
                "paired_brier_ci95": metrics["paired_brier"]["ci95"],
                "paired_log_loss_ci95": metrics["paired_log_loss"]["ci95"],
            },
            "physical_uniqueness": {
                "passed": True,
                "freeze_rows": uniqueness["freeze_rows"],
                "unique_fixture_ids": uniqueness["unique_fixture_ids"],
                "duplicate_fixture_id_groups": uniqueness["duplicate_fixture_id_groups"],
            },
            "source_cycle_freeze_binding": {
                "passed": True,
                "canonical_ready_inputs": len(inputs),
                "governed_p_matrix_rows": len(matrix_rows),
                "blocked_without_valid_freeze": len(blocked_ids),
            },
        },
        "legacy_sport_wide_engine_gate": {
            "superseded": False,
            "scope": "SPORT_WIDE_OR_REAL_MONEY",
            "note": (
                "This market-scoped promotion does not promote 1X2, BTTS, automatic wagering, "
                "or real-money execution and does not claim the external audit is closed."
            ),
        },
        "other_markets": {
            "1X2": "NOT_PROMOTED_BY_THIS_GATE",
            "BTTS": "NO_GO",
        },
        "downstream_policy": {
            "physical_bookmaker_odds_required": True,
            "minimum_decimal_odds_exclusive": 1.50,
            "break_even_required": True,
            "ev_required": True,
            "bet_no_bet_is_separate_from_probability_generation": True,
        },
        "protections": {
            "no_backfill": True,
            "missing_not_zero": True,
            "silent_imputation": False,
            "odds_to_p_matrix": False,
            "target_outcomes_used_to_generate_probability": False,
            "parameter_tuning": False,
            "automatic_wagering": False,
            "external_audit_closed": False,
            "real_money": "BLOCKED",
        },
    }

    p_matrix = {
        "schema": "MATRIX_FOOTBALL_OVER25_GOVERNED_P_MATRIX_V1",
        "generated_at_utc": now.isoformat(),
        "market": "OVER_2_5",
        "engine_id": ENGINE_ID,
        "p_matrix_status": "GENERATED_GOVERNED_MARKET_SCOPED",
        "promotion_artifact": "evidence/api_football/governance/over_2_5_p_matrix_promotion.json",
        "source_cycle": source_cycle.as_posix(),
        "source_canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"),
        "source_freeze_sha256": freeze_manifest.get("freeze_sha256"),
        "source_ready_input_count": len(inputs),
        "scored_count": len(matrix_rows),
        "blocked_count": len(blocked_ids),
        "blocked_fixture_ids": blocked_ids,
        "rows": matrix_rows,
        "protections": {
            "p_matrix_equals_immutable_frozen_probability": True,
            "parameter_refit": False,
            "parameter_search": False,
            "odds_used_to_generate_probability": False,
            "target_outcomes_used": False,
            "bet_decisions_generated": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    p_matrix["bundle_sha256"] = _sha(
        {k: v for k, v in p_matrix.items() if k != "bundle_sha256"}
    )
    promotion["generated_p_matrix_bundle_sha256"] = p_matrix["bundle_sha256"]
    return promotion, p_matrix


def main() -> None:
    root = Path(".")
    promotion, p_matrix = build_market_scoped_promotion(root)

    promotion_path = root / "evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(promotion, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    matrix_path = (
        root
        / DEFAULT_SOURCE_CYCLE
        / "p_matrix_governed"
        / "over_2_5.json"
    )
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_text(
        json.dumps(p_matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "promotion_status": promotion["promotion_status"],
                "market": promotion["market"],
                "engine_id": promotion["engine_id"],
                "scored_count": p_matrix["scored_count"],
                "blocked_count": p_matrix["blocked_count"],
                "bundle_sha256": p_matrix["bundle_sha256"],
                "real_money": promotion["protections"]["real_money"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
