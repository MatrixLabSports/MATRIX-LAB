from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

REGISTRY_PATH = Path("config/tennis_model_lane_registry_v1.json")
PROTECTED_COR_ROOT = "evidence/cor0203"


def _load(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("TENNIS_LANE_REGISTRY_ROOT_NOT_OBJECT")
    return value


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().upper().replace("_", " ").split())


def _surface_family(value: object) -> str:
    token = _norm(value)
    if token in {"HARD", "I.HARD", "I HARD", "INDOOR HARD"}:
        return "HARD"
    if token == "CLAY":
        return "CLAY"
    if token == "GRASS":
        return "GRASS"
    return "UNKNOWN"


def resolve_lane(
    *,
    circuit: str,
    gender: str,
    event_format: str,
    surface: str,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    reg = dict(registry or _load())
    target_circuit = _norm(circuit).replace(" ", "_")
    target_gender = _norm(gender)
    target_format = _norm(event_format)
    target_surface = _surface_family(surface)

    matches = []
    for lane in reg.get("lanes", []) or []:
        if not isinstance(lane, Mapping):
            continue
        aliases = {
            _norm(x).replace(" ", "_")
            for x in (lane.get("circuit_aliases") or [])
        }
        aliases.add(_norm(lane.get("circuit")).replace(" ", "_"))
        if target_circuit not in aliases:
            continue
        if _norm(lane.get("gender")) != target_gender:
            continue
        if _norm(lane.get("format")) != target_format:
            continue
        if _norm(lane.get("surface_family")) != target_surface:
            continue
        matches.append(dict(lane))

    if len(matches) > 1:
        raise ValueError("TENNIS_LANE_ROUTING_AMBIGUOUS")
    return matches[0] if matches else None


def validate_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    lanes = [dict(x) for x in registry.get("lanes", []) if isinstance(x, Mapping)]
    if len(lanes) != 36:
        raise ValueError(f"TENNIS_LANE_COUNT_INVALID:{len(lanes)}")

    ids = [str(x.get("lane_id") or "") for x in lanes]
    if len(set(ids)) != len(ids):
        raise ValueError("TENNIS_LANE_ID_DUPLICATE")

    active = [x for x in lanes if x.get("status") == "ACTIVE_GOVERNED_COR0203"]
    if len(active) != 1:
        raise ValueError("TENNIS_ACTIVE_GOVERNED_LANE_COUNT_INVALID")
    legacy = active[0]
    if legacy.get("lane_id") != registry.get("active_legacy_lane_id"):
        raise ValueError("TENNIS_ACTIVE_LEGACY_LANE_MISMATCH")
    if legacy.get("evidence_root") != PROTECTED_COR_ROOT:
        raise ValueError("TENNIS_LEGACY_EVIDENCE_ROOT_CHANGED")
    if legacy.get("holdout", {}).get("holdout_id") != "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1":
        raise ValueError("TENNIS_LEGACY_HOLDOUT_CHANGED")
    if legacy.get("model_binding", {}).get("elo_sha256") != "123b25888e203fba792c9f68ccffd611bb9561cd259f52b92e5a107a3178b4a9":
        raise ValueError("TENNIS_LEGACY_ELO_BINDING_CHANGED")
    if legacy.get("model_binding", {}).get("glicko_sha256") != "7701aaa009de782ab4485806606d304805c0bee923239ab3ffd511ca82c41ef6":
        raise ValueError("TENNIS_LEGACY_GLICKO_BINDING_CHANGED")

    parallel = [x for x in lanes if x.get("status") != "ACTIVE_GOVERNED_COR0203"]
    active_prospective = [x for x in parallel if x.get("status") == "ACTIVE_PROSPECTIVE_RESEARCH"]
    research_only = [x for x in parallel if x.get("status") == "RESEARCH_ONLY_NOT_TRAINED"]
    unsupported = [
        x for x in parallel
        if x.get("status") not in {"RESEARCH_ONLY_NOT_TRAINED", "ACTIVE_PROSPECTIVE_RESEARCH"}
    ]
    if unsupported:
        raise ValueError("TENNIS_PARALLEL_LANE_STATUS_UNSUPPORTED")

    for lane in parallel:
        if lane.get("feeds_cor0203") is not False:
            raise ValueError("TENNIS_RESEARCH_LANE_FEEDS_COR0203:" + lane["lane_id"])
        if lane.get("can_reuse_cor0203_holdout") is not False:
            raise ValueError("TENNIS_RESEARCH_LANE_REUSES_COR0203_HOLDOUT:" + lane["lane_id"])
        if lane.get("can_reuse_cor0203_observations") is not False:
            raise ValueError("TENNIS_RESEARCH_LANE_REUSES_COR0203_OBSERVATIONS:" + lane["lane_id"])
        if str(lane.get("evidence_root") or "").startswith(PROTECTED_COR_ROOT):
            raise ValueError("TENNIS_RESEARCH_LANE_WRITES_PROTECTED_COR_ROOT:" + lane["lane_id"])
        if lane.get("automatic_model_promotion") is not False:
            raise ValueError("TENNIS_RESEARCH_LANE_AUTO_PROMOTION_ENABLED:" + lane["lane_id"])
        if lane.get("real_money") != "BLOCKED":
            raise ValueError("TENNIS_RESEARCH_LANE_REAL_MONEY_NOT_BLOCKED:" + lane["lane_id"])

        holdout = lane.get("holdout") or {}
        if lane.get("status") == "RESEARCH_ONLY_NOT_TRAINED":
            if holdout.get("holdout_id") is not None:
                raise ValueError("TENNIS_RESEARCH_LANE_PRETENDS_HOLDOUT_EXISTS:" + lane["lane_id"])
            if lane.get("model_binding") is not None:
                raise ValueError("TENNIS_RESEARCH_LANE_PRETENDS_MODEL_EXISTS:" + lane["lane_id"])
        else:
            if not holdout.get("holdout_id"):
                raise ValueError("TENNIS_ACTIVE_PROSPECTIVE_HOLDOUT_MISSING:" + lane["lane_id"])
            if holdout.get("holdout_id") == "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1":
                raise ValueError("TENNIS_ACTIVE_PROSPECTIVE_REUSES_LEGACY_HOLDOUT:" + lane["lane_id"])
            if not isinstance(lane.get("model_binding"), Mapping):
                raise ValueError("TENNIS_ACTIVE_PROSPECTIVE_MODEL_BINDING_MISSING:" + lane["lane_id"])

    return {
        "status": "PASS",
        "lane_count": len(lanes),
        "active_governed_lane_count": len(active),
        "parallel_lane_count": len(parallel),
        "research_only_lane_count": len(research_only),
        "active_prospective_lane_count": len(active_prospective),
        "legacy_lane_id": legacy["lane_id"],
        "legacy_holdout_id": legacy["holdout"]["holdout_id"],
        "protected_cor_root": PROTECTED_COR_ROOT,
    }


def initialize_lane_states(
    *,
    registry: Mapping[str, Any],
    out_root: Path,
) -> dict[str, Any]:
    validation = validate_registry(registry)
    created = []
    for lane in registry["lanes"]:
        lane_id = lane["lane_id"]
        if lane["status"] != "RESEARCH_ONLY_NOT_TRAINED":
            continue
        state_dir = out_root / lane_id
        state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "MATRIX_TENNIS_PARALLEL_LANE_STATE_V1",
            "lane_id": lane_id,
            "status": "RESEARCH_ONLY_NOT_TRAINED",
            "domain": {
                "circuit": lane["circuit"],
                "gender": lane["gender"],
                "format": lane["format"],
                "surface_family": lane["surface_family"],
                "market": lane["market"],
            },
            "historical_dataset_status": "NOT_BUILT",
            "candidate_model_status": "NOT_TRAINED",
            "holdout_status": "NOT_CREATED",
            "prospective_observations": 0,
            "metrics_opened": False,
            "feeds_cor0203": False,
            "cor0203_holdout_reuse": False,
            "cor0203_observation_reuse": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        payload["sha256_without_self"] = hashlib.sha256(raw).hexdigest()
        (state_dir / "state.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        created.append(lane_id)

    manifest = {
        "schema": "MATRIX_TENNIS_PARALLEL_LANE_INITIALIZATION_V1",
        **validation,
        "initialized_research_lane_count": len(created),
        "initialized_research_lane_ids": created,
        "existing_cor0203_modified": False,
        "model_training_performed": False,
        "holdout_creation_performed": False,
        "metrics_opened": False,
        "real_money": "BLOCKED",
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--initialize-out")
    args = parser.parse_args()

    registry = _load(Path(args.registry))
    validation = validate_registry(registry)
    print(json.dumps(validation, sort_keys=True))

    if args.validate_only:
        return
    if args.initialize_out:
        result = initialize_lane_states(
            registry=registry,
            out_root=Path(args.initialize_out),
        )
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
