from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from math import log
from pathlib import Path
from typing import Any

EPS = 1e-15
THRESHOLD = 200
ROOT = Path("evidence/api_football")
SOURCE_LEDGER = ROOT / "prospective_calibration" / "ledger.jsonl"
LANE_ROOT = ROOT / "calibration_v2" / "lanes"
DEFAULT_OUT = ROOT / "calibration_v2" / "checkpoint_200_1x2_over_2_5_20261006.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError(f"JSONL_ROW_NOT_OBJECT:{path}:{line_no}")
        rows.append(value)
    return rows


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1.0 - EPS)


def _binary_metrics(rows: list[dict[str, Any]], source_key: str, probability_key: str, outcome_key: str) -> dict[str, Any]:
    brier = 0.0
    log_loss = 0.0
    correct = 0
    positives = 0
    probs: list[float] = []
    ys: list[float] = []
    for row in rows:
        p = _clip(float(row[source_key][probability_key]))
        y = 1.0 if bool(row["outcomes"][outcome_key]) else 0.0
        probs.append(p)
        ys.append(y)
        positives += int(y)
        correct += int((p >= 0.5) == bool(y))
        brier += (p - y) ** 2
        log_loss += -(y * log(p) + (1.0 - y) * log(1.0 - p))
    n = len(rows)
    return {
        "sample_size": n,
        "brier_score": brier / n,
        "log_loss": log_loss / n,
        "accuracy_at_0_5": correct / n,
        "observed_positive_rate": positives / n,
        "mean_predicted_probability": sum(probs) / n,
        "calibration": _binary_calibration(probs, ys),
    }


def _binary_calibration(probs: list[float], ys: list[float], bins: int = 10) -> dict[str, Any]:
    n = len(probs)
    ece = 0.0
    mce = 0.0
    rows: list[dict[str, Any]] = []
    for i in range(bins):
        lo = i / bins
        hi = (i + 1) / bins
        idx = [j for j, p in enumerate(probs) if (lo <= p < hi) or (i == bins - 1 and p == 1.0)]
        if not idx:
            continue
        mean_p = sum(probs[j] for j in idx) / len(idx)
        mean_y = sum(ys[j] for j in idx) / len(idx)
        gap = abs(mean_p - mean_y)
        ece += (len(idx) / n) * gap
        mce = max(mce, gap)
        rows.append({
            "bin": i,
            "lower": lo,
            "upper": hi,
            "count": len(idx),
            "mean_probability": mean_p,
            "observed_rate": mean_y,
            "absolute_gap": gap,
        })
    return {"bin_count": bins, "ece": ece, "max_calibration_error": mce, "nonempty_bins": rows}


def _multiclass_metrics(rows: list[dict[str, Any]], source_key: str) -> dict[str, Any]:
    classes = ("H", "D", "A")
    brier = 0.0
    log_loss = 0.0
    correct = 0
    observed = {k: 0 for k in classes}
    mean_prob = {k: 0.0 for k in classes}
    class_probs: dict[str, list[float]] = {k: [] for k in classes}
    class_ys: dict[str, list[float]] = {k: [] for k in classes}
    for row in rows:
        probs = row[source_key]["1x2"]
        actual = row["outcomes"]["1x2"]
        observed[actual] += 1
        for klass in classes:
            p = _clip(float(probs[klass]))
            y = 1.0 if actual == klass else 0.0
            mean_prob[klass] += p
            class_probs[klass].append(p)
            class_ys[klass].append(y)
            brier += (p - y) ** 2
        log_loss += -log(max(float(probs[actual]), EPS))
        predicted = max(classes, key=lambda k: float(probs[k]))
        correct += int(predicted == actual)
    n = len(rows)
    per_class_cal = {k: _binary_calibration(class_probs[k], class_ys[k]) for k in classes}
    return {
        "sample_size": n,
        "brier_score": brier / n,
        "log_loss": log_loss / n,
        "accuracy": correct / n,
        "observed_class_rate": {k: observed[k] / n for k in classes},
        "mean_predicted_probability": {k: mean_prob[k] / n for k in classes},
        "calibration": {
            "method": "ONE_VS_REST_EQUAL_WIDTH_10_BINS_DIAGNOSTIC_ONLY",
            "per_class": per_class_cal,
            "macro_ece": sum(per_class_cal[k]["ece"] for k in classes) / len(classes),
            "max_class_calibration_error": max(per_class_cal[k]["max_calibration_error"] for k in classes),
        },
    }


