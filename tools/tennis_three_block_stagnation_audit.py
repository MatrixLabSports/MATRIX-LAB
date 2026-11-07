from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("evidence")
HARD_RUNTIME = ROOT / "cor0203" / "runtime"
CLAY_RUNTIME = ROOT / "tennis_parallel_lanes" / "ATP_CHALLENGER_MEN_SINGLES_CLAY" / "runtime"
LIVE_ROOT = ROOT / "live_tennis_lab"
OUT = ROOT / "tennis" / "MATRIX_TENNIS_THREE_BLOCK_STAGNATION_AUDIT_LAST.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_reason(reason: str) -> tuple[str, str, list[str]]:
    r = reason.upper()
    if "ALREADY_FROZEN" in r or "DUPLICATE" in r:
        return ("DUPLICATE_OR_ALREADY_FROZEN", "NOT_RECOVERABLE_AS_NEW_OBSERVATION", [])
    if "IDENTITY" in r or "CROSSWALK" in r or "PLAYER_NOT_FOUND" in r:
        return ("IDENTITY", "RECOVERABLE_IF_PREMATCH_AND_EVIDENCE_EXISTS", ["SofaScore", "Flashscore", "RapidAPI Tennis", "governed identity authority"])
    if "ELO" in r or "GLICKO" in r or "SURFACE_HISTORY" in r or "HISTORY" in r or "PIT" in r or "CATCHUP" in r:
        return ("PIT_OR_SURFACE_HISTORY", "RECOVERABLE_ONLY_WITH_CAUSAL_PREMATCH_HISTORY", ["SofaScore", "Flashscore", "RapidAPI Tennis", "sealed historical sources"])
    if "RANKING" in r:
        return ("RANKING_CUT", "RECOVERABLE_ONLY_IF_PRE_CUT_SOURCE_EXISTS", ["SofaScore", "Flashscore", "RapidAPI Tennis", "sealed ranking cut"])
    if "POST_START" in r or "KICKOFF" in r:
        return ("TIMING", "NOT_RECOVERABLE_NO_BACKFILL", [])
    if "SURFACE_MISMATCH" in r:
        return ("SURFACE", "NOT_ELIGIBLE_FOR_LANE", [])
    if "PREFEATURE_EVENT_MISSING" in r:
        return ("DISCOVERY_BINDING", "RECOVERABLE_WHILE_PREMATCH", ["SofaScore", "Flashscore", "RapidAPI Tennis"])
    return ("OTHER", "REVIEW_REQUIRED", ["SofaScore", "Flashscore", "RapidAPI Tennis"])


def hard_block() -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    recoverability: Counter[str] = Counter()
    records = 0
    revisions = 0
    for p in sorted(HARD_RUNTIME.glob("MATRIX_COR0203_BATCH_PREFLIGHT_R*.json")):
        try:
            j = load(p)
        except Exception:
            continue
        revisions += 1
        for row in j.get("blocked") or []:
            records += 1
            blockers = row.get("blockers") or ["UNSPECIFIED_BLOCKER"]
            for reason in blockers:
                reason = str(reason)
                reason_counts[reason] += 1
                cat, rec, _ = classify_reason(reason)
                category_counts[cat] += 1
                recoverability[rec] += 1

    unique = load(HARD_RUNTIME / "MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json")
    batch = load(HARD_RUNTIME / "MATRIX_COR0203_BATCH_RUNNER_LAST.json")
    prereg = load(HARD_RUNTIME / "MATRIX_COR0203_DISCOVERY_PREREG_LAST.json")
    return {
        "current_counter": int(unique.get("unique_calibration_observations") or 0),
        "target": 600,
        "remaining": int(unique.get("unique_remaining_to_600") or 0),
        "physical_frozen_rows": int(unique.get("physical_frozen_rows") or 0),
        "duplicates_quarantined": int(unique.get("duplicate_observations_quarantined") or 0),
        "latest_batch_new_freezes": int(batch.get("new_freezes") or 0),
        "latest_batch_new_blocked": int(batch.get("new_blocked") or 0),
        "latest_prereg_status": prereg.get("status"),
        "preflight_revisions_scanned": revisions,
        "blocked_event_records_scanned": records,
        "blocker_occurrences_by_reason": dict(reason_counts.most_common()),
        "blocker_occurrences_by_category": dict(category_counts.most_common()),
        "recoverability_counts": dict(recoverability.most_common()),
        "bottleneck": "CONVERSION_AFTER_DISCOVERY",
    }


