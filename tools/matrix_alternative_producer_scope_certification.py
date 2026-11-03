"""Scope-specific, immutable-evidence alternative producer certification.

Certifies only historical raw-group replay when documented. Never grants
original calibrated model equivalence or production authority from replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("CERTIFICATION_SOURCE_NOT_OBJECT")
    return data


def certify(historical: dict, prospective: dict, historical_hash: str,
            prospective_hash: str) -> dict:
    """Fail-closed. A historical replay cannot authorize an unverified producer."""
    if not all(isinstance(h, str) and len(h) == 64
               and all(c in "0123456789abcdef" for c in h)
               for h in (historical_hash, prospective_hash)):
        raise ValueError("CERTIFICATION_INVALID_SHA256")
    if historical.get("schema") != "MATRIX_INDEPENDENT_OVER25_SERIE_A_SOURCE_PARITY_V1":
        raise ValueError("CERTIFICATION_HISTORICAL_SCHEMA_UNEXPECTED")
    if prospective.get("schema") != "MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1":
        raise ValueError("CERTIFICATION_PROSPECTIVE_SCHEMA_UNEXPECTED")
    if (historical.get("real_money") != "BLOCKED"
        or prospective.get("real_money") != "BLOCKED"
        or historical.get("signal_generation_authorized") is not False
        or prospective.get("telegram_signal_authorized") is not False
        or prospective.get("calibration_untouched") is not True
        or prospective.get("production_p_matrix_authorized_count") != 0):
        raise ValueError("CERTIFICATION_GOVERNANCE_INVALID")
    feature = historical.get("raw_group_feature_parity")
    if not isinstance(feature, dict):
        raise ValueError("CERTIFICATION_FEATURE_EVIDENCE_MISSING")

    # Only source-grounded, zero-difference raw replay gets a scoped historical PASS.
    historic_pass = all((
        historical.get("history_result_concordance_verified") is True,
        historical.get("free_provider_http_status") == 200,
        historical.get("matched_exact_result_count", 0) >= 75,
        historical.get("score_disagreement_count") == 0,
        historical.get("ambiguous_count") == 0,
        feature.get("pairs_with_matching_full_time_score", 0) >= 75,
        feature.get("scoreable_both", 0) >= 30,
        feature.get("same_raw_group_feature_and_probability_count", -1)
          == feature.get("scoreable_both"),
        feature.get("different_raw_group_feature_or_probability_count") == 0,
        feature.get("blocked_one_side") == 0,
        feature.get("max_absolute_model_probability_difference") == 0,
        feature.get("future_target_outcomes_used") is False,
        feature.get("original_p_matrix_calibration_refit") is False,
        feature.get("canonical_enriched_pit_parity_verified") is False,
        historical.get("calibrated_model_feature_equivalence_verified") is False,
        historical.get("equivalence_across_all_six_leagues_verified") is False,
    ))
    prospective_rows = prospective.get("rows")
    if not isinstance(prospective_rows, list):
        raise ValueError("CERTIFICATION_PROSPECTIVE_ROWS_MISSING")
    if len(prospective_rows) != prospective.get("championship_fixture_count"):
        raise ValueError("CERTIFICATION_PROSPECTIVE_COUNT_MISMATCH")
    if any(row.get("governed_probability_authorized") is not False
           or row.get("telegram_signal_authorized") is not False
           for row in prospective_rows):
        raise ValueError("CERTIFICATION_UNAUTHORIZED_PROSPECTIVE_PROBABILITY")

    # This attestation is intentionally NOT a GO gate. Production requires
    # independently evidenced enriched feature, OOS and prospective parity.
    blockers = [
        "ORIGINAL_ENRICHED_FEATURE_PARITY_NOT_CERTIFIED",
        "ALL_SIX_LEAGUES_NOT_CERTIFIED",
        "PROSPECTIVE_GOVERNED_PROBABILITY_NOT_CERTIFIED",
        "OUT_OF_SAMPLE_CALIBRATION_AND_HOLDOUT_NOT_CERTIFIED",
    ]
    if not historic_pass:
        blockers.insert(0, "HISTORICAL_RAW_GROUP_REPLAY_NOT_CERTIFIED")
    return {
        "schema": "MATRIX_ALTERNATIVE_PRODUCER_SCOPE_CERTIFICATE_V1",
        "status": ("PASS_SCOPED_HISTORICAL_RAW_GROUP_ONLY_PRODUCTION_BLOCKED"
                   if historic_pass else "BLOCKED_HISTORICAL_PARITY_EVIDENCE"),
        "source_sha256": {
            "historical_parity": historical_hash,
            "prospective_pit": prospective_hash,
        },
        "historical_scope": {
            "league": "SERIE_A_2026",
            "matched_results": historical.get("matched_exact_result_count"),
            "scoreable_raw_group_pairs": feature.get("scoreable_both"),
            "identical_raw_group_pairs": feature.get(
                "same_raw_group_feature_and_probability_count"),
            "different_raw_group_pairs": feature.get(
                "different_raw_group_feature_or_probability_count"),
            "certified": historic_pass,
            "meaning": "HISTORICAL_RAW_GROUP_REPLAY_ONLY_NOT_MODEL_EQUIVALENCE",
        },
        "prospective_scope": {
            "league": "CHAMPIONSHIP_2026",
            "day": prospective.get("target_date_bogota"),
            "fixtures": len(prospective_rows),
            "research_history_certified": prospective.get(
                "prospective_research_history_certified_count"),
            "governed_probability_authorized": 0,
        },
        "required_before_production": blockers,
        "full_alternative_producer_certified": False,
        "original_calibration_untouched": True,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", type=Path, required=True)
    ap.add_argument("--prospective", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if "daily_prematch_reports" in args.out.parts or "telegram" in args.out.parts:
        raise SystemExit("CERTIFICATION_CANNOT_WRITE_CANONICAL_OR_TELEGRAM")
    result = certify(read_object(args.historical), read_object(args.prospective),
                     digest(args.historical), digest(args.prospective))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "historical_scope_certified":
                          result["historical_scope"]["certified"],
                      "full_alternative_producer_certified": False,
                      "telegram_signal_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
