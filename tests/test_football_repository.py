import pytest

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.repository import FootballMatchRepository
from app.sports.football.external_identity import ExternalMatchIdentity
from app.sports.football.match_record import FootballMatchRecord
from app.sports.football.sync_state import FootballSyncState


def test_football_repository_saves_and_loads_matches(tmp_path):
    file_path = tmp_path / "football_matches.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )

    repository.save_matches([match])

    loaded_matches = repository.load_matches()

    assert len(loaded_matches) == 1

    loaded = loaded_matches[0]

    assert loaded.contract.home_team == "Millonarios"
    assert loaded.contract.away_team == "Atlético Nacional"
    assert loaded.contract.competition == "Liga BetPlay"
    assert loaded.contract.country == "Colombia"
    assert loaded.season == 2026
    assert loaded.round == "Clausura - 8"
    assert loaded.datetime == "2026-08-16T20:00:00-05:00"
    assert loaded.status == "scheduled"


def test_football_repository_rejects_invalid_json(tmp_path):
    file_path = tmp_path / "football_matches.json"
    file_path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    with pytest.raises(
        ValueError,
        match="archivo JSON de fútbol es inválido",
    ):
        repository.load_matches()

def test_football_repository_rejects_non_list_payload(tmp_path):
    file_path = tmp_path / "football_matches.json"
    file_path.write_text(
        '{"home_team": "Millonarios"}',
        encoding="utf-8",
    )

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    with pytest.raises(
        ValueError,
        match="archivo de partidos de fútbol debe contener una lista",
    ):
        repository.load_matches()


def test_football_repository_upsert_inserts_new_record(tmp_path):
    file_path = tmp_path / "football_records.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

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

    repository.upsert_records([record])

    loaded_records = repository.load_records()

    assert len(loaded_records) == 1
    assert loaded_records[0].identity == identity
    assert loaded_records[0].match == match


def test_football_repository_upsert_updates_same_identity_and_preserves_others(
    tmp_path,
):
    file_path = tmp_path / "football_records.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    identity_a = ExternalMatchIdentity(
        provider="api_football",
        external_id="1001",
    )
    identity_b = ExternalMatchIdentity(
        provider="api_football",
        external_id="1002",
    )

    contract_a = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )
    contract_b = FootballMatchContract(
        home_team="Santa Fe",
        away_team="Once Caldas",
        competition="Liga BetPlay",
        country="Colombia",
    )

    scheduled_match = FootballMatchModel(
        contract=contract_a,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )
    other_match = FootballMatchModel(
        contract=contract_b,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T22:00:00-05:00",
        status="scheduled",
    )

    repository.upsert_records(
        [
            FootballMatchRecord(
                identity=identity_a,
                match=scheduled_match,
            ),
            FootballMatchRecord(
                identity=identity_b,
                match=other_match,
            ),
        ]
    )

    finished_match = FootballMatchModel(
        contract=contract_a,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="finished",
    )

    repository.upsert_records(
        [
            FootballMatchRecord(
                identity=identity_a,
                match=finished_match,
            ),
        ]
    )

    loaded_records = repository.load_records()

    assert len(loaded_records) == 2

    records_by_identity = {
        record.identity: record
        for record in loaded_records
    }

    assert records_by_identity[identity_a].match.status == "finished"
    assert records_by_identity[identity_b].match.status == "scheduled"


def test_football_repository_persists_record_sync_state(tmp_path):
    file_path = tmp_path / "football_records.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

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
        sync_state=FootballSyncState(
            status="temporarily_missing",
        ),
    )

    repository.upsert_records([record])

    loaded_records = repository.load_records()

    assert len(loaded_records) == 1
    assert loaded_records[0].sync_state.status == "temporarily_missing"


def test_football_repository_reconciles_missing_records_without_deleting(
    tmp_path,
):
    file_path = tmp_path / "football_records.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    identity_a = ExternalMatchIdentity(
        provider="api_football",
        external_id="1001",
    )
    identity_b = ExternalMatchIdentity(
        provider="api_football",
        external_id="1002",
    )

    contract_a = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )
    contract_b = FootballMatchContract(
        home_team="Santa Fe",
        away_team="Once Caldas",
        competition="Liga BetPlay",
        country="Colombia",
    )

    match_a = FootballMatchModel(
        contract=contract_a,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )
    match_b = FootballMatchModel(
        contract=contract_b,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T22:00:00-05:00",
        status="scheduled",
    )

    repository.upsert_records(
        [
            FootballMatchRecord(
                identity=identity_a,
                match=match_a,
            ),
            FootballMatchRecord(
                identity=identity_b,
                match=match_b,
            ),
        ]
    )

    repository.reconcile_records(
        [
            FootballMatchRecord(
                identity=identity_a,
                match=match_a,
            ),
        ]
    )

    loaded_records = repository.load_records()

    assert len(loaded_records) == 2

    records_by_identity = {
        record.identity: record
        for record in loaded_records
    }

    assert (
        records_by_identity[identity_a].sync_state.status
        == "seen_current_sync"
    )
    assert (
        records_by_identity[identity_b].sync_state.status
        == "temporarily_missing"
    )


def test_football_repository_reconciles_reappearing_record_to_seen_current_sync(
    tmp_path,
):
    file_path = tmp_path / "football_records.json"

    repository = FootballMatchRepository(
        file_path=str(file_path),
    )

    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1001",
    )

    contract = FootballMatchContract(
        home_team="Millonarios",
        away_team="Atlético Nacional",
        competition="Liga BetPlay",
        country="Colombia",
    )

    match = FootballMatchModel(
        contract=contract,
        season=2026,
        round="Clausura - 8",
        datetime="2026-08-16T20:00:00-05:00",
        status="scheduled",
    )

    repository.upsert_records(
        [
            FootballMatchRecord(
                identity=identity,
                match=match,
                sync_state=FootballSyncState(
                    status="temporarily_missing",
                ),
            ),
        ]
    )

    repository.reconcile_records(
        [
            FootballMatchRecord(
                identity=identity,
                match=match,
            ),
        ]
    )

    loaded_records = repository.load_records()

    assert len(loaded_records) == 1
    assert loaded_records[0].sync_state.status == "seen_current_sync"
