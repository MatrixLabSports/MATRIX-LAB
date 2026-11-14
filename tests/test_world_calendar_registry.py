from app.research.tennis.world_calendar_registry import (
    WorldCalendarEvent,
    build_world_calendar_registry,
)


SHA = "a" * 64
AS_OF = "2026-09-25T04:00:00+00:00"


def event(**overrides):
    data = dict(
        event_id="evt-1",
        sport="TENNIS",
        competition_id="challenger-x",
        competition_name="Challenger X",
        tour_level="C",
        surface="Hard",
        environment="Outdoor",
        round="R32",
        event_start_utc="2026-09-26T18:00:00+00:00",
        player1_id="player-a",
        player2_id="player-b",
        source_provider="authority",
        source_reference="schedule/1",
        source_snapshot_sha256=SHA,
    )
    data.update(overrides)
    return WorldCalendarEvent(**data)


def test_world_calendar_preserves_out_of_domain_events():
    registry = build_world_calendar_registry(
        events=[
            event(event_id="hard-challenger"),
            event(event_id="clay-challenger", surface="Clay"),
            event(event_id="atp-main-tour", tour_level="ATP"),
        ],
        as_of_utc=AS_OF,
    )
    assert registry["world_calendar_unique_events"] == 3
    assert registry["cor0203_eligible_events"] == 1
    rows = {row["event_id"]: row for row in registry["rows"]}
    assert rows["clay-challenger"]["world_calendar_status"] == "PRESERVED"
    assert "COR0203_SURFACE_OUT_OF_DOMAIN" in rows["clay-challenger"]["cor0203_blockers"]
    assert rows["atp-main-tour"]["world_calendar_status"] == "PRESERVED"
    assert "COR0203_TOUR_LEVEL_OUT_OF_DOMAIN" in rows["atp-main-tour"]["cor0203_blockers"]


def test_placeholder_identity_stays_in_world_calendar_but_not_holdout():
    registry = build_world_calendar_registry(
        events=[event(player2_id="QF1")],
        as_of_utc=AS_OF,
    )
    assert registry["world_calendar_unique_events"] == 1
    assert registry["cor0203_eligible_events"] == 0
    assert "IDENTITY_NOT_FIXED" in registry["rows"][0]["cor0203_blockers"]


def test_past_event_is_preserved_but_not_eligible():
    registry = build_world_calendar_registry(
        events=[event(event_start_utc="2026-09-24T18:00:00+00:00")],
        as_of_utc=AS_OF,
    )
    assert registry["world_calendar_unique_events"] == 1
    assert registry["cor0203_eligible_events"] == 0
    assert "EVENT_NOT_FUTURE" in registry["rows"][0]["cor0203_blockers"]


def test_duplicate_does_not_inflate_either_denominator():
    e = event()
    registry = build_world_calendar_registry(events=[e, e], as_of_utc=AS_OF)
    assert registry["world_calendar_unique_events"] == 1
    assert registry["cor0203_eligible_events"] == 1
    assert registry["duplicate_rows"] == 1
    assert registry["rows"][1]["world_calendar_status"] == "DUPLICATE_REJECTED"


def test_denominator_definitions_are_explicit_and_distinct():
    registry = build_world_calendar_registry(events=[event()], as_of_utc=AS_OF)
    assert "all unique discovered scheduled events" in registry["world_calendar_denominator_definition"]
    assert "derived subset" in registry["cor0203_denominator_definition"]
    assert registry["world_calendar_denominator_definition"] != registry["cor0203_denominator_definition"]


def test_invalid_provenance_never_enters_holdout_projection():
    registry = build_world_calendar_registry(
        events=[event(source_snapshot_sha256="bad")],
        as_of_utc=AS_OF,
    )
    assert registry["world_calendar_unique_events"] == 1
    assert registry["cor0203_eligible_events"] == 0
    assert "SOURCE_PROVENANCE_INVALID" in registry["rows"][0]["cor0203_blockers"]
