from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, Sequence

from app.research.tennis.prospective_ledger import (
    TennisCanonicalEvent,
    TennisProspectiveEvidenceLedger,
)

UTC = timezone.utc
BASE12_FIELDS = (
    "rank_diff", "rank_points_diff", "age_diff", "hand_same",
    "form5_diff", "form10_diff", "form20_diff", "surface_wr_diff",
    "overall_wr_diff", "serve_pts_won_diff", "return_pts_won_diff",
    "prior_opponent_strength_diff",
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(UTC)


def _sha(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class WorldTennisEvent:
    event_id: str
    player1_id: str
    player2_id: str
    competition_id: str
    competition_name: str
    season_id: str
    round: str
    surface: str
    environment: str
    tour_level: str
    event_start_utc: str
    source_provider: str
    source_reference: str
    source_snapshot_sha256: str


def r251_domain_blockers(event: WorldTennisEvent) -> tuple[str, ...]:
    blockers: list[str] = []
    if event.tour_level.strip().upper() not in {"C", "ATP_CHALLENGER", "CHALLENGER"}:
        blockers.append("R251_TOUR_LEVEL_OUT_OF_DOMAIN")
    if event.surface.strip().upper() != "HARD":
        blockers.append("R251_SURFACE_OUT_OF_DOMAIN")
    if not event.player1_id.strip() or not event.player2_id.strip() or event.player1_id == event.player2_id:
        blockers.append("IDENTITY_NOT_FIXED")
    try:
        _utc(event.event_start_utc)
    except (TypeError, ValueError):
        blockers.append("START_AUTHORITY_INVALID")
    if len(event.source_snapshot_sha256) != 64:
        blockers.append("SOURCE_PROVENANCE_INVALID")
    return tuple(sorted(set(blockers)))


def canonicalize_for_preregistration(event: WorldTennisEvent, registered_at_utc: str) -> TennisCanonicalEvent:
    blockers = r251_domain_blockers(event)
    if blockers:
        raise ValueError("EVENT_NOT_R251_ELIGIBLE:" + ",".join(blockers))
    registered = _utc(registered_at_utc)
    start = _utc(event.event_start_utc)
    if registered >= start:
        raise ValueError("RETROACTIVE_PREREGISTRATION_FORBIDDEN")
    identity = {
        "event_id": event.event_id,
        "player1_id": event.player1_id,
        "player2_id": event.player2_id,
        "competition_id": event.competition_id,
        "season_id": event.season_id,
        "round": event.round,
        "surface": "hard",
        "event_start_utc": start.isoformat(),
        "source_provider": event.source_provider,
        "source_reference": event.source_reference,
        "source_snapshot_sha256": event.source_snapshot_sha256.lower(),
    }
    return TennisCanonicalEvent(
        event_id=event.event_id,
        player1_id=event.player1_id,
        player2_id=event.player2_id,
        competition_id=event.competition_id,
        season_id=event.season_id,
        round=event.round,
        surface="hard",
        event_start_utc=start.isoformat(),
        registered_at_utc=registered.isoformat(),
        source_provider=event.source_provider,
        source_reference=event.source_reference,
        canonical_event_sha256=_sha(identity),
    )


def validate_base12(features: Mapping[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    for field in BASE12_FIELDS:
        value = features.get(field)
        if isinstance(value, bool):
            if field != "hand_same":
                blockers.append("BASE12_NON_NUMERIC:" + field)
            continue
        if not isinstance(value, (int, float)):
            blockers.append("BASE12_MISSING:" + field)
            continue
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            blockers.append("BASE12_NON_FINITE:" + field)
    return tuple(blockers)


def run_r251_world_pipeline(
    *,
    events: Sequence[WorldTennisEvent],
    ledger: TennisProspectiveEvidenceLedger,
    registered_at_utc: str,
    feature_loader: Callable[[WorldTennisEvent], Mapping[str, Any]],
) -> Mapping[str, Any]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.event_id in seen:
            rows.append({"event_id": event.event_id, "status": "BLOCKED", "blockers": ("DUPLICATE_EVENT_ID",)})
            continue
        seen.add(event.event_id)
        domain_blockers = r251_domain_blockers(event)
        if domain_blockers:
            rows.append({"event_id": event.event_id, "status": "BLOCKED", "blockers": domain_blockers})
            continue

        # Ordering invariant: physical ledger registration MUST happen before feature acquisition.
        try:
            canonical = canonicalize_for_preregistration(event, registered_at_utc)
            ledger.register_event(canonical)
        except ValueError as error:
            rows.append({"event_id": event.event_id, "status": "BLOCKED", "blockers": (str(error),)})
            continue

        features = feature_loader(event)
        feature_blockers = validate_base12(features)
        if feature_blockers:
            rows.append({"event_id": event.event_id, "status": "BLOCKED", "blockers": feature_blockers})
            continue
        rows.append({
            "event_id": event.event_id,
            "status": "BASE12_READY",
            "base12_observed": 12,
            "feature_snapshot_sha256": _sha({key: features[key] for key in BASE12_FIELDS}),
        })

    return {
        "schema": "matrix.r251-world-prospective-pipeline/1",
        "domain": "ATP_CHALLENGER_HARD",
        "discovered": len(events),
        "unique_event_ids": len(seen),
        "registered": sum(1 for row in rows if row["status"] == "BASE12_READY"),
        "base12_ready": sum(1 for row in rows if row["status"] == "BASE12_READY"),
        "blocked": sum(1 for row in rows if row["status"] == "BLOCKED"),
        "rows": rows,
        "automatic_wagering": False,
    }
