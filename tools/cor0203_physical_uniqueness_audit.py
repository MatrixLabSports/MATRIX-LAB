from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_physical_identity import physical_identity, physical_event_key

REV_RE = re.compile(r"_R(\d+)\.json$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rev(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _prefeature_by_revision(runtime_dir: Path) -> dict[int, dict[str, Mapping[str, Any]]]:
    result: dict[int, dict[str, Mapping[str, Any]]] = {}
    for path in runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"):
        revision = _rev(path)
        if revision < 0:
            continue
        payload = _load(path)
        result[revision] = {
            str(row.get("event_id") or ""): row
            for row in payload.get("events", []) or []
            if row.get("event_id")
        }
    return result


def audit_physical_uniqueness(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
    integrity: Mapping[str, Any],
) -> dict[str, Any]:
    admissible = {
        int(value)
        for value in integrity.get("admissible_batch_revisions", []) or []
    }
    pre_by_rev = _prefeature_by_revision(runtime_dir)
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for path in sorted(
        holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"),
        key=_rev,
    ):
        revision = _rev(path)
        if revision not in admissible:
            continue
        batch = _load(path)
        pre_map = pre_by_rev.get(revision, {})
        for observation in batch.get("observations", []) or []:
            event_id = str(observation.get("event_id") or "")
            pre = pre_map.get(event_id)
            source: Mapping[str, Any]
            if isinstance(pre, Mapping):
                source = pre
            else:
                source = observation

            identity = physical_identity(source)
            key = identity.get("physical_event_key")
            if not key:
                unresolved.append({
                    "revision": revision,
                    "event_id": event_id,
                    "observation_index": observation.get("observation_index"),
                    "authority": identity.get("authority"),
                })
                continue

            rows.append({
                "revision": revision,
                "event_id": event_id,
                "canonical_source_event_id": observation.get(
                    "canonical_source_event_id"
                ),
                "observation_index": int(observation.get("observation_index", -1)),
                "freeze_at_utc": observation.get("freeze_at_utc"),
                "event_start_utc": observation.get("event_start_utc"),
                "competition": observation.get("competition"),
                "round": observation.get("round"),
                "alphabetical_player_a": observation.get("alphabetical_player_a"),
                "alphabetical_player_b": observation.get("alphabetical_player_b"),
                "physical_event_key": str(key),
                "physical_identity_authority": identity.get("authority"),
                "physical_identity_components": identity.get("components"),
            })

    rows.sort(key=lambda row: (row["observation_index"], row["revision"], row["event_id"]))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["physical_event_key"]].append(row)

    canonical: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for key, members in grouped.items():
        members.sort(key=lambda row: (row["observation_index"], row["revision"], row["event_id"]))
        first = members[0]
        canonical.append({
            **first,
            "canonical_unique_index": 0,
            "duplicate_alias_count": max(0, len(members) - 1),
        })
        for duplicate in members[1:]:
            duplicates.append({
                **duplicate,
                "quarantine_reason": "DUPLICATE_PHYSICAL_MATCH",
                "canonical_event_id": first["event_id"],
                "canonical_observation_index": first["observation_index"],
                "canonical_physical_event_key": key,
            })

    canonical.sort(key=lambda row: row["observation_index"])
    for index, row in enumerate(canonical, start=1):
        row["canonical_unique_index"] = index
        row["window"] = 1 + (index - 1) // 200

    duplicates.sort(key=lambda row: row["observation_index"])
    physical_rows = len(rows) + len(unresolved)
    unique_count = len(canonical)
    duplicate_count = len(duplicates)
    expected_rows = int(integrity.get("admissible_observations", 0))

    blockers: list[str] = []
    if physical_rows != expected_rows:
        blockers.append("AUDIT_ROW_COUNT_MISMATCH")
    if unresolved:
        blockers.append("PHYSICAL_IDENTITY_UNRESOLVED")

    result = "PASS" if not blockers else "FAIL"
    return {
        "schema": "MATRIX_COR0203_PHYSICAL_UNIQUENESS_AUDIT_V1",
        "holdout_id": integrity.get("holdout_id"),
        "source_integrity_result": integrity.get("result"),
        "physical_frozen_rows": physical_rows,
        "unique_calibration_observations": unique_count,
        "duplicate_observations_quarantined": duplicate_count,
        "duplicate_groups": sum(1 for members in grouped.values() if len(members) > 1),
        "unresolved_identity_rows": len(unresolved),
        "unique_remaining_to_200": max(0, 200 - unique_count),
        "unique_remaining_to_600": max(0, 600 - unique_count),
        "canonical_observations": canonical,
        "quarantined_duplicates": duplicates,
        "unresolved": unresolved,
        "blockers": blockers,
        "metrics": "SEALED_UNTIL_600_UNIQUE",
        "metrics_opened": False,
        "outcomes_read": 0,
        "outcomes_used_for_uniqueness": 0,
        "historical_backfill": False,
        "raw_append_only_evidence_preserved": True,
        "duplicate_rows_count_toward_cor0203": False,
        "result": result,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument(
        "--integrity",
        default="evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = audit_physical_uniqueness(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
        integrity=_load(Path(args.integrity)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "result": report["result"],
        "physical_frozen_rows": report["physical_frozen_rows"],
        "unique_calibration_observations": report["unique_calibration_observations"],
        "duplicate_observations_quarantined": report[
            "duplicate_observations_quarantined"
        ],
        "duplicate_groups": report["duplicate_groups"],
        "unique_remaining_to_600": report["unique_remaining_to_600"],
        "outcomes_read": report["outcomes_read"],
        "metrics_opened": report["metrics_opened"],
    }, sort_keys=True))
    if report["result"] != "PASS":
        raise SystemExit("PHYSICAL_UNIQUENESS_AUDIT_FAILED")


if __name__ == "__main__":
    main()
