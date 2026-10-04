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




def _provider_family(row: Mapping[str, Any]) -> str:
    explicit = _norm(row.get("source_provider"))
    if explicit:
        return explicit
    for key in ("canonical_source_event_id", "event_id"):
        value = str(row.get(key) or "").strip()
        if ":" in value:
            return value.split(":", 1)[0].casefold()
    return ""


def _competition_signature(value: object) -> str:
    token = _norm(value)
    token = re.sub(r"\([^)]*\)", " ", token)
    token = re.sub(r"[^a-z0-9]+", " ", token)
    noise = {
        "atp",
        "challenger",
        "men",
        "singles",
        "qualification",
        "qualifying",
    }
    parts = [part for part in token.split() if part not in noise]
    return " ".join(parts)


def _secondary_cross_provider_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    players = sorted(
        {
            _norm(row.get("alphabetical_player_a")),
            _norm(row.get("alphabetical_player_b")),
        }
    )
    if len(players) != 2 or not all(players):
        return None
    start = str(row.get("event_start_utc") or "").strip()
    competition = _competition_signature(row.get("competition"))
    if not start or not competition:
        return None
    return ("|".join(players), start, competition)


def _round_identity_token(row: Mapping[str, Any]) -> str:
    components = row.get("physical_identity_components")
    if isinstance(components, Mapping):
        return str(components.get("round") or "").strip().upper()
    return str(row.get("round") or "").strip().upper().replace("_", " ")


def _rounds_compatible(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    unknown = {"", "UNKNOWN", "UNKNOWN ROUND", "N/A", "NA", "NONE"}
    a = _round_identity_token(left)
    b = _round_identity_token(right)
    return a == b or a in unknown or b in unknown


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
                "source_provider": source.get("source_provider"),
            })

    rows.sort(key=lambda row: (row["observation_index"], row["revision"], row["event_id"]))

    # Primary identity remains the provider-aware physical_event_key. A second,
    # conservative cross-provider gate prevents the same physical match from
    # counting twice when providers use different tournament/player IDs.
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a = find(left)
        b = find(right)
        if a != b:
            parent[b] = a

    strict_groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        strict_groups[row["physical_event_key"]].append(index)
    for members in strict_groups.values():
        for index in members[1:]:
            union(members[0], index)

    secondary_groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        key = _secondary_cross_provider_key(row)
        if key is not None:
            secondary_groups[key].append(index)

    for members in secondary_groups.values():
        for left_pos, left_index in enumerate(members):
            left = rows[left_index]
            left_provider = _provider_family(left)
            if not left_provider:
                continue
            for right_index in members[left_pos + 1 :]:
                right = rows[right_index]
                right_provider = _provider_family(right)
                if not right_provider or left_provider == right_provider:
                    continue
                if _rounds_compatible(left, right):
                    union(left_index, right_index)

    grouped_indexes: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        grouped_indexes[find(index)].append(index)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for members in grouped_indexes.values():
        materialized = [rows[index] for index in members]
        materialized.sort(
            key=lambda row: (row["observation_index"], row["revision"], row["event_id"])
        )
        grouped[materialized[0]["physical_event_key"]] = materialized

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
            cross_provider = (
                duplicate["physical_event_key"] != first["physical_event_key"]
            )
            duplicates.append({
                **duplicate,
                "quarantine_reason": (
                    "DUPLICATE_PHYSICAL_MATCH_CROSS_PROVIDER"
                    if cross_provider
                    else "DUPLICATE_PHYSICAL_MATCH"
                ),
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
