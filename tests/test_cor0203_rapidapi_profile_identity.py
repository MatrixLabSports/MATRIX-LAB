import argparse

import pytest

from tools.cor0203_rapidapi_profile_identity import _parse_target_spec, _sanitize_profile


def test_profile_identity_keeps_biography_and_discards_competitive_fields():
    payload={
        "data":{
            "id":92649,
            "name":"Tiago Pereira",
            "birthday":"2004-06-21",
            "countryAcr":"POR",
            "currentRank":332,
            "points":161,
            "information":{"plays":"Right-handed"},
        }
    }
    row=_sanitize_profile("92649","Tiago Pereira",payload)
    assert row["numeric_player_id"]=="92649"
    assert row["birthday"]=="2004-06-21"
    assert row["country_acr"]=="POR"
    assert "currentRank" in row["competitive_fields_discarded"]
    assert "points" in row["competitive_fields_discarded"]
    assert "currentRank" not in row
    assert "points" not in row


def test_profile_identity_rejects_wrong_numeric_id():
    with pytest.raises(ValueError,match="PROFILE_ID_MISMATCH"):
        _sanitize_profile("92649","Tiago Pereira",{"data":{"id":123,"name":"Tiago Pereira"}})


def test_profile_identity_parses_repeatable_governed_target():
    assert _parse_target_spec("18094=Mackenzie Mcdonald")==("18094","Mackenzie Mcdonald")


@pytest.mark.parametrize(
    "value",
    [
        "18094",
        "abc=Toby Samuel",
        "79068=",
    ],
)
def test_profile_identity_rejects_invalid_target_spec(value):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_target_spec(value)
