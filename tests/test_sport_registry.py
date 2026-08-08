import pytest

from app.core.contracts.sport_registry import get_sport


def test_tennis_is_registered():
    sport = get_sport("TENNIS")

    assert sport.code == "TENNIS"
    assert sport.name == "Tennis"


def test_football_is_registered():
    sport = get_sport("FOOTBALL")

    assert sport.code == "FOOTBALL"
    assert sport.name == "Football"


def test_sport_code_is_normalized():
    sport = get_sport(" tennis ")

    assert sport.code == "TENNIS"


def test_unknown_sport_is_rejected():
    with pytest.raises(ValueError):
        get_sport("BASKETBALL")