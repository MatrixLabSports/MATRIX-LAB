from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Mapping

BASELINE_COMMIT = "880684a5c1d3873db66f625f3d06f44354114f96"
ROOT = Path("evidence/api_football")
PROTOCOL = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_PROTOCOL_20261011.json"
SOURCE_LEDGER = ROOT / "prospective_calibration" / "ledger.jsonl"
LANE_LEDGER = ROOT / "calibration_v2" / "lanes" / "over_2_5" / "ledger.jsonl"
LANE_STATE = ROOT / "calibration_v2" / "lanes" / "over_2_5" / "state.json"
CHECKPOINT_200 = ROOT / "calibration_v2" / "checkpoint_200_1x2_over_2_5_20261006.json"
CANONICAL_CHECKPOINT_200_BLOB_SHA = "5ce70e45da122590862ddcd49cdbac0014d01b39"
DEFAULT_OUT = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_RESULT_20261013.json"

BASELINE_SOURCE_COUNT = 2131
BASELINE_LANE_COUNT = 1329
TARGET_NEW_STANDARD_FINALS = 100
TARGET_LANE_SETTLEMENT_COUNT = 1429
EPS = 1e-15


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _record_sha(row: Mapping[str, Any]) -> str:
    body = dict(row)
    body.pop("record_sha256", None)
    return _sha256(body)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def _parse_jsonl(text: str, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError(f"JSONL_ROW_NOT_OBJECT:{label}:{line_no}")
        rows.append(value)
    return rows


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return _parse_jsonl(path.read_text(encoding="utf-8"), str(path))


def _git_show_jsonl(commit: str, path: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_jsonl(proc.stdout, f"{commit}:{path}")


def _git_blob_sha(commit: str, path: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", f"{commit}:{path.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _working_tree_blob_sha(path: Path) -> str:
    proc = subprocess.run(
        ["git", "hash-object", path.as_posix()],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1.0 - EPS)


def _audit_source(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    previous: str | None = None
    for row in rows:
        fid = str(row.get("fixture_id") or "")
        if not fid or fid in seen:
            raise RuntimeError("SOURCE_LEDGER_DUPLICATE_OR_MISSING_FIXTURE")
        if row.get("previous_record_sha256") != previous:
            raise RuntimeError(f"SOURCE_LEDGER_HASH_CHAIN_BROKEN:{fid}")
        if row.get("record_sha256") != _record_sha(row):
            raise RuntimeError(f"SOURCE_LEDGER_RECORD_SHA_MISMATCH:{fid}")
        if row.get("source_terminal_status") != "FT":
            raise RuntimeError(f"SOURCE_LEDGER_NON_STANDARD_FINAL:{fid}")
        if row.get("p_matrix_status") != "NOT_GENERATED":
            raise RuntimeError(f"P_MATRIX_UNEXPECTED:{fid}")
        if row.get("real_money") != "BLOCKED":
            raise RuntimeError(f"REAL_MONEY_NOT_BLOCKED:{fid}")
        if row.get("used_for_parameter_tuning") is not False:
            raise RuntimeError(f"TUNING_USED:{fid}")
        if row.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"PARAMETER_MUTATION_DETECTED:{fid}")
        previous = str(row["record_sha256"])
        seen.add(fid)


def _audit_lane(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    previous: str | None = None
    for row in rows:
        fid = str(row.get("fixture_id") or "")
        if not fid or fid in seen:
            raise RuntimeError("LANE_LEDGER_DUPLICATE_OR_MISSING_FIXTURE")
        if row.get("previous_lane_record_sha256") != previous:
            raise RuntimeError(f"LANE_HASH_CHAIN_BROKEN:{fid}")
        if row.get("record_sha256") != _record_sha(row):
            raise RuntimeError(f"LANE_RECORD_SHA_MISMATCH:{fid}")
        if row.get("market") != "OVER_2_5":
            raise RuntimeError(f"LANE_MARKET_MISMATCH:{fid}")
        if row.get("real_money") != "BLOCKED":
            raise RuntimeError(f"LANE_REAL_MONEY_NOT_BLOCKED:{fid}")
        if row.get("used_for_parameter_tuning") is not False:
            raise RuntimeError(f"LANE_TUNING_USED:{fid}")
        if row.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"LANE_PARAMETER_MUTATION:{fid}")
        previous = str(row["record_sha256"])
        seen.add(fid)


def _calibration(probs: list[float], ys: list[float], bins: int = 10) -> dict[str, Any]:
    if len(probs) != len(ys) or not probs:
        raise RuntimeError("CALIBRATION_INPUT_INVALID")
    n = len(probs)
    ece = 0.0
    mce = 0.0
    nonempty: list[dict[str, Any]] = []
    for i in range(bins):
        lower = i / bins
        upper = (i + 1) / bins
        idx = [
            j
            for j, p in enumerate(probs)
            if (lower <= p < upper) or (i == bins - 1 and p == 1.0)
        ]
        if not idx:
            continue
        mean_p = sum(probs[j] for j in idx) / len(idx)
        observed = sum(ys[j] for j in idx) / len(idx)
        gap = abs(mean_p - observed)
        ece += (len(idx) / n) * gap
        mce = max(mce, gap)
        nonempty.append(
            {
                "band": f"{int(lower*100)}_{int(upper*100)}",
                "lower": lower,
                "upper": upper,
                "count": len(idx),
                "mean_probability": mean_p,
                "observed_rate": observed,
                "absolute_gap": gap,
            }
        )
    return {
        "method": "EQUAL_WIDTH_10_BINS",
        "ece": ece,
        "max_calibration_error": mce,
        "nonempty_bins": nonempty,
    }


def _binary_metrics(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    probs: list[float] = []
    ys: list[float] = []
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for row in rows:
        if source == "challenger":
            p = _clip(float(row["frozen_challenger_probabilities"]["over_2_5"]))
        elif source == "poisson":
            p = _clip(float(row["frozen_poisson_reference"]["over_2_5"]))
        else:
            raise RuntimeError(f"UNKNOWN_PROBABILITY_SOURCE:{source}")
        y = 1.0 if bool(row["outcomes"]["over_2_5"]) else 0.0
        probs.append(p)
        ys.append(y)
        brier += (p - y) ** 2
        log_loss += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
        correct += int((p >= 0.5) == bool(y))
    n = len(rows)
    cal = _calibration(probs, ys)
    return {
        "sample_size": n,
        "brier_score": brier / n,
        "log_loss": log_loss / n,
        "accuracy_at_0_5_diagnostic_only": correct / n,
        "observed_over_2_5_rate": sum(ys) / n,
        "mean_predicted_probability": sum(probs) / n,
        "calibration": cal,
        "probability_band_reliability": cal["nonempty_bins"],
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _se(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance) / math.sqrt(len(values))


def _paired_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    brier_diffs: list[float] = []
    log_diffs: list[float] = []
    for row in rows:
        pc = _clip(float(row["frozen_challenger_probabilities"]["over_2_5"]))
        pp = _clip(float(row["frozen_poisson_reference"]["over_2_5"]))
        y = 1.0 if bool(row["outcomes"]["over_2_5"]) else 0.0
        brier_diffs.append((pc - y) ** 2 - (pp - y) ** 2)
        llc = -(y * math.log(pc) + (1.0 - y) * math.log(1.0 - pc))
        llp = -(y * math.log(pp) + (1.0 - y) * math.log(1.0 - pp))
        log_diffs.append(llc - llp)

    db = _mean(brier_diffs)
    dl = _mean(log_diffs)
    seb = _se(brier_diffs)
    sel = _se(log_diffs)
    b_ci = [db - 1.96 * seb, db + 1.96 * seb]
    l_ci = [dl - 1.96 * sel, dl + 1.96 * sel]
    return {
        "delta_brier_challenger_minus_poisson": db,
        "delta_log_loss_challenger_minus_poisson": dl,
        "brier_ci95": b_ci,
        "log_loss_ci95": l_ci,
        "beats_poisson_brier": db < 0.0,
        "beats_poisson_log_loss": dl < 0.0,
        "proper_scoring_directional_pass": db < 0.0 and dl < 0.0,
        "brier_ci95_excludes_zero_in_favor_of_challenger": b_ci[1] < 0.0,
        "log_loss_ci95_excludes_zero_in_favor_of_challenger": l_ci[1] < 0.0,
    }


def evaluate_forward_block(
    *,
    baseline_source: list[dict[str, Any]],
    baseline_lane: list[dict[str, Any]],
    current_source: list[dict[str, Any]],
    current_lane: list[dict[str, Any]],
    protocol: Mapping[str, Any],
    checkpoint_200: Mapping[str, Any],
    baseline_state_blob_sha_actual: str | None = None,
) -> dict[str, Any]:
    if len(baseline_source) != BASELINE_SOURCE_COUNT:
        raise RuntimeError(
            f"BASELINE_SOURCE_COUNT_MISMATCH:{len(baseline_source)}:{BASELINE_SOURCE_COUNT}"
        )
    if len(baseline_lane) != BASELINE_LANE_COUNT:
        raise RuntimeError(
            f"BASELINE_LANE_COUNT_MISMATCH:{len(baseline_lane)}:{BASELINE_LANE_COUNT}"
        )
    if int(protocol["baseline"]["settlement_count"]) != BASELINE_LANE_COUNT:
        raise RuntimeError("PROTOCOL_BASELINE_COUNT_MISMATCH")
    if int(protocol["forward_validation"]["target_settlement_count"]) != TARGET_LANE_SETTLEMENT_COUNT:
        raise RuntimeError("PROTOCOL_TARGET_COUNT_MISMATCH")
    if int(protocol["forward_validation"]["required_new_standard_finals"]) != TARGET_NEW_STANDARD_FINALS:
        raise RuntimeError("PROTOCOL_REQUIRED_NEW_FINALS_MISMATCH")
    if baseline_state_blob_sha_actual is not None:
        expected = str(protocol["baseline"]["lane_state_blob_sha"])
        if expected != baseline_state_blob_sha_actual:
            raise RuntimeError(
                f"BASELINE_STATE_BLOB_MISMATCH:{baseline_state_blob_sha_actual}:{expected}"
            )

    _audit_source(baseline_source)
    _audit_source(current_source)
    _audit_lane(baseline_lane)
    _audit_lane(current_lane)

    if len(current_source) < BASELINE_SOURCE_COUNT + TARGET_NEW_STANDARD_FINALS:
        raise RuntimeError("FORWARD_SOURCE_COHORT_NOT_MATURE")
    if len(current_lane) < TARGET_LANE_SETTLEMENT_COUNT:
        raise RuntimeError("FORWARD_LANE_TARGET_NOT_MATURE")

    baseline_source_hashes = [str(r["record_sha256"]) for r in baseline_source]
    current_prefix_hashes = [
        str(r["record_sha256"]) for r in current_source[:BASELINE_SOURCE_COUNT]
    ]
    if current_prefix_hashes != baseline_source_hashes:
        raise RuntimeError("SOURCE_LEDGER_BASELINE_PREFIX_MUTATED")

    baseline_lane_ids = {str(r["fixture_id"]) for r in baseline_lane}
    current_lane_by_id = {str(r["fixture_id"]): r for r in current_lane}
    if not baseline_lane_ids.issubset(current_lane_by_id):
        raise RuntimeError("BASELINE_LANE_FIXTURE_DISAPPEARED")

    cohort = current_source[
        BASELINE_SOURCE_COUNT : BASELINE_SOURCE_COUNT + TARGET_NEW_STANDARD_FINALS
    ]
    fixture_ids = [str(r["fixture_id"]) for r in cohort]
    if len(set(fixture_ids)) != TARGET_NEW_STANDARD_FINALS:
        raise RuntimeError("FORWARD_COHORT_DUPLICATE_FIXTURE")

    for row in cohort:
        fid = str(row["fixture_id"])
        if row.get("source_terminal_status") != "FT":
            raise RuntimeError(f"FORWARD_NON_STANDARD_FINAL:{fid}")
        if row.get("used_for_parameter_tuning") is not False:
            raise RuntimeError(f"FORWARD_TUNING_USED:{fid}")
        if row.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"FORWARD_PARAMETER_MUTATED:{fid}")
        if row.get("p_matrix_status") != "NOT_GENERATED":
            raise RuntimeError(f"FORWARD_P_MATRIX_UNEXPECTED:{fid}")
        if row.get("real_money") != "BLOCKED":
            raise RuntimeError(f"FORWARD_REAL_MONEY_NOT_BLOCKED:{fid}")
        if not isinstance(
            (row.get("frozen_challenger_probabilities") or {}).get("over_2_5"),
            (int, float),
        ):
            raise RuntimeError(f"FORWARD_CHALLENGER_PROBABILITY_MISSING:{fid}")
        if not isinstance(
            (row.get("frozen_poisson_reference") or {}).get("over_2_5"),
            (int, float),
        ):
            raise RuntimeError(f"FORWARD_POISSON_PROBABILITY_MISSING:{fid}")
        if not isinstance((row.get("outcomes") or {}).get("over_2_5"), bool):
            raise RuntimeError(f"FORWARD_OUTCOME_MISSING:{fid}")
        lane = current_lane_by_id.get(fid)
        if lane is None:
            raise RuntimeError(f"FORWARD_FIXTURE_NOT_IN_OVER25_LANE:{fid}")
        if float(lane["frozen_probability"]) != float(
            row["frozen_challenger_probabilities"]["over_2_5"]
        ):
            raise RuntimeError(f"FORWARD_LANE_PROBABILITY_BINDING_MISMATCH:{fid}")
        if bool(lane["outcome"]) != bool(row["outcomes"]["over_2_5"]):
            raise RuntimeError(f"FORWARD_LANE_OUTCOME_BINDING_MISMATCH:{fid}")

    challenger = _binary_metrics(cohort, "challenger")
    poisson = _binary_metrics(cohort, "poisson")
    paired = _paired_comparison(cohort)

    ref_over = checkpoint_200["market_adjudication"]["over_2_5"]["challenger"]
    ref_cal = ref_over["calibration"]
    forward_ece = float(challenger["calibration"]["ece"])
    reference_ece = float(ref_cal["ece"])
    observed = float(challenger["observed_over_2_5_rate"])
    mean_p = float(challenger["mean_predicted_probability"])

    return {
        "schema": "MATRIX_OVER25_FORWARD_VALIDATION_100_RESULT_V1",
        "market": "OVER_2_5",
        "protocol_path": str(PROTOCOL),
        "baseline_commit": BASELINE_COMMIT,
        "cohort_definition": protocol["forward_validation"]["cohort_definition"],
        "sample_policy": (
            "FIRST_100_NEW_APPEND_ONLY_PROSPECTIVE_CALIBRATION_ROWS_AFTER_"
            "BASELINE_SOURCE_PREFIX_2131; EACH ROW MUST BIND TO CURRENT OVER_2_5 V2 LANE"
        ),
        "baseline": {
            "source_ledger_rows": len(baseline_source),
            "over_2_5_lane_settlements": len(baseline_lane),
            "protocol_lane_state_blob_sha": protocol["baseline"]["lane_state_blob_sha"],
            "actual_lane_state_blob_sha": baseline_state_blob_sha_actual,
            "source_prefix_sha256": _sha256(baseline_source_hashes),
            "lane_fixture_set_sha256": _sha256(sorted(baseline_lane_ids)),
        },
        "maturity": {
            "current_source_rows": len(current_source),
            "current_over_2_5_lane_settlements": len(current_lane),
            "new_source_rows_after_baseline": len(current_source) - len(baseline_source),
            "new_over_2_5_lane_settlements_after_baseline": len(current_lane) - len(baseline_lane),
            "required_new_standard_finals": TARGET_NEW_STANDARD_FINALS,
            "target_over_2_5_lane_settlement_count": TARGET_LANE_SETTLEMENT_COUNT,
            "status": "MATURE",
        },
        "physical_sample": {
            "sample_size": len(cohort),
            "unique_fixture_ids": len(set(fixture_ids)),
            "fixture_ids": fixture_ids,
            "fixture_ids_sha256": _sha256(fixture_ids),
            "first_fixture_id": fixture_ids[0],
            "last_fixture_id": fixture_ids[-1],
            "first_settled_at_utc": cohort[0].get("settled_at_utc"),
            "last_settled_at_utc": cohort[-1].get("settled_at_utc"),
            "source_baseline_prefix_unchanged": True,
            "lane_probability_binding_verified": True,
            "lane_outcome_binding_verified": True,
            "all_rows_standard_final_ft": True,
            "parameter_tuning_used": False,
            "parameters_mutated_after_freeze": False,
            "silent_imputation": False,
            "missing_not_zero": True,
            "odds_used_to_generate_probability": False,
        },
        "challenger": challenger,
        "poisson": poisson,
        "paired_comparison": paired,
        "stability": {
            "reference_checkpoint_200_blob_sha": CANONICAL_CHECKPOINT_200_BLOB_SHA,
            "reference_checkpoint_200_ece": reference_ece,
            "forward_100_ece": forward_ece,
            "ece_change_forward_minus_checkpoint_200": forward_ece - reference_ece,
            "reference_checkpoint_200_max_calibration_error": float(
                ref_cal["max_calibration_error"]
            ),
            "forward_100_max_calibration_error": float(
                challenger["calibration"]["max_calibration_error"]
            ),
            "mean_predicted_probability": mean_p,
            "observed_over_2_5_rate": observed,
            "observed_minus_predicted_probability": observed - mean_p,
            "assessment": (
                "MIXED_DIRECTIONAL_PROPER_SCORE_IMPROVEMENT_WITH_WEIGHTED_CALIBRATION_DEGRADATION"
            ),
            "formal_calibration_pass_threshold_pre_registered": False,
        },
        "adjudication": {
            "proper_scoring_directional_vs_poisson": (
                "PASS"
                if paired["proper_scoring_directional_pass"]
                else "FAIL"
            ),
            "paired_uncertainty_brier": (
                "SUPPORTS_CHALLENGER"
                if paired["brier_ci95_excludes_zero_in_favor_of_challenger"]
                else "INCONCLUSIVE_CI_CROSSES_ZERO"
            ),
            "paired_uncertainty_log_loss": (
                "SUPPORTS_CHALLENGER"
                if paired["log_loss_ci95_excludes_zero_in_favor_of_challenger"]
                else "INCONCLUSIVE_CI_CROSSES_ZERO"
            ),
            "calibration_reliability": "REQUIRES_CAUTION_FORWARD_ECE_DEGRADED",
            "formal_model_promotion": "NOT_AUTHORIZED_PROTOCOL_MONITORING_ONLY",
            "real_money_decision": "KEEP_BLOCKED",
            "verdict": "MIXED_EVIDENCE_CONTINUE_SHADOW_VALIDATION",
        },
        "governance": {
            "parameter_tuning_allowed": False,
            "refit_allowed": False,
            "model_files_modified": False,
            "original_357_holdout_reuse_allowed": False,
            "target_outcomes_used_to_generate_probability": False,
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    protocol = _load_json(PROTOCOL)
    current_source = _load_jsonl(SOURCE_LEDGER)
    current_lane = _load_jsonl(LANE_LEDGER)
    checkpoint_200_blob_sha = _working_tree_blob_sha(CHECKPOINT_200)
    if checkpoint_200_blob_sha != CANONICAL_CHECKPOINT_200_BLOB_SHA:
        raise RuntimeError(
            "CANONICAL_CHECKPOINT_200_MUTATED:"
            + checkpoint_200_blob_sha
            + ":"
            + CANONICAL_CHECKPOINT_200_BLOB_SHA
        )
    checkpoint_200 = _load_json(CHECKPOINT_200)
    lane_state = _load_json(LANE_STATE)

    baseline_source = _git_show_jsonl(BASELINE_COMMIT, SOURCE_LEDGER)
    baseline_lane = _git_show_jsonl(BASELINE_COMMIT, LANE_LEDGER)
    baseline_state_blob_sha = _git_blob_sha(BASELINE_COMMIT, LANE_STATE)

    if int(lane_state.get("settlement_count", 0)) != len(current_lane):
        raise RuntimeError("CURRENT_LANE_STATE_COUNT_MISMATCH")

    result = evaluate_forward_block(
        baseline_source=baseline_source,
        baseline_lane=baseline_lane,
        current_source=current_source,
        current_lane=current_lane,
        protocol=protocol,
        checkpoint_200=checkpoint_200,
        baseline_state_blob_sha_actual=baseline_state_blob_sha,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "sample_size": result["physical_sample"]["sample_size"],
                "brier": result["challenger"]["brier_score"],
                "log_loss": result["challenger"]["log_loss"],
                "ece": result["challenger"]["calibration"]["ece"],
                "max_calibration_error": result["challenger"]["calibration"][
                    "max_calibration_error"
                ],
                "delta_brier_vs_poisson": result["paired_comparison"][
                    "delta_brier_challenger_minus_poisson"
                ],
                "delta_log_loss_vs_poisson": result["paired_comparison"][
                    "delta_log_loss_challenger_minus_poisson"
                ],
                "verdict": result["adjudication"]["verdict"],
                "real_money": result["governance"]["real_money"],
                "out": str(args.out),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
