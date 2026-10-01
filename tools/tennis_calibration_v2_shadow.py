from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "MATRIX_TENNIS_CALIBRATION_V2_SHADOW_FREEZE_V1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _sha(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)


def _finite(value: object, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OBSERVED_FEATURE_MISSING:" + field) from exc
    if not math.isfinite(result):
        raise ValueError("OBSERVED_FEATURE_MISSING:" + field)
    return result


def _score(model: Mapping[str, Any], observation: Mapping[str, Any]) -> float:
    features = dict(observation.get("features") or {})
    elo = dict(observation.get("elo") or {})
    values = {
        **features,
        "elo_overall_diff": elo.get("elo_overall_diff"),
        "elo_surface_diff": elo.get("elo_surface_diff"),
    }
    names = list(model["features"])
    means = list(model["scaler_mean"])
    scales = list(model["scaler_scale"])
    coefficients = list(model["coef"])
    if not (len(names) == len(means) == len(scales) == len(coefficients)):
        raise ValueError("MODEL_DIMENSION_MISMATCH")

    eta = float(model["intercept"])
    for name, mean, scale, coefficient in zip(names, means, scales, coefficients):
        value = _finite(values.get(name), name)
        scale = float(scale)
        standardized = 0.0 if scale == 0.0 else (value - float(mean)) / scale
        eta += float(coefficient) * standardized
    if eta >= 0:
        z = math.exp(-eta)
        return 1.0 / (1.0 + z)
    z = math.exp(eta)
    return z / (1.0 + z)


def build_shadow(bundle: Mapping[str, Any], batch: Mapping[str, Any]) -> dict[str, Any]:
    cutoff = _parse_utc(bundle["inference_contract"]["candidate_future_cutoff_utc"])
    if batch.get("holdout_id") != "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1":
        raise ValueError("ACTIVE_HOLDOUT_ID_MISMATCH")
    if batch.get("metrics") != "SEALED_UNTIL_600":
        raise ValueError("ACTIVE_HOLDOUT_METRICS_NOT_SEALED")
    if int(batch.get("outcomes_read", -1)) != 0:
        raise ValueError("ACTIVE_HOLDOUT_OUTCOME_READ_DETECTED")

    rows = []
    for observation in batch.get("observations", []) or []:
        if observation.get("outcome") is not None:
            raise ValueError("OUTCOME_PRESENT_AT_SHADOW_FREEZE")
        freeze_at = _parse_utc(observation["freeze_at_utc"])
        start_at = _parse_utc(observation["event_start_utc"])
        if freeze_at <= cutoff:
            raise ValueError("CANDIDATE_PRE_FREEZE_EVENT_FORBIDDEN")
        if freeze_at >= start_at:
            raise ValueError("POST_START_SHADOW_FREEZE_FORBIDDEN")
        if observation.get("surface") != "Hard":
            raise ValueError("SURFACE_OUT_OF_DOMAIN")

        probability = _score(bundle["model"], observation)
        row = {
            "candidate_id": bundle["candidate_id"],
            "event_id": observation["event_id"],
            "canonical_source_event_id": observation.get("canonical_source_event_id"),
            "observation_index": observation["observation_index"],
            "source_observation_sha256": observation["observation_sha256"],
            "freeze_at_utc": observation["freeze_at_utc"],
            "event_start_utc": observation["event_start_utc"],
            "alphabetical_player_a": observation["alphabetical_player_a"],
            "alphabetical_player_b": observation["alphabetical_player_b"],
            "p_player_a": probability,
            "p_player_b": 1.0 - probability,
            "outcome": None,
            "metrics_opened": False,
            "used_for_tuning": False,
            "p_matrix_status": "NOT_GENERATED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
        row["shadow_row_sha256"] = _sha(row)
        rows.append(row)

    payload = {
        "schema": SCHEMA,
        "candidate_id": bundle["candidate_id"],
        "candidate_future_cutoff_utc": bundle["inference_contract"]["candidate_future_cutoff_utc"],
        "source_holdout_id": batch["holdout_id"],
        "source_batch_sha256": batch.get("batch_sha256"),
        "source_batch_created_at_utc": batch.get("created_at_utc"),
        "rows": rows,
        "row_count": len(rows),
        "outcomes_read": 0,
        "metrics_opened": False,
        "evaluation_policy": "SEALED_WHILE_A22_ACTIVE_HOLDOUT_IS_BELOW_600",
        "p_matrix_status": "NOT_GENERATED",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    payload["payload_sha256"] = _sha(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = build_shadow(_load(Path(args.bundle)), _load(Path(args.batch)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "row_count": result["row_count"],
        "metrics_opened": result["metrics_opened"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
