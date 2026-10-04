from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COHORT_ID = "FOOTBALL_ALL_MARKETS_V2_20261004"
COHORT_START_UTC = "2026-10-04T18:51:32Z"
SOURCE_LEDGER = Path("evidence/api_football/prospective_calibration/ledger.jsonl")
ROOT = Path("evidence/api_football/calibration_v2/lanes")

ACTIVE_LANES = {
    "1x2": "1X2",
    "over_2_5": "OVER_2_5",
    "under_2_5": "UNDER_2_5",
    "double_chance_1x": "DOUBLE_CHANCE_1X",
    "double_chance_x2": "DOUBLE_CHANCE_X2",
}


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _canonical_sha(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _lane_payloads(row: dict[str, Any]) -> dict[str, tuple[Any, Any, str | None]]:
    probs = row.get("frozen_challenger_probabilities") or {}
    outcomes = row.get("outcomes") or {}
    out: dict[str, tuple[Any, Any, str | None]] = {}

    p1 = probs.get("1x2")
    y1 = outcomes.get("1x2")
    if isinstance(p1, dict) and y1 in {"H", "D", "A"}:
        h, d, a = float(p1["H"]), float(p1["D"]), float(p1["A"])
        out["1x2"] = ({"H": h, "D": d, "A": a}, y1, None)
        out["double_chance_1x"] = (h + d, y1 != "A", "1X2")
        out["double_chance_x2"] = (a + d, y1 != "H", "1X2")

    po = probs.get("over_2_5")
    yo = outcomes.get("over_2_5")
    if isinstance(po, (int, float)) and isinstance(yo, bool):
        p = float(po)
        out["over_2_5"] = (p, yo, None)
        out["under_2_5"] = (1.0 - p, not yo, "OVER_2_5")

    return out


def build_lane_records(
    rows: list[dict[str, Any]],
    cohort_start_utc: str = COHORT_START_UTC,
) -> dict[str, list[dict[str, Any]]]:
    start = _dt(cohort_start_utc)
    result = {slug: [] for slug in ACTIVE_LANES}

    eligible = []
    for row in rows:
        freeze = row.get("freeze_at_utc")
        kickoff = row.get("kickoff_utc")
        if not freeze or not kickoff:
            continue
        if _dt(freeze) < start:
            continue
        if _dt(freeze) >= _dt(kickoff):
            raise RuntimeError(f"NON_PREMATCH_SOURCE_FREEZE:{row.get('fixture_id')}")
        if row.get("parameters_mutated_after_freeze") is not False:
            raise RuntimeError(f"PARAMETER_MUTATION_SOURCE_ROW:{row.get('fixture_id')}")
        if row.get("used_for_parameter_tuning") is not False:
            raise RuntimeError(f"TUNING_SOURCE_ROW:{row.get('fixture_id')}")
        eligible.append(row)

    eligible.sort(key=lambda r: (r["freeze_at_utc"], str(r.get("fixture_id", ""))))

    for row in eligible:
        for slug, (probability, outcome, parent) in _lane_payloads(row).items():
            prev = result[slug][-1]["record_sha256"] if result[slug] else None
            payload = {
                "schema": "MATRIX_FOOTBALL_MARKET_CALIBRATION_V2_OBSERVATION_V1",
                "cohort_id": COHORT_ID,
                "market": ACTIVE_LANES[slug],
                "parent_market": parent,
                "fixture_id": str(row["fixture_id"]),
                "freeze_at_utc": row["freeze_at_utc"],
                "kickoff_utc": row["kickoff_utc"],
                "settled_at_utc": row.get("settled_at_utc"),
                "frozen_probability": probability,
                "outcome": outcome,
                "source_record_sha256": row.get("record_sha256"),
                "source_target_key": row.get("target_key"),
                "previous_lane_record_sha256": prev,
                "parameters_mutated_after_freeze": False,
                "used_for_parameter_tuning": False,
                "real_money": "BLOCKED",
                "automatic_wagering": False,
            }
            payload["record_sha256"] = _canonical_sha(payload)
            result[slug].append(payload)

    return result


def _read_source() -> list[dict[str, Any]]:
    if not SOURCE_LEDGER.exists():
        raise SystemExit("SOURCE_LEDGER_MISSING")
    return [
        json.loads(line)
        for line in SOURCE_LEDGER.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_lane(slug: str, rows: list[dict[str, Any]]) -> None:
    lane_dir = ROOT / slug
    lane_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = lane_dir / "ledger.jsonl"
    state_path = lane_dir / "state.json"

    old_count = 0
    if state_path.exists():
        old_count = int(json.loads(state_path.read_text(encoding="utf-8")).get("observation_count", 0))
    if len(rows) < old_count:
        raise RuntimeError(f"V2_COUNT_REGRESSION:{slug}:{old_count}->{len(rows)}")

    ledger_text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)
    ledger_path.write_text(ledger_text, encoding="utf-8")

    thresholds = {}
    for n in (30, 50, 100, 200):
        thresholds[str(n)] = (
            "READY_FOR_SEPARATE_EVALUATION_NOT_OPENED"
            if len(rows) >= n
            else f"SEALED_PENDING_{n - len(rows)}"
        )

    state = {
        "schema": "MATRIX_FOOTBALL_MARKET_CALIBRATION_V2_STATE_V1",
        "cohort_id": COHORT_ID,
        "cohort_start_utc": COHORT_START_UTC,
        "market": ACTIVE_LANES[slug],
        "status": "ACTIVE_V2",
        "observation_count": len(rows),
        "settlement_count": len(rows),
        "metrics_opened": False,
        "thresholds": thresholds,
        "pre_v2_observations_carried_forward": 0,
        "no_backfill": True,
        "parameter_tuning_allowed": False,
        "source_ledger": str(SOURCE_LEDGER),
        "source_rows_scanned": sum(1 for _ in SOURCE_LEDGER.read_text(encoding="utf-8").splitlines() if _.strip()),
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    rows = _read_source()
    lanes = build_lane_records(rows)
    for slug, lane_rows in lanes.items():
        _write_lane(slug, lane_rows)
    print(json.dumps({slug: len(v) for slug, v in lanes.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
