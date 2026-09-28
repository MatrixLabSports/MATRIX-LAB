from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

REV_RE = re.compile(r"_R(\d+)\.json$")
EXACT_HOLDOUT_RE = re.compile(r"^MATRIX_COR0203_HOLDOUT_BATCH_R(\d+)\.json$")


def _rev(path: Path) -> int:
    m = REV_RE.search(path.name)
    return int(m.group(1)) if m else -1


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _frozen_event_ids(holdout_dir: Path) -> set[str]:
    out: set[str] = set()
    for p in holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
        if not EXACT_HOLDOUT_RE.match(p.name):
            continue
        d = _load(p)
        for row in d.get("observations", []) or []:
            event_id = str(row.get("event_id") or "")
            if event_id:
                out.add(event_id)
    return out


def _physical_observation_count(holdout_dir: Path) -> int:
    count = 0
    for p in holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"):
        if not EXACT_HOLDOUT_RE.match(p.name):
            continue
        try:
            d = _load(p)
            count = max(count, int(d.get("ending_observation_count", 0)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return count


def _staged_event_ids(runtime_dir: Path) -> set[str]:
    out: set[str] = set()
    for p in runtime_dir.glob("MATRIX_COR0203_PROSPECTIVE_EVENTS_R*.json"):
        d = _load(p)
        for row in d.get("events", []) or []:
            event_id = str(row.get("event_id") or "")
            if event_id:
                out.add(event_id)
    return out


def build_identity_restage_delta(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
) -> dict[str, Any]:
    pref_paths = sorted(
        runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"),
        key=_rev,
    )
    if not pref_paths:
        return {
            "schema": "MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_SUMMARY_V1",
            "status": "NO_PREFEATURE_REGISTRIES",
            "created": False,
            "events": 0,
            "real_money": "BLOCKED",
        }

    frozen = _frozen_event_ids(holdout_dir)
    physical_count = _physical_observation_count(holdout_dir)
    staged = _staged_event_ids(runtime_dir)
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    for pre_path in pref_paths:
        revision = _rev(pre_path)
        crosswalk_path = runtime_dir / f"MATRIX_COR0203_IDENTITY_CROSSWALK_R{revision}.json"
        if not crosswalk_path.exists():
            continue
        pre = _load(pre_path)
        crosswalk = _load(crosswalk_path)
        event_status = {
            str(row.get("event_id") or ""): str(row.get("status") or "")
            for row in crosswalk.get("events", []) or []
            if isinstance(row, Mapping)
        }
        for row in pre.get("events", []) or []:
            if not isinstance(row, Mapping):
                continue
            event_id = str(row.get("event_id") or "")
            if not event_id or event_id in frozen or event_id in staged:
                continue
            if event_status.get(event_id) != "PASS":
                continue
            if row.get("outcome") is not None:
                raise ValueError("RESTAGE_DELTA_OUTCOME_ALREADY_PRESENT:" + event_id)
            if row.get("metrics_opened") is not False:
                raise ValueError("RESTAGE_DELTA_METRICS_NOT_SEALED:" + event_id)
            if row.get("features_loaded") is not False:
                raise ValueError("RESTAGE_DELTA_FEATURES_ALREADY_LOADED:" + event_id)
            candidates.append((revision, pre_path.name, dict(row)))

    if not candidates:
        return {
            "schema": "MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_SUMMARY_V1",
            "status": "NO_NEWLY_UNBLOCKED_EVENTS",
            "created": False,
            "events": 0,
            "real_money": "BLOCKED",
        }

    existing_revs = {_rev(p) for p in pref_paths}
    next_rev = max(existing_revs) + 1
    while next_rev in existing_revs:
        next_rev += 1

    # Preserve original preregistration order and never re-select by model/output.
    unique: dict[str, tuple[int, str, dict[str, Any]]] = {}
    for item in candidates:
        event_id = str(item[2]["event_id"])
        unique.setdefault(event_id, item)
    selected = list(unique.values())

    payload = {
        "schema": f"MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_R{next_rev}_V1",
        "revision": f"R{next_rev}",
        "holdout_id": "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1",
        "starting_observation_count": physical_count,
        "created_before_feature_acquisition": True,
        "selection_unchanged_from_original_preregistration": True,
        "new_event_selection": False,
        "delta_reason": "IDENTITY_EVIDENCE_IMPROVED_AFTER_ORIGINAL_PREREGISTRATION",
        "source_preregistrations": sorted({name for _, name, _ in selected}),
        "source_revisions": sorted({rev for rev, _, _ in selected}),
        "events": [
            {
                **row,
                "restage_original_revision": f"R{rev}",
                "restage_original_prefeature": name,
            }
            for rev, name, row in selected
        ],
        "protections": {
            "original_preregistration_preserved": True,
            "outcomes_read": False,
            "metrics_opened": False,
            "odds_used_for_probability": False,
            "silent_imputation": False,
            "duplicate_frozen_or_staged_events_excluded": True,
        },
        "real_money": "BLOCKED",
    }
    out = runtime_dir / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{next_rev}.json"
    if out.exists():
        raise ValueError("RESTAGE_DELTA_REVISION_COLLISION:" + str(next_rev))
    _write(out, payload)

    return {
        "schema": "MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_SUMMARY_V1",
        "status": "CREATED",
        "created": True,
        "revision": next_rev,
        "path": str(out),
        "events": len(payload["events"]),
        "event_ids": [str(row["event_id"]) for row in payload["events"]],
        "source_revisions": payload["source_revisions"],
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument(
        "--summary-out",
        default="evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_LAST.json",
    )
    args = parser.parse_args()
    result = build_identity_restage_delta(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
    )
    _write(Path(args.summary_out), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
