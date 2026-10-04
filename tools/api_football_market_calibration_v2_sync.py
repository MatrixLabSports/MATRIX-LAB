from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COHORT_ID = "FOOTBALL_ALL_MARKETS_V2_20261004"
COHORT_START_UTC = "2026-10-04T18:51:32Z"
SOURCE_LEDGER = Path("evidence/api_football/prospective_calibration/ledger.jsonl")
SOURCE_FREEZE = Path("evidence/api_football/prospective_market_freeze/freeze.json")
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


def _freeze_lane_payloads(row: dict[str, Any]) -> dict[str, tuple[Any, str | None]]:
    probs = row.get("frozen_research_probabilities") or {}
    out: dict[str, tuple[Any, str | None]] = {}

    p1 = probs.get("1x2")
    if isinstance(p1, dict):
        h, d, a = float(p1["H"]), float(p1["D"]), float(p1["A"])
        out["1x2"] = ({"H": h, "D": d, "A": a}, None)
        out["double_chance_1x"] = (h + d, "1X2")
        out["double_chance_x2"] = (a + d, "1X2")

    po = probs.get("over_2_5")
    if isinstance(po, (int, float)):
        p = float(po)
        out["over_2_5"] = (p, None)
        out["under_2_5"] = (1.0 - p, "OVER_2_5")

    return out


def build_lane_freeze_records(
    rows: list[dict[str, Any]],
    cohort_start_utc: str = COHORT_START_UTC,
) -> dict[str, list[dict[str, Any]]]:
    start = _dt(cohort_start_utc)
    result = {slug: [] for slug in ACTIVE_LANES}
    seen_fixture_ids: set[str] = set()

    eligible = []
    for row in rows:
        freeze = row.get("freeze_at_utc")
        kickoff = row.get("kickoff_utc")
        if not freeze or not kickoff:
            continue
        if _dt(freeze) < start:
            continue
        if _dt(freeze) >= _dt(kickoff):
            raise RuntimeError(f"NON_PREMATCH_FREEZE_SOURCE_ROW:{row.get('fixture_id')}")
        if row.get("outcome") is not None:
            raise RuntimeError(f"FREEZE_SOURCE_OUTCOME_NOT_NULL:{row.get('fixture_id')}")
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id:
            raise RuntimeError("FREEZE_SOURCE_FIXTURE_ID_MISSING")
        if fixture_id in seen_fixture_ids:
            raise RuntimeError(f"FREEZE_SOURCE_DUPLICATE_FIXTURE:{fixture_id}")
        seen_fixture_ids.add(fixture_id)
        eligible.append(row)

    eligible.sort(key=lambda r: (r["freeze_at_utc"], str(r.get("fixture_id", ""))))

    for row in eligible:
        for slug, (probability, parent) in _freeze_lane_payloads(row).items():
            prev = result[slug][-1]["record_sha256"] if result[slug] else None
            payload = {
                "schema": "MATRIX_FOOTBALL_MARKET_CALIBRATION_V2_FREEZE_V1",
                "cohort_id": COHORT_ID,
                "market": ACTIVE_LANES[slug],
                "parent_market": parent,
                "fixture_id": str(row["fixture_id"]),
                "freeze_at_utc": row["freeze_at_utc"],
                "kickoff_utc": row["kickoff_utc"],
                "frozen_probability": probability,
                "outcome": None,
                "settlement_status": "PENDING_FINAL",
                "source_input_sha256": row.get("input_sha256"),
                "source_target_key": row.get("target_key"),
                "previous_lane_record_sha256": prev,
                "real_money": "BLOCKED",
                "automatic_wagering": False,
            }
            payload["record_sha256"] = _canonical_sha(payload)
            result[slug].append(payload)

    return result


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


