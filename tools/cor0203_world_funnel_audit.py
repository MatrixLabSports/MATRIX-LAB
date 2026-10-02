from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WORLD_FUNNEL_JSON_ROOT_MUST_BE_OBJECT")
    return value


def _match_id(value: object) -> str:
    token = str(value or "").strip()
    internal = re.fullmatch(
        r"COR0203-RAPIDAPI-TENNIS-(\d+)(?:-[0-9a-f]{12})?",
        token,
    )
    if internal:
        return internal.group(1)
    provider = re.search(r"(?:match:|:)(\d+)$", token)
    if provider:
        return provider.group(1)
    plain = re.fullmatch(r"(\d+)", token)
    return plain.group(1) if plain else token


def _revision(path: Path) -> int:
    match = re.search(r"_R(\d+)\.json$", path.name)
    return int(match.group(1)) if match else -1


def build_world_funnel(
    *,
    world_inventory: Mapping[str, Any],
    world_discovery: Mapping[str, Any],
    uniqueness: Mapping[str, Any],
    runtime_dir: Path,
) -> dict[str, Any]:
    lane = (
        world_inventory.get("derived_lanes", {})
        .get("COR02_COR03_ATP_CHALLENGER_HARD", {})
    )
    world_source_ids = [
        str(value)
        for value in lane.get("source_event_ids", []) or []
    ]
    world_events = {
        str(row.get("source_event_id") or ""): row
        for row in world_inventory.get("events", []) or []
        if isinstance(row, Mapping) and row.get("source_event_id")
    }
    eligible = {
        _match_id(row.get("canonical_source_event_id") or row.get("event_id")): row
        for row in world_discovery.get("eligible_candidates", []) or []
        if isinstance(row, Mapping)
    }
    rejected = {
        _match_id(row.get("match_id")): row
        for row in world_discovery.get("provider_rejected", []) or []
        if isinstance(row, Mapping)
    }

    prereg_by_physical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(
        runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"),
        key=_revision,
    ):
        try:
            payload = _load(path)
        except Exception:
            continue
        for row in payload.get("events", []) or []:
            if not isinstance(row, Mapping):
                continue
            pkey = str(row.get("physical_event_key") or "")
            if not pkey:
                continue
            prereg_by_physical[pkey].append({
                "event_id": str(row.get("event_id") or ""),
                "revision": _revision(path),
                "path": path.name,
            })

    stage_blockers: dict[str, set[str]] = defaultdict(set)
    staged_ids: set[str] = set()
    for path in runtime_dir.glob("MATRIX_COR0203_STAGE_BLOCKERS_R*.json"):
        try:
            payload = _load(path)
        except Exception:
            continue
        for event_id in payload.get("staged_event_ids", []) or []:
            staged_ids.add(str(event_id))
        for row in payload.get("blocked", []) or []:
            if not isinstance(row, Mapping):
                continue
            event_id = str(row.get("event_id") or "")
            stage_blockers[event_id].update(
                str(value) for value in row.get("blockers", []) or []
            )

    preflight_blockers: dict[str, set[str]] = defaultdict(set)
    for path in runtime_dir.glob("MATRIX_COR0203_BATCH_PREFLIGHT_R*.json"):
        try:
            payload = _load(path)
        except Exception:
            continue
        for row in payload.get("blocked", []) or []:
            if not isinstance(row, Mapping):
                continue
            event_id = str(row.get("event_id") or "")
            preflight_blockers[event_id].update(
                str(value) for value in row.get("blockers", []) or []
            )

    frozen_by_physical = {
        str(row.get("physical_event_key") or ""): row
        for row in uniqueness.get("canonical_observations", []) or []
        if isinstance(row, Mapping) and row.get("physical_event_key")
    }

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for source_id in world_source_ids:
        mid = _match_id(source_id)
        world_row = world_events.get(source_id, {})
        discovery_row = eligible.get(mid)
        rejection = rejected.get(mid)
        blockers: set[str] = set()
        internal_event_ids: list[str] = []
        physical_key = None
        frozen_observation_index = None

        if rejection is not None:
            status = "DISCOVERY_REJECTED"
            blockers.update(
                str(value)
                for value in rejection.get("blockers", []) or []
            )
        elif discovery_row is None:
            status = "DISCOVERY_NOT_MAPPED"
            blockers.add("WORLD_DOMAIN_CANDIDATE_NOT_IN_DERIVED_DISCOVERY")
        else:
            physical_key = str(
                discovery_row.get("physical_event_key") or ""
            )
            frozen = frozen_by_physical.get(physical_key)
            prereg_rows = prereg_by_physical.get(physical_key, [])
            internal_event_ids = sorted({
                row["event_id"]
                for row in prereg_rows
                if row.get("event_id")
            })
            if frozen is not None:
                status = "FROZEN_UNIQUE"
                frozen_observation_index = frozen.get("observation_index")
            elif prereg_rows:
                for event_id in internal_event_ids:
                    blockers.update(stage_blockers.get(event_id, set()))
                    blockers.update(preflight_blockers.get(event_id, set()))
                if blockers:
                    status = "PREREGISTERED_BLOCKED"
                elif any(
                    event_id in staged_ids
                    for event_id in internal_event_ids
                ):
                    status = "STAGED_PENDING_FREEZE"
                else:
                    status = "PREREGISTERED_PENDING"
            else:
                status = "ELIGIBLE_NOT_PREREGISTERED"

        counts[status] += 1
        rows.append({
            "world_source_event_id": source_id,
            "match_id": mid,
            "competition": world_row.get("tournament_name"),
            "round": world_row.get("round"),
            "event_start_bogota": world_row.get("event_start_bogota"),
            "players": [
                (world_row.get("player1") or {}).get("name")
                if isinstance(world_row.get("player1"), Mapping)
                else None,
                (world_row.get("player2") or {}).get("name")
                if isinstance(world_row.get("player2"), Mapping)
                else None,
            ],
            "physical_event_key": physical_key,
            "internal_event_ids": internal_event_ids,
            "status": status,
            "blockers": sorted(blockers),
            "frozen_observation_index": frozen_observation_index,
        })

    return {
        "schema": "MATRIX_COR0203_WORLD_FUNNEL_AUDIT_V1",
        "target_date_bogota": world_inventory.get("target_date_bogota"),
        "world_inventory_status": world_inventory.get("status"),
        "world_inventory_complete": world_inventory.get(
            "world_inventory_complete"
        ),
        "world_inventory_total": world_inventory.get(
            "world_calendar_inventory_count"
        ),
        "world_domain_candidates": len(world_source_ids),
        "status_counts": dict(sorted(counts.items())),
        "rows": rows,
        "unique_holdout_count": uniqueness.get(
            "unique_calibration_observations"
        ),
        "metrics": "SEALED_UNTIL_600",
        "metrics_opened": False,
        "outcomes_read": 0,
        "automatic_model_feed": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-inventory", required=True)
    parser.add_argument("--world-discovery", required=True)
    parser.add_argument("--uniqueness", required=True)
    parser.add_argument(
        "--runtime-dir",
        default="evidence/cor0203/runtime",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = build_world_funnel(
        world_inventory=_load(Path(args.world_inventory)),
        world_discovery=_load(Path(args.world_discovery)),
        uniqueness=_load(Path(args.uniqueness)),
        runtime_dir=Path(args.runtime_dir),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "target_date_bogota": report["target_date_bogota"],
        "world_inventory_total": report["world_inventory_total"],
        "world_domain_candidates": report["world_domain_candidates"],
        "status_counts": report["status_counts"],
        "unique_holdout_count": report["unique_holdout_count"],
        "metrics": report["metrics"],
        "real_money": report["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
