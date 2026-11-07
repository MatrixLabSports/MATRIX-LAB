from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from app.research.football.experimental_evaluator import evaluate_transparent_poisson_baseline
from app.research.football.match_analysis_input import (
    FootballHistoryObservation,
    FootballMatchAnalysisInput,
)
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle


MODEL_NAME = "transparent_poisson_baseline_v1"
MODEL_ROLE = "RESEARCH_SHADOW_BASELINE"
MODEL_STATUS = "EXPERIMENTAL_NOT_PROMOTED"


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FREEZE_AT_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rehydrate_input(raw: Mapping[str, Any]) -> FootballMatchAnalysisInput:
    kwargs = {
        key: value
        for key, value in raw.items()
        if key not in {"readiness", "canonical_sha256"}
    }
    kwargs["home_history"] = tuple(
        FootballHistoryObservation(**row)
        for row in raw.get("home_history", [])
    )
    kwargs["away_history"] = tuple(
        FootballHistoryObservation(**row)
        for row in raw.get("away_history", [])
    )
    value = FootballMatchAnalysisInput(**kwargs)
    expected = str(raw.get("canonical_sha256") or "").strip()
    if not expected or value.canonical_sha256() != expected:
        raise ValueError(f"CANONICAL_INPUT_SHA_MISMATCH:{value.target_key}")
    return value