def clay_block() -> dict[str, Any]:
    producer = load(CLAY_RUNTIME / "MATRIX_CLAY_PROSPECTIVE_PRODUCER_LAST.json")
    catchup = load(CLAY_RUNTIME / "MATRIX_CLAY_ELO_PIT_CATCHUP_LAST.json")
    cross = load(CLAY_RUNTIME / "MATRIX_CLAY_IDENTITY_CROSSWALK_SUMMARY_LAST.json")
    reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    recoverability: Counter[str] = Counter()
    player_blockers: Counter[str] = Counter()

    for row in producer.get("blocked") or []:
        main_reason = str(row.get("reason") or "UNSPECIFIED")
        reason_counts[main_reason] += 1
        cat, rec, _ = classify_reason(main_reason)
        category_counts[cat] += 1
        recoverability[rec] += 1
        for b in row.get("blockers") or []:
            b = str(b)
            reason_counts[b.split(":",1)[0]] += 1
            cat, rec, _ = classify_reason(b)
            category_counts[cat] += 1
            recoverability[rec] += 1
            if ":" in b:
                player_blockers[b.split(":",1)[1]] += 1

    cross_passed = sum(int(x.get("passed_events") or 0) for x in cross.get("crosswalk_revisions") or [])
    cross_blocked = sum(int(x.get("blocked_events") or 0) for x in cross.get("crosswalk_revisions") or [])
    ending = int(producer.get("ending_observation_count") or 0)
    return {
        "current_counter": ending,
        "target": 600,
        "remaining": max(0, 600-ending),
        "new_observations_latest": int(producer.get("new_observations") or 0),
        "blocked_events_latest": len(producer.get("blocked") or []),
        "pit_ready_targets": int(catchup.get("ready_targets") or 0),
        "pit_blocked_targets": int(catchup.get("blocked_targets") or 0),
        "catchup_standard_clay_matches": int(catchup.get("catchup_standard_clay_matches") or 0),
        "provider_network_calls": int(catchup.get("provider_network_calls") or 0),
        "crosswalk_passed_events_all_revisions": cross_passed,
        "crosswalk_blocked_events_all_revisions": cross_blocked,
        "blocker_occurrences_by_reason": dict(reason_counts.most_common()),
        "blocker_occurrences_by_category": dict(category_counts.most_common()),
        "recoverability_counts": dict(recoverability.most_common()),
        "unique_provider_player_ids_blocked_latest": len(player_blockers),
        "bottleneck": "PIT_CAUSAL_HISTORY_AND_IDENTITY_CLOSURE",
    }


def live_block() -> dict[str, Any]:
    gate = load(LIVE_ROOT / "MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json")
    lanes = gate.get("lanes") or {}
    focus = lanes.get("itf|women|hard") or {}
    if not focus:
        # Preserve visibility if the canonical focus lane name changes.
        candidates = [(k,v) for k,v in lanes.items() if "women" in k and "hard" in k]
        focus_name, focus = max(candidates, key=lambda kv: int(kv[1].get("settled_quality_valid_unique_match_count") or 0), default=("itf|women|hard", {}))
    else:
        focus_name = "itf|women|hard"
    usable = int(focus.get("settled_quality_valid_unique_match_count") or 0)
    g50 = (focus.get("gates") or {}).get("50") or {}
    excluded = int(focus.get("excluded_settled_without_quality_valid_state") or 0)
    return {
        "focus_lane": focus_name,
        "current_counter": usable,
        "target_gate": 50,
        "remaining_to_50": int(g50.get("remaining") if g50.get("remaining") is not None else max(0,50-usable)),
        "gate_50_status": g50.get("status"),
        "excluded_settled_without_quality_valid_state": excluded,
        "global_unique_match_count": int(gate.get("global_unique_match_count") or 0),
        "bottleneck": "LIVE_PROVIDER_COVERAGE_AND_QUALITY_VALID_STATE_CAPTURE",
        "recovery_sources": ["RapidAPI Tennis live-capable endpoints if governed", "existing governed live provider", "new provider only after equivalence/identity validation"],
        "api_tennis_status": "RETIRED_COST_UTILITY_DECISION",
    }


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    hard = hard_block()
    clay = clay_block()
    live = live_block()
    out = {
        "schema": "MATRIX_TENNIS_THREE_BLOCK_STAGNATION_AUDIT_V1",
        "generated_at_utc": now,
        "source_order": ["SofaScore", "Flashscore", "RapidAPI Tennis", "governed historical sources"],
        "blocks": {"hard": hard, "clay": clay, "live": live},
        "diagnosis": {
            "primary_systemic_cause": "DISCOVERY_VOLUME_IS_NOT_THE_MAIN_LIMIT; ADMISSION_CONVERSION_IS",
            "hard": hard["bottleneck"],
            "clay": clay["bottleneck"],
            "live": live["bottleneck"],
        },
        "permanent_rules": {
            "missing_not_zero": True,
            "silent_imputation": False,
            "historical_backfill_into_holdout": False,
            "odds_to_probability": False,
            "post_event_outcome_to_prematch_probability": False,
            "metrics_remain_sealed_until_gate": True,
            "real_money": "BLOCKED",
        },
        "automatic_recovery_policy": {
            "identity": "SEARCH_SOFASCORE_FLASHSCORE_RAPIDAPI_THEN_GOVERNED_IDENTITY_AUTHORITY",
            "pit_or_surface_history": "ONLY_PRE_EVENT_CAUSAL_HISTORY_CAN_RECOVER",
            "ranking": "ONLY_PRE_CUT_RANKING_SOURCE_CAN_RECOVER",
            "duplicates": "NEVER_COUNT_AS_NEW",
            "timing": "NEVER_BACKFILL_AFTER_START",
            "live_provider": "USE_ONLY_GOVERNED_PROVIDER_OR_PROVEN_EQUIVALENT_FAILOVER",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({
        "hard": {"counter":hard["current_counter"],"remaining":hard["remaining"],"categories":hard["blocker_occurrences_by_category"]},
        "clay": {"counter":clay["current_counter"],"remaining":clay["remaining"],"categories":clay["blocker_occurrences_by_category"]},
        "live": {"counter":live["current_counter"],"remaining_to_50":live["remaining_to_50"]},
        "real_money":"BLOCKED"
    }, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
