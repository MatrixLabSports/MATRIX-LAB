from app.sports.football.contract import FootballMatchContract
from app.sports.football.external_identity import ExternalMatchIdentity
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.match_record import FootballMatchRecord
from app.sports.football.sync_state import FootballSyncState


def test_football_match_record_can_be_created():
    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    contract = FootballMatchContract(
        home_team="Western United II",
        away_team="Langwarrin",
        competition="Victoria NPL 2",
        country="Australia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Regular Season - 24",
        datetime="2026-08-16T04:00:00+00:00",
        status="awarded",
    )

    record = FootballMatchRecord(
        identity=identity,
        match=match,
    )

    assert record.identity == identity
    assert record.match == match

def test_football_match_record_can_update_match_state_with_same_identity():
    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    scheduled_match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )

    finished_match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="finished",
    )

    first_record = FootballMatchRecord(
        identity=identity,
        match=scheduled_match,
    )

    updated_record = FootballMatchRecord(
        identity=identity,
        match=finished_match,
    )

    assert first_record.identity == updated_record.identity
    assert first_record.match.status == "scheduled"
    assert updated_record.match.status == "finished"


def test_football_match_record_defaults_to_seen_current_sync():
    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    contract = FootballMatchContract(
        home_team="Western United II",
        away_team="Langwarrin",
        competition="Victoria NPL 2",
        country="Australia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Regular Season - 24",
        datetime="2026-08-16T04:00:00+00:00",
        status="awarded",
    )

    record = FootballMatchRecord(
        identity=identity,
        match=match,
    )

    assert record.sync_state == FootballSyncState(
        status="seen_current_sync",
    )


def test_football_match_record_accepts_explicit_sync_state():
    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    contract = FootballMatchContract(
        home_team="Western United II",
        away_team="Langwarrin",
        competition="Victoria NPL 2",
        country="Australia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Regular Season - 24",
        datetime="2026-08-16T04:00:00+00:00",
        status="awarded",
    )

    sync_state = FootballSyncState(
        status="temporarily_missing",
    )

    record = FootballMatchRecord(
        identity=identity,
        match=match,
        sync_state=sync_state,
    )

    assert record.sync_state == sync_state
