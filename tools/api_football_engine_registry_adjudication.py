from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.engine_registry import EngineRegistry
from app.research.football.experimental_evaluator import (
    evaluate_transparent_poisson_baseline,
)
from tools.api_football_canonicalize_analysis_inputs import (
    load_chunked_canonical_bundle,
)
from tools.api_football_freeze_experimental_shadow import _rehydrate_input


LEGACY_ENGINE_IDS = ("R315", "R442", "R316", "R318", "R320", "R322")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _legacy_identifier_occurrences(root: Path, identifier: str) -> list[str]:
    hits: list[str] = []
    allowed_suffixes = {".py", ".json", ".md", ".yml", ".yaml", ".txt"}
    excluded_roots = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
    }
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
            continue
        if any(part in excluded_roots for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if identifier in text:
            hits.append(path.as_posix())
    return sorted(set(hits))


def adjudicate(root: Path) -> dict[str, Any]:
    canonical_root = root / "evidence/api_football/canonical_analysis"
    canonical_bundle, canonical_manifest = load_chunked_canonical_bundle(canonical_root)
    prior = _load(root / "evidence/api_football/experimental_shadow/engine_adjudication.json")

    if canonical_manifest.get("status") != "PASS":
        raise ValueError("CANONICAL_INPUTS_NOT_PASS")
    if canonical_manifest.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_REMAIN_BLOCKED")
    if canonical_manifest.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_ALREADY_GENERATED_WITHOUT_ADJUDICATION")

    inputs = canonical_bundle.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("NO_CANONICAL_READY_INPUTS")

    registry = EngineRegistry()
    governed_registry_lookup = "NOT_REGISTERED"
    try:
        registry.get("FOOTBALL")
    except ValueError:
        governed_registry_lookup = "NOT_REGISTERED"
    else:
        governed_registry_lookup = "REGISTERED"

    sample = _rehydrate_input(inputs[0])
    evaluation = evaluate_transparent_poisson_baseline(sample)
    if evaluation.model_status != "EXPERIMENTAL_NOT_PROMOTED":
        raise ValueError("POISSON_STATUS_UNEXPECTED")
    if evaluation.decision != "NO_BET":
        raise ValueError("POISSON_MUST_REMAIN_NO_BET")
    if not isinstance(evaluation.probabilities, dict) or len(evaluation.probabilities) < 3:
        raise ValueError("POISSON_RESEARCH_EXECUTION_FAILED")

    legacy = []
    for identifier in LEGACY_ENGINE_IDS:
        occurrences = _legacy_identifier_occurrences(root, identifier)
        active_python = [
            path for path in occurrences
            if path.endswith(".py") and not path.startswith("tests/")
        ]
        legacy.append({
            "engine_id": identifier,
            "classification": "NOT_PHYSICALLY_ADJUDICATED",
            "engine_executable": False,
            "active_python_occurrences": active_python,
            "all_occurrences": occurrences,
            "reason": (
                "NO_ACTIVE_EXECUTABLE_IMPLEMENTATION_OR_PROMOTION_EVIDENCE"
                if not active_python
                else "IDENTIFIER_PRESENT_BUT_NOT_REGISTERED_OR_PROMOTED"
            ),
        })

    governed_available = (
        governed_registry_lookup == "REGISTERED"
        and prior.get("governed_p_matrix_engine_available") is True
        and bool(prior.get("governed_p_matrix_engine"))
    )

    result = {
        "schema": "MATRIX_FOOTBALL_ENGINE_PHYSICAL_ADJUDICATION_V1",
        "adjudicated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"),
        "canonical_ready_input_count": canonical_manifest.get("ready_input_count"),
        "core_registry_football_status": governed_registry_lookup,
        "engine_executable_count": 1 if governed_available else 0,
        "governed_p_matrix_engine_available": bool(governed_available),
        "governed_p_matrix_engine": prior.get("governed_p_matrix_engine") if governed_available else None,
        "p_matrix_status": "NOT_GENERATED",
        "classifications": [
            {
                "engine_id": "transparent_poisson_baseline_v1",
                "classification": "EXPERIMENTAL_ONLY",
                "technical_execution_verified": True,
                "engine_executable_for_p_matrix": False,
                "sample_fixture_id": evaluation.fixture_id,
                "sample_market_count": len(evaluation.probabilities),
                "decision": evaluation.decision,
                "model_status": evaluation.model_status,
                "implementation": "app.research.football.experimental_evaluator.evaluate_transparent_poisson_baseline",
                "promotion_blockers": list(prior.get("promotion_blockers") or []),
            },
            *legacy,
        ],
        "decision": (
            "ENGINE_EXECUTABLE_AVAILABLE"
            if governed_available
            else "NO_GOVERNED_ENGINE_EXECUTABLE"
        ),
        "protections": {
            "no_silent_promotion": True,
            "odds_to_p_matrix": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "external_audit_closed": False,
        },
    }
    return result


def main() -> None:
    root = Path(".")
    out = root / "evidence/api_football/engine_registry"
    out.mkdir(parents=True, exist_ok=True)
    result = adjudicate(root)
    (out / "physical_adjudication.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "decision": result["decision"],
        "canonical_ready_input_count": result["canonical_ready_input_count"],
        "core_registry_football_status": result["core_registry_football_status"],
        "engine_executable_count": result["engine_executable_count"],
        "governed_p_matrix_engine_available": result["governed_p_matrix_engine_available"],
        "p_matrix_status": result["p_matrix_status"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