def _compare(challenger: dict[str, Any], poisson: dict[str, Any]) -> dict[str, Any]:
    db = float(challenger["brier_score"]) - float(poisson["brier_score"])
    dl = float(challenger["log_loss"]) - float(poisson["log_loss"])
    gate = db < 0.0 and dl < 0.0
    return {
        "challenger": challenger,
        "poisson": poisson,
        "delta_brier_challenger_minus_poisson": db,
        "delta_log_loss_challenger_minus_poisson": dl,
        "beats_poisson_brier": db < 0.0,
        "beats_poisson_log_loss": dl < 0.0,
        "gate_rule": "delta_brier<0 AND delta_log_loss<0",
        "gate_passed": gate,
        "status": "PROSPECTIVE_SUPPORT_CONFIRMED_AT_200" if gate else "PROSPECTIVE_CHECKPOINT_200_REJECTED_NOT_SUPERIOR_TO_POISSON",
    }


def _verify_lane_state(slug: str) -> dict[str, Any]:
    state = _load_json(LANE_ROOT / slug / "state.json")
    if int(state.get("observation_count", 0)) < THRESHOLD:
        raise RuntimeError(f"INSUFFICIENT_SETTLED_OBSERVATIONS:{slug}")
    if state.get("thresholds", {}).get(str(THRESHOLD)) != "READY_FOR_SEPARATE_EVALUATION_NOT_OPENED":
        raise RuntimeError(f"THRESHOLD_200_NOT_READY:{slug}")
    if state.get("parameter_tuning_allowed") is not False:
        raise RuntimeError(f"TUNING_ALLOWED_UNEXPECTED:{slug}")
    if state.get("metrics_opened") is not False:
        raise RuntimeError(f"LANE_METRICS_ALREADY_OPENED:{slug}")
    if state.get("real_money") != "BLOCKED":
        raise RuntimeError(f"REAL_MONEY_NOT_BLOCKED:{slug}")
    return state


def _verify_lane_prefix(slug: str, market: str, source_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    state = _verify_lane_state(slug)
    lane_rows = _load_jsonl(LANE_ROOT / slug / "ledger.jsonl")
    prefix = lane_rows[:THRESHOLD]
    if len(prefix) != THRESHOLD:
        raise RuntimeError(f"PREFIX_NOT_200:{slug}:{len(prefix)}")
    fixture_ids = [str(r.get("fixture_id") or "") for r in prefix]
    if len(set(fixture_ids)) != THRESHOLD:
        raise RuntimeError(f"DUPLICATE_FIXTURE_IN_PREFIX:{slug}")

    source_rows: list[dict[str, Any]] = []
    previous_freeze: tuple[str, str] | None = None
    for row in prefix:
        fid = str(row.get("fixture_id") or "")
        source = source_by_id.get(fid)
        if source is None:
            raise RuntimeError(f"SOURCE_ROW_MISSING:{slug}:{fid}")
        if row.get("parameters_mutated_after_freeze") is not False or source.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"PARAMETER_MUTATION_DETECTED:{slug}:{fid}")
        if row.get("used_for_parameter_tuning") is not False or source.get("used_for_parameter_tuning") is not False:
            raise RuntimeError(f"TUNING_DETECTED:{slug}:{fid}")
        if row.get("real_money") != "BLOCKED" or source.get("real_money") != "BLOCKED":
            raise RuntimeError(f"REAL_MONEY_NOT_BLOCKED_ROW:{slug}:{fid}")
        if source.get("source_terminal_status") != "FT":
            raise RuntimeError(f"NON_FINAL_SOURCE_ROW:{slug}:{fid}")
        if source.get("p_matrix_status") != "NOT_GENERATED":
            raise RuntimeError(f"P_MATRIX_UNEXPECTED:{slug}:{fid}")
        if row.get("freeze_at_utc") != source.get("freeze_at_utc") or row.get("kickoff_utc") != source.get("kickoff_utc"):
            raise RuntimeError(f"TEMPORAL_BINDING_MISMATCH:{slug}:{fid}")
        key = (str(row["freeze_at_utc"]), fid)
        if previous_freeze is not None and key < previous_freeze:
            raise RuntimeError(f"LANE_ORDER_NOT_MONOTONIC:{slug}:{fid}")
        previous_freeze = key

        if market == "1x2":
            if row.get("frozen_probability") != source.get("frozen_challenger_probabilities", {}).get("1x2"):
                raise RuntimeError(f"CHALLENGER_PROBABILITY_MISMATCH:{slug}:{fid}")
            if row.get("outcome") != source.get("outcomes", {}).get("1x2"):
                raise RuntimeError(f"OUTCOME_MISMATCH:{slug}:{fid}")
            poisson = source.get("frozen_poisson_reference", {}).get("1x2")
            if not isinstance(poisson, dict) or set(poisson) != {"H", "D", "A"}:
                raise RuntimeError(f"POISSON_REFERENCE_MISSING:{slug}:{fid}")
        elif market == "over_2_5":
            if float(row.get("frozen_probability")) != float(source.get("frozen_challenger_probabilities", {}).get("over_2_5")):
                raise RuntimeError(f"CHALLENGER_PROBABILITY_MISMATCH:{slug}:{fid}")
            if bool(row.get("outcome")) != bool(source.get("outcomes", {}).get("over_2_5")):
                raise RuntimeError(f"OUTCOME_MISMATCH:{slug}:{fid}")
            poisson = source.get("frozen_poisson_reference", {}).get("over_2_5")
            if not isinstance(poisson, (int, float)):
                raise RuntimeError(f"POISSON_REFERENCE_MISSING:{slug}:{fid}")
        else:
            raise RuntimeError(f"UNSUPPORTED_MARKET:{market}")
        source_rows.append(source)

    audit = {
        "lane": slug,
        "market": market.upper(),
        "available_settlements": int(state["observation_count"]),
        "observations_used": THRESHOLD,
        "fixture_id_count": len(fixture_ids),
        "unique_fixture_id_count": len(set(fixture_ids)),
        "first_fixture_id": fixture_ids[0],
        "last_fixture_id": fixture_ids[-1],
        "first_freeze_at_utc": prefix[0]["freeze_at_utc"],
        "last_prefix_freeze_at_utc": prefix[-1]["freeze_at_utc"],
        "lane_prefix_sha256": _sha([r["record_sha256"] for r in prefix]),
        "source_prefix_sha256": _sha([r["record_sha256"] for r in source_rows]),
        "all_rows_final_ft": True,
        "probability_binding_verified": True,
        "outcome_binding_verified": True,
        "parameter_tuning_used": False,
        "parameters_mutated_after_freeze": False,
    }
    return prefix, source_rows, audit


