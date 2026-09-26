from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

REV_RE = re.compile(r"_R(\d+)(?:_|\.)")
EXACT_HOLDOUT_RE = re.compile(r"^MATRIX_COR0203_HOLDOUT_BATCH_R(\d+)\.json$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _revision(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _next_revision(cor_root: Path) -> int:
    highest = 0
    for path in cor_root.rglob("*"):
        if path.is_file():
            highest = max(highest, _revision(path))
    return highest + 1


def _physical_holdout_count(holdout_dir: Path) -> int:
    count = 0
    for path in holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
        if not EXACT_HOLDOUT_RE.match(path.name):
            continue
        payload = _load(path)
        try:
            count = max(count, int(payload.get("ending_observation_count", 0)))
        except (TypeError, ValueError):
            continue
    return count


def _existing_ids(runtime_dir: Path, holdout_dir: Path) -> tuple[set[str], set[str]]:
    event_ids: set[str] = set()
    source_ids: set[str] = set()

    for path in runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"):
        try:
            payload = _load(path)
        except Exception:
            continue
        for row in payload.get("events", []) or []:
            event_id = str(row.get("event_id") or "")
            source_id = str(row.get("canonical_source_event_id") or "")
            if event_id:
                event_ids.add(event_id)
            if source_id:
                source_ids.add(source_id)

    for path in holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
        if not EXACT_HOLDOUT_RE.match(path.name):
            continue
        payload = _load(path)
        for row in payload.get("observations", []) or []:
            event_id = str(row.get("event_id") or "")
            source_id = str(row.get("canonical_source_event_id") or "")
            if event_id:
                event_ids.add(event_id)
            if source_id:
                source_ids.add(source_id)

    return event_ids, source_ids


def preregister_discovery(
    *,
    discovery: Mapping[str, Any],
    cor_root: Path,
    runtime_dir: Path,
    holdout_dir: Path,
) -> dict[str, Any]:
    status = str(discovery.get("status") or "")
    if status != "DISCOVERY_COMPLETED":
        return {
            "schema": "MATRIX_COR0203_DISCOVERY_PREREGISTRATION_RESULT_V1",
            "status": "NO_DISCOVERY_INPUT",
            "provider_status": status or "UNKNOWN",
            "created": False,
            "events_registered": 0,
        }

    candidates = list(discovery.get("eligible_candidates") or [])
    existing_event_ids, existing_source_ids = _existing_ids(runtime_dir, holdout_dir)
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in candidates:
        source_event_id = str(candidate.get("canonical_source_event_id") or candidate.get("event_id") or "")
        raw_event_id = str(candidate.get("event_id") or "")
        provider_event_key = raw_event_id.rsplit(":", 1)[-1] if raw_event_id else ""
        event_id = f"COR0203-API-TENNIS-{provider_event_key}" if provider_event_key.isdigit() else ""

        blockers: list[str] = []
        if not event_id or not source_event_id:
            blockers.append("DISCOVERY_EVENT_ID_INVALID")
        if event_id in existing_event_ids or source_event_id in existing_source_ids:
            blockers.append("ALREADY_PREREGISTERED_OR_FROZEN")

        players = list(candidate.get("players") or [])
        if len(players) != 2:
            blockers.append("TWO_PROVIDER_IDENTITIES_REQUIRED")
        else:
            provider_ids = [str(p.get("provider_player_id") or "") for p in players]
            names = [str(p.get("name") or "").strip() for p in players]
            if not all(re.fullmatch(r"api-tennis:player:\d+", value) for value in provider_ids):
                blockers.append("PROVIDER_PLAYER_ID_INVALID")
            if not all(names) or names[0] == names[1] or provider_ids[0] == provider_ids[1]:
                blockers.append("PROVIDER_PLAYER_IDENTITY_NOT_FIXED")

        source_sha = str(candidate.get("source_snapshot_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            blockers.append("SOURCE_SNAPSHOT_SHA_INVALID")

        if blockers:
            skipped.append({
                "source_event_id": source_event_id or None,
                "blockers": sorted(set(blockers)),
            })
            continue

        selected.append({
            "event_id": event_id,
            "canonical_source_event_id": source_event_id,
            "competition": candidate.get("competition"),
            "competition_id": candidate.get("competition_id"),
            "round": candidate.get("round"),
            "surface": "Hard",
            "tour_level": "C",
            "target_period": int(candidate.get("target_period", 20260921)),
            "event_start_utc": candidate.get("event_start_utc"),
            "identity_source": candidate.get("source_reference"),
            "schedule_source": candidate.get("source_reference"),
            "source_provider": "api_tennis",
            "source_snapshot_sha256": source_sha,
            "players": [str(p.get("name") or "").strip() for p in players],
            "player_identities": [
                {
                    "display_name": str(p.get("name") or "").strip(),
                    "provider_player_id": str(p.get("provider_player_id") or ""),
                    "provider": "api_tennis",
                }
                for p in players
            ],
            "identity_crosswalk_required": True,
            "historical_identity_crosswalk_status": "PENDING",
            "features_loaded": False,
            "outcome": None,
            "metrics_opened": False,
        })

    if not selected:
        return {
            "schema": "MATRIX_COR0203_DISCOVERY_PREREGISTRATION_RESULT_V1",
            "status": "NO_NEW_EVENTS",
            "provider_status": status,
            "created": False,
            "events_registered": 0,
            "skipped": skipped,
        }

    revision = _next_revision(cor_root)
    count = _physical_holdout_count(holdout_dir)
    out = runtime_dir / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{revision}.json"
    payload = {
        "schema": f"MATRIX_COR0203_API_TENNIS_PREFEATURE_REGISTRY_R{revision}_V1",
        "revision": f"R{revision}",
        "holdout_id": "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1",
        "created_before_feature_acquisition": True,
        "registration_timestamp_authority": "GIT_COMMIT_TIMESTAMP",
        "starting_observation_count": count,
        "discovery_provider": "api_tennis",
        "events": selected,
        "protections": {
            "outcome_read_for_performance": False,
            "metrics_opened": False,
            "odds_used": False,
            "historical_backfill": False,
            "feature_acquisition_before_this_commit": False,
            "identity_crosswalk_required": True,
        },
        "real_money": "BLOCKED",
    }
    _write(out, payload)

    return {
        "schema": "MATRIX_COR0203_DISCOVERY_PREREGISTRATION_RESULT_V1",
        "status": "PREREGISTERED",
        "provider_status": status,
        "created": True,
        "revision": revision,
        "path": str(out),
        "starting_observation_count": count,
        "events_registered": len(selected),
        "event_ids": [row["event_id"] for row in selected],
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--cor-root", default="evidence/cor0203")
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument("--result-out", required=True)
    args = parser.parse_args()

    result = preregister_discovery(
        discovery=_load(Path(args.discovery)),
        cor_root=Path(args.cor_root),
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
    )
    _write(Path(args.result_out), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
