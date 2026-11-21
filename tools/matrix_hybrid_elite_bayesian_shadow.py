"""Hierarchical beta-binomial research challenger for MATRIX Hybrid Elite.

Offline only. Bayesian partial pooling across sport/market/surface groups.
Historical results MUST be independently certified and settled BEFORE each
forecast freeze. This producer never supplies governed MATRIX probabilities.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from tools.matrix_hybrid_elite_lab import LANES, stamp

HISTORY_SCHEMA = "MATRIX_HYBRID_ELITE_CERTIFIED_HISTORY_V1"
FORECAST_SCHEMA = "MATRIX_HYBRID_ELITE_BAYESIAN_RESEARCH_REQUEST_V1"
OUTPUT_SCHEMA = "MATRIX_HYBRID_ELITE_BAYESIAN_SHADOW_V1"
MIN_POOLED_OBS = 30
PRIOR_WEIGHT = 20.0


def build(history: dict, requests: dict) -> dict:
    if (history.get("schema") != HISTORY_SCHEMA
        or history.get("real_money") != "BLOCKED"
        or history.get("source") != "CERTIFIED_SETTLED_PHYSICAL_LEDGER"
        or history.get("synthetic") is not False
        or requests.get("schema") != FORECAST_SCHEMA
        or requests.get("real_money") != "BLOCKED"
        or requests.get("automatic_wagering") is not False
        or requests.get("synthetic") is not False):
        raise ValueError("BAYESIAN_UNTRUSTED_SOURCE")
    rows = history.get("rows")
    targets = requests.get("targets")
    if not isinstance(rows, list) or not isinstance(targets, list):
        raise ValueError("BAYESIAN_INVALID_ROWS")
    unique = set()
    certified = []
    for rec in rows:
        if (not isinstance(rec, dict) or rec.get("lane") not in LANES
            or not isinstance(rec.get("group"), str) or not rec["group"]
            or not isinstance(rec.get("physical_event_id"), str)
            or not rec["physical_event_id"].strip()
            or rec.get("independent_identity_certified") is not True
            or rec.get("independent_outcome_certified") is not True
            or rec.get("pre_event_features_certified") is not True
            or rec.get("source_timestamp_immutable") is not True
            or type(rec.get("outcome")) is not int
            or rec["outcome"] not in (0, 1)):
            raise ValueError("BAYESIAN_UNCERTIFIED_HISTORY_ROW")
        key = (rec["lane"], rec["physical_event_id"])
        if key in unique:
            raise ValueError("BAYESIAN_DUPLICATE_HISTORY_ID")
        unique.add(key)
        event_start = stamp(rec["event_start_at_utc"])
        finished = stamp(rec["independently_certified_final_at_utc"])
        if finished <= event_start:
            raise ValueError("BAYESIAN_HISTORICAL_FINAL_ORDER")
        certified.append({
            "lane": rec["lane"], "group": rec["group"],
            "physical_event_id": rec["physical_event_id"],
            "outcome": rec["outcome"], "final_at": finished,
        })
    output, target_ids = [], set()
    for target in targets:
        if (not isinstance(target, dict) or target.get("lane") not in LANES
            or not isinstance(target.get("group"), str) or not target["group"]
            or not isinstance(target.get("physical_event_id"), str)
            or not target["physical_event_id"].strip()
            or target.get("prematch_or_live_identity_certified") is not True
            or target.get("target_features_pit_certified") is not True):
            raise ValueError("BAYESIAN_UNCERTIFIED_TARGET")
        key = (target["lane"], target["physical_event_id"])
        if key in target_ids or key in unique:
            raise ValueError("BAYESIAN_DUPLICATE_OR_SETTLED_TARGET_ID")
        target_ids.add(key)
        frozen = stamp(target["prediction_frozen_at_utc"])
        kickoff = stamp(target["event_start_at_utc"])
        if target["lane"] == "TENNIS_LIVE":
            # Strict allowlist: prohibit even nested/renamed result fields in
            # research forecast requests. Match-end belongs to settlement.
            allowed_live_target_keys = {
                "lane", "group", "physical_event_id",
                "prematch_or_live_identity_certified",
                "target_features_pit_certified",
                "prediction_frozen_at_utc", "event_start_at_utc",
                "observed_live_state_at_utc",
                "original_receipt_path", "original_receipt_sha256"
            }
            if set(target) - allowed_live_target_keys:
                raise ValueError("BAYESIAN_LIVE_FUTURE_FACT_IN_FORECAST_INPUT")
            state_at = stamp(target["observed_live_state_at_utc"])
            if not kickoff < state_at <= frozen:
                raise ValueError("BAYESIAN_LIVE_PIT_LEAKAGE")
        elif not frozen < kickoff:
            raise ValueError("BAYESIAN_PREMATCH_PIT_LEAKAGE")
        # No future settled outcome can enter an earlier forecast, even if a
        # historical file contains many later rows. An unverified end timestamp
        # must be rejected by the certified history gate upstream.
        past = [r for r in certified if r["lane"] == target["lane"]
                and r["final_at"] < frozen]
        pooled_n = len(past)
        same_group = [r for r in past if r["group"] == target["group"]]
        status = "RESEARCH_ONLY_INSUFFICIENT_CERTIFIED_HISTORY"
        p = None
        if pooled_n >= MIN_POOLED_OBS:
            pooled_p = (2 + sum(r["outcome"] for r in past)) / (4 + pooled_n)
            p = (PRIOR_WEIGHT * pooled_p +
                 sum(r["outcome"] for r in same_group)) / (
                     PRIOR_WEIGHT + len(same_group))
            status = "RESEARCH_ONLY_PROSPECTIVE_BAYESIAN_PROBABILITY"
        output.append({
            "lane": target["lane"], "group": target["group"],
            "physical_event_id": target["physical_event_id"],
            "frozen_at_utc": frozen.isoformat(),
            "certified_histories_available_before_freeze": pooled_n,
            "certified_same_group_histories_before_freeze": len(same_group),
            "p_bayesian_research_only": round(p, 10) if p is not None else None,
            "status": status,
            "governed_p_matrix_authorized": False,
            "telegram_signal_authorized": False,
        })
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "BAYESIAN_SHADOW_RESEARCH_ONLY_NOT_MODEL_PROMOTION",
        "method": "HIERARCHICAL_BETA_BINOMIAL_PARTIAL_POOLING",
        "min_pooled_certified_history": MIN_POOLED_OBS,
        "prior_weight": PRIOR_WEIGHT,
        "training_never_reads_after_prediction_freeze": True,
        "outcome_labels_for_targets_used": False,
        "original_matrix_parameters_modified": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "targets": output,
    }



def verify_physical_receipts(history: dict, requests: dict, *,
                             history_root: Path, request_root: Path) -> dict:
    """Prove historical labels and target clocks against original SHA-bound bytes.

    This is mandatory for CLI use. The pure build() function remains a
    synthetic-fixture unit-test helper; it does not authenticate external data.
    """
    counter = 0
    for collection, items, root, kind in (
        (history, history.get("rows"), history_root, "HISTORY"),
        (requests, requests.get("targets"), request_root, "REQUEST"),
    ):
        if not isinstance(items, list):
            raise ValueError("BAYESIAN_RECEIPT_SOURCE_ROWS_MISSING")
        for row in items:
            if not isinstance(row, dict):
                raise ValueError("BAYESIAN_RECEIPT_SOURCE_ROW_INVALID")
            p = row.get("original_receipt_path")
            expected = row.get("original_receipt_sha256")
            if (not isinstance(p, str) or not p
                or not isinstance(expected, str) or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)):
                raise ValueError("BAYESIAN_ORIGINAL_RECEIPT_REQUIRED")
            rel = Path(p)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("BAYESIAN_RECEIPT_PATH_UNSAFE")
            absolute = (root / rel).resolve()
            if not absolute.is_relative_to(root.resolve()):
                raise ValueError("BAYESIAN_RECEIPT_PATH_UNSAFE")
            original = absolute.read_bytes()
            if (len(original) > 1_000_000
                or hashlib.sha256(original).hexdigest() != expected):
                raise ValueError("BAYESIAN_ORIGINAL_RECEIPT_HASH_CONFLICT")
            evidence = json.loads(original)
            if (not isinstance(evidence, dict)
                or evidence.get("schema") !=
                    "MATRIX_HYBRID_ELITE_BAYESIAN_" + kind + "_RECEIPT_V1"
                or evidence.get("real_money") != "BLOCKED"
                or evidence.get("lane") != row.get("lane")
                or evidence.get("physical_event_id") != row.get("physical_event_id")
                or evidence.get("group") != row.get("group")):
                raise ValueError("BAYESIAN_ORIGINAL_RECEIPT_IDENTITY_CONFLICT")
            if kind == "HISTORY":
                if (evidence.get("independent_identity_certified") is not True
                    or evidence.get("independent_outcome_certified") is not True
                    or evidence.get("pre_event_features_certified") is not True
                    or evidence.get("source_timestamp_immutable") is not True
                    or type(evidence.get("outcome")) is not int
                    or evidence.get("outcome") != row.get("outcome")
                    or stamp(evidence["event_start_at_utc"]) !=
                       stamp(row["event_start_at_utc"])
                    or stamp(evidence["independently_certified_final_at_utc"]) !=
                       stamp(row["independently_certified_final_at_utc"])):
                    raise ValueError("BAYESIAN_ORIGINAL_HISTORY_VALUE_CONFLICT")
            else:
                if (evidence.get("prematch_or_live_identity_certified") is not True
                    or evidence.get("target_features_pit_certified") is not True
                    or stamp(evidence["prediction_frozen_at_utc"]) !=
                       stamp(row["prediction_frozen_at_utc"])
                    or stamp(evidence["event_start_at_utc"]) !=
                       stamp(row["event_start_at_utc"])):
                    raise ValueError("BAYESIAN_ORIGINAL_TARGET_VALUE_CONFLICT")
                if row.get("lane") == "TENNIS_LIVE":
                    allowed_live_receipt_keys = {
                        "schema", "real_money", "lane", "group",
                        "physical_event_id", "prematch_or_live_identity_certified",
                        "target_features_pit_certified",
                        "prediction_frozen_at_utc", "event_start_at_utc",
                        "observed_live_state_at_utc"
                    }
                    if (set(evidence) - allowed_live_receipt_keys
                        or stamp(evidence["observed_live_state_at_utc"]) !=
                           stamp(row["observed_live_state_at_utc"])):
                        raise ValueError("BAYESIAN_ORIGINAL_TARGET_VALUE_CONFLICT")
            counter += 1
    return {"physical_sha_bound_receipts_verified": counter,
            "training_row_count": len(history["rows"]),
            "target_count": len(requests["targets"]),
            "real_money": "BLOCKED", "automatic_model_promotion": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    a, b = args.history.read_bytes(), args.requests.read_bytes()
    if len(a) > 10_000_000 or len(b) > 10_000_000:
        raise ValueError("BAYESIAN_SOURCE_TOO_LARGE")
    history_doc, request_doc = json.loads(a), json.loads(b)
    receipt_verification = verify_physical_receipts(
        history_doc, request_doc,
        history_root=args.history.parent, request_root=args.requests.parent)
    report = build(history_doc, request_doc)
    report["source_receipt_verification"] = receipt_verification
    report["source_sha256"] = {
        "certified_history": hashlib.sha256(a).hexdigest(),
        "requests": hashlib.sha256(b).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"research_targets": len(report["targets"]),
                      "model_promotions": 0, "real_money": "BLOCKED"}, sort_keys=True))


if __name__ == "__main__":
    main()