def build_checkpoint() -> dict[str, Any]:
    source_rows_all = _load_jsonl(SOURCE_LEDGER)
    source_by_id = {str(r.get("fixture_id") or ""): r for r in source_rows_all}
    if len(source_by_id) != len(source_rows_all):
        raise RuntimeError("SOURCE_LEDGER_DUPLICATE_FIXTURE")

    one_prefix, one_source, one_audit = _verify_lane_prefix("1x2", "1x2", source_by_id)
    over_prefix, over_source, over_audit = _verify_lane_prefix("over_2_5", "over_2_5", source_by_id)

    one = _compare(
        _multiclass_metrics(one_source, "frozen_challenger_probabilities"),
        _multiclass_metrics(one_source, "frozen_poisson_reference"),
    )
    over = _compare(
        _binary_metrics(over_source, "frozen_challenger_probabilities", "over_2_5", "over_2_5"),
        _binary_metrics(over_source, "frozen_poisson_reference", "over_2_5", "over_2_5"),
    )

    overlap = len(set(r["fixture_id"] for r in one_prefix) & set(r["fixture_id"] for r in over_prefix))
    both = bool(one["gate_passed"] and over["gate_passed"])
    return {
        "schema": "MATRIX_FOOTBALL_MARKET_CALIBRATION_V2_CLOSED_CHECKPOINT_200_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cohort_id": "FOOTBALL_ALL_MARKETS_V2_20261004",
        "checkpoint": 200,
        "checkpoint_role": "CLOSED_FIXED_PREFIX_200_INFORMATIVE_STABILITY_CHECKPOINT_NOT_PROMOTION_GATE",
        "sample_policy": "FIRST_200_SETTLED_OBSERVATIONS_IN_EACH_V2_LANE_ORDERED_BY_FREEZE_AT_UTC_THEN_FIXTURE_ID",
        "source_ledger_observation_count": len(source_rows_all),
        "lane_audit": {
            "1x2": one_audit,
            "over_2_5": over_audit,
            "prefix_fixture_overlap_count": overlap,
        },
        "market_adjudication": {
            "1x2": one,
            "over_2_5": over,
        },
        "overall": {
            "both_markets_pass_proper_scoring_gate": both,
            "verdict": "PASS_BOTH_MARKETS_PROSPECTIVE_SUPPORT_CONFIRMED_AT_200" if both else "PARTIAL_OR_FAIL_KEEP_MODELS_FROZEN_NO_PROMOTION",
        },
        "governance": {
            "checkpoint_metrics_opened": True,
            "continuous_lane_metrics_remain_sealed": True,
            "parameter_tuning_allowed": False,
            "parameters_mutated": False,
            "model_files_modified": False,
            "promotion_gate": False,
            "model_promotion_performed": False,
            "original_357_holdout_reuse_allowed": False,
            "odds_used_to_generate_probability": False,
            "p_matrix_status": "NOT_GENERATED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = build_checkpoint()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "checkpoint": result["checkpoint"],
        "one_x_two_gate_passed": result["market_adjudication"]["1x2"]["gate_passed"],
        "over_2_5_gate_passed": result["market_adjudication"]["over_2_5"]["gate_passed"],
        "overall_verdict": result["overall"]["verdict"],
        "parameters_mutated": result["governance"]["parameters_mutated"],
        "real_money": result["governance"]["real_money"],
        "out": str(args.out),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
