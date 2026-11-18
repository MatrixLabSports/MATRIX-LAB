"""MATRIX HYBRID ELITE — isolated prospective probability challenger laboratory.

No model training, provider calls, bookmaker calls, calibration mutation, or
betting. The input must contain independently frozen prematch predictions and
later certified outcomes. Synthetic data may be used only in unit tests.
A challenger can NEVER be automatically promoted by this laboratory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "MATRIX_HYBRID_ELITE_PROSPECTIVE_INPUT_V1"
RESULT_SCHEMA = "MATRIX_HYBRID_ELITE_COMPARISON_V1"
LANES = {"FOOTBALL_OVER25", "TENNIS_CHALLENGER_HARD",
         "TENNIS_CHALLENGER_CLAY", "TENNIS_LIVE"}
MIN_HOLDOUT = 200
MIN_PER_LANE = 50
MARGIN_BRIER = 0.005
MARGIN_LOGLOSS = 0.005


def stamp(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("LAB_TIMESTAMP_NEEDS_TIMEZONE")
    return dt.astimezone(timezone.utc)


def probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("LAB_PROBABILITY_NOT_NUMERIC")
    x = float(value)
    if not math.isfinite(x) or not 0.0 < x < 1.0:
        raise ValueError("LAB_PROBABILITY_OUT_OF_RANGE")
    return x


def validate(document: dict) -> list[dict]:
    if (document.get("schema") != SCHEMA
        or document.get("real_money") != "BLOCKED"
        or document.get("automatic_wagering") is not False
        or document.get("source") != "CERTIFIED_PROSPECTIVE_LEDGER"
        or document.get("synthetic") is not False
        or document.get("original_model_parameters_modified") is not False):
        raise ValueError("LAB_UNTRUSTED_PROSPECTIVE_INPUT")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("LAB_ROWS_MISSING")
    seen: set[tuple[str, str]] = set()
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("LAB_ROW_NOT_OBJECT")
        lane = row.get("lane")
        fixture_id = row.get("physical_event_id")
        if lane not in LANES or not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("LAB_UNTRUSTED_EVENT_ID_OR_LANE")
        key = (lane, fixture_id)
        if key in seen:
            raise ValueError("LAB_DUPLICATE_PHYSICAL_EVENT")
        seen.add(key)
        if (row.get("prospective_identity_certified") is not True
            or row.get("original_feature_pit_certified") is not True
            or row.get("independent_outcome_certified") is not True
            or row.get("source_timestamp_immutable") is not True):
            raise ValueError("LAB_UNCERTIFIED_PROSPECTIVE_ROW")
        captured = stamp(row["prediction_frozen_at_utc"])
        kickoff = stamp(row["event_start_at_utc"])
        settled = stamp(row["outcome_certified_at_utc"])
        if not captured < kickoff < settled:
            raise ValueError("LAB_PIT_OR_OUTCOME_TIME_LEAKAGE")
        if lane == "TENNIS_LIVE":
            # Live requires an independently certified prediction-state instant
            # strictly before an independent event completion timestamp.
            completed = stamp(row["independently_certified_event_end_at_utc"])
            if not captured < completed <= settled:
                raise ValueError("LAB_LIVE_END_CHRONOLOGY_NOT_CERTIFIED")
        label = row.get("outcome")
        if type(label) is not int or label not in (0, 1):
            raise ValueError("LAB_BINARY_OUTCOME_REQUIRED")
        base = probability(row.get("p_matrix_frozen"))
        contenders = row.get("contenders")
        if not isinstance(contenders, dict) or not contenders:
            raise ValueError("LAB_NO_CHALLENGER_PREDICTION")
        for name, record in contenders.items():
            if not isinstance(name, str) or not name or name == "MATRIX":
                raise ValueError("LAB_CHALLENGER_NAME_INVALID")
            if not isinstance(record, dict):
                raise ValueError("LAB_CHALLENGER_RECORD_INVALID")
            probability(record.get("p_frozen"))
            trained = stamp(record["training_closed_at_utc"])
            if trained > captured:
                raise ValueError("LAB_CHALLENGER_TRAINED_AFTER_FORECAST")
        clean.append({"lane": lane, "physical_event_id": fixture_id,
                      "captured": captured, "start": kickoff,
                      "outcome": label, "p_matrix": base,
                      "contenders": {name: probability(v["p_frozen"])
                                     for name, v in contenders.items()}})
    return clean


def metrics(rows: list[tuple[float, int]]) -> dict:
    n = len(rows)
    if not n:
        raise ValueError("LAB_EMPTY_METRICS")
    brier = sum((p - y) ** 2 for p, y in rows) / n
    logloss = -sum(y * math.log(p) + (1 - y) * math.log1p(-p)
                   for p, y in rows) / n
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for p, y in rows:
        buckets[min(9, int(p * 10))].append((p, y))
    ece = sum(
        len(bucket) / n * abs(
            sum(y for _, y in bucket) / len(bucket)
            - sum(p for p, _ in bucket) / len(bucket))
        for bucket in buckets if bucket)
    return {"n": n, "brier": round(brier, 8),
            "logloss": round(logloss, 8), "ece_10": round(ece, 8)}


def evaluate(document: dict) -> dict:
    rows = validate(document)
    by_lane = defaultdict(list)
    for row in rows:
        by_lane[row["lane"]].append(row)
    reports = []
    for lane in sorted(LANES):
        group = sorted(by_lane[lane], key=lambda row: (row["start"], row["physical_event_id"]))
        baseline = metrics([(r["p_matrix"], r["outcome"]) for r in group]) if group else None
        names = sorted(set().union(*(set(r["contenders"]) for r in group))) if group else []
        challengers = []
        for name in names:
            common = [r for r in group if name in r["contenders"]]
            base_common = metrics([(r["p_matrix"], r["outcome"]) for r in common])
            comparison = metrics([(r["contenders"][name], r["outcome"]) for r in common])
            enough = len(common) >= MIN_HOLDOUT and len(common) >= MIN_PER_LANE
            # Improvement must be achieved on IDENTICAL independently frozen rows.
            lower_brier = base_common["brier"] - comparison["brier"]
            lower_logloss = base_common["logloss"] - comparison["logloss"]
            lower_ece = base_common["ece_10"] - comparison["ece_10"]
            candidate_pass = (enough and lower_brier >= MARGIN_BRIER
                              and lower_logloss >= MARGIN_LOGLOSS
                              and lower_ece >= 0)
            challengers.append({
                "name": name, "common_events": len(common),
                "matrix_same_events": base_common, "challenger": comparison,
                "delta_brier_matrix_minus_challenger": round(lower_brier, 8),
                "delta_logloss_matrix_minus_challenger": round(lower_logloss, 8),
                "delta_ece_matrix_minus_challenger": round(lower_ece, 8),
                "sufficient_historical_holdout_to_consider": enough,
                "metrics_pass_screen_not_authorization": candidate_pass,
                "independent_reproducible_prospective_replication_verified": False,
                "automatically_promoted": False,
            })
        reports.append({"lane": lane, "certified_events": len(group),
                        "matrix_original": baseline, "challengers": challengers,
                        "automatic_promotion": False})
    return {"schema": RESULT_SCHEMA,
            "status": "RESEARCH_ONLY_NO_MODEL_WINNER_OR_PROMOTION",
            "certified_total_events": len(rows),
            "synthetic_results_used": False,
            "minimum_same_row_holdout_per_lane": MIN_HOLDOUT,
            "require_future_independent_replication": True,
            "any_model_promoted": False,
            "original_parameters_modified": False,
            "telegram_signal_authorized": False,
            "automatic_wagering": False, "real_money": "BLOCKED",
            "lanes": reports}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    if len(raw) > 10_000_000:
        raise ValueError("LAB_INPUT_TOO_LARGE")
    document = json.loads(raw)
    result = evaluate(document)
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"certified_events": result["certified_total_events"],
                      "promoted": 0, "status": result["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
