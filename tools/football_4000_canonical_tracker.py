from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("evidence/api_football")
TARGET = 4000
OUT = ROOT / "governance" / "MATRIX_FOOTBALL_4000_CANONICAL_TRACKER_LAST.json"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return value


def main() -> None:
    manifest = load(ROOT / "prospective_market_freeze" / "manifest.json")
    settlement = load(ROOT / "prospective_market_freeze" / "settlement_sync_last.json")
    calibration = load(ROOT / "prospective_calibration" / "sync_last.json")

    lanes = {}
    for slug in ("over_2_5", "under_2_5", "1x2"):
        state = load(ROOT / "calibration_v2" / "lanes" / slug / "state.json")
        lanes[slug] = {
            "cohort_id": state.get("cohort_id"),
            "cohort_start_utc": state.get("cohort_start_utc"),
            "cohort_settlement_count": int(state.get("settlement_count") or 0),
            "cohort_freeze_count": int(state.get("freeze_observation_count") or 0),
            "scope": "PARTIAL_V2_COHORT_NOT_GLOBAL_TARGET_COUNTER",
        }

    frozen = int(settlement.get("frozen_event_count") or manifest.get("frozen_event_count") or 0)
    settled = int(settlement.get("ledger_final_count") or 0)
    pending = settlement.get("pending") or []
    blocked = settlement.get("blocked") or []

    pending_reasons = Counter(str(x.get("reason") or "UNSPECIFIED") for x in pending)
    blocked_reasons = Counter(str(x.get("reason") or "UNSPECIFIED") for x in blocked)

    calibration_count = int(calibration.get("calibration_observation_count") or 0)
    if calibration_count != settled:
        raise RuntimeError(f"GLOBAL_SETTLEMENT_CALIBRATION_MISMATCH:{settled}!={calibration_count}")
    if frozen != settled + len(pending) + len(blocked):
        raise RuntimeError(
            f"GLOBAL_RECONCILIATION_FAILED:{frozen}!={settled}+{len(pending)}+{len(blocked)}"
        )
    for slug, state in lanes.items():
        if state["cohort_settlement_count"] > settled:
            raise RuntimeError(f"V2_COHORT_EXCEEDS_GLOBAL:{slug}")

    remaining_closures = max(0, TARGET - settled)
    inventory_shortfall = max(0, TARGET - frozen)
    resolvable_inventory = len(pending) + len(blocked)

    out = {
        "schema": "MATRIX_FOOTBALL_4000_CANONICAL_TRACKER_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_scope": "GLOBAL_APPEND_ONLY_PROSPECTIVE_FINAL_CALIBRATION",
        "target_valid_final_observations": TARGET,
        "global": {
            "frozen_event_count": frozen,
            "valid_final_settlement_count": settled,
            "calibration_observation_count": calibration_count,
            "pending_count": len(pending),
            "blocked_count": len(blocked),
            "remaining_valid_finals_to_target": remaining_closures,
            "new_frozen_events_still_required_even_if_all_current_inventory_resolves": inventory_shortfall,
            "current_inventory_unresolved_total": resolvable_inventory,
            "reconciliation_equation": f"{settled}+{len(pending)}+{len(blocked)}={frozen}",
        },
        "pending_reason_counts": dict(sorted(pending_reasons.items())),
        "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
        "v2_lane_counters": lanes,
        "counter_precedence": {
            "target_4000": "global.valid_final_settlement_count",
            "never_use_for_global_4000": "v2_lane_counters.*.cohort_settlement_count",
            "reason": "V2 lanes start at a later cohort cut and are intentionally partial.",
        },
        "governance": {
            "settlement_final_only": bool(settlement.get("settlement_final_only")),
            "automatic_wagering": False,
            "real_money": "BLOCKED",
            "no_backfill": True,
            "missing_not_zero": True,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out["global"], sort_keys=True))


if __name__ == "__main__":
    main()
