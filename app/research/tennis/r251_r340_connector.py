from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from app.research.tennis.r251_world_pipeline import (
    BASE12_FIELDS,
    WorldTennisEvent,
    run_r251_world_pipeline,
)


@dataclass(frozen=True)
class Static4Snapshot:
    rank: float
    rank_points: float
    age: float
    hand: str
    available_at_utc: str
    source_sha256: str


HIST8_FIELDS = BASE12_FIELDS[4:]


def assemble_base12(
    *,
    player1: Static4Snapshot,
    player2: Static4Snapshot,
    hist8: Mapping[str, Any],
) -> dict[str, float]:
    p1_hand = player1.hand.strip().upper()
    p2_hand = player2.hand.strip().upper()
    if p1_hand not in {"R", "L"} or p2_hand not in {"R", "L"}:
        raise ValueError("STATIC4_HAND_INVALID")
    for snap in (player1, player2):
        if len(snap.source_sha256) != 64:
            raise ValueError("STATIC4_PROVENANCE_INVALID")
    row: dict[str, float] = {
        "rank_diff": float(player2.rank) - float(player1.rank),
        "rank_points_diff": float(player1.rank_points) - float(player2.rank_points),
        "age_diff": float(player1.age) - float(player2.age),
        "hand_same": float(p1_hand == p2_hand),
    }
    for field in HIST8_FIELDS:
        if field not in hist8:
            raise ValueError("R340_HIST8_MISSING:" + field)
        row[field] = float(hist8[field])
    return row


def run_world_to_r251(
    *,
    events: Sequence[WorldTennisEvent],
    ledger,
    registered_at_utc: str,
    static4_loader: Callable[[WorldTennisEvent], tuple[Static4Snapshot, Static4Snapshot]],
    r340_hist8_loader: Callable[[WorldTennisEvent], Mapping[str, Any]],
    r251_scorer: Callable[[WorldTennisEvent, Mapping[str, float]], Mapping[str, Any]],
) -> Mapping[str, Any]:
    scored: dict[str, Mapping[str, Any]] = {}

    def feature_loader(event: WorldTennisEvent) -> Mapping[str, Any]:
        p1, p2 = static4_loader(event)
        hist8 = r340_hist8_loader(event)
        row = assemble_base12(player1=p1, player2=p2, hist8=hist8)
        # R251 is called only after the R348 complete-case gate in the outer pipeline.
        return row

    base = run_r251_world_pipeline(
        events=events,
        ledger=ledger,
        registered_at_utc=registered_at_utc,
        feature_loader=feature_loader,
    )

    rows = []
    by_id = {event.event_id: event for event in events}
    for item in base["rows"]:
        out = dict(item)
        if item["status"] == "BASE12_READY":
            event = by_id[item["event_id"]]
            p1, p2 = static4_loader(event)
            hist8 = r340_hist8_loader(event)
            features = assemble_base12(player1=p1, player2=p2, hist8=hist8)
            result = dict(r251_scorer(event, features))
            if "p_matrix" not in result:
                raise ValueError("R251_SCORER_P_MATRIX_REQUIRED")
            probability = float(result["p_matrix"])
            if not 0.0 <= probability <= 1.0:
                raise ValueError("R251_PROBABILITY_OUT_OF_RANGE")
            if any("odd" in str(key).lower() for key in result):
                raise ValueError("ODDS_TO_P_MATRIX_BOUNDARY_VIOLATION")
            scored[event.event_id] = result
            out["status"] = "R251_SCORED_READY_FOR_FREEZE"
            out["p_matrix"] = probability
        rows.append(out)

    return {
        **base,
        "rows": rows,
        "r251_scored": len(scored),
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
