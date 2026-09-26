import pytest

from app.research.tennis.prospective_ledger import TennisProspectiveEvidenceLedger
from app.research.tennis.r251_world_pipeline import (
    BASE12_FIELDS,
    WorldTennisEvent,
    run_r251_world_pipeline,
)


SHA = "a" * 64


def world_event(**overrides):
    data = dict(
        event_id="evt-1", player1_id="p1", player2_id="p2",
        competition_id="challenger-x", competition_name="Challenger X",
        season_id="2026", round="R32", surface="Hard", environment="Outdoor",
        tour_level="C", event_start_utc="2026-09-25T18:00:00+00:00",
        source_provider="authority", source_reference="schedule/1",
        source_snapshot_sha256=SHA,
    )
    data.update(overrides)
    return WorldTennisEvent(**data)


def base12():
    return {field: (1 if field == "hand_same" else 0.1) for field in BASE12_FIELDS}


def test_preregistration_happens_before_feature_acquisition(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    observed = []

    def loader(event):
        observed.append(ledger.audit().registered_event_count)
        return base12()

    result = run_r251_world_pipeline(
        events=[world_event()], ledger=ledger,
        registered_at_utc="2026-09-24T10:00:00+00:00", feature_loader=loader,
    )
    assert observed == [1]
    assert result["base12_ready"] == 1


@pytest.mark.parametrize("change,reason", [
    ({"surface": "Clay"}, "R251_SURFACE_OUT_OF_DOMAIN"),
    ({"tour_level": "ATP"}, "R251_TOUR_LEVEL_OUT_OF_DOMAIN"),
])
def test_domain_exclusion_never_calls_features(tmp_path, change, reason):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    called = []
    result = run_r251_world_pipeline(
        events=[world_event(**change)], ledger=ledger,
        registered_at_utc="2026-09-24T10:00:00+00:00",
        feature_loader=lambda event: called.append(event) or base12(),
    )
    assert called == []
    assert reason in result["rows"][0]["blockers"]


def test_retroactive_registration_is_blocked_without_feature_call(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    called = []
    result = run_r251_world_pipeline(
        events=[world_event()], ledger=ledger,
        registered_at_utc="2026-09-25T18:00:00+00:00",
        feature_loader=lambda event: called.append(event) or base12(),
    )
    assert called == []
    assert "RETROACTIVE_PREREGISTRATION_FORBIDDEN" in result["rows"][0]["blockers"]


def test_missing_base12_blocks_publication_but_keeps_registration(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    features = base12()
    del features["age_diff"]
    result = run_r251_world_pipeline(
        events=[world_event()], ledger=ledger,
        registered_at_utc="2026-09-24T10:00:00+00:00",
        feature_loader=lambda event: features,
    )
    assert ledger.audit().registered_event_count == 1
    assert result["base12_ready"] == 0
    assert "BASE12_MISSING:age_diff" in result["rows"][0]["blockers"]


def test_duplicate_event_does_not_trigger_second_feature_acquisition(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    calls = []
    result = run_r251_world_pipeline(
        events=[world_event(), world_event()],
        ledger=ledger,
        registered_at_utc="2026-09-24T10:00:00+00:00",
        feature_loader=lambda event: calls.append(event.event_id) or base12(),
    )
    assert calls == ["evt-1"]
    assert result["blocked"] == 1
    assert result["rows"][1]["blockers"] == ("DUPLICATE_EVENT_ID",)


def test_indoor_hard_is_inside_r251_domain(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "indoor.jsonl")
    result = run_r251_world_pipeline(events=[world_event(environment="Indoor")], ledger=ledger, registered_at_utc="2026-09-24T10:00:00+00:00", feature_loader=lambda event: base12())
    assert result["domain"] == "ATP_CHALLENGER_HARD"
    assert result["base12_ready"] == 1