def _read_freeze_source() -> list[dict[str, Any]]:
    if not SOURCE_FREEZE.exists():
        raise SystemExit("SOURCE_FREEZE_MISSING")
    payload = json.loads(SOURCE_FREEZE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise RuntimeError("SOURCE_FREEZE_ROWS_INVALID")
    protections = payload.get("protections") or {}
    required = {
        "future_only": True,
        "unseen_events_only": True,
        "outcomes_read_at_freeze": False,
        "odds_used_to_generate_probability": False,
        "p_matrix_generated": False,
        "automatic_wagering": False,
    }
    for key, expected in required.items():
        if protections.get(key) is not expected:
            raise RuntimeError(f"SOURCE_FREEZE_PROTECTION_FAILED:{key}")
    if protections.get("real_money") != "BLOCKED":
        raise RuntimeError("SOURCE_FREEZE_REAL_MONEY_NOT_BLOCKED")
    return payload["rows"]


def _write_lane(slug: str, rows: list[dict[str, Any]], frozen_rows: list[dict[str, Any]]) -> None:
    lane_dir = ROOT / slug
    lane_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = lane_dir / "ledger.jsonl"
    state_path = lane_dir / "state.json"

    old_count = 0
    old_freeze_count = 0
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        old_count = int(previous.get("observation_count", 0))
        old_freeze_count = int(previous.get("freeze_observation_count", 0))
    if len(rows) < old_count:
        raise RuntimeError(f"V2_COUNT_REGRESSION:{slug}:{old_count}->{len(rows)}")
    if len(frozen_rows) < old_freeze_count:
        raise RuntimeError(f"V2_FREEZE_COUNT_REGRESSION:{slug}:{old_freeze_count}->{len(frozen_rows)}")

    settled_ids = {str(r["fixture_id"]) for r in rows}
    frozen_ids = {str(r["fixture_id"]) for r in frozen_rows}
    if not settled_ids.issubset(frozen_ids):
        raise RuntimeError(f"V2_SETTLEMENT_OUTSIDE_FREEZE:{slug}")

    ledger_text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)
    ledger_path.write_text(ledger_text, encoding="utf-8")
    freeze_ledger_path = lane_dir / "freeze_ledger.jsonl"
    freeze_ledger_text = "".join(
        json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in frozen_rows
    )
    freeze_ledger_path.write_text(freeze_ledger_text, encoding="utf-8")

    thresholds = {}
    for n in (30, 50, 100, 200):
        thresholds[str(n)] = (
            "READY_FOR_SEPARATE_EVALUATION_NOT_OPENED"
            if len(rows) >= n
            else f"SEALED_PENDING_{n - len(rows)}"
        )

    frozen_thresholds = {}
    for n in (30, 50, 100, 200):
        if len(rows) >= n:
            frozen_thresholds[str(n)] = "SETTLED_THRESHOLD_REACHED"
        elif len(frozen_rows) >= n:
            frozen_thresholds[str(n)] = "SECURED_PENDING_FINAL"
        else:
            frozen_thresholds[str(n)] = f"NOT_YET_SECURED_{n - len(frozen_rows)}"

    state = {
        "schema": "MATRIX_FOOTBALL_MARKET_CALIBRATION_V2_STATE_V1",
        "cohort_id": COHORT_ID,
        "cohort_start_utc": COHORT_START_UTC,
        "market": ACTIVE_LANES[slug],
        "status": "ACTIVE_V2",
        "freeze_observation_count": len(frozen_rows),
        "pending_settlement_count": len(frozen_rows) - len(rows),
        "observation_count": len(rows),
        "settlement_count": len(rows),
        "metrics_opened": False,
        "thresholds": thresholds,
        "frozen_thresholds": frozen_thresholds,
        "pre_v2_observations_carried_forward": 0,
        "no_backfill": True,
        "parameter_tuning_allowed": False,
        "source_ledger": str(SOURCE_LEDGER),
        "source_freeze": str(SOURCE_FREEZE),
        "source_rows_scanned": sum(1 for _ in SOURCE_LEDGER.read_text(encoding="utf-8").splitlines() if _.strip()),
        "source_freeze_rows_scanned": len(_read_freeze_source()),
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    rows = _read_source()
    freeze_rows = _read_freeze_source()
    lanes = build_lane_records(rows)
    freeze_lanes = build_lane_freeze_records(freeze_rows)
    for slug, lane_rows in lanes.items():
        _write_lane(slug, lane_rows, freeze_lanes[slug])
    print(json.dumps({
        slug: {
            "settled": len(lanes[slug]),
            "frozen": len(freeze_lanes[slug]),
            "pending_final": len(freeze_lanes[slug]) - len(lanes[slug]),
        }
        for slug in ACTIVE_LANES
    }, sort_keys=True))


if __name__ == "__main__":
    main()
