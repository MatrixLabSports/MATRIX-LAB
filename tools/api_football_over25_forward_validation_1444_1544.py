from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Mapping

ROOT = Path("evidence/api_football")
PROTOCOL_PATH = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_PROTOCOL_1444_1544.json"
LANE_STATE = ROOT / "calibration_v2" / "lanes" / "over_2_5" / "state.json"
LANE_LEDGER = ROOT / "calibration_v2" / "lanes" / "over_2_5" / "ledger.jsonl"
SOURCE_LEDGER = ROOT / "prospective_calibration" / "ledger.jsonl"
PROMOTION = ROOT / "governance" / "over_2_5_p_matrix_promotion.json"
PRIOR_RESULT = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_RESULT_20261013.json"
STATE_OUT = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_1444_1544_STATE.json"
RESULT_OUT = ROOT / "calibration_v2" / "OVER25_FORWARD_VALIDATION_1444_1544_RESULT.json"
EPS = 1e-15


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def _parse_jsonl(text: str, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
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
    p = subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        check=True, capture_output=True, text=True,
    )
    return _parse_jsonl(p.stdout, f"{commit}:{path}")


def _git_blob_sha(commit: str, path: Path) -> str:
    p = subprocess.run(
        ["git", "rev-parse", f"{commit}:{path.as_posix()}"],
        check=True, capture_output=True, text=True,
    )
    return p.stdout.strip()


def _working_blob_sha(path: Path) -> str:
    p = subprocess.run(["git", "hash-object", path.as_posix()], check=True, capture_output=True, text=True)
    return p.stdout.strip()


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1.0 - EPS)


def _calibration(probs: list[float], ys: list[float]) -> dict[str, Any]:
    n = len(probs)
    if n == 0 or n != len(ys):
        raise RuntimeError("CALIBRATION_INPUT_INVALID")
    ece = 0.0
    mce = 0.0
    bands: list[dict[str, Any]] = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        idx = [j for j, p in enumerate(probs) if (lo <= p < hi) or (i == 9 and p == 1.0)]
        if not idx:
            continue
        mp = sum(probs[j] for j in idx) / len(idx)
        oy = sum(ys[j] for j in idx) / len(idx)
        gap = abs(mp - oy)
        ece += (len(idx) / n) * gap
        mce = max(mce, gap)
        bands.append({
            "band": f"{i*10}_{(i+1)*10}",
            "lower": lo, "upper": hi, "count": len(idx),
            "mean_probability": mp, "observed_rate": oy, "absolute_gap": gap,
        })
    return {"method": "EQUAL_WIDTH_10_BINS", "ece": ece, "max_calibration_error": mce, "nonempty_bins": bands}


def _metrics(source_rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    probs: list[float] = []
    ys: list[float] = []
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for row in source_rows:
        if key == "challenger":
            p = _clip(float(row["frozen_challenger_probabilities"]["over_2_5"]))
        elif key == "poisson":
            p = _clip(float(row["frozen_poisson_reference"]["over_2_5"]))
        else:
            raise RuntimeError("UNKNOWN_PROBABILITY_SOURCE")
        y = 1.0 if bool(row["outcomes"]["over_2_5"]) else 0.0
        probs.append(p)
        ys.append(y)
        brier += (p - y) ** 2
        log_loss += -(y * math.log(p) + (1-y) * math.log(1-p))
        correct += int((p >= 0.5) == bool(y))
    n = len(source_rows)
    cal = _calibration(probs, ys)
    return {
        "sample_size": n,
        "brier_score": brier / n,
        "log_loss": log_loss / n,
        "ece": cal["ece"],
        "max_calibration_error": cal["max_calibration_error"],
        "observed_over_2_5_rate": sum(ys) / n,
        "mean_predicted_probability": sum(probs) / n,
        "accuracy_at_0_5_diagnostic_only": correct / n,
        "probability_band_reliability": cal["nonempty_bins"],
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _se(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x-m)**2 for x in xs) / (len(xs)-1)) / math.sqrt(len(xs))