def freeze_experimental_shadow(
    *,
    canonical_bundle: Mapping[str, Any],
    canonical_manifest: Mapping[str, Any],
    freeze_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if canonical_bundle.get("provider") != "api_football":
        raise ValueError("PROVIDER_MISMATCH")
    if canonical_manifest.get("status") != "PASS":
        raise ValueError("CANONICAL_MANIFEST_NOT_PASS")
    if canonical_manifest.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")
    if canonical_manifest.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_MUST_NOT_ALREADY_EXIST")
    if canonical_manifest.get("baseline_poisson_status") != "EXPERIMENTAL_NOT_PROMOTED":
        raise ValueError("BASELINE_STATUS_MISMATCH")
    if canonical_manifest.get("bundle_sha256") != _canonical_hash(canonical_bundle):
        raise ValueError("CANONICAL_BUNDLE_SHA_MISMATCH")

    raw_inputs = canonical_bundle.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("CANONICAL_INPUTS_MUST_BE_LIST")

    freeze = _aware_utc(freeze_at)
    freeze_text = freeze.isoformat()
    frozen: list[dict[str, Any]] = []
    excluded_not_future: list[str] = []

    for raw in raw_inputs:
        if not isinstance(raw, Mapping):
            raise ValueError("CANONICAL_INPUT_ROW_INVALID")
        value = _rehydrate_input(raw)
        kickoff = _utc(value.kickoff_utc)
        if freeze >= kickoff:
            excluded_not_future.append(value.target_key)
            continue
        if _utc(value.as_of_utc) > freeze:
            raise ValueError(f"INPUT_AS_OF_AFTER_FREEZE:{value.target_key}")

        evaluation = evaluate_transparent_poisson_baseline(value)
        if evaluation.model_name != MODEL_NAME:
            raise ValueError("UNEXPECTED_MODEL_NAME")
        if evaluation.model_status != MODEL_STATUS:
            raise ValueError(f"BASELINE_NOT_EXECUTABLE:{value.target_key}")
        if evaluation.decision != "NO_BET":
            raise ValueError("EXPERIMENTAL_BASELINE_MUST_BE_NO_BET")
        if not isinstance(evaluation.probabilities, dict) or len(evaluation.probabilities) < 3:
            raise ValueError("MINIMUM_THREE_MARKETS_NOT_AVAILABLE")

        frozen.append({
            "target_key": value.target_key,
            "fixture_id": value.fixture_id,
            "kickoff_utc": value.kickoff_utc,
            "analysis_as_of_utc": value.as_of_utc,
            "freeze_at_utc": freeze_text,
            "input_sha256": evaluation.input_sha256,
            "model_name": evaluation.model_name,
            "model_role": MODEL_ROLE,
            "model_status": evaluation.model_status,
            "expected_home_goals": evaluation.expected_home_goals,
            "expected_away_goals": evaluation.expected_away_goals,
            "markets": dict(evaluation.probabilities),
            "market_count": len(evaluation.probabilities),
            "decision": evaluation.decision,
            "reasons": list(evaluation.reasons),
            "p_matrix": None,
            "governed_model_probability": None,
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
        })

    frozen.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"]))
    excluded_not_future = sorted(set(excluded_not_future))

    ledger = {
        "schema": "MATRIX_API_FOOTBALL_EXPERIMENTAL_SHADOW_FREEZE_V1",
        "provider": "api_football",
        "freeze_at_utc": freeze_text,
        "source_canonical_analysis_as_of_utc": canonical_manifest.get("analysis_as_of_utc"),
        "source_canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"),
        "model_name": MODEL_NAME,
        "model_role": MODEL_ROLE,
        "model_status": MODEL_STATUS,
        "governed_p_matrix_engine": None,
        "p_matrix_status": "NOT_GENERATED",
        "frozen_prediction_count": len(frozen),
        "excluded_not_future_count": len(excluded_not_future),
        "excluded_not_future_targets": excluded_not_future,
        "rows": frozen,
        "protections": {
            "minimum_markets_per_fixture": 3,
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "pinnacle_reference_joined": False,
            "money_decisions_enabled": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    adjudication = {
        "schema": "MATRIX_FOOTBALL_ENGINE_ADJUDICATION_V1",
        "adjudicated_at_utc": freeze_text,
        "provider": "api_football",
        "canonical_ready_input_count": canonical_manifest.get("ready_input_count"),
        "frozen_shadow_input_count": len(frozen),
        "governed_p_matrix_engine_available": False,
        "governed_p_matrix_engine": None,
        "selected_research_baseline": MODEL_NAME,
        "selected_role": MODEL_ROLE,
        "selected_status": MODEL_STATUS,
        "promotion_status": "BLOCKED",
        "promotion_blockers": [
            "NO_GOVERNED_FOOTBALL_P_MATRIX_ENGINE_PHYSICALLY_ADJUDICATED",
            "BASELINE_IS_EXPERIMENTAL_NOT_PROMOTED",
            "REQUIRED_TEST_AND_CALIBRATION_EVIDENCE_NOT_SATISFIED",
            "PAPER_TRADING_REQUIREMENT_NOT_SATISFIED",
            "ODDS_EV_VALIDATION_NOT_SATISFIED",
            "EXTERNAL_AUDIT_NOT_CLOSED",
        ],
        "shadow_freeze_created": True,
        "shadow_probability_role": "RESEARCH_ONLY_NOT_P_MATRIX",
        "minimum_three_markets_enforced": True,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return ledger, adjudication


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    source = Path("evidence/api_football/canonical_analysis")
    out = Path("evidence/api_football/experimental_shadow")
    freeze_at = datetime.now(timezone.utc).replace(microsecond=0)
    canonical_bundle, canonical_manifest = load_chunked_canonical_bundle(source)
    ledger, adjudication = freeze_experimental_shadow(
        canonical_bundle=canonical_bundle,
        canonical_manifest=canonical_manifest,
        freeze_at=freeze_at,
    )
    _write(out / "shadow_freeze.json", ledger)
    _write(out / "engine_adjudication.json", adjudication)
    print(json.dumps({
        "freeze_at_utc": ledger["freeze_at_utc"],
        "frozen_prediction_count": ledger["frozen_prediction_count"],
        "excluded_not_future_count": ledger["excluded_not_future_count"],
        "model_name": ledger["model_name"],
        "model_role": ledger["model_role"],
        "model_status": ledger["model_status"],
        "p_matrix_status": ledger["p_matrix_status"],
        "real_money": ledger["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
