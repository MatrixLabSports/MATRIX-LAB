from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

REV_RE = re.compile(r"_R(\d+)\.json$")
EXACT_HOLDOUT_RE = re.compile(r"^MATRIX_COR0203_HOLDOUT_BATCH_R(\d+)\.json$")
CONTROL_WINDOW1 = 0.4967308051559873
MODEL_BINDING = "MATRIX_COR0203_MODEL_BINDING_R707_V1"


def _rev(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _frozen_event_ids(holdout_dir: Path) -> set[str]:
    result: set[str] = set()
    for path in holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
        if not EXACT_HOLDOUT_RE.match(path.name):
            continue
        payload = _load(path)
        for observation in payload.get("observations", []) or []:
            event_id = str(observation.get("event_id") or "")
            if event_id:
                result.add(event_id)
    return result


def build_sealed_player_registry(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
) -> dict[str, dict[str, Any]]:
    frozen = _frozen_event_ids(holdout_dir)
    observations: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(runtime_dir.glob("MATRIX_COR0203_PROSPECTIVE_EVENTS_R*.json"), key=_rev):
        payload = _load(path)
        for event in payload.get("events", []) or []:
            if str(event.get("event_id") or "") not in frozen:
                continue
            target_period = int(event.get("target_period", 0))
            if target_period != 20260921:
                continue
            for player in event.get("players", []) or []:
                name = str(player.get("name") or "").strip()
                if not name:
                    continue
                row = {
                    "name": name,
                    "source_id": str(player.get("source_id") or ""),
                    "hand": player.get("hand"),
                    "age": player.get("age"),
                    "rank": player.get("rank"),
                    "rank_points": player.get("rank_points"),
                    "inherited_from": path.name,
                    "source_event_id": event.get("event_id"),
                }
                observations.setdefault(name, []).append(row)

    registry: dict[str, dict[str, Any]] = {}
    for name, rows in observations.items():
        static_signatures = {
            (
                str(row.get("hand") or ""),
                float(row["age"]),
                float(row["rank"]),
                float(row["rank_points"]),
            )
            for row in rows
        }
        if len(static_signatures) != 1:
            registry[name] = {
                "status": "CONFLICT",
                "rows": rows,
                "blocker": "SEALED_STATIC4_CONFLICT",
            }
            continue

        nonempty_ids = {str(row["source_id"]) for row in rows if str(row["source_id"])}
        if len(nonempty_ids) > 1:
            registry[name] = {
                "status": "CONFLICT",
                "rows": rows,
                "blocker": "SEALED_SOURCE_ID_CONFLICT",
            }
            continue

        representative = rows[-1]
        registry[name] = {
            "status": "PASS",
            "source_id": next(iter(nonempty_ids), ""),
            "hand": representative["hand"],
            "age": representative["age"],
            "rank": representative["rank"],
            "rank_points": representative["rank_points"],
            "inherited_from": sorted({row["inherited_from"] for row in rows}),
            "source_event_ids": sorted({str(row["source_event_id"]) for row in rows}),
        }

    return registry


def stage_prefeature(
    *,
    prefeature_path: Path,
    runtime_dir: Path,
    player_registry: Mapping[str, Mapping[str, Any]],
    frozen_event_ids: set[str],
) -> dict[str, Any]:
    revision = _rev(prefeature_path)
    if revision < 0:
        raise ValueError("PREFEATURE_REVISION_UNRESOLVED")

    pre = _load(prefeature_path)
    static_path = runtime_dir / f"MATRIX_COR0203_STATIC4_R{revision}.json"
    events_path = runtime_dir / f"MATRIX_COR0203_PROSPECTIVE_EVENTS_R{revision}.json"
    blocker_path = runtime_dir / f"MATRIX_COR0203_STAGE_BLOCKERS_R{revision}.json"

    pre_rows = list(pre.get("events", []) or [])
    pre_event_ids = {str(row.get("event_id") or "") for row in pre_rows}
    real_pre_event_ids = {event_id for event_id in pre_event_ids if event_id}

    if real_pre_event_ids and real_pre_event_ids.issubset(frozen_event_ids):
        return {
            "revision": revision,
            "status": "ALREADY_FROZEN",
            "staged_events": 0,
            "blocked_events": 0,
        }

    if static_path.exists() and events_path.exists():
        return {
            "revision": revision,
            "status": "ALREADY_STAGED",
            "staged_events": 0,
            "blocked_events": 0,
        }

    if static_path.exists() != events_path.exists():
        reason = (
            "STATIC4_EXISTS_EVENT_MANIFEST_MISSING"
            if static_path.exists()
            else "EVENT_MANIFEST_EXISTS_STATIC4_MISSING"
        )
        payload = {
            "schema": "MATRIX_COR0203_STAGE_BLOCKERS_V1",
            "revision": f"R{revision}",
            "prefeature": prefeature_path.name,
            "staged_event_ids": [],
            "blocked": [{"event_id": event_id, "blockers": [reason]} for event_id in sorted(real_pre_event_ids)],
            "staged_events": 0,
            "blocked_events": len(real_pre_event_ids),
            "result": "INCOMPLETE_EXISTING_STAGE",
            "real_money": "BLOCKED",
        }
        _write(blocker_path, payload)
        return {
            "revision": revision,
            "status": "INCOMPLETE_EXISTING_STAGE",
            "staged_events": 0,
            "blocked_events": len(real_pre_event_ids),
        }

    staged_events: list[dict[str, Any]] = []
    static_events: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    crosswalk_path = runtime_dir / f"MATRIX_COR0203_IDENTITY_CROSSWALK_R{revision}.json"
    crosswalk = _load(crosswalk_path) if crosswalk_path.exists() else None
    crosswalk_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(crosswalk, Mapping):
        for mapping in crosswalk.get("mappings", []) or []:
            if not isinstance(mapping, Mapping):
                continue
            provider_id = str(mapping.get("provider_player_id") or "")
            if provider_id:
                crosswalk_map[provider_id] = mapping

    for event in pre_rows:
        event_id = str(event.get("event_id") or "")
        if event_id in frozen_event_ids:
            continue
        names = [str(name).strip() for name in event.get("players", []) or []]
        event_blockers: list[str] = []

        if bool(event.get("identity_crosswalk_required")):
            identities = list(event.get("player_identities") or [])
            if not isinstance(crosswalk, Mapping) or crosswalk.get("status") != "PASS":
                event_blockers.append("HISTORICAL_IDENTITY_CROSSWALK_REQUIRED")
            elif len(identities) != 2:
                event_blockers.append("PROVIDER_IDENTITIES_REQUIRED")
            else:
                canonical_names: list[str] = []
                for identity in identities:
                    provider_id = str(identity.get("provider_player_id") or "")
                    mapping = crosswalk_map.get(provider_id)
                    if not isinstance(mapping, Mapping) or mapping.get("status") != "PASS":
                        event_blockers.append("IDENTITY_CROSSWALK_MISSING:" + provider_id)
                        continue
                    canonical_name = str(mapping.get("canonical_name") or "").strip()
                    if not canonical_name:
                        event_blockers.append("IDENTITY_CROSSWALK_CANONICAL_NAME_MISSING:" + provider_id)
                        continue
                    canonical_names.append(canonical_name)
                if len(canonical_names) == 2:
                    names = canonical_names

        if len(names) != 2 or not all(names) or names[0] == names[1]:
            event_blockers.append("PREFEATURE_IDENTITY_INVALID")

        resolved: list[dict[str, Any]] = []
        for name in names:
            entry = player_registry.get(name)
            if entry is None:
                event_blockers.append("SEALED_STATIC4_PLAYER_NOT_FOUND:" + name)
                continue
            if entry.get("status") != "PASS":
                event_blockers.append(str(entry.get("blocker") or "SEALED_STATIC4_CONFLICT") + ":" + name)
                continue
            resolved.append({
                "name": name,
                "source_id": str(entry.get("source_id") or ""),
                "hand": entry["hand"],
                "age": entry["age"],
                "rank": entry["rank"],
                "rank_points": entry["rank_points"],
            })

        if event_blockers:
            blockers.append({"event_id": event_id, "blockers": sorted(set(event_blockers))})
            continue

        source_reference = " | ".join(
            part for part in [
                str(event.get("identity_source") or "").strip(),
                str(event.get("schedule_source") or "").strip(),
            ] if part
        )
        if not source_reference:
            source_reference = "PREFEATURE_REGISTRY:" + prefeature_path.name

        static_events.append({
            "event_id": event_id,
            "players": {
                player["name"]: {
                    "source_id": player["source_id"],
                    "hand": player["hand"],
                    "age": player["age"],
                    "rank": player["rank"],
                    "rank_points": player["rank_points"],
                    "inherited_from": player_registry[player["name"]]["inherited_from"],
                }
                for player in resolved
            },
        })

        staged_events.append({
            "event_id": event_id,
            "canonical_source_event_id": event.get("canonical_source_event_id"),
            "competition": event.get("competition"),
            "round": event.get("round"),
            "surface": event.get("surface"),
            "tour_level": event.get("tour_level"),
            "target_period": int(event.get("target_period")),
            "event_start_utc": event.get("event_start_utc"),
            "source_reference": source_reference,
            "prior_preregistration_reference": str(pre.get("schema") or prefeature_path.stem),
            "players": resolved,
        })

    if staged_events:
        static_payload: dict[str, Any] = {
            "schema": f"MATRIX_COR0203_STATIC4_R{revision}_AUTO_V1",
            "revision": f"R{revision}",
            "holdout_id": pre.get("holdout_id"),
            "as_of_date": "2026-09-21",
            "source_authority": "Reused unchanged from physically frozen prospective manifests in the same 21-SEP sealed player registry",
            "events": static_events,
            "provenance": {
                "ranking_cut": "2026-09-21",
                "silent_imputation": False,
                "missing_as_zero": False,
                "odds_used": False,
                "post_prereg_feature_acquisition": True,
                "registry_source_only_frozen_events": True,
            },
            "real_money": "BLOCKED",
        }
        if len(static_events) == 1:
            static_payload["event_id"] = static_events[0]["event_id"]
            static_payload["players"] = static_events[0]["players"]
        _write(static_path, static_payload)

        event_payload = {
            "schema": f"MATRIX_COR0203_PROSPECTIVE_EVENT_BATCH_R{revision}_AUTO_V1",
            "revision": f"R{revision}",
            "holdout_id": pre.get("holdout_id"),
            "model_binding": MODEL_BINDING,
            "starting_observation_count": int(pre.get("starting_observation_count", 0)),
            "control_probability_window1": CONTROL_WINDOW1,
            "events": staged_events,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
        _write(events_path, event_payload)

    blocker_payload = {
        "schema": "MATRIX_COR0203_STAGE_BLOCKERS_V1",
        "revision": f"R{revision}",
        "prefeature": prefeature_path.name,
        "staged_event_ids": [row["event_id"] for row in staged_events],
        "blocked": blockers,
        "staged_events": len(staged_events),
        "blocked_events": len(blockers),
        "result": (
            "PASS_WITH_BLOCKERS" if staged_events and blockers
            else "PASS" if staged_events
            else "ALL_BLOCKED"
        ),
        "real_money": "BLOCKED",
    }
    _write(blocker_path, blocker_payload)

    return {
        "revision": revision,
        "status": blocker_payload["result"],
        "staged_events": len(staged_events),
        "blocked_events": len(blockers),
    }


def stage_all_pending(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
) -> dict[str, Any]:
    frozen_event_ids = _frozen_event_ids(holdout_dir)
    registry = build_sealed_player_registry(runtime_dir=runtime_dir, holdout_dir=holdout_dir)
    results = []
    for prefeature in sorted(runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"), key=_rev):
        results.append(
            stage_prefeature(
                prefeature_path=prefeature,
                runtime_dir=runtime_dir,
                player_registry=registry,
                frozen_event_ids=frozen_event_ids,
            )
        )
    return {
        "schema": "MATRIX_COR0203_AUTO_STAGE_SUMMARY_V1",
        "registry_players": len(registry),
        "registry_pass": sum(1 for row in registry.values() if row.get("status") == "PASS"),
        "registry_conflicts": sum(1 for row in registry.values() if row.get("status") != "PASS"),
        "revisions": results,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    summary = stage_all_pending(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
    )
    _write(Path(args.summary_out), summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