def _paired(rows: list[dict[str, Any]]) -> dict[str, Any]:
    db: list[float] = []
    dl: list[float] = []
    for row in rows:
        pc = _clip(float(row["frozen_challenger_probabilities"]["over_2_5"]))
        pp = _clip(float(row["frozen_poisson_reference"]["over_2_5"]))
        y = 1.0 if bool(row["outcomes"]["over_2_5"]) else 0.0
        db.append((pc-y)**2 - (pp-y)**2)
        llc = -(y*math.log(pc) + (1-y)*math.log(1-pc))
        llp = -(y*math.log(pp) + (1-y)*math.log(1-pp))
        dl.append(llc-llp)
    mb, ml = _mean(db), _mean(dl)
    seb, sel = _se(db), _se(dl)
    return {
        "delta_brier_challenger_minus_poisson": mb,
        "delta_log_loss_challenger_minus_poisson": ml,
        "brier_ci95": [mb-1.96*seb, mb+1.96*seb],
        "log_loss_ci95": [ml-1.96*sel, ml+1.96*sel],
        "beats_poisson_brier": mb < 0,
        "beats_poisson_log_loss": ml < 0,
        "proper_scoring_directional_pass": mb < 0 and ml < 0,
    }


def _write_state(payload: Mapping[str, Any]) -> None:
    STATE_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def monitor_or_close() -> dict[str, Any]:
    protocol = _load_json(PROTOCOL_PATH)
    state = _load_json(LANE_STATE)
    promotion = _load_json(PROMOTION)
    prior = _load_json(PRIOR_RESULT)
    pre = protocol["preregistration"]
    fv = protocol["forward_validation"]
    frozen = protocol["frozen_engine"]

    if int(pre["baseline_over_2_5_settlements"]) != 1444:
        raise RuntimeError("BASELINE_NOT_1444")
    if int(fv["target_settlement_count"]) != 1544 or int(fv["required_new_standard_finals"]) != 100:
        raise RuntimeError("TARGET_NOT_1544_100")
    if promotion["parameter_sha256"] != frozen["parameter_sha256"]:
        raise RuntimeError("ENGINE_PARAMETER_SHA_CHANGED")
    if promotion["frozen_parameters"] != frozen["parameters"]:
        raise RuntimeError("ENGINE_PARAMETERS_CHANGED")
    if promotion["protections"]["parameter_tuning"] is not False:
        raise RuntimeError("PROMOTION_TUNING_UNEXPECTED")
    if promotion["protections"]["real_money"] != "BLOCKED":
        raise RuntimeError("PROMOTION_REAL_MONEY_NOT_BLOCKED")
    if state["parameter_tuning_allowed"] is not False or state["metrics_opened"] is not False:
        raise RuntimeError("CONTINUOUS_LANE_GOVERNANCE_CHANGED")
    if state["real_money"] != "BLOCKED" or state["automatic_wagering"] is not False:
        raise RuntimeError("LANE_REAL_MONEY_OR_AUTOWAGER_CHANGED")

    # Verify immutable preregistration anchors without opening outcomes.
    baseline_commit = str(pre["baseline_commit"])
    if _git_blob_sha(baseline_commit, SOURCE_LEDGER) != pre["baseline_source_ledger_blob_sha"]:
        raise RuntimeError("BASELINE_SOURCE_BLOB_MISMATCH")
    if _git_blob_sha(baseline_commit, LANE_LEDGER) != pre["baseline_over_2_5_lane_blob_sha"]:
        raise RuntimeError("BASELINE_LANE_BLOB_MISMATCH")
    if _git_blob_sha(baseline_commit, LANE_STATE) != pre["baseline_over_2_5_state_blob_sha"]:
        raise RuntimeError("BASELINE_STATE_BLOB_MISMATCH")
    if _working_blob_sha(PRIOR_RESULT) != pre["prior_forward_100_result_blob_sha"]:
        raise RuntimeError("PRIOR_FORWARD_RESULT_MUTATED")

    current = int(state["settlement_count"])
    baseline = int(fv["baseline_settlement_count"])
    target = int(fv["target_settlement_count"])
    new_count = max(0, current - baseline)
    remaining = max(0, target - current)

    pending_state = {
        "schema": "MATRIX_OVER25_FORWARD_VALIDATION_1444_1544_STATE_V1",
        "market": "OVER_2_5",
        "protocol_path": str(PROTOCOL_PATH),
        "baseline_commit": baseline_commit,
        "baseline_settlement_count": baseline,
        "target_settlement_count": target,
        "current_settlement_count": current,
        "new_settlements_after_baseline": new_count,
        "remaining_to_target": remaining,
        "cohort_size_required": 100,
        "metrics_opened": False,
        "outcomes_read_for_metrics": 0,
        "parameter_tuning_allowed": False,
        "refit_allowed": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "continuous_lane_metrics_remain_sealed": True,
        "status": "SEALED_PENDING" if current < target else "TARGET_REACHED_READY_TO_CLOSE",
    }

    if current < target:
        _write_state(pending_state)
        if RESULT_OUT.exists():
            raise RuntimeError("RESULT_EXISTS_BEFORE_TARGET")
        return pending_state

    # Only now are outcomes opened for the exact fixed cohort.
    baseline_lane = _git_show_jsonl(baseline_commit, LANE_LEDGER)
    current_lane = _load_jsonl(LANE_LEDGER)
    if len(baseline_lane) != baseline:
        raise RuntimeError("BASELINE_LANE_COUNT_MISMATCH")
    if len(current_lane) < target:
        raise RuntimeError("CURRENT_LANE_FILE_BELOW_TARGET")
    baseline_hashes = [r["record_sha256"] for r in baseline_lane]
    current_prefix_hashes = [r["record_sha256"] for r in current_lane[:baseline]]
    if current_prefix_hashes != baseline_hashes:
        mismatch_index = next(
            (
                i for i, (expected, actual)
                in enumerate(zip(baseline_hashes, current_prefix_hashes))
                if expected != actual
            ),
            min(len(baseline_hashes), len(current_prefix_hashes)),
        )
        baseline_row = baseline_lane[mismatch_index] if mismatch_index < len(baseline_lane) else {}
        current_row = current_lane[mismatch_index] if mismatch_index < len(current_lane) else {}
        raise RuntimeError(
            "BASELINE_LANE_PREFIX_MUTATED:"
            f"index={mismatch_index}:"
            f"baseline_fixture={baseline_row.get('fixture_id')}:"
            f"current_fixture={current_row.get('fixture_id')}:"
            f"baseline_hash={baseline_row.get('record_sha256')}:"
            f"current_hash={current_row.get('record_sha256')}"
        )

    cohort_lane = current_lane[baseline:target]
    if len(cohort_lane) != 100:
        raise RuntimeError("COHORT_NOT_EXACTLY_100")
    fixture_ids = [str(r["fixture_id"]) for r in cohort_lane]
    if len(set(fixture_ids)) != 100:
        raise RuntimeError("COHORT_DUPLICATE_FIXTURE")

    source_rows = _load_jsonl(SOURCE_LEDGER)
    source_by_id = {str(r["fixture_id"]): r for r in source_rows}
    cohort_source: list[dict[str, Any]] = []
    for lane in cohort_lane:
        fid = str(lane["fixture_id"])
        src = source_by_id.get(fid)
        if src is None:
            raise RuntimeError(f"SOURCE_BINDING_MISSING:{fid}")
        if src.get("source_terminal_status") != "FT":
            raise RuntimeError(f"NON_STANDARD_FINAL:{fid}")
        if src.get("used_for_parameter_tuning") is not False or src.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"TUNING_OR_MUTATION:{fid}")
        if src.get("p_matrix_status") != "NOT_GENERATED":
            raise RuntimeError(f"SOURCE_P_MATRIX_UNEXPECTED:{fid}")
        if src.get("real_money") != "BLOCKED":
            raise RuntimeError(f"SOURCE_REAL_MONEY_NOT_BLOCKED:{fid}")
        if float(lane["frozen_probability"]) != float(src["frozen_challenger_probabilities"]["over_2_5"]):
            raise RuntimeError(f"PROBABILITY_BINDING_MISMATCH:{fid}")
        if bool(lane["outcome"]) != bool(src["outcomes"]["over_2_5"]):
            raise RuntimeError(f"OUTCOME_BINDING_MISMATCH:{fid}")
        cohort_source.append(src)

    challenger = _metrics(cohort_source, "challenger")
    poisson = _metrics(cohort_source, "poisson")
    paired = _paired(cohort_source)
    previous_ece = float(prior["challenger"]["calibration"]["ece"])

    result = {
        "schema": "MATRIX_OVER25_FORWARD_VALIDATION_1444_1544_RESULT_V1",
        "market": "OVER_2_5",
        "protocol_path": str(PROTOCOL_PATH),
        "baseline_commit": baseline_commit,
        "baseline_settlement_count": baseline,
        "target_settlement_count": target,
        "sample_size": 100,
        "fixture_ids": fixture_ids,
        "fixture_ids_sha256": _sha(fixture_ids),
        "all_rows_standard_final_ft": True,
        "baseline_lane_prefix_unchanged": True,
        "lane_probability_binding_verified": True,
        "lane_outcome_binding_verified": True,
        "challenger": challenger,
        "poisson": poisson,
        "paired_comparison": paired,
        "stability": {
            "previous_forward_100_ece": previous_ece,
            "current_forward_100_ece": challenger["ece"],
            "ece_change_current_minus_previous": challenger["ece"] - previous_ece,
            "previous_forward_result_blob_sha": pre["prior_forward_100_result_blob_sha"],
        },
        "adjudication": {
            "proper_scoring_directional_vs_poisson": "PASS" if paired["proper_scoring_directional_pass"] else "FAIL",
            "formal_model_promotion": "NOT_AUTHORIZED_BY_THIS_MONITORING_BLOCK",
            "real_money_decision": "KEEP_BLOCKED",
            "verdict": "REPORT_FOR_GOVERNANCE_REVIEW_NO_AUTOMATIC_PARAMETER_CHANGE",
        },
        "governance": {
            "metrics_opened_for_fixed_block_only": True,
            "continuous_lane_metrics_remain_sealed": True,
            "parameter_tuning_allowed": False,
            "refit_allowed": False,
            "model_files_modified": False,
            "odds_used_to_generate_probability": False,
            "target_outcomes_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    serialized = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if RESULT_OUT.exists() and RESULT_OUT.read_text(encoding="utf-8") != serialized:
        raise RuntimeError("CLOSED_RESULT_IMMUTABILITY_VIOLATION")
    RESULT_OUT.write_text(serialized, encoding="utf-8")

    closed_state = dict(pending_state)
    closed_state.update({
        "status": "CLOSED_FIXED_100",
        "remaining_to_target": 0,
        "metrics_opened": True,
        "outcomes_read_for_metrics": 100,
        "result_path": str(RESULT_OUT),
        "result_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    })
    _write_state(closed_state)
    return closed_state


def main() -> None:
    state = monitor_or_close()
    print(json.dumps({
        "status": state["status"],
        "baseline": state["baseline_settlement_count"],
        "current": state["current_settlement_count"],
        "target": state["target_settlement_count"],
        "new": state["new_settlements_after_baseline"],
        "remaining": state["remaining_to_target"],
        "metrics_opened": state["metrics_opened"],
        "outcomes_read_for_metrics": state["outcomes_read_for_metrics"],
        "real_money": state["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
