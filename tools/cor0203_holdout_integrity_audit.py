from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_prospective_producer import (
    canonical_sha,
    extend_state,
    feature_snapshot,
    load_state,
    score_spec,
)

REV_RE = re.compile(r"_R(\d+)\.json$")
SURFACE = "Hard"
TOL = 1e-12


def _rev(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _close(left: object, right: object, tol: float = TOL) -> bool:
    return _finite(left) and _finite(right) and abs(float(left) - float(right)) <= tol


def _history_blockers(state: Mapping[str, Any], player: str) -> list[str]:
    history = state.get("history", {})
    blockers: list[str] = []

    if not list(history.get("matches", {}).get(player, [])):
        blockers.append("FORM_HISTORY_MISSING")

    for section, code in (
        ("overall", "OVERALL_HISTORY_MISSING"),
        ("serve", "SERVE_HISTORY_MISSING"),
        ("ret", "RETURN_HISTORY_MISSING"),
        ("opp_strength", "OPPONENT_STRENGTH_HISTORY_MISSING"),
    ):
        pair = history.get(section, {}).get(player)
        if (
            not isinstance(pair, list)
            or len(pair) < 2
            or not _finite(pair[1])
            or float(pair[1]) <= 0
        ):
            blockers.append(code)

    pair = history.get("surface", {}).get(player, {}).get(SURFACE)
    if (
        not isinstance(pair, list)
        or len(pair) < 2
        or not _finite(pair[1])
        or float(pair[1]) <= 0
    ):
        blockers.append("SURFACE_HISTORY_MISSING")

    if player not in state.get("elo_overall", {}):
        blockers.append("ELO_OVERALL_MISSING")
    if player not in state.get("elo_surface", {}).get(SURFACE, {}):
        blockers.append("ELO_SURFACE_MISSING")
    if player not in state.get("glicko_overall", {}):
        blockers.append("GLICKO_OVERALL_MISSING")
    if player not in state.get("glicko_surface", {}).get(SURFACE, {}):
        blockers.append("GLICKO_SURFACE_MISSING")

    return blockers


def _admissible_chain(
    *,
    holdout_dir: Path,
    binding: Mapping[str, Any],
) -> tuple[list[tuple[int, Path, dict[str, Any]]], list[dict[str, Any]], int]:
    quarantine_path = str(binding.get("quarantine", {}).get("batch") or "")
    quarantine_name = Path(quarantine_path).name if quarantine_path else ""
    elo_id = str(binding["candidates"]["elo"]["identity"])
    glicko_id = str(binding["candidates"]["glicko"]["identity"])

    candidates = sorted(
        holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"),
        key=_rev,
    )
    expected = 0
    chain: list[tuple[int, Path, dict[str, Any]]] = []
    excluded: list[dict[str, Any]] = []

    for path in candidates:
        revision = _rev(path)
        payload = _load(path)

        if path.name == quarantine_name:
            excluded.append({
                "revision": revision,
                "path": str(path),
                "reason": str(binding.get("quarantine", {}).get("reason") or "BINDING_QUARANTINE"),
                "admissible_observations": int(binding.get("quarantine", {}).get("admissible_observations", 0)),
            })
            continue

        observations = list(payload.get("observations") or [])
        start = int(payload.get("starting_observation_count", -1))
        added = int(payload.get("added_observations", -1))
        end = int(payload.get("ending_observation_count", -1))

        structural = (
            start == expected
            and added == len(observations)
            and end == start + added
            and int(payload.get("window1_count", -1)) == end
            and payload.get("metrics") == "SEALED_UNTIL_600"
            and int(payload.get("outcomes_read", -1)) == 0
            and all(obs.get("outcome") is None for obs in observations)
            and all(obs.get("metrics_opened") is False for obs in observations)
            and all(obs.get("elo", {}).get("model_id") == elo_id for obs in observations)
            and all(obs.get("glicko", {}).get("model_id") == glicko_id for obs in observations)
        )
        if not structural:
            excluded.append({
                "revision": revision,
                "path": str(path),
                "reason": "NOT_IN_ADMISSIBLE_CONTIGUOUS_CHAIN",
                "declared_start": start,
                "expected_start": expected,
            })
            continue

        expected_indices = list(range(start + 1, end + 1))
        actual_indices = [int(obs.get("observation_index", -1)) for obs in observations]
        if actual_indices != expected_indices:
            excluded.append({
                "revision": revision,
                "path": str(path),
                "reason": "OBSERVATION_INDEX_DISCONTINUITY",
                "actual_indices": actual_indices,
                "expected_indices": expected_indices,
            })
            continue

        chain.append((revision, path, payload))
        expected = end

    return chain, excluded, expected


def audit_holdout(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
    state_b64: Path,
    bundle_path: Path,
    annual_2026: Path,
    binding_path: Path,
) -> dict[str, Any]:
    binding = _load(binding_path)
    bundle = _load(bundle_path)
    annual_rows = list(csv.DictReader(annual_2026.open(encoding="utf-8-sig", newline="")))

    chain, excluded, physical_count = _admissible_chain(
        holdout_dir=holdout_dir,
        binding=binding,
    )

    state_cache: dict[int, Mapping[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    global_blockers: list[str] = []

    for revision, _, batch in chain:
        event_path = runtime_dir / f"MATRIX_COR0203_PROSPECTIVE_EVENTS_R{revision}.json"
        if not event_path.exists():
            global_blockers.append(f"EVENT_MANIFEST_MISSING:R{revision}")
            continue
        event_manifest = _load(event_path)
        events = {
            str(event.get("event_id") or ""): event
            for event in event_manifest.get("events", []) or []
        }

        for observation in batch.get("observations", []) or []:
            event_id = str(observation.get("event_id") or "")
            blockers: list[str] = []
            event = events.get(event_id)
            if not event_id or event_id in event_ids:
                blockers.append("DUPLICATE_OR_MISSING_ADMISSIBLE_EVENT_ID")
            event_ids.add(event_id)

            if not isinstance(event, Mapping):
                blockers.append("SOURCE_EVENT_MANIFEST_ROW_MISSING")
                rows.append({
                    "revision": revision,
                    "observation_index": observation.get("observation_index"),
                    "event_id": event_id,
                    "blockers": blockers,
                })
                continue

            target_period = int(event.get("target_period"))
            if target_period not in state_cache:
                state, _ = load_state(state_b64)
                state, _, _ = extend_state(state, annual_rows, target_period)
                state_cache[target_period] = state
            state = state_cache[target_period]

            players = list(event.get("players") or [])
            if len(players) != 2:
                blockers.append("TWO_PLAYERS_REQUIRED")
            for player in players:
                name = str(player.get("name") or "")
                for field in ("age", "rank", "rank_points"):
                    if not _finite(player.get(field)):
                        blockers.append(f"STATIC_NONFINITE:{name}:{field}")
                if str(player.get("hand") or "").upper() not in {"R", "L"}:
                    blockers.append(f"STATIC_HAND_INVALID:{name}")
                blockers.extend(f"{code}:{name}" for code in _history_blockers(state, name))

            if not blockers:
                a, b, base, eo, es, go, gs = feature_snapshot(state, event)
                if observation.get("alphabetical_player_a") != a["name"]:
                    blockers.append("PLAYER_A_ORIENTATION_MISMATCH")
                if observation.get("alphabetical_player_b") != b["name"]:
                    blockers.append("PLAYER_B_ORIENTATION_MISMATCH")

                observed_features = observation.get("features") or {}
                if set(observed_features) != set(base):
                    blockers.append("FEATURE_KEY_SET_MISMATCH")
                else:
                    for key, value in base.items():
                        if not _close(observed_features.get(key), value):
                            blockers.append("FEATURE_VALUE_MISMATCH:" + key)

                if canonical_sha(base) != observation.get("feature_snapshot_sha256"):
                    blockers.append("FEATURE_SNAPSHOT_SHA_MISMATCH")

                elo_values = {**base, "elo_overall_diff": eo, "elo_surface_diff": es}
                glicko_values = {**base, "glicko_overall_diff": go, "glicko_surface_diff": gs}
                p_elo = score_spec(bundle["elo"], elo_values)
                p_glicko = score_spec(bundle["glicko"], glicko_values)
                if not _close(observation.get("elo", {}).get("p_player_a"), p_elo):
                    blockers.append("ELO_PROBABILITY_REPRODUCTION_FAIL")
                if not _close(observation.get("glicko", {}).get("p_player_a"), p_glicko):
                    blockers.append("GLICKO_PROBABILITY_REPRODUCTION_FAIL")

            rows.append({
                "revision": revision,
                "observation_index": int(observation.get("observation_index", -1)),
                "event_id": event_id,
                "blockers": sorted(set(blockers)),
                "pass": not blockers,
            })

    blockers = sorted(set(global_blockers + [
        blocker
        for row in rows
        for blocker in row.get("blockers", [])
    ]))

    quarantined = [
        row for row in excluded if row.get("reason") != "NOT_IN_ADMISSIBLE_CONTIGUOUS_CHAIN"
        or row.get("revision") == 706
    ]

    return {
        "schema": "MATRIX_COR0203_HOLDOUT_INTEGRITY_AUDIT_V1",
        "holdout_id": binding.get("holdout_id"),
        "binding": binding.get("schema"),
        "admissible_batch_revisions": [revision for revision, _, _ in chain],
        "excluded_batches": excluded,
        "quarantined_batches": quarantined,
        "admissible_observations": physical_count,
        "audited_observations": len(rows),
        "passed_observations": sum(1 for row in rows if row["pass"]),
        "failed_observations": sum(1 for row in rows if not row["pass"]),
        "rows": rows,
        "blockers": blockers,
        "outcomes_read": 0,
        "metrics_opened": False,
        "silent_imputation_detected": bool(blockers),
        "median_or_neutral_fallback_admissible": False,
        "result": "PASS" if not blockers and len(rows) == physical_count else "FAIL",
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument("--state-b64", default="evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64")
    parser.add_argument("--bundle", default="evidence/cor0203/runtime/MATRIX_COR0203_ELO_GLICKO_PROSPECTIVE_BUNDLE_R706.json")
    parser.add_argument("--annual-2026", default="evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv")
    parser.add_argument("--binding", default="evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = audit_holdout(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
        state_b64=Path(args.state_b64),
        bundle_path=Path(args.bundle),
        annual_2026=Path(args.annual_2026),
        binding_path=Path(args.binding),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "admissible_observations": report["admissible_observations"],
        "audited_observations": report["audited_observations"],
        "passed_observations": report["passed_observations"],
        "failed_observations": report["failed_observations"],
        "admissible_batch_revisions": report["admissible_batch_revisions"],
    }, sort_keys=True))
    if report["result"] != "PASS":
        raise SystemExit("HOLDOUT_INTEGRITY_AUDIT_FAILED")


if __name__ == "__main__":
    main()
