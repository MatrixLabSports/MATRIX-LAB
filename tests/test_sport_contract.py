import pytest

from app.core.contracts.sport_contract import SportContract


def test_valid_sport_contract():
    sport = SportContract(
        code="TENNIS",
        name="Tennis",
    )

    assert sport.code == "TENNIS"
    assert sport.name == "Tennis"
    assert sport.version == "1.0"


def test_empty_sport_code_is_rejected():
    with pytest.raises(ValueError):
        SportContract(
            code="",
            name="Tennis",
        )


def test_empty_sport_name_is_rejected():
    with pytest.raises(ValueError):
        SportContract(
            code="TENNIS",
            name="",
        )