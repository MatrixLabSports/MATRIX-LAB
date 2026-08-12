import json

import pytest

from app.data.match_repository import MatchRepository


def valid_match() -> dict:
    return {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "tournament": "US Open",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R32",
        "datetime": "2026-08-07T19:00:00Z",
        "status": "scheduled",
    }


def write_json(tmp_path, data) -> str:
    file_path = tmp_path / "matches.json"
    file_path.write_text(
        json.dumps(data),
        encoding="utf-8",
    )
    return str(file_path)


def test_repository_loads_valid_matches(tmp_path):
    file_path = write_json(tmp_path, [valid_match()])

    repository = MatchRepository(file_path)

    matches = repository.load_matches()

    assert len(matches) == 1
    assert matches[0] == valid_match()


def test_repository_rejects_missing_file(tmp_path):
    file_path = tmp_path / "missing.json"
    repository = MatchRepository(str(file_path))

    with pytest.raises(FileNotFoundError):
        repository.load_matches()


def test_repository_rejects_invalid_json(tmp_path):
    file_path = tmp_path / "matches.json"
    file_path.write_text("{invalid json", encoding="utf-8")

    repository = MatchRepository(str(file_path))

    with pytest.raises(ValueError):
        repository.load_matches()


def test_repository_rejects_non_list_root(tmp_path):
    file_path = write_json(tmp_path, valid_match())

    repository = MatchRepository(file_path)

    with pytest.raises(ValueError):
        repository.load_matches()


def test_repository_rejects_non_dict_match(tmp_path):
    file_path = write_json(tmp_path, ["invalid-match"])

    repository = MatchRepository(file_path)

    with pytest.raises(ValueError):
        repository.load_matches()


def test_repository_rejects_missing_required_field(tmp_path):
    match = valid_match()
    del match["surface"]

    file_path = write_json(tmp_path, [match])
    repository = MatchRepository(file_path)

    with pytest.raises(ValueError):
        repository.load_matches()


def test_repository_rejects_empty_required_field(tmp_path):
    match = valid_match()
    match["player1"] = "   "

    file_path = write_json(tmp_path, [match])
    repository = MatchRepository(file_path)

    with pytest.raises(ValueError):
        repository.load_matches()


def test_repository_preserves_multiple_valid_matches(tmp_path):
    first_match = valid_match()

    second_match = valid_match()
    second_match["player1"] = "Alexander Zverev"
    second_match["player2"] = "Daniil Medvedev"

    file_path = write_json(
        tmp_path,
        [first_match, second_match],
    )

    repository = MatchRepository(file_path)

    matches = repository.load_matches()

    assert len(matches) == 2
    assert matches[0] == first_match
    assert matches[1] == second_match