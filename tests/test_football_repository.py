import pytest

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.repository import FootballMatchRepository


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
