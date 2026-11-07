from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
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


def build_bridge(
    *,
    world_inventory: Mapping[str, Any],
    cor_discovery: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    if world_inventory.get("status") != "PASS":
        return {
            "schema": "MATRIX_COR0203_WORLD_INVENTORY_BRIDGE_V1",
            "target_date_bogota": world_inventory.get("target_date_bogota"),
            "world_inventory_status": world_inventory.get("status"),
            "world_inventory_complete": False,
            "world_inventory_total": world_inventory.get(
                "world_calendar_inventory_count", 0
            ),
            "world_domain_candidates": 0,
            "status_counts": {
                "WORLD_INVENTORY_NOT_COMPLETE": 1,
            },
            "rows": [],
            "cor_discovery_eligible_total": len(
                cor_discovery.get("eligible_candidates", []) or []
            ),
            "cor_discovery_rejected_total": len(
                cor_discovery.get("provider_rejected", []) or []
            ),
            "cor_candidates_outside_today_world_lane": [],
            "automatic_model_feed": False,
            "governed_preregistration_authoritative": True,
            "metrics_opened": False,
            "outcomes_read": 0,
            "real_money": "BLOCKED",
        }
    lane = (
        world_inventory.get("derived_lanes", {})
        .get("COR02_COR03_ATP_CHALLENGER_HARD", {})
    )
    world_ids = [
        str(value)
        for value in lane.get("source_event_ids", []) or []
    ]
    world_match_ids = {_match_id(value) for value in world_ids}

    eligible_by_match: dict[str, Mapping[str, Any]] = {}
    for row in cor_discovery.get("eligible_candidates", []) or []:
        event_id = str(
            row.get("canonical_source_event_id")
            or row.get("event_id")
            or ""
        )
        mid = _match_id(event_id)
        if mid:
            eligible_by_match[mid] = row

    rejected_by_match: dict[str, Mapping[str, Any]] = {}
    for row in cor_discovery.get("provider_rejected", []) or []:
        mid = str(row.get("match_id") or "")
        if mid:
            rejected_by_match[mid] = row

    prereg_skipped: dict[str, list[str]] = {}
    for row in prereg.get("skipped", []) or []:
        mid = _match_id(row.get("source_event_id"))
        if mid:
            prereg_skipped[mid] = [
                str(x) for x in row.get("blockers", []) or []
            ]

    prereg_event_ids = {
        _match_id(value)
        for value in prereg.get("event_ids", []) or []
    }

    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for source_event_id in world_ids:
        mid = _match_id(source_event_id)
        if mid in prereg_event_ids:
            status = "PREREGISTERED"
            blockers: list[str] = []
        elif mid in prereg_skipped:
            status = "PREREGISTRATION_SKIPPED"
            blockers = prereg_skipped[mid]
        elif mid in eligible_by_match:
            status = "COR_DISCOVERY_ELIGIBLE_NOT_PREREGISTERED"
            blockers = []
        elif mid in rejected_by_match:
            status = "COR_DISCOVERY_REJECTED"
            blockers = [
                str(x)
                for x in rejected_by_match[mid].get("blockers", []) or []
            ]
        else:
            status = "NOT_PRESENT_IN_CURRENT_COR_DISCOVERY"
            blockers = [
                "CURRENT_COR_DISCOVERY_HORIZON_FILTER_OR_PROVIDER_SNAPSHOT_MISMATCH"
            ]

        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append({
            "world_source_event_id": source_event_id,
            "match_id": mid,
            "status": status,
            "blockers": blockers,
        })

    unexpected_cor_candidates = []
    for mid, row in eligible_by_match.items():
        if mid in world_match_ids:
            continue
        unexpected_cor_candidates.append({
            "match_id": mid,
            "event_id": row.get("event_id"),
            "reason": (
                "COR candidate is outside today's world-inventory lane; "
                "it may belong to the governed future horizon."
            ),
        })

    return {
        "schema": "MATRIX_COR0203_WORLD_INVENTORY_BRIDGE_V1",
        "target_date_bogota": world_inventory.get("target_date_bogota"),
        "world_inventory_status": world_inventory.get("status"),
        "provider_inventory_complete": world_inventory.get(
            "provider_inventory_complete"
        ),
        "world_inventory_complete": world_inventory.get(
            "world_inventory_complete"
        ),
        "world_complete_gate": world_inventory.get("world_complete_gate"),
        "world_inventory_total": world_inventory.get(
            "world_calendar_inventory_count"
        ),
        "world_domain_candidates": len(world_ids),
        "status_counts": dict(sorted(status_counts.items())),
        "rows": rows,
        "cor_discovery_eligible_total": len(eligible_by_match),
        "cor_discovery_rejected_total": len(rejected_by_match),
        "cor_candidates_outside_today_world_lane": unexpected_cor_candidates,
        "automatic_model_feed": False,
        "governed_preregistration_authoritative": True,
        "metrics_opened": False,
        "outcomes_read": 0,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-inventory", required=True)
    parser.add_argument("--cor-discovery", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = build_bridge(
        world_inventory=_load(Path(args.world_inventory)),
        cor_discovery=_load(Path(args.cor_discovery)),
        prereg=_load(Path(args.prereg)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "target_date_bogota": report["target_date_bogota"],
        "world_domain_candidates": report["world_domain_candidates"],
        "status_counts": report["status_counts"],
        "cor_discovery_eligible_total": report["cor_discovery_eligible_total"],
        "real_money": report["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
