from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

UTC = timezone.utc

CHALLENGER_LEVELS = {"C", "ATP_CHALLENGER", "CHALLENGER"}
PLACEHOLDER_TOKENS = {
    "", "TBD", "TBA", "Q", "Q1", "Q2", "Q3", "Q4",
    "QUALIFIER", "LUCKY_LOSER", "LL", "WINNER", "LOSER",
}


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(UTC)


def _identity_is_real(value: str) -> bool:
    token = str(value or "").strip().upper()
    if token in PLACEHOLDER_TOKENS:
        return False
    if token.startswith("WINNER OF ") or token.startswith("LOSER OF "):
        return False
    if token.startswith("QF") or token.startswith("SF"):
        return False
    return True


@dataclass(frozen=True)
class WorldCalendarEvent:
    event_id: str
    sport: str
    competition_id: str
    competition_name: str
    tour_level: str
    surface: str
    environment: str
    round: str
    event_start_utc: str
    player1_id: str
    player2_id: str
    source_provider: str
    source_reference: str
    source_snapshot_sha256: str


def cor0203_blockers(event: WorldCalendarEvent, *, as_of_utc: str) -> tuple[str, ...]:
    blockers: list[str] = []

    if str(event.sport).strip().upper() != "TENNIS":
        blockers.append("COR0203_SPORT_OUT_OF_DOMAIN")
    if str(event.tour_level).strip().upper() not in CHALLENGER_LEVELS:
        blockers.append("COR0203_TOUR_LEVEL_OUT_OF_DOMAIN")
    if str(event.surface).strip().upper() != "HARD":
        blockers.append("COR0203_SURFACE_OUT_OF_DOMAIN")

    p1 = str(event.player1_id or "").strip()
    p2 = str(event.player2_id or "").strip()
    if not _identity_is_real(p1) or not _identity_is_real(p2) or p1 == p2:
        blockers.append("IDENTITY_NOT_FIXED")

    try:
        start = _utc(event.event_start_utc)
        as_of = _utc(as_of_utc)
        if start <= as_of:
            blockers.append("EVENT_NOT_FUTURE")
    except (TypeError, ValueError):
        blockers.append("START_AUTHORITY_INVALID")

    sha = str(event.source_snapshot_sha256 or "").strip().lower()
    if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
        blockers.append("SOURCE_PROVENANCE_INVALID")

    return tuple(sorted(set(blockers)))


def build_world_calendar_registry(
    *,
    events: Iterable[WorldCalendarEvent],
    as_of_utc: str,
) -> dict:
    """
    Preserve the world-discovery universe first. COR02/COR03 eligibility is a
    derived projection and MUST NOT redefine the world-calendar denominator.
    """
    _utc(as_of_utc)

    rows: list[dict] = []
    seen: set[str] = set()
    duplicate_rows = 0
    eligible_ids: list[str] = []

    for event in events:
        row = asdict(event)

        if event.event_id in seen:
            duplicate_rows += 1
            row.update({
                "world_calendar_status": "DUPLICATE_REJECTED",
                "cor0203_eligible": False,
                "cor0203_blockers": ["DUPLICATE_EVENT_ID"],
            })
            rows.append(row)
            continue

        seen.add(event.event_id)
        blockers = cor0203_blockers(event, as_of_utc=as_of_utc)
        eligible = not blockers
        if eligible:
            eligible_ids.append(event.event_id)

        row.update({
            "world_calendar_status": "PRESERVED",
            "cor0203_eligible": eligible,
            "cor0203_blockers": list(blockers),
        })
        rows.append(row)

    return {
        "schema": "matrix.world-calendar-registry/1",
        "as_of_utc": _utc(as_of_utc).isoformat(),
        "world_calendar_denominator_definition": (
            "all unique discovered scheduled events preserved before model-domain filtering"
        ),
        "cor0203_denominator_definition": (
            "derived subset: future ATP Challenger Hard events with two real fixed identities "
            "and valid source provenance"
        ),
        "world_calendar_unique_events": len(seen),
        "world_calendar_input_rows": len(rows),
        "duplicate_rows": duplicate_rows,
        "cor0203_eligible_events": len(eligible_ids),
        "cor0203_eligible_event_ids": eligible_ids,
        "rows": rows,
    }
